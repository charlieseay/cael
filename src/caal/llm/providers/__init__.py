"""LLM provider implementations for CAAL.

This package provides a unified interface for different LLM backends,
enabling CAAL to work with Ollama, Groq, and potentially other providers
while sharing common tool orchestration logic.

Providers:
    - OllamaProvider: Local Ollama with think parameter support
    - GroqProvider: Groq cloud API
    - OpenAICompatibleProvider: Any OpenAI-compatible server
    - OpenRouterProvider: OpenRouter cloud API (400+ models)

Example:
    >>> from caal.llm.providers import create_provider
    >>>
    >>> # Create Ollama provider
    >>> provider = create_provider("ollama", model="qwen3:8b", think=False)
    >>>
    >>> # Create Groq provider
    >>> provider = create_provider("groq", model="llama-3.3-70b-versatile")
    >>>
    >>> # Create OpenAI-compatible provider (LiteLLM, vLLM, etc.)
    >>> provider = create_provider("openai_compatible", model="mistral",
    ...                            base_url="http://localhost:8000/v1")
    >>>
    >>> # Create OpenRouter provider
    >>> provider = create_provider("openrouter", model="openai/gpt-4",
    ...                            api_key="sk-...")
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, LLMResponse, ToolCall
from .claude_cli_provider import ClaudeCLIProvider
from .gemini_cli_provider import GeminiCLIProvider
from .google_provider import GoogleProvider
from .groq_provider import GroqProvider
from .ollama_provider import OllamaProvider
from .openai_compatible_provider import OpenAICompatibleProvider
from .openrouter_provider import OpenRouterProvider

# Router lives in the parent llm package; re-export here so callers can do
# `from caal.llm.providers import ModelRouter` without a relative-import dance.
from ..model_router import ModelRouter, RouterConfig, create_router_from_settings, score_complexity

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "OllamaProvider",
    "GroqProvider",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "ClaudeCLIProvider",
    "AnthropicProvider",
    "GeminiCLIProvider",
    "GoogleProvider",
    "create_provider",
    "ModelRouter",
    "RouterConfig",
    "create_router_from_settings",
    "score_complexity",
]

logger = logging.getLogger(__name__)


def create_provider(
    provider_name: str,
    **kwargs: Any,
) -> LLMProvider:
    """Factory function to create an LLM provider by name.

    Args:
        provider_name: Provider identifier ("ollama", "groq", "openai_compatible",
            or "openrouter")
        **kwargs: Provider-specific configuration options

    Returns:
        Configured LLMProvider instance

    Raises:
        ValueError: If provider_name is not recognized

    Example:
        >>> provider = create_provider(
        ...     "ollama",
        ...     model="qwen3:8b",
        ...     think=False,
        ...     temperature=0.15,
        ... )
        >>> provider = create_provider(
        ...     "openai_compatible",
        ...     model="mistral",
        ...     base_url="http://localhost:8000/v1",
        ... )
    """
    provider_name = provider_name.lower()

    if provider_name == "ollama":
        return OllamaProvider(**kwargs)
    elif provider_name == "groq":
        return GroqProvider(**kwargs)
    elif provider_name == "openai_compatible":
        return OpenAICompatibleProvider(**kwargs)
    elif provider_name == "openrouter":
        return OpenRouterProvider(**kwargs)
    elif provider_name == "claude_cli":
        return ClaudeCLIProvider(**kwargs)
    elif provider_name == "anthropic":
        return AnthropicProvider(**kwargs)
    elif provider_name == "gemini_cli":
        return GeminiCLIProvider(**kwargs)
    elif provider_name == "google":
        return GoogleProvider(**kwargs)
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. "
            f"Supported providers: ollama, groq, openai_compatible, openrouter, "
            f"claude_cli, anthropic, gemini_cli, google"
        )


def create_provider_from_settings(settings: dict[str, Any]) -> LLMProvider:
    """Create an LLM provider from CAAL settings dict.

    This function reads the provider type and model settings from the
    runtime settings dictionary and creates the appropriate provider.

    Args:
        settings: Runtime settings dict with keys like:
            - llm_provider: "ollama", "groq", "openai_compatible", or "openrouter"
            - ollama_model: Ollama model name
            - groq_model: Groq model name
            - openai_model: OpenAI-compatible model name
            - openai_base_url: OpenAI-compatible server URL
            - openai_api_key: OpenAI-compatible API key (optional)
            - openrouter_model: OpenRouter model name
            - openrouter_api_key: OpenRouter API key (required)
            - temperature: Sampling temperature
            - num_ctx: Context window size (Ollama only)

    Returns:
        Configured LLMProvider instance

    Example:
        >>> from caal.settings import load_settings
        >>> settings = load_settings()
        >>> provider = create_provider_from_settings(settings)
    """
    provider_name = settings.get("llm_provider", "ollama").lower()

    if provider_name == "ollama":
        return OllamaProvider(
            model=settings.get("ollama_model", "qwen3:8b"),
            base_url=settings.get("ollama_host"),
            think=settings.get("think", False),
            temperature=settings.get("temperature", 0.15),
            num_ctx=settings.get("num_ctx", 8192),
        )
    elif provider_name == "groq":
        # API key from settings, fallback to environment variable
        api_key = settings.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
        return GroqProvider(
            model=settings.get("groq_model", "llama-3.3-70b-versatile"),
            api_key=api_key,
            temperature=settings.get("temperature", 0.15),
        )
    elif provider_name == "openai_compatible":
        # API key from settings, fallback to environment variable
        api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        return OpenAICompatibleProvider(
            model=settings.get("openai_model", "gpt-3.5-turbo"),
            base_url=settings.get("openai_base_url", "http://localhost:8000/v1"),
            api_key=api_key,
            temperature=settings.get("temperature", 0.7),
        )
    elif provider_name == "openrouter":
        api_key = settings.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenRouter API key required. Set openrouter_api_key in settings "
                "or OPENROUTER_API_KEY environment variable."
            )
        return OpenRouterProvider(
            model=settings.get("openrouter_model", "openai/gpt-4"),
            api_key=api_key,
            temperature=settings.get("temperature", 0.7),
        )
    elif provider_name == "claude_cli":
        return ClaudeCLIProvider(
            model=settings.get("claude_cli_model", "claude-haiku-4-5"),
            temperature=settings.get("temperature", 0.15),
        )
    elif provider_name == "anthropic":
        api_key = settings.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
        return AnthropicProvider(
            model=settings.get("anthropic_model", "claude-haiku-4-5"),
            api_key=api_key,
            temperature=settings.get("temperature", 0.15),
        )
    elif provider_name == "gemini_cli":
        return GeminiCLIProvider(
            model=settings.get("gemini_cli_model", "gemini-2.0-flash"),
            temperature=settings.get("temperature", 0.15),
        )
    elif provider_name == "google":
        api_key = settings.get("google_api_key") or os.environ.get("GOOGLE_API_KEY")
        return GoogleProvider(
            model=settings.get("google_model", "gemini-2.0-flash"),
            api_key=api_key,
            temperature=settings.get("temperature", 0.15),
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. "
            f"Supported providers: ollama, groq, openai_compatible, openrouter"
        )
