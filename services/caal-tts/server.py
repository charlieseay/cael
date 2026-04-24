"""caal-tts — lean text-to-speech microservice.

POST /synthesize returns 16-bit PCM WAV audio. Backend will be Piper
(CPU, Python package — matches what SoniqueBar configures today) on
servers, and a native TTS path (AVSpeechSynthesizer or bundled Piper)
when we migrate to Swift (Option C).
"""

import io
import os
import wave

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="caal-tts", version="0.1.0")


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "caal-tts"}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest) -> Response:
    # Backend not wired. Returns a valid but silent 100ms WAV so callers can
    # treat the contract as stable while caal-tts is under construction.
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 2205)
    return Response(
        content=buf.getvalue(),
        media_type="audio/wav",
        headers={"X-Stub": "true"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8082")),
    )
