# caal-tts

Lean text-to-speech microservice. Replaces the Piper-via-Speaches path for Sonique's single-user deployments. (Sonique today uses Piper, not Kokoro — see `ContainerManager.swift` in sonique-mac.)

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{"ok": true, "service": "caal-tts"}` |
| POST | `/synthesize` | `{"text": "...", "voice": "af_heart"}` | `audio/wav` (16-bit PCM) |

## Run (dev)

```bash
cd services/caal-tts
pip install -r requirements.txt
python server.py
```

Defaults: `HOST=127.0.0.1`, `PORT=8082`.

## Run (container)

```bash
docker build -t caal-tts:dev .
docker run --rm -p 8082:8082 -e HOST=0.0.0.0 caal-tts:dev
```

## Status

Backend wired — Piper via the `piper-tts` Python package. Default voice `en_US-ryan-high` matches SoniqueBar's current config. The voice name Speaches uses (`speaches-ai/piper-en_US-ryan-high`) is normalized to the bare Piper form, so existing callers don't have to change.

Voices auto-download on first use from `rhasspy/piper-voices` on HuggingFace into `TTS_VOICE_DIR` (container default `/app/voices`) and are cached in memory after load.

Not yet integration-tested against live CAAL containers — next step is to run alongside the existing stack and compare output against the current Speaches-routed path.
