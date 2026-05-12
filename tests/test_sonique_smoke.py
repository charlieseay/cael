"""Sonique path helpers and smoke-oriented checks.

Integration probes (live HTTP) run only when RUN_SONIQUE_SMOKE=1.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from caal.llm.providers import normalize_openai_api_base_url, normalize_ollama_host


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:11434", "http://localhost:11434/v1"),
        ("http://host:8000/", "http://host:8000/v1"),
        ("http://host:8000/v1", "http://host:8000/v1"),
        ("http://host:8000/v1/", "http://host:8000/v1"),
        ("", "http://localhost:8000/v1"),
    ],
)
def test_normalize_openai_api_base_url(raw: str, expected: str) -> None:
    assert normalize_openai_api_base_url(raw) == expected


@pytest.mark.parametrize(
    ("ollama_raw", "expected_host"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://localhost:11434/v1", "http://localhost:11434"),
        ("http://localhost:11434/v1/", "http://localhost:11434"),
        ("", "http://localhost:11434"),
        (None, "http://localhost:11434"),
    ],
)
def test_normalize_ollama_host(ollama_raw: str | None, expected_host: str) -> None:
    assert normalize_ollama_host(ollama_raw) == expected_host


@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get("RUN_SONIQUE_SMOKE") != "1", reason="set RUN_SONIQUE_SMOKE=1 to hit live services")
async def test_live_piper_tts_returns_wav() -> None:
    base = os.environ.get("PIPER_URL", "http://127.0.0.1:8082").rstrip("/")
    url = f"{base}/v1/audio/speech"
    payload = {
        "model": "piper",
        "input": "smoke check one two",
        "voice": "speaches-ai/piper-en_US-ryan-high",
        "response_format": "wav",
    }
    async with httpx.AsyncClient() as client:
        for attempt in range(1, 8):
            try:
                r = await client.post(url, json=payload, timeout=120.0)
                if r.status_code in (404, 502, 503, 504) and attempt < 7:
                    await asyncio.sleep(1.0 * attempt)
                    continue
                r.raise_for_status()
                assert r.content[:4] == b"RIFF"
                return
            except (httpx.ConnectError, httpx.ReadTimeout):
                if attempt >= 7:
                    raise
                await asyncio.sleep(1.0 * attempt)
    pytest.fail("Piper TTS did not return WAV after retries")
