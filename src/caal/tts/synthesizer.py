"""Standalone TTS synthesis for HTTP bridge clients (Siri Shortcuts, PWA, etc.).

Separate from the LiveKit TTS path — no agents dependency.
Supports Kokoro, Speaches, and Piper HTTP backends.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random

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

    Routes by ``tts_provider`` (from ``provider`` arg or settings): ``auto``
    prefers Kokoro when its ``/health`` responds, otherwise Piper. ``kokoro``
    and ``speaches`` are attempted first and fall back to Piper on failure so
    Siri / SoniqueBar voice replies never return empty after a Docker-era
    settings.json left ``tts_provider`` on Kokoro while only caal-tts runs.

    Returns:
        WAV audio bytes.

    Raises:
        RuntimeError: If Piper (ultimate fallback) fails.
    """
    from ..settings import load_settings

    cfg = load_settings()
    tts_provider = (provider or cfg.get("tts_provider", "auto") or "auto").strip().lower()
    kokoro_voice = voice or cfg.get("tts_voice_kokoro", "bm_george")
    piper_voice = cfg.get("tts_voice_piper", "speaches-ai/piper-en_US-ryan-high")

    async def _piper_only() -> bytes:
        return await _piper(text, voice=piper_voice)

    if tts_provider == "auto":
        if await is_kokoro_available():
            try:
                return await _kokoro(text, voice=kokoro_voice)
            except Exception as e:
                logger.warning("Kokoro failed during auto TTS (%s); using Piper", e)
        return await _piper_only()

    if tts_provider == "piper":
        return await _piper_only()

    if tts_provider == "kokoro":
        try:
            return await _kokoro(text, voice=kokoro_voice)
        except Exception as e:
            logger.warning("Kokoro TTS failed (%s); falling back to Piper", e)
        return await _piper_only()

    if tts_provider == "speaches":
        try:
            return await _speaches(text, voice=piper_voice)
        except Exception as e:
            logger.warning("Speaches TTS failed (%s); falling back to Piper", e)
        return await _piper_only()

    logger.warning("Unknown tts_provider %r; using Piper", tts_provider)
    return await _piper_only()


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


def _piper_retry_env() -> tuple[int, float, float]:
    """Max attempts, base delay seconds, max delay cap (exponential backoff + jitter)."""
    try:
        attempts = max(1, int(os.getenv("CAAL_PIPER_HTTP_RETRIES", "6")))
    except ValueError:
        attempts = 6
    try:
        base = float(os.getenv("CAAL_PIPER_RETRY_BASE_S", "0.5"))
    except ValueError:
        base = 0.5
    try:
        cap = float(os.getenv("CAAL_PIPER_RETRY_MAX_S", "8.0"))
    except ValueError:
        cap = 8.0
    return attempts, base, cap


async def _piper(text: str, *, voice: str) -> bytes:
    """Call local Piper OpenAI-compatible endpoint (caal-tts or Speaches).

    Retries with exponential backoff on connection errors and 404/502/503/504 so
    cold starts (route registration, model download, process restart) do not fail
    a single client attempt.
    """
    url = (os.getenv("PIPER_URL", _PIPER_DEFAULT)).rstrip("/")
    endpoint = f"{url}/v1/audio/speech"
    payload = {
        "model": "piper",
        "input": text,
        "voice": voice,
        "response_format": "wav",
    }
    attempts, base_s, cap_s = _piper_retry_env()
    last_exc: Exception | None = None
    async with httpx.AsyncClient() as client:
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.post(endpoint, json=payload, timeout=120.0)
                if resp.status_code in (404, 502, 503, 504) and attempt < attempts:
                    delay = min(cap_s, base_s * (2 ** (attempt - 1)))
                    delay *= 0.85 + 0.3 * random.random()
                    logger.warning(
                        "Piper TTS %s (attempt %s/%s), retry in %.2fs",
                        resp.status_code,
                        attempt,
                        attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.content
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                last_exc = e
                if attempt >= attempts:
                    raise
                delay = min(cap_s, base_s * (2 ** (attempt - 1)))
                delay *= 0.85 + 0.3 * random.random()
                logger.warning(
                    "Piper TTS connection error (attempt %s/%s): %s; retry in %.2fs",
                    attempt,
                    attempts,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
    raise RuntimeError("Piper HTTP: internal error (retry loop fell through)")


async def is_kokoro_available() -> bool:
    """Check if Kokoro TTS is reachable."""
    url = os.getenv("KOKORO_URL", _KOKORO_DEFAULT)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/health", timeout=3.0)
            return resp.status_code == 200
    except Exception:
        return False
