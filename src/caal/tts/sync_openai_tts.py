"""Synchronous OpenAI-compatible TTS wrapper.

This bypasses httpx async issues in LiveKit subprocess by using
synchronous requests wrapped in asyncio.run_in_executor.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

import requests
from livekit.agents import APIConnectionError, APIConnectOptions, APIStatusError, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

logger = logging.getLogger(__name__)

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
        self._executor = ThreadPoolExecutor(max_workers=4)

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
        url = f"{opts.base_url}/audio/speech"
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

        logger.debug(f"Requesting: {url} with model={opts.model}, voice={opts.voice}")

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
                stream=True,
            )

            if response.status_code != 200:
                exc = APIStatusError(
                    f"TTS request failed: {response.text}",
                    status_code=response.status_code,
                    request_id="",
                    body=response.text,
                )
                loop.call_soon_threadsafe(out_q.put_nowait, exc)
                return

            total = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    total += len(chunk)
                    loop.call_soon_threadsafe(out_q.put_nowait, chunk)
            logger.debug(f"Streamed {total} bytes of audio")

        except requests.exceptions.Timeout:
            loop.call_soon_threadsafe(
                out_q.put_nowait, APIConnectionError("TTS request timed out")
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            loop.call_soon_threadsafe(
                out_q.put_nowait, APIConnectionError(f"TTS connection failed: {e}")
            )
        except Exception as e:
            logger.error(f"{type(e).__name__}: {e}")
            loop.call_soon_threadsafe(
                out_q.put_nowait, APIConnectionError(str(e))
            )
        finally:
            loop.call_soon_threadsafe(out_q.put_nowait, None)  # sentinel

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        """Stream TTS synthesis: thread feeds chunks into asyncio queue as they arrive."""
        loop = asyncio.get_running_loop()
        opts = self._tts._opts
        timeout = max(30.0, self._conn_options.timeout)

        out_q: asyncio.Queue = asyncio.Queue()

        thread_future = loop.run_in_executor(
            self._tts._executor,
            partial(self._fetch_chunks, self.input_text, opts, timeout, out_q, loop),
        )

        output_emitter.initialize(
            request_id="sync-tts",
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type=f"audio/{opts.response_format}",
        )

        try:
            while True:
                item = await out_q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                output_emitter.push(item)

            output_emitter.flush()
        finally:
            await thread_future
