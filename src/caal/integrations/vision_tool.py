"""Vision tools — screen capture and image analysis via Anthropic vision API.

Four tools:
  take_screenshot   — full Mac screen capture, analyzes + speaks result
  capture_region    — captures a named region (e.g. "nav menu"), sends to iOS + speaks
  dismiss_screen    — tells iOS to close the screen capture overlay
  analyze_image     — analyzes a base64 image from iOS camera

capture_region uses a two-pass approach: full screenshot → Haiku identifies region
coordinates → screencapture -R crops that region → sends to iOS data channel + speaks.
All vision calls route to COMPLEX tier (vision-capable models only).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
from pathlib import Path

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

_SCREENSHOT_PATH = Path(tempfile.gettempdir()) / "cael-screen.png"
_FULL_PATH = Path(tempfile.gettempdir()) / "cael-screen-full.png"
_ANALYSIS_PATH = Path(tempfile.gettempdir()) / "cael-screen-analysis.jpg"
_REGION_PATH = Path(tempfile.gettempdir()) / "cael-screen-region.jpg"

_VISION_MODEL = "claude-haiku-4-5-20251001"
_VISION_MAX_TOKENS = 512
_COORD_MAX_TOKENS = 256  # region coordinate responses are short

_DEFAULT_SCREEN_Q = (
    "Describe what is on the screen concisely. "
    "Focus on the active application, any visible text, and what the user appears to be doing."
)
_DEFAULT_IMAGE_Q = "Describe what you see in this image concisely."


async def _call_vision(
    image_data: bytes,
    mime_type: str,
    question: str,
    max_tokens: int = _VISION_MAX_TOKENS,
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
            max_tokens=max_tokens,
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


async def _compress_for_analysis(src: Path) -> bytes:
    """Downsample to JPEG for the region-identification vision call (faster + cheaper)."""
    proc = await asyncio.create_subprocess_exec(
        "sips", "-Z", "1600", "-s", "format", "jpeg",
        "-s", "formatOptions", "60",
        str(src), "--out", str(_ANALYSIS_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.wait_for(proc.communicate(), timeout=10.0)
    if _ANALYSIS_PATH.exists() and _ANALYSIS_PATH.stat().st_size > 0:
        return _ANALYSIS_PATH.read_bytes()
    return src.read_bytes()


async def _resize_region(path: Path) -> bytes:
    """Resize region JPEG to ≤1200px wide before sending to iOS."""
    if not path.exists() or path.stat().st_size == 0:
        return b""
    if path.stat().st_size <= 400_000:
        return path.read_bytes()
    proc = await asyncio.create_subprocess_exec(
        "sips", "-Z", "1200", str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.wait_for(proc.communicate(), timeout=10.0)
    return path.read_bytes()


async def _publish_screen_capture(
    image_data: bytes,
    mime_type: str,
    publish_fn,
    description: str = "",
) -> None:
    """Encode image as base64 and publish to iOS via LiveKit data channel."""
    b64 = base64.standard_b64encode(image_data).decode("utf-8")
    payload = json.dumps({
        "type": "screen_capture",
        "image_b64": b64,
        "mime_type": mime_type,
        "description": description,
    })
    await publish_fn(
        payload.encode("utf-8"),
        reliable=True,
        topic="screen_capture",
    )
    logger.info(f"Screen capture published to iOS ({len(image_data):,} bytes, {description!r})")


async def execute_take_screenshot(question: str = "") -> str:
    """Capture the Mac screen and describe it using vision."""
    q = question.strip() or _DEFAULT_SCREEN_Q

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


async def execute_capture_region(
    description: str,
    question: str = "",
    publish_fn=None,
) -> str:
    """Capture a named region of the Mac screen, send to iOS, and describe it.

    Two-pass: full screenshot → Haiku finds region coords → screencapture -R
    crops exactly that region → compress → publish to iOS → analyze for voice.
    All screencapture -R coordinates are in logical screen points. Retina displays
    output 2× physical pixels, so Haiku's image-pixel coords are divided by 2.0.
    """
    # Pass 1: full screenshot for analysis
    proc = await asyncio.create_subprocess_exec(
        "screencapture", "-x", "-t", "png", str(_FULL_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
    if proc.returncode != 0 or not _FULL_PATH.exists() or _FULL_PATH.stat().st_size == 0:
        return f"Screenshot failed: {stderr.decode().strip() or 'output file empty'}"

    analysis_bytes = await _compress_for_analysis(_FULL_PATH)

    # Ask Haiku to locate the region
    coord_prompt = (
        f"This is a screenshot of a Mac screen. Find the region that best matches: '{description}'. "
        f"Return ONLY a JSON object with integer keys x, y, width, height representing the "
        f"bounding box in image pixels (top-left origin, no padding). "
        f"No explanation, no markdown — just the JSON."
    )
    coords_raw = await _call_vision(
        analysis_bytes, "image/jpeg", coord_prompt, max_tokens=_COORD_MAX_TOKENS
    )
    logger.info(f"Region coords raw: {coords_raw[:200]}")

    # Parse coordinates and convert image pixels → logical screen points (÷2 for Retina)
    region_bytes: bytes
    mime = "image/jpeg"
    try:
        match = re.search(r'\{[^{}]+\}', coords_raw, re.DOTALL)
        if not match:
            raise ValueError("no JSON object found")
        coords = json.loads(match.group())
        scale = 2.0  # all modern Macs (MacBook, Mac Mini, iMac) use Retina 2×
        lx = max(0, int(int(coords["x"]) / scale))
        ly = max(0, int(int(coords["y"]) / scale))
        lw = max(80, int(int(coords["width"]) / scale))
        lh = max(40, int(int(coords["height"]) / scale))
        logger.info(f"Logical region: x={lx} y={ly} w={lw} h={lh}")

        # Pass 2: crop exactly that region
        proc = await asyncio.create_subprocess_exec(
            "screencapture", "-x", "-t", "jpg",
            "-R", f"{lx},{ly},{lw},{lh}",
            str(_REGION_PATH),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)

        if proc.returncode == 0 and _REGION_PATH.exists() and _REGION_PATH.stat().st_size > 0:
            region_bytes = await _resize_region(_REGION_PATH)
            logger.info(f"Region JPEG: {len(region_bytes):,} bytes")
        else:
            logger.warning(f"Region crop failed ({stderr.decode().strip()}), using compressed full")
            region_bytes = analysis_bytes

    except Exception as e:
        logger.warning(f"Region parse failed ({e}), using full screenshot")
        region_bytes = analysis_bytes

    # Publish to iOS
    if publish_fn is not None:
        await _publish_screen_capture(region_bytes, mime, publish_fn, description)

    # Analyze for voice response
    q = question.strip() or f"Describe what you see in this region of the Mac screen: '{description}'."
    result = await _call_vision(region_bytes, mime, q)
    logger.info(f"Region analysis ({len(result)} chars): {result[:80]}...")
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


async def execute_dismiss_screen(publish_fn=None) -> str:
    """Tell iOS to dismiss the screen capture overlay."""
    if publish_fn is not None:
        payload = json.dumps({"type": "screen_dismiss"})
        await publish_fn(payload.encode("utf-8"), reliable=True, topic="screen_dismiss")
        logger.info("screen_dismiss published to iOS")
    return "Screen dismissed."


# ── Tool definitions ──────────────────────────────────────────────────────────

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
                    "description": "Specific question about the screen content. Optional.",
                }
            },
            "required": [],
        },
    },
}

CAPTURE_REGION_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "capture_region",
        "description": (
            "Capture a specific region of the Mac screen by description and send it to the iOS app. "
            "Use when the user says 'show me the nav menu', 'send me that error dialog', "
            "'share the toolbar', 'send me what you see in X', or any request to share a specific "
            "visible element. The region is identified automatically, cropped, and sent as an "
            "image to iOS. Also analyzes and describes it verbally."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What to capture, e.g. 'navigation menu', 'error dialog', 'top toolbar', 'sidebar'.",
                },
                "question": {
                    "type": "string",
                    "description": "Specific question to answer about the captured region. Optional.",
                },
            },
            "required": ["description"],
        },
    },
}

DISMISS_SCREEN_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "dismiss_screen",
        "description": (
            "Dismiss the screen capture overlay on the iOS app. "
            "Call when the user says 'close', 'dismiss', 'hide the image', 'done', or 'clear that'."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
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


# ── Mixin class ───────────────────────────────────────────────────────────────

class VisionTools:
    """Mixin providing vision tools: full screenshot, region capture, dismiss, image analysis."""

    @function_tool
    async def take_screenshot(self, question: str = "") -> str:
        """Capture the Mac screen and describe it."""
        return await execute_take_screenshot(question)

    @function_tool
    async def capture_region(self, description: str, question: str = "") -> str:
        """Capture a named region of the Mac screen and send it to iOS."""
        publish_fn = getattr(self, "_publish_data_fn", None)
        return await execute_capture_region(description, question, publish_fn)

    @function_tool
    async def dismiss_screen(self) -> str:
        """Dismiss the screen capture overlay on iOS."""
        publish_fn = getattr(self, "_publish_data_fn", None)
        return await execute_dismiss_screen(publish_fn)

    @function_tool
    async def analyze_image(
        self,
        image_b64: str,
        mime_type: str = "image/jpeg",
        question: str = "",
    ) -> str:
        """Analyze a base64-encoded image and return a description."""
        return await execute_analyze_image(image_b64, mime_type, question)
