"""clipboard_tool.py — macOS clipboard access via pbpaste / pbcopy."""

from __future__ import annotations

import asyncio
import logging

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

_CLIPBOARD_LIMIT = 4096  # 4 KB read cap

GET_CLIPBOARD_TOOL_DEF: dict = {
    "type": "function",
    "function": {
        "name": "get_clipboard",
        "description": (
            "Read the current contents of the Mac Mini clipboard. "
            "Use when the user says 'what's in my clipboard' or wants to "
            "work with text they've copied."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

SET_CLIPBOARD_TOOL_DEF: dict = {
    "type": "function",
    "function": {
        "name": "set_clipboard",
        "description": (
            "Write text to the Mac Mini clipboard. "
            "Use when the user says 'copy that to my clipboard' or "
            "'put X in my clipboard'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to put on the clipboard.",
                },
            },
            "required": ["text"],
        },
    },
}


async def execute_get_clipboard() -> str:
    """Read the clipboard via pbpaste."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pbpaste",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        text = stdout.decode("utf-8", errors="replace")
        if len(text) > _CLIPBOARD_LIMIT:
            text = text[:_CLIPBOARD_LIMIT] + f"\n... [truncated at {_CLIPBOARD_LIMIT} chars]"
        return text if text.strip() else "(clipboard is empty)"
    except asyncio.TimeoutError:
        return "[error] pbpaste timed out."
    except Exception as e:
        logger.error("get_clipboard error: %s", e)
        return f"[error] {e}"


async def execute_set_clipboard(text: str) -> str:
    """Write text to the clipboard via pbcopy."""
    if not text:
        return "[error] No text provided."
    try:
        proc = await asyncio.create_subprocess_exec(
            "pbcopy",
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=text.encode("utf-8")), timeout=5.0
        )
        rc = proc.returncode or 0
        if rc != 0:
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            return f"[exit {rc}] {err}"
        return f"Copied to clipboard ({len(text)} chars)."
    except asyncio.TimeoutError:
        return "[error] pbcopy timed out."
    except Exception as e:
        logger.error("set_clipboard error: %s", e)
        return f"[error] {e}"


class ClipboardTools:
    """Mixin providing get_clipboard and set_clipboard as @function_tool."""

    @function_tool
    async def get_clipboard(self) -> str:
        """Read the current contents of the Mac Mini clipboard.

        Returns:
            Clipboard text or an empty message.
        """
        return await execute_get_clipboard()

    @function_tool
    async def set_clipboard(self, text: str) -> str:
        """Write text to the Mac Mini clipboard.

        Args:
            text: The text to copy.

        Returns:
            Confirmation or error message.
        """
        return await execute_set_clipboard(text=text)
