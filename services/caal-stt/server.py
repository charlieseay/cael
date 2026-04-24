"""caal-stt — lean speech-to-text microservice.

Wraps faster-whisper. Exposes two endpoint shapes:

  1. OpenAI-compatible: POST /v1/audio/transcriptions
     multipart form with file, model, language, response_format — matches
     what caal-agent's openai.STT plugin posts. Drop-in for Speaches.

  2. Minimal: POST /transcribe
     multipart file field only; returns JSON with extra fields (language
     probability, duration). For direct callers that don't need OpenAI
     compatibility.

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

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
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


def _run_transcribe(
    audio_bytes: bytes,
    filename: str | None,
    *,
    language: str | None = None,
    initial_prompt: str | None = None,
    temperature: float = 0.0,
) -> tuple[str, list, object]:
    if _model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    suffix = Path(filename or "in.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
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
        # Materialize the generator once; text and segments both need it.
        segments = list(segment_gen)
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, segments, info
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@app.get("/health")
def health() -> dict:
    return {
        "ok": _model is not None,
        "service": "caal-stt",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "compute": COMPUTE_TYPE,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8081")),
    )
