"""caal-stt — lean speech-to-text microservice.

Exposes exactly what SoniqueBar and sonique-ios need: POST /transcribe and GET
/health. No auth, no batching, no multi-model. Backend will be faster-whisper
on servers and MLX Whisper when we migrate to a native Swift runtime (Option
C in the packaging plan).
"""

import os

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="caal-stt", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "caal-stt"}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> JSONResponse:
    # Backend not wired. Returns a stub so Swift/iOS callers can exercise the
    # contract while caal-stt is under construction.
    _size = len(await audio.read())
    return JSONResponse(
        {
            "text": "",
            "stub": True,
            "received_bytes": _size,
            "content_type": audio.content_type,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8081")),
    )
