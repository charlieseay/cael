"""Anthropic API provider — uses the Anthropic SDK with an API key.

Full tool calling support. For subscription-native access (no API key),
use ClaudeCLIProvider instead.

Prerequisites:
    pip install anthropic
    ANTHROPIC_API_KEY set in environment or settings
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from .base import LLMProvider, LLMResponse, TokenUsage, ToolCall

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5"


class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic SDK (API key required).

    Supports full tool calling. Use this when you have an Anthropic API key
    and want structured tool use alongside voice responses.

    For subscription-native access without an API key, use ClaudeCLIProvider.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.temperature = temperature
        self._max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def _build_request(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> dict[str, Any]:
        """Build Anthropic API request. Extracts system prompt from messages."""
        system = ""
        filtered: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content", "")
            else:
                filtered.append(msg)

        req: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self.temperature,
            "messages": filtered,
        }
        if system:
            req["system"] = system
        if tools:
            req["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"].get("parameters", {}),
                }
                for t in tools
                if t.get("type") == "function"
            ]
        return req

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        req = self._build_request(messages, tools)

        response = await client.messages.create(**req)

        content_text: str | None = None
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
        return LLMResponse(content=content_text, tool_calls=tool_calls, usage=usage)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        req = self._build_request(messages, tools)

        async with client.messages.stream(**req) as stream:
            async for text in stream.text_stream:
                yield text

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
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content,
                }
            ],
        }
