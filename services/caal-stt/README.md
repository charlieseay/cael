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

Backend wired — faster-whisper `small.en` by default, CPU int8. The model downloads from HuggingFace on first run and is cached in `$HF_HOME` (container default `/app/cache/huggingface`). Configurable via `STT_MODEL`, `STT_DEVICE`, `STT_COMPUTE`.

Not yet integration-tested against live CAAL containers — next step is to run alongside the existing stack and send real audio.
