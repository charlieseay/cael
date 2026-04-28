"""Cursor CLI provider — uses `cursor -p` headless prompt mode.

No API key required. Routes through the locally authenticated Cursor CLI.
Tool calling is not supported on this path — responses are plain text.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = ""


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Flatten conversation history to a single prompt string."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue
        if role == "system":
            parts.append(f"[System]\n{content}")
        elif role == "assistant":
            parts.append(f"[Assistant]\n{content}")
        else:
            parts.append(f"[User]\n{content}")
    return "\n\n".join(parts)


class CursorCLIProvider(LLMProvider):
    """LLM provider that wraps Cursor CLI headless mode."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.15,
    ) -> None:
        self._model = model or _DEFAULT_MODEL
        self.temperature = temperature

    @property
    def provider_name(self) -> str:
        return "cursor_cli"

    @property
    def model(self) -> str:
        return self._model

    @property
    def supports_tools(self) -> bool:
        return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        chunks: list[str] = []
        async for chunk in self.chat_stream(messages, tools=None):
            chunks.append(chunk)
        return LLMResponse(content="".join(chunks), tool_calls=[], usage=None)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        prompt = _messages_to_prompt(messages)
        cmd = ["cursor", "-p", prompt]
        if self._model:
            cmd.extend(["-m", self._model])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("cursor CLI not found.")
            yield "(Cursor CLI not found — install/login Cursor CLI first)"
            return

        assert proc.stdout is not None

        buffer = bytearray()
        while True:
            chunk = await proc.stdout.read(64)
            if not chunk:
                break
            buffer.extend(chunk)
            try:
                text = buffer.decode("utf-8")
                if text:
                    yield text
                    buffer.clear()
            except UnicodeDecodeError:
                pass

        if buffer:
            yield buffer.decode("utf-8", errors="replace")

        await proc.wait()
