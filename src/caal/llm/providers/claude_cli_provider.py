"""Claude CLI provider — uses the `claude` CLI subprocess (subscription-native).

No API key required. Routes through the user's Claude Max (or Pro) subscription
via the locally installed `claude` CLI. Tool calling is not supported on this
path — responses are plain text.

Prerequisites:
    claude CLI installed and authenticated:
        npm install -g @anthropic-ai/claude-code
        claude login
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from .base import LLMProvider, LLMResponse, TokenUsage

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5"

# Map friendly model names to claude CLI --model values
_MODEL_ALIASES: dict[str, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-5",
    "opus": "claude-opus-4-5",
    "haiku-4-5": "claude-haiku-4-5",
    "sonnet-4-5": "claude-sonnet-4-5",
}


def _resolve_model(model: str) -> str:
    return _MODEL_ALIASES.get(model.lower(), model)


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Flatten conversation history to a single prompt string for claude --print."""
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
            parts.append(f"[Human]\n{content}")
    return "\n\n".join(parts)


class ClaudeCLIProvider(LLMProvider):
    """LLM provider that wraps the `claude` CLI subprocess.

    Uses the user's Claude subscription (Max/Pro) — no API key or per-token cost.
    Streaming is supported via char-by-char stdout reading.

    Tool calling is not available on this path. For full tool support, use
    AnthropicProvider (API key required).
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
        return "claude_cli"

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
        """Run claude CLI and return full response."""
        prompt = _messages_to_prompt(messages)
        chunks: list[str] = []
        async for chunk in self.chat_stream(messages, tools=None):
            chunks.append(chunk)
        return LLMResponse(
            content="".join(chunks),
            tool_calls=[],
            usage=None,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream response from claude CLI, yielding text chunks."""
        prompt = _messages_to_prompt(messages)

        try:
            proc = await asyncio.create_subprocess_exec(
                "claude",
                "--model", self._model,
                "--print",
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.error(
                "claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )
            yield "(Claude CLI not found — run: npm install -g @anthropic-ai/claude-code)"
            return

        assert proc.stdout is not None

        buffer = bytearray()
        while True:
            chunk = await proc.stdout.read(64)
            if not chunk:
                break
            buffer.extend(chunk)
            # Yield complete UTF-8 characters as they arrive
            try:
                text = buffer.decode("utf-8")
                if text:
                    yield text
                    buffer.clear()
            except UnicodeDecodeError:
                # Incomplete multi-byte sequence — wait for more bytes
                pass

        # Flush any remaining bytes
        if buffer:
            yield buffer.decode("utf-8", errors="replace")

        await proc.wait()
