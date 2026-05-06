"""caal-stt — lean speech-to-text microservice.

Wraps faster-whisper. Exposes three endpoint shapes:

  1. OpenAI-compatible: POST /v1/audio/transcriptions
     multipart form with file, model, language, response_format — matches
     what caal-agent's openai.STT plugin posts. Drop-in for Speaches.

  2. Minimal: POST /transcribe
     multipart file field only; returns JSON with extra fields (language
     probability, duration). For direct callers that don't need OpenAI
     compatibility.

  3. Streaming SSE: POST /v1/audio/transcriptions/stream
     Same form as (1). Returns Server-Sent Events streaming each Whisper
     segment as it completes. Final event has is_final=true with full text.
     Enables partial transcript delivery for long utterances.

The model loads once at startup and stays resident. FFmpeg is available
in the container image so non-WAV inputs work.

Env:
  HOST          bind host (default 127.0.0.1)
  PORT          bind port (default 8081)
  STT_MODEL     faster-whisper model size or HF path (default small.en)
  STT_DEVICE    cpu | cuda | auto (default cpu)
  STT_COMPUTE   int8 | int8_float16 | float16 | float32 (default int8)
  STT_BEAM_SIZE beam search size (default 5)
"""

import asyncio
import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from faster_whisper import WhisperModel

MODEL_SIZE = os.getenv("STT_MODEL", "small.en")
DEVICE = os.getenv("STT_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("STT_COMPUTE", "int8")
BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "5"))

_model: WhisperModel | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _model
    _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    yield
    _model = None


app = FastAPI(title="caal-stt", version="0.1.0", lifespan=lifespan)


def _iter_transcribe(
    audio_bytes: bytes,
    filename: str | None,
    *,
    language: str | None = None,
    initial_prompt: str | None = None,
    temperature: float = 0.0,
    out_q: "asyncio.Queue | None" = None,
    loop: "asyncio.AbstractEventLoop | None" = None,
):
    """Run transcription in a thread, yielding segments synchronously.

    If out_q and loop are provided, also pushes each segment into the asyncio
    queue (for SSE streaming). Pushes None as sentinel when done.
    """
    if _model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    suffix = Path(filename or "in.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    segments = []
    info = None
    try:
        tmp.write(audio_bytes)
        tmp.close()
        segment_gen, info = _model.transcribe(
            tmp.name,
            beam_size=BEAM_SIZE,
            language=language,
            initial_prompt=initial_prompt,
            temperature=temperature,
        )
        for seg in segment_gen:
            segments.append(seg)
            if out_q is not None and loop is not None:
                loop.call_soon_threadsafe(out_q.put_nowait, seg)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
        if out_q is not None and loop is not None:
            loop.call_soon_threadsafe(out_q.put_nowait, None)  # sentinel
    return segments, info


def _run_transcribe(
    audio_bytes: bytes,
    filename: str | None,
    *,
    language: str | None = None,
    initial_prompt: str | None = None,
    temperature: float = 0.0,
) -> tuple[str, list, object]:
    segments, info = _iter_transcribe(
        audio_bytes, filename,
        language=language, initial_prompt=initial_prompt, temperature=temperature,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, segments, info


@app.get("/health")
def health() -> dict:
    return {
        "ok": _model is not None,
        "service": "caal-stt",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "compute": COMPUTE_TYPE,
        "beam_size": BEAM_SIZE,
    }


@app.get("/v1/models")
def list_models() -> dict:
    return {"object": "list", "data": [{"id": MODEL_SIZE, "object": "model"}]}


@app.post("/v1/audio/transcriptions")
async def openai_transcriptions(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
) -> Response:
    data = await file.read()
    text, segments, info = _run_transcribe(
        data,
        file.filename,
        language=language,
        initial_prompt=prompt,
        temperature=temperature,
    )
    if response_format == "text":
        return Response(content=text, media_type="text/plain")
    if response_format == "verbose_json":
        return JSONResponse(
            {
                "task": "transcribe",
                "language": info.language,
                "duration": info.duration,
                "text": text,
                "segments": [
                    {"id": i, "start": s.start, "end": s.end, "text": s.text}
                    for i, s in enumerate(segments)
                ],
            }
        )
    return JSONResponse({"text": text})


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict:
    data = await audio.read()
    text, _segments, info = _run_transcribe(data, audio.filename)
    return {
        "text": text,
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
    }


@app.post("/v1/audio/transcriptions/stream")
async def openai_transcriptions_stream(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    temperature: float = Form(0.0),
) -> StreamingResponse:
    """Stream Whisper segments via SSE as they complete.

    Each event: data: {"text": str, "start": float, "end": float, "is_final": false}
    Final event: data: {"text": str, "is_final": true}
    """
    data = await file.read()
    loop = asyncio.get_event_loop()
    out_q: asyncio.Queue = asyncio.Queue()

    # Run transcription in thread pool so segments stream into the queue
    asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _iter_transcribe(
            data, file.filename,
            language=language, initial_prompt=prompt, temperature=temperature,
            out_q=out_q, loop=loop,
        ),
    )

    async def event_stream():
        accumulated = []
        while True:
            seg = await out_q.get()
            if seg is None:
                # Final event with full concatenated text
                full_text = " ".join(s.text.strip() for s in accumulated).strip()
                yield f"data: {json.dumps({'text': full_text, 'is_final': True})}\n\n"
                break
            accumulated.append(seg)
            yield f"data: {json.dumps({'text': seg.text.strip(), 'start': seg.start, 'end': seg.end, 'is_final': False})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8081")),
    )
