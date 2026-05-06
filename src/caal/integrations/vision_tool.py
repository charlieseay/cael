"""Vision tools — screen capture and image analysis via Anthropic vision API.

Two tools:
  take_screenshot  — captures the Mac screen silently, analyzes it, speaks the result
  analyze_image    — analyzes an image provided as base64 (e.g., from iOS camera)

Both call claude-haiku-4-5 directly (vision-capable, fast). Vision calls always
route to COMPLEX tier so the main router doesn't downgrade them.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from pathlib import Path

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

_SCREENSHOT_PATH = Path(tempfile.gettempdir()) / "cael-screen.png"
_VISION_MODEL = "claude-haiku-4-5-20251001"
_VISION_MAX_TOKENS = 512

# Default question when no specific question is asked
_DEFAULT_SCREEN_Q = (
    "Describe what is on the screen concisely. "
    "Focus on the active application, any visible text, and what the user appears to be doing."
)
_DEFAULT_IMAGE_Q = "Describe what you see in this image concisely."


async def _call_vision(
    image_data: bytes,
    mime_type: str,
    question: str,
) -> str:
    """Call Anthropic vision API with an image and return the text response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "Vision analysis unavailable — ANTHROPIC_API_KEY not set."

    try:
        import anthropic
    except ImportError:
        return "Vision analysis unavailable — anthropic package not installed."

    b64 = base64.standard_b64encode(image_data).decode("utf-8")

    def _sync_call() -> str:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_VISION_MODEL,
            max_tokens=_VISION_MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": question},
                    ],
                }
            ],
        )
        return response.content[0].text if response.content else "No description returned."

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_call)


async def execute_take_screenshot(question: str = "") -> str:
    """Capture the Mac screen and describe it using vision."""
    q = question.strip() or _DEFAULT_SCREEN_Q

    # screencapture -x: silent (no shutter sound), -t png: PNG format
    proc = await asyncio.create_subprocess_exec(
        "screencapture", "-x", "-t", "png", str(_SCREENSHOT_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        logger.error(f"screencapture failed: {err}")
        return f"Screenshot failed: {err or 'unknown error'}"

    if not _SCREENSHOT_PATH.exists() or _SCREENSHOT_PATH.stat().st_size == 0:
        return "Screenshot failed: output file is empty."

    image_data = _SCREENSHOT_PATH.read_bytes()
    logger.info(f"Screenshot captured: {len(image_data):,} bytes → analyzing with {_VISION_MODEL}")

    result = await _call_vision(image_data, "image/png", q)
    logger.info(f"Vision result ({len(result)} chars): {result[:80]}...")
    return result


async def execute_analyze_image(
    image_b64: str,
    mime_type: str = "image/jpeg",
    question: str = "",
) -> str:
    """Analyze an image provided as a base64 string."""
    q = question.strip() or _DEFAULT_IMAGE_Q
    try:
        image_data = base64.b64decode(image_b64)
    except Exception as e:
        return f"Invalid image data: {e}"

    logger.info(f"Analyzing image: {len(image_data):,} bytes, {mime_type}")
    result = await _call_vision(image_data, mime_type, q)
    logger.info(f"Vision result ({len(result)} chars): {result[:80]}...")
    return result


TAKE_SCREENSHOT_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "take_screenshot",
        "description": (
            "Capture the current Mac screen and describe what is visible. "
            "Use when the user asks 'what's on my screen', 'what does this error say', "
            "'describe the active window', or similar visual questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Specific question about the screen content. Optional — defaults to a general description.",
                }
            },
            "required": [],
        },
    },
}

ANALYZE_IMAGE_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "analyze_image",
        "description": (
            "Analyze an image sent from the iOS app. Called automatically when the user "
            "shares a photo or screenshot from their phone. Do not call this directly — "
            "it is invoked by the iOS image handler."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_b64": {
                    "type": "string",
                    "description": "Base64-encoded image data.",
                },
                "mime_type": {
                    "type": "string",
                    "description": "Image MIME type, e.g. image/jpeg or image/png.",
                },
                "question": {
                    "type": "string",
                    "description": "Question about the image. Optional.",
                },
            },
            "required": ["image_b64"],
        },
    },
}


class VisionTools:
    """Mixin providing vision (screenshot + image analysis) tools."""

    @function_tool
    async def take_screenshot(self, question: str = "") -> str:
        """Capture the Mac screen and describe it."""
        return await execute_take_screenshot(question)

    @function_tool
    async def analyze_image(
        self,
        image_b64: str,
        mime_type: str = "image/jpeg",
        question: str = "",
    ) -> str:
        """Analyze a base64-encoded image and return a description."""
        return await execute_analyze_image(image_b64, mime_type, question)
