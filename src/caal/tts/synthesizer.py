"""Standalone TTS synthesis for HTTP bridge clients (Siri Shortcuts, PWA, etc.).

Separate from the LiveKit TTS path — no agents dependency.
Tries Kokoro first, falls back to Speaches if unavailable.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_KOKORO_DEFAULT = "http://kokoro:8880"
_SPEACHES_DEFAULT = "http://speaches:8000"


async def synthesize(
    text: str,
    *,
    voice: str | None = None,
    provider: str | None = None,
) -> bytes:
    """Synthesize text to WAV bytes.

    Tries Kokoro first (if available and not overridden), then Speaches.
    Returns raw WAV bytes ready to send as audio/wav.

    Args:
        text: Text to synthesize.
        voice: Voice ID override. Defaults to current settings value.
        provider: Force "kokoro" or "speaches". Auto-detects if None.

    Returns:
        WAV audio bytes.

    Raises:
        RuntimeError: If all TTS backends fail.
    """
    from ..settings import load_settings

    cfg = load_settings()
    tts_provider = provider or cfg.get("tts_provider", "kokoro")
    kokoro_voice = voice or cfg.get("tts_voice_kokoro", "bm_george")
    piper_voice = cfg.get("tts_voice_piper", "speaches-ai/piper-en_US-ryan-high")

    if tts_provider == "kokoro":
        try:
            return await _kokoro(text, voice=kokoro_voice)
        except Exception as e:
            logger.warning(f"Kokoro TTS failed, falling back to Speaches: {e}")
            return await _speaches(text, voice=piper_voice)
    else:
        try:
            return await _speaches(text, voice=piper_voice)
        except Exception as e:
            logger.warning(f"Speaches TTS failed, trying Kokoro: {e}")
            return await _kokoro(text, voice=kokoro_voice)


async def _kokoro(text: str, *, voice: str) -> bytes:
    """Call Kokoro OpenAI-compatible TTS API."""
    url = os.getenv("KOKORO_URL", _KOKORO_DEFAULT)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/v1/audio/speech",
            json={
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "response_format": "wav",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


async def _speaches(text: str, *, voice: str) -> bytes:
    """Call Speaches OpenAI-compatible TTS API."""
    url = os.getenv("SPEACHES_URL", _SPEACHES_DEFAULT)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/v1/audio/speech",
            json={
                "model": voice,
                "input": text,
                "voice": voice,
                "response_format": "wav",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


async def is_kokoro_available() -> bool:
    """Check if Kokoro TTS is reachable."""
    url = os.getenv("KOKORO_URL", _KOKORO_DEFAULT)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/health", timeout=3.0)
            return resp.status_code == 200
    except Exception:
        return False
