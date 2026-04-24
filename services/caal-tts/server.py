"""caal-tts — lean text-to-speech microservice.

Wraps Piper. Exposes two endpoint shapes:

  1. OpenAI-compatible: POST /v1/audio/speech
     JSON {model, input, voice, response_format} — matches what
     caal-agent's synthesizer.py posts. Drop-in for the Piper path
     through Speaches. Only `response_format: "wav"` is supported.

  2. Minimal: POST /synthesize
     JSON {text, voice} — simpler surface for direct callers.

Voices download on first use from HuggingFace (rhasspy/piper-voices)
into TTS_VOICE_DIR and stay cached. Loaded voices are kept in memory.

Voice names follow Piper's layout: `{lang_region}-{speaker}-{quality}`,
e.g. `en_US-ryan-high`. The Speaches prefix (`speaches-ai/piper-`) is
stripped if present so existing SoniqueBar/CAAL configs work unchanged.

Env:
  HOST            bind host (default 127.0.0.1)
  PORT            bind port (default 8082)
  TTS_VOICE       default voice name (default en_US-ryan-high)
  TTS_VOICE_DIR   cache dir for .onnx voice files (default /app/voices)
"""

import io
import os
import urllib.request
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from piper import PiperVoice
from pydantic import BaseModel

DEFAULT_VOICE = os.getenv("TTS_VOICE", "en_US-ryan-high")
VOICE_DIR = Path(os.getenv("TTS_VOICE_DIR", "/app/voices"))
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

_voices: dict[str, PiperVoice] = {}


def _normalize(name: str) -> str:
    prefix = "speaches-ai/piper-"
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name


def _voice_paths(name: str) -> tuple[Path, Path]:
    return VOICE_DIR / f"{name}.onnx", VOICE_DIR / f"{name}.onnx.json"


def _voice_urls(name: str) -> tuple[str, str]:
    lang_region, speaker, quality = name.split("-", 2)
    lang = lang_region.split("_", 1)[0]
    base = f"{HF_BASE}/{lang}/{lang_region}/{speaker}/{quality}/{name}"
    return f"{base}.onnx", f"{base}.onnx.json"


def _ensure_voice(name: str) -> tuple[Path, Path]:
    onnx_path, config_path = _voice_paths(name)
    if onnx_path.exists() and config_path.exists():
        return onnx_path, config_path
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    onnx_url, config_url = _voice_urls(name)
    urllib.request.urlretrieve(onnx_url, onnx_path)
    urllib.request.urlretrieve(config_url, config_path)
    return onnx_path, config_path


def _get_voice(name: str) -> PiperVoice:
    name = _normalize(name)
    if name not in _voices:
        onnx_path, config_path = _ensure_voice(name)
        _voices[name] = PiperVoice.load(str(onnx_path), config_path=str(config_path))
    return _voices[name]


def _render_wav(voice: PiperVoice, text: str) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        voice.synthesize(text, wav)
    return buf.getvalue()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _get_voice(DEFAULT_VOICE)
    yield
    _voices.clear()


app = FastAPI(title="caal-tts", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "caal-tts",
        "default_voice": DEFAULT_VOICE,
        "voices_loaded": list(_voices.keys()),
    }


@app.get("/v1/models")
def list_models() -> dict:
    return {
        "object": "list",
        "data": [{"id": f"speaches-ai/piper-{DEFAULT_VOICE}", "object": "model"}],
    }


class OpenAISpeechRequest(BaseModel):
    input: str
    model: str | None = None
    voice: str | None = None
    response_format: str = "wav"
    speed: float = 1.0


@app.post("/v1/audio/speech")
def openai_speech(req: OpenAISpeechRequest) -> Response:
    if not req.input.strip():
        raise HTTPException(status_code=400, detail="input is empty")
    if req.response_format != "wav":
        raise HTTPException(
            status_code=400,
            detail=f"only response_format=wav supported, got {req.response_format!r}",
        )
    # caal-agent's synthesizer.py sends the voice in both `model` and `voice`
    # fields. Prefer `voice`; fall back to `model`; then env default.
    voice_name = req.voice or req.model or DEFAULT_VOICE
    try:
        voice = _get_voice(voice_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"voice unavailable: {voice_name} ({exc})")
    return Response(
        content=_render_wav(voice, req.input),
        media_type="audio/wav",
        headers={"X-Voice": _normalize(voice_name)},
    )


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest) -> Response:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    voice_name = req.voice or DEFAULT_VOICE
    try:
        voice = _get_voice(voice_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"voice unavailable: {voice_name} ({exc})")
    return Response(
        content=_render_wav(voice, req.text),
        media_type="audio/wav",
        headers={"X-Voice": _normalize(voice_name)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8082")),
    )
