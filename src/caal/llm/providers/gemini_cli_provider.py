"""Gemini CLI provider — uses the `gemini` CLI subprocess (subscription-native).

No API key required. Routes through the user's Google One Premium subscription
via the locally installed Gemini CLI. Tool calling is not supported on this path.

Prerequisites:
    gemini CLI installed and authenticated:
        npm install -g @google/generative-ai-cli   (or via gem/pip — see gemini docs)
        gemini auth login
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"

_MODEL_ALIASES: dict[str, str] = {
    "flash": "gemini-2.0-flash",
    "flash-lite": "gemini-2.0-flash-lite",
    "pro": "gemini-1.5-pro",
    "2.0-flash": "gemini-2.0-flash",
    "1.5-pro": "gemini-1.5-pro",
}


def _resolve_model(model: str) -> str:
    return _MODEL_ALIASES.get(model.lower(), model)


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
            parts.append(f"[Model]\n{content}")
        else:
            parts.append(f"[User]\n{content}")
    return "\n\n".join(parts)


class GeminiCLIProvider(LLMProvider):
    """LLM provider that wraps the `gemini` CLI subprocess.

    Uses the user's Google One Premium subscription — no API key or per-token cost.
    Streaming is supported via stdout reading.

    Tool calling is not available on this path. For full tool support, use
    GoogleProvider (API key required).
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.15,
    ) -> None:
        self._model = _resolve_model(model)
        self.temperature = temperature

    @property
    def provider_name(self) -> str:
        return "gemini_cli"

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

        # gemini CLI accepts prompt via stdin or as positional argument
        # Using stdin to avoid shell quoting issues with long prompts
        try:
            proc = await asyncio.create_subprocess_exec(
                "gemini",
                "--model", self._model,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error("gemini CLI not found. Install and authenticate the Gemini CLI.")
            yield "(Gemini CLI not found — install and run: gemini auth login)"
            return

        assert proc.stdin is not None
        assert proc.stdout is not None

        # Write prompt to stdin, then close
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

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
