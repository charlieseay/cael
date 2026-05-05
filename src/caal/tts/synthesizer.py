"""Standalone TTS synthesis for HTTP bridge clients (Siri Shortcuts, PWA, etc.).

Separate from the LiveKit TTS path — no agents dependency.
Supports Kokoro, Speaches, and Piper HTTP backends.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_KOKORO_DEFAULT = "http://kokoro:8880"
_SPEACHES_DEFAULT = "http://speaches:8000"
_PIPER_DEFAULT = "http://127.0.0.1:8082"


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
    tts_provider = (provider or cfg.get("tts_provider", "auto") or "auto").strip().lower()
    kokoro_voice = voice or cfg.get("tts_voice_kokoro", "bm_george")
    piper_voice = cfg.get("tts_voice_piper", "speaches-ai/piper-en_US-ryan-high")

    # Embedded sidecar: Piper only (no remote fallback)
    if tts_provider == "auto" or tts_provider == "piper":
        tts_provider = "piper"

    if tts_provider == "piper":
        return await _piper(text, voice=piper_voice)


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


async def _piper(text: str, *, voice: str) -> bytes:
    """Call local Piper OpenAI-compatible endpoint."""
    url = os.getenv("PIPER_URL", _PIPER_DEFAULT)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/v1/audio/speech",
            json={
                "model": "piper",
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
