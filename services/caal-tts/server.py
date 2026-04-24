"""caal-tts — lean text-to-speech microservice.

Wraps Piper. Voices download on first use from HuggingFace
(rhasspy/piper-voices) into TTS_VOICE_DIR and stay cached. Loaded voices
are kept in memory; synthesis returns 16-bit PCM WAV.

Env:
  HOST            bind host (default 127.0.0.1)
  PORT            bind port (default 8082)
  TTS_VOICE       default voice name (default en_US-ryan-high)
  TTS_VOICE_DIR   cache dir for .onnx voice files (default /app/voices)

Voice naming follows Piper's HuggingFace layout: `{lang_region}-{speaker}-{quality}`,
e.g. `en_US-ryan-high`. The Speaches prefix (`speaches-ai/piper-`) is
stripped if present, for compatibility with SoniqueBar's current config.
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
    # SoniqueBar stores voices as "speaches-ai/piper-en_US-ryan-high"; Piper
    # uses the bare "en_US-ryan-high" form. Accept both.
    prefix = "speaches-ai/piper-"
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name


def _voice_paths(name: str) -> tuple[Path, Path]:
    return VOICE_DIR / f"{name}.onnx", VOICE_DIR / f"{name}.onnx.json"


def _voice_urls(name: str) -> tuple[str, str]:
    # en_US-ryan-high -> en/en_US/ryan/high/en_US-ryan-high.{onnx,onnx.json}
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _get_voice(DEFAULT_VOICE)
    yield
    _voices.clear()


app = FastAPI(title="caal-tts", version="0.1.0", lifespan=lifespan)


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "caal-tts",
        "default_voice": DEFAULT_VOICE,
        "voices_loaded": list(_voices.keys()),
    }


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest) -> Response:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")
    name = req.voice or DEFAULT_VOICE
    try:
        voice = _get_voice(name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"voice unavailable: {name} ({exc})")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        voice.synthesize(req.text, wav)
    return Response(
        content=buf.getvalue(),
        media_type="audio/wav",
        headers={"X-Voice": _normalize(name)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8082")),
    )
