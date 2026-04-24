# caal-stt

Lean speech-to-text microservice. Replaces the Speaches container for Sonique's single-user deployments.

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{"ok": true, "service": "caal-stt"}` |
| POST | `/transcribe` | multipart `audio` | `{"text": "..."}` |

## Run (dev)

```bash
cd services/caal-stt
pip install -r requirements.txt
python server.py
```

Defaults: `HOST=127.0.0.1`, `PORT=8081`.

## Run (container)

```bash
docker build -t caal-stt:dev .
docker run --rm -p 8081:8081 -e HOST=0.0.0.0 caal-stt:dev
```

## Status

Backend is a stub. `/transcribe` returns an empty string so callers can exercise the contract. Next: wire faster-whisper and add a model env var.
