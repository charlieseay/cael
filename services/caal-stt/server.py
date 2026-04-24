"""caal-stt — lean speech-to-text microservice.

Wraps faster-whisper. The model loads once at startup and stays resident;
/transcribe accepts multipart audio, returns JSON with the transcript and
the detected language. FFmpeg is available in the container image for
non-WAV inputs.

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

from fastapi import FastAPI, File, HTTPException, UploadFile
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


@app.get("/health")
def health() -> dict:
    return {
        "ok": _model is not None,
        "service": "caal-stt",
        "model": MODEL_SIZE,
        "device": DEVICE,
        "compute": COMPUTE_TYPE,
    }


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict:
    if _model is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    data = await audio.read()
    suffix = Path(audio.filename or "in.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.close()
        segments, info = _model.transcribe(tmp.name, beam_size=BEAM_SIZE)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
        }
    finally:
        Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8081")),
    )
