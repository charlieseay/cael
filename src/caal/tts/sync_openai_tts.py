"""Synchronous OpenAI-compatible TTS wrapper.

This bypasses httpx async issues in LiveKit subprocess by using
synchronous requests wrapped in asyncio.run_in_executor.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import requests
from livekit.agents import APIConnectionError, APIConnectOptions, APIStatusError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

logger = logging.getLogger(__name__)

# Declared capability rate. LiveKit uses this for track setup; the emitter
# re-initializes with the real rate from the WAV header on first chunk.
# Kokoro (active TTS) outputs 24000 Hz natively. If Piper is re-introduced
# (22050 Hz), lower this to 22050 — resampling up is cheaper than down.
SAMPLE_RATE = 24000
NUM_CHANNELS = 1


@dataclass
class _TTSOptions:
    model: str
    voice: str
    speed: float
    base_url: str
    api_key: str
    response_format: str


class SyncOpenAITTS(tts.TTS):
    """OpenAI-compatible TTS using synchronous requests."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        voice: str,
        api_key: str = "not-needed",
        speed: float = 1.0,
        response_format: str = "mp3",
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._opts = _TTSOptions(
            model=model,
            voice=voice,
            speed=speed,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            response_format=response_format,
        )
        max_workers = max(2, int(os.getenv("CAAL_TTS_MAX_WORKERS", "6")))
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> "SyncChunkedStream":
        return SyncChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        self._executor.shutdown(wait=False)


class SyncChunkedStream(tts.ChunkedStream):
    """Stream that uses synchronous HTTP for TTS requests."""

    def __init__(
        self,
        *,
        tts: SyncOpenAITTS,
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: SyncOpenAITTS = tts

    def _fetch_chunks(
        self,
        text: str,
        opts: _TTSOptions,
        timeout: float,
        out_q: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Run in thread pool: stream HTTP response chunks into an asyncio queue.

        Puts chunk bytes as they arrive, then None as a sentinel when done.
        Puts an Exception instance on error (before the sentinel).
        """
        # OpenAI-compatible TTS: base_url is .../v1 (see voice_agent.py).
        logger.debug(f"Requesting TTS with model={opts.model}, voice={opts.voice}")

        def _int_env(name: str, default: int) -> int:
            try:
                return max(1, int(os.getenv(name, str(default))))
            except ValueError:
                return default

        def _float_env(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        max_retries = _int_env("CAAL_SYNC_TTS_HTTP_RETRIES", 5)
        base_wait = _float_env("CAAL_SYNC_TTS_RETRY_BASE_S", 0.6)
        wait_cap = _float_env("CAAL_SYNC_TTS_RETRY_MAX_S", 6.0)

        try:
            for attempt in range(1, max_retries + 1):
                effective_url = f"{opts.base_url}/audio/speech"
                headers = {
                    "Authorization": f"Bearer {opts.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "input": text,
                    "model": opts.model,
                    "voice": opts.voice,
                    "speed": opts.speed,
                    "response_format": opts.response_format,
                }
                try:
                    started_at = time.perf_counter()
                    response = requests.post(
                        effective_url,
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                        stream=True,
                    )

                    if response.status_code == 404:
                        root = opts.base_url.removesuffix("/v1").rstrip("/")
                        legacy_url = f"{root}/audio/speech"
                        if legacy_url != effective_url:
                            response.close()
                            response = requests.post(
                                legacy_url,
                                headers=headers,
                                json=payload,
                                timeout=timeout,
                                stream=True,
                            )
                            effective_url = legacy_url

                    if response.status_code in (502, 503, 504, 429) and attempt < max_retries:
                        response.close()
                        delay = min(
                            wait_cap,
                            base_wait * (2 ** (attempt - 1)),
                        ) * (0.85 + 0.25 * random.random())
                        logger.warning(
                            "TTS HTTP %s on %s (attempt %s/%s), retry in %.2fs",
                            response.status_code,
                            effective_url,
                            attempt,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
                        continue

                    if response.status_code != 200:
                        exc = APIStatusError(
                            f"TTS request failed: {response.text}",
                            status_code=response.status_code,
                            request_id="",
                            body=response.text,
                        )
                        loop.call_soon_threadsafe(out_q.put_nowait, exc)
                        return

                    total_bytes = 0
                    is_first = True
                    for chunk in response.iter_content(chunk_size=4096):
                        if not chunk:
                            continue
                        if is_first:
                            first_ms = (time.perf_counter() - started_at) * 1000
                            logger.info(
                                "TTS_METRIC first_chunk_ms=%.0f format=%s voice=%s",
                                first_ms,
                                opts.response_format,
                                opts.voice,
                            )
                            if opts.response_format == "wav" and not chunk.startswith(b"RIFF"):
                                preview = chunk[:32].hex()
                                logger.error(
                                    "TTS returned non-WAV payload: first 32 bytes=%s url=%s",
                                    preview,
                                    effective_url,
                                )
                                response.close()
                                loop.call_soon_threadsafe(
                                    out_q.put_nowait,
                                    APIConnectionError(
                                        f"TTS returned non-WAV payload (got {preview!r})"
                                    ),
                                )
                                return
                            is_first = False
                        total_bytes += len(chunk)
                        loop.call_soon_threadsafe(out_q.put_nowait, chunk)

                    response.close()

                    if total_bytes == 0:
                        loop.call_soon_threadsafe(
                            out_q.put_nowait,
                            APIConnectionError("TTS returned empty audio body"),
                        )
                        return

                    total_ms = (time.perf_counter() - started_at) * 1000
                    logger.info(
                        "TTS_METRIC total_ms=%.0f bytes=%d format=%s voice=%s",
                        total_ms,
                        total_bytes,
                        opts.response_format,
                        opts.voice,
                    )
                    return

                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt >= max_retries:
                        logger.error("%s: %s", type(e).__name__, e)
                        loop.call_soon_threadsafe(
                            out_q.put_nowait,
                            APIConnectionError(f"TTS connection failed after retries: {e}"),
                        )
                        return
                    delay = min(
                        wait_cap,
                        base_wait * (2 ** (attempt - 1)),
                    ) * (0.85 + 0.25 * random.random())
                    logger.warning(
                        "TTS %s (attempt %s/%s), retry in %.2fs",
                        type(e).__name__,
                        attempt,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)

        except Exception as e:
            logger.error(f"{type(e).__name__}: {e}")
            loop.call_soon_threadsafe(out_q.put_nowait, APIConnectionError(str(e)))
        finally:
            loop.call_soon_threadsafe(out_q.put_nowait, None)  # sentinel

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        """Stream TTS synthesis: thread feeds chunks into asyncio queue as they arrive."""
        loop = asyncio.get_running_loop()
        opts = self._tts._opts
        timeout = max(120.0, float(os.getenv("CAAL_SYNC_TTS_TIMEOUT_S", "120")), self._conn_options.timeout)

        out_q: asyncio.Queue = asyncio.Queue()

        thread_future = loop.run_in_executor(
            self._tts._executor,
            partial(self._fetch_chunks, self.input_text, opts, timeout, out_q, loop),
        )
        initialized = False

        try:
            while True:
                item = await out_q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                if not initialized:
                    sample_rate = SAMPLE_RATE
                    num_channels = NUM_CHANNELS
                    if opts.response_format == "wav":
                        try:
                            with wave.open(io.BytesIO(item), "rb") as wav_file:
                                sample_rate = wav_file.getframerate() or SAMPLE_RATE
                                num_channels = wav_file.getnchannels() or NUM_CHANNELS
                        except Exception as e:
                            logger.warning(f"Could not read WAV header, using defaults: {e}")

                    output_emitter.initialize(
                        request_id="sync-tts",
                        sample_rate=sample_rate,
                        num_channels=num_channels,
                        mime_type=f"audio/{opts.response_format}",
                    )
                    initialized = True
                output_emitter.push(item)

            output_emitter.flush()
        finally:
            await thread_future
