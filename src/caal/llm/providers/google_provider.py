"""Google AI (Gemini) API provider — uses the Gemini API with an API key.

Full tool calling support via OpenAI-compatible Gemini endpoint.
For subscription-native access (no API key), use GeminiCLIProvider instead.

Prerequisites:
    GOOGLE_API_KEY set in environment or settings
    (Get from https://aistudio.google.com/apikey)
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from .base import LLMProvider, LLMResponse, TokenUsage, ToolCall

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"
_OPENAI_COMPAT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


class GoogleProvider(LLMProvider):
    """LLM provider using the Gemini API (API key required).

    Uses Gemini's OpenAI-compatible endpoint for full tool calling support.
    For subscription-native access without an API key, use GeminiCLIProvider.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        temperature: float = 0.15,
        base_url: str = _OPENAI_COMPAT_BASE,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        self.temperature = temperature
        self._base_url = base_url.rstrip("/")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
            except ImportError:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()

        req: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            req["tools"] = tools

        response = await client.chat.completions.create(**req)
        choice = response.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            usage=usage,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()

        req: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        if tools:
            req["tools"] = tools

        async with await client.chat.completions.create(**req) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content

    def parse_tool_arguments(self, arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except json.JSONDecodeError:
                return {}
        return {}

    def format_tool_result(
        self,
        content: str,
        tool_call_id: str | None,
        tool_name: str,
    ) -> dict[str, Any]:
        return {
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
            "name": tool_name,
        }
