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

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


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


class LLMProvider:
    """Base class for LLM providers."""

    def generate(self, prompt: str, system_prompt: str | None = None, max_tokens: int = 2048) -> LLMResponse:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider (free, no API key needed).

    Uses subprocess to call `ollama run <model>`.
    """

    def __init__(self, model: str = "qwen3:8b", base_url: str | None = None):
        self.model = model
        self.base_url = base_url or "http://localhost:11434"

    def generate(self, prompt: str, system_prompt: str | None = None, max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        try:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            result = subprocess.run(
                ["ollama", "run", self.model, full_prompt],
                capture_output=True,
                text=True,
                timeout=180,
            )
            duration = time.time() - start

            if result.returncode != 0:
                return LLMResponse(
                    content="",
                    model=self.model,
                    provider="ollama",
                    duration_seconds=duration,
                    error=result.stderr.strip() or "Unknown Ollama error",
                )

            content = result.stdout.strip()
            words = len(content.split())
            estimated_tokens = int(words * 1.3)

            return LLMResponse(
                content=content,
                model=self.model,
                provider="ollama",
                duration_seconds=duration,
                input_tokens=estimated_tokens // 2,
                output_tokens=estimated_tokens,
                total_tokens=estimated_tokens,
            )

        except subprocess.TimeoutExpired:
            return LLMResponse(
                content="",
                model=self.model,
                provider="ollama",
                duration_seconds=time.time() - start,
                error="LLM call timed out after 180s",
            )
        except FileNotFoundError:
            return LLMResponse(
                content="",
                model=self.model,
                provider="ollama",
                duration_seconds=time.time() - start,
                error="Ollama not found. Install: brew install ollama && ollama pull qwen3:8b",
            )


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (GPT-4, GPT-4o, etc.)."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o", base_url: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"

    def generate(self, prompt: str, system_prompt: str | None = None, max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        try:
            import httpx

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
            data = response.json()
            duration = time.time() - start

            if response.status_code != 200:
                return LLMResponse(
                    content="",
                    model=self.model,
                    provider="openai",
                    duration_seconds=duration,
                    error=data.get("error", {}).get("message", str(data)),
                )

            usage = data.get("usage", {})
            content = data["choices"][0]["message"]["content"] if data.get("choices") else ""

            return LLMResponse(
                content=content,
                model=self.model,
                provider="openai",
                duration_seconds=duration,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

        except Exception as e:
            return LLMResponse(
                content="",
                model=self.model,
                provider="openai",
                duration_seconds=time.time() - start,
                error=str(e),
            )


class AnthropicProvider(LLMProvider):
    """Anthropic API provider (Claude Sonnet, Claude Opus, etc.)."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def generate(self, prompt: str, system_prompt: str | None = None, max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        try:
            import httpx

            payload: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                payload["system"] = system_prompt

            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            data = response.json()
            duration = time.time() - start

            if response.status_code != 200:
                return LLMResponse(
                    content="",
                    model=self.model,
                    provider="anthropic",
                    duration_seconds=duration,
                    error=data.get("error", {}).get("message", str(data)),
                )

            content = ""
            for block in data.get("content", []):
                if block["type"] == "text":
                    content += block["text"]

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

        except Exception as e:
            return LLMResponse(
                content="",
                model=self.model,
                provider="anthropic",
                duration_seconds=time.time() - start,
                error=str(e),
            )


def get_provider(
    provider: str = "ollama",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Factory function to get an LLM provider by name.

    Args:
        provider: "ollama", "openai", or "anthropic"
        model: Model name (defaults: ollama=qwen3:8b, openai=gpt-4o, anthropic=claude-sonnet-4-20250514)
        api_key: API key for the provider (not needed for Ollama)
        base_url: Optional base URL override (for OpenAI-compatible endpoints like Ollama)

    Returns:
        Configured LLMProvider instance

    Examples:
        >>> provider = get_provider("ollama", model="qwen3:8b")
        >>> provider = get_provider("openai", api_key="sk-...", model="gpt-4o")
        >>> provider = get_provider("anthropic", api_key="sk-ant-...")
    """
    provider = provider.lower().strip()

    if provider == "ollama":
        return OllamaProvider(model=model or "qwen3:8b", base_url=base_url)
    elif provider == "openai":
        return OpenAIProvider(api_key=api_key, model=model or "gpt-4o", base_url=base_url)
    elif provider == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or "claude-sonnet-4-20250514")
    else:
        raise ValueError(f"Unknown provider: {provider}. Choose from: ollama, openai, anthropic")