"""Multi-provider LLM support — OpenAI, Anthropic, and Ollama.

Usage:
    from shadow_engine.llm import get_provider, OpenAIProvider, AnthropicProvider

    provider = get_provider("openai", api_key="sk-...")
    response = provider.generate("Hello, world!")

    provider = get_provider("anthropic", api_key="sk-ant-...")
    response = provider.generate("Hello, world!")

    provider = get_provider("ollama", model="qwen3:8b")
    response = provider.generate("Hello, world!")
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ── Custom Exceptions ────────────────────────────────────────────

class LLMError(Exception):
    """Base exception for all LLM provider errors."""
    pass


class LLMRateLimitError(LLMError):
    """Provider rate limit exceeded (HTTP 429)."""
    pass


class LLMAuthError(LLMError):
    """Authentication / API key error (HTTP 401/403)."""
    pass


class LLMTimeoutError(LLMError):
    """Request timed out."""
    pass


class LLMConnectionError(LLMError):
    """Cannot connect to provider."""
    pass


class LLMModelNotFoundError(LLMError):
    """Model not found on provider (HTTP 404)."""
    pass


# ── Response Model ───────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Structured response from any LLM provider."""
    content: str
    model: str
    provider: str
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and len(self.content) > 0


# ── Base Provider ────────────────────────────────────────────────

class LLMProvider:
    """Base class for LLM providers with configurable timeout and retries."""

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout

    def generate(
        self, prompt: str, system_prompt: str | None = None,
        max_tokens: int = 2048, retries: int = 3,
    ) -> LLMResponse:
        raise NotImplementedError

    @staticmethod
    def _exponential_backoff(attempt: int, base_delay: float = 2.0) -> float:
        """Compute delay for exponential backoff: base_delay ^ attempt seconds."""
        return min(base_delay ** attempt, 60.0)

    @staticmethod
    def _handle_http_error(
        status_code: int, error_body: str, provider: str,
    ) -> LLMError:
        """Map HTTP status codes to specific LLM exceptions."""
        if status_code == 429:
            return LLMRateLimitError(f"[{provider}] Rate limit exceeded: {error_body}")
        elif status_code in (401, 403):
            return LLMAuthError(f"[{provider}] Authentication failed: {error_body}")
        elif status_code == 404:
            return LLMModelNotFoundError(f"[{provider}] Model not found: {error_body}")
        elif status_code >= 500:
            return LLMError(f"[{provider}] Server error ({status_code}): {error_body}")
        else:
            return LLMError(f"[{provider}] HTTP {status_code}: {error_body}")


# ── Ollama Provider (HTTP API) ───────────────────────────────────

class OllamaProvider(LLMProvider):
    """Ollama local LLM provider using the official HTTP API.

    Uses POST /api/generate for programmatic, structured responses
    with real token counts. No subprocess — fully async-compatible.
    """

    def __init__(
        self, model: str = "qwen3:8b", base_url: str | None = None,
        timeout: float = 180.0,
    ):
        super().__init__(timeout=timeout)
        self.model = model
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")

    def generate(
        self, prompt: str, system_prompt: str | None = None,
        max_tokens: int = 2048, retries: int = 3,
    ) -> LLMResponse:
        import httpx

        start = time.time()
        last_error: str | None = None

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if system_prompt:
            payload["system"] = system_prompt

        for attempt in range(retries):
            try:
                response = httpx.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                duration = time.time() - start

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("response", "").strip()
                    return LLMResponse(
                        content=content,
                        model=self.model,
                        provider="ollama",
                        duration_seconds=duration,
                        input_tokens=data.get("prompt_eval_count", 0),
                        output_tokens=data.get("eval_count", 0),
                        total_tokens=data.get("prompt_eval_count", 0)
                        + data.get("eval_count", 0),
                    )

                # Non-200: parse error
                error_detail = str(response.text)[:500]
                last_error = f"Ollama HTTP {response.status_code}: {error_detail}"

                if response.status_code == 404:
                    return LLMResponse(
                        content="", model=self.model, provider="ollama",
                        duration_seconds=duration,
                        error=f"Model '{self.model}' not found. Pull it: ollama pull {self.model}",
                    )
                if response.status_code in (429, 500, 502, 503) and attempt < retries - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.warning(f"Ollama {response.status_code} — retrying in {delay:.0f}s (attempt {attempt + 1}/{retries})")
                    time.sleep(delay)
                    continue

                if attempt < retries - 1:
                    time.sleep(self._exponential_backoff(attempt))
                    continue

            except httpx.ConnectError:
                return LLMResponse(
                    content="", model=self.model, provider="ollama",
                    duration_seconds=time.time() - start,
                    error=f"Cannot connect to Ollama at {self.base_url}. Is it running? Start with: ollama serve",
                )
            except httpx.TimeoutException:
                last_error = f"Ollama timed out after {self.timeout}s"
                if attempt < retries - 1:
                    continue
            except Exception as e:
                last_error = str(e)[:500]
                if attempt < retries - 1:
                    time.sleep(self._exponential_backoff(attempt))
                    continue

        return LLMResponse(
            content="", model=self.model, provider="ollama",
            duration_seconds=time.time() - start,
            error=last_error or "All retries failed",
        )


# ── OpenAI Provider ──────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT-4, GPT-4o, etc.)."""

    def __init__(
        self, api_key: str | None = None, model: str = "gpt-4o",
        base_url: str | None = None, timeout: float = 120.0,
    ):
        super().__init__(timeout=timeout)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def generate(
        self, prompt: str, system_prompt: str | None = None,
        max_tokens: int = 2048, retries: int = 3,
    ) -> LLMResponse:
        import httpx

        start = time.time()
        last_error: str | None = None

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(retries):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                    },
                    timeout=self.timeout,
                )
                duration = time.time() - start
                data = response.json()

                if response.status_code != 200:
                    error_msg = data.get("error", {}).get("message", str(data))
                    last_error = f"OpenAI HTTP {response.status_code}: {error_msg}"

                    if response.status_code == 429 and attempt < retries - 1:
                        delay = self._exponential_backoff(attempt)
                        logger.warning(f"OpenAI rate limited — retrying in {delay:.0f}s")
                        time.sleep(delay)
                        continue
                    if response.status_code in (401, 403):
                        return LLMResponse(
                            content="", model=self.model, provider="openai",
                            duration_seconds=duration,
                            error="OpenAI authentication failed. Check your OPENAI_API_KEY.",
                        )
                    if attempt < retries - 1:
                        time.sleep(self._exponential_backoff(attempt))
                        continue

                    return LLMResponse(
                        content="", model=self.model, provider="openai",
                        duration_seconds=duration, error=last_error,
                    )

                usage = data.get("usage", {})
                content = ""
                if data.get("choices"):
                    content = data["choices"][0].get("message", {}).get("content", "")

                return LLMResponse(
                    content=content,
                    model=self.model,
                    provider="openai",
                    duration_seconds=duration,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )

            except httpx.TimeoutException:
                last_error = f"OpenAI timed out after {self.timeout}s"
                if attempt < retries - 1:
                    continue
            except httpx.ConnectError:
                return LLMResponse(
                    content="", model=self.model, provider="openai",
                    duration_seconds=time.time() - start,
                    error=f"Cannot connect to OpenAI API at {self.base_url}",
                )
            except Exception as e:
                last_error = str(e)[:500]
                if attempt < retries - 1:
                    time.sleep(self._exponential_backoff(attempt))
                    continue

        return LLMResponse(
            content="", model=self.model, provider="openai",
            duration_seconds=time.time() - start,
            error=last_error or "All retries failed",
        )


# ── Anthropic Provider ───────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    """Anthropic API provider (Claude Sonnet, Claude Opus, etc.)."""

    def __init__(
        self, api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        timeout: float = 120.0,
    ):
        super().__init__(timeout=timeout)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def generate(
        self, prompt: str, system_prompt: str | None = None,
        max_tokens: int = 2048, retries: int = 3,
    ) -> LLMResponse:
        import httpx

        start = time.time()
        last_error: str | None = None

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        for attempt in range(retries):
            try:
                response = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                duration = time.time() - start
                data = response.json()

                if response.status_code != 200:
                    error_msg = data.get("error", {}).get("message", str(data))
                    last_error = f"Anthropic HTTP {response.status_code}: {error_msg}"

                    if response.status_code == 429 and attempt < retries - 1:
                        delay = self._exponential_backoff(attempt)
                        logger.warning(f"Anthropic rate limited — retrying in {delay:.0f}s")
                        time.sleep(delay)
                        continue
                    if response.status_code in (401, 403):
                        return LLMResponse(
                            content="", model=self.model, provider="anthropic",
                            duration_seconds=duration,
                            error="Anthropic authentication failed. Check your ANTHROPIC_API_KEY.",
                        )
                    if attempt < retries - 1:
                        time.sleep(self._exponential_backoff(attempt))
                        continue

                    return LLMResponse(
                        content="", model=self.model, provider="anthropic",
                        duration_seconds=duration, error=last_error,
                    )

                content = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        content += block.get("text", "")

                usage = data.get("usage", {})
                return LLMResponse(
                    content=content,
                    model=self.model,
                    provider="anthropic",
                    duration_seconds=duration,
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                )

            except httpx.TimeoutException:
                last_error = f"Anthropic timed out after {self.timeout}s"
                if attempt < retries - 1:
                    continue
            except httpx.ConnectError:
                return LLMResponse(
                    content="", model=self.model, provider="anthropic",
                    duration_seconds=time.time() - start,
                    error="Cannot connect to Anthropic API",
                )
            except Exception as e:
                last_error = str(e)[:500]
                if attempt < retries - 1:
                    time.sleep(self._exponential_backoff(attempt))
                    continue

        return LLMResponse(
            content="", model=self.model, provider="anthropic",
            duration_seconds=time.time() - start,
            error=last_error or "All retries failed",
        )


# ── Provider Factory ─────────────────────────────────────────────

def get_provider(
    provider: str = "ollama",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 120.0,
) -> LLMProvider:
    """Factory function to get an LLM provider by name.

    Args:
        provider: "ollama", "openai", or "anthropic"
        model: Model name (defaults: ollama=qwen3:8b, openai=gpt-4o, anthropic=claude-sonnet-4-20250514)
        api_key: API key for the provider (not needed for Ollama)
        base_url: Optional base URL override
        timeout: Request timeout in seconds (default 120s)

    Returns:
        Configured LLMProvider instance
    """
    provider = provider.lower().strip()

    if provider == "ollama":
        return OllamaProvider(
            model=model or "qwen3:8b", base_url=base_url, timeout=max(timeout, 60.0),
        )
    elif provider == "openai":
        return OpenAIProvider(
            api_key=api_key, model=model or "gpt-4o", base_url=base_url, timeout=timeout,
        )
    elif provider == "anthropic":
        return AnthropicProvider(
            api_key=api_key, model=model or "claude-sonnet-4-20250514", timeout=timeout,
        )
    else:
        raise ValueError(
            f"Unknown provider: '{provider}'. Choose from: ollama, openai, anthropic"
        )