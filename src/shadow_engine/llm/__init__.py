"""Multi-provider LLM support — OpenAI, Anthropic, and Ollama.

Pluggable architecture for connecting Shadow Engineer to different LLM backends.
Each provider handles its own API format and authentication method.
"""

from .providers import (
    LLMProvider,
    LLMResponse,
    OllamaProvider,
    OpenAIProvider,
    AnthropicProvider,
    get_provider,
)

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
]