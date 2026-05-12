"""Piper HTTP client retries (readiness / transient errors)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_piper_retries_503_then_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPER_URL", "http://127.0.0.1:59999")
    monkeypatch.setenv("CAAL_PIPER_HTTP_RETRIES", "5")
    monkeypatch.setenv("CAAL_PIPER_RETRY_BASE_S", "0.01")
    monkeypatch.setenv("CAAL_PIPER_RETRY_MAX_S", "0.05")

    from caal.tts.synthesizer import _piper

    req = httpx.Request("POST", "http://127.0.0.1:59999/v1/audio/speech")
    r503 = httpx.Response(503, request=req)
    r200 = httpx.Response(200, request=req, content=b"RIFFok")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[r503, r503, r200])
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    sleeper = AsyncMock()

    with (
        patch("caal.tts.synthesizer.httpx.AsyncClient", return_value=mock_client),
        patch("caal.tts.synthesizer.asyncio.sleep", sleeper),
    ):
        out = await _piper("hi", voice="speaches-ai/piper-en_US-ryan-high")
        assert out == b"RIFFok"
        assert sleeper.await_count == 2


@pytest.mark.asyncio
async def test_piper_retries_connect_then_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPER_URL", "http://127.0.0.1:59998")
    monkeypatch.setenv("CAAL_PIPER_HTTP_RETRIES", "4")
    monkeypatch.setenv("CAAL_PIPER_RETRY_BASE_S", "0.01")
    monkeypatch.setenv("CAAL_PIPER_RETRY_MAX_S", "0.05")

    from caal.tts.synthesizer import _piper

    req = httpx.Request("POST", "http://127.0.0.1:59998/v1/audio/speech")
    ok = httpx.Response(200, request=req, content=b"RIFFx")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[httpx.ConnectError("refused"), ok])
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    sleeper = AsyncMock()

    with (
        patch("caal.tts.synthesizer.httpx.AsyncClient", return_value=mock_client),
        patch("caal.tts.synthesizer.asyncio.sleep", sleeper),
    ):
        out = await _piper("x", voice="en_US-ryan-high")
        assert out.startswith(b"RIFF")
        assert sleeper.await_count == 1
