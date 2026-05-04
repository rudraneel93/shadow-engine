"""Unit tests for LLM providers using mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shadow_engine.llm.providers import (
    AnthropicProvider,
    LLMResponse,
    OllamaProvider,
    OpenAIProvider,
    get_provider,
)


class MockResponse:
    """Fake httpx response."""
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json_data


class TestOllamaProvider:
    """Tests for OllamaProvider."""

    def test_provider_created_by_factory(self):
        provider = get_provider("ollama", model="qwen3:8b")
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "qwen3:8b"

    def test_default_model(self):
        provider = get_provider("ollama")
        assert provider.model == "qwen3:8b"

    def test_custom_timeout(self):
        provider = OllamaProvider(model="test", timeout=60.0)
        assert provider.timeout == 60.0

    def test_generate_success(self):
        provider = OllamaProvider(model="qwen3:8b", base_url="http://test:11434")
        mock_resp = MockResponse(200, {
            "model": "qwen3:8b",
            "response": "def fix_login(): pass",
            "prompt_eval_count": 150,
            "eval_count": 25,
        })
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("fix the login bug")
        assert result.success is True
        assert "fix_login" in result.content
        assert result.provider == "ollama"
        assert result.input_tokens == 150
        assert result.output_tokens == 25
        assert result.total_tokens == 175

    def test_generate_with_system_prompt(self):
        provider = OllamaProvider(base_url="http://test:11434")
        mock_resp = MockResponse(200, {"response": "ok", "prompt_eval_count": 100, "eval_count": 10})
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("hello", system_prompt="Be helpful")
        assert result.success is True

    def test_model_not_found(self):
        provider = OllamaProvider(model="nonexistent", base_url="http://test:11434")
        mock_resp = MockResponse(404, text="model not found")
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("test")
        assert result.success is False
        assert "not found" in (result.error or "")

    def test_connection_error(self):
        provider = OllamaProvider(base_url="http://test:11434")
        import httpx
        with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
            result = provider.generate("test")
        assert result.success is False
        assert "connect" in (result.error or "").lower()

    def test_retries_then_fails(self):
        provider = OllamaProvider(base_url="http://test:11434")
        mock_resp = MockResponse(503, text="overloaded")
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("test", retries=2)
        assert result.success is False
        assert result.error is not None

    def test_timeout_handling(self):
        provider = OllamaProvider(base_url="http://test:11434", timeout=0.001)
        import httpx
        with patch("httpx.post", side_effect=httpx.TimeoutException("timeout")):
            result = provider.generate("test", retries=1)
        assert result.success is False


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_factory_creates_provider(self):
        provider = get_provider("openai", api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)

    def test_generate_success(self):
        provider = OpenAIProvider(api_key="sk-test", base_url="http://test/v1")
        mock_resp = MockResponse(200, {
            "choices": [{"message": {"content": "The fix is X"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        })
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("fix bug")
        assert result.success is True
        assert result.input_tokens == 100
        assert result.output_tokens == 10

    def test_auth_error(self):
        provider = OpenAIProvider(api_key="bad-key", base_url="http://test/v1")
        mock_resp = MockResponse(401, {"error": {"message": "Invalid API key"}})
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("test")
        assert result.success is False
        assert "authentication" in (result.error or "").lower()


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_factory_creates_provider(self):
        provider = get_provider("anthropic", api_key="sk-ant-test")
        assert isinstance(provider, AnthropicProvider)

    def test_generate_success(self):
        provider = AnthropicProvider(api_key="sk-ant-test")
        mock_resp = MockResponse(200, {
            "content": [{"type": "text", "text": "Here is the fix."}],
            "usage": {"input_tokens": 50, "output_tokens": 15},
        })
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("fix login bug")
        assert result.success is True
        assert result.input_tokens == 50
        assert result.output_tokens == 15
        assert result.total_tokens == 65

    def test_rate_limit_error(self):
        provider = AnthropicProvider(api_key="sk-ant-test")
        mock_resp = MockResponse(429, {"error": {"message": "Rate limited"}})
        with patch("httpx.post", return_value=mock_resp):
            result = provider.generate("test", retries=1)
        assert result.success is False
        assert result.error is not None


class TestProviderFactory:
    """Tests for get_provider factory function."""

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError, match="invalid"):
            get_provider("invalid")

    def test_default_timeout(self):
        provider = get_provider("ollama")
        assert provider.timeout > 0


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_success_property_with_content(self):
        r = LLMResponse(content="Hello", model="test", provider="ollama")
        assert r.success is True

    def test_success_property_with_error(self):
        r = LLMResponse(content="", model="test", provider="ollama", error="failed")
        assert r.success is False

    def test_success_property_empty_content_no_error(self):
        r = LLMResponse(content="", model="test", provider="ollama")
        assert r.success is False