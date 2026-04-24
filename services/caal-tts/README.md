# caal-tts

Lean text-to-speech microservice. Replaces the Kokoro container for Sonique's single-user deployments.

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

Backend is a stub. `/synthesize` returns silent PCM (100 ms) so callers can exercise the contract. Next: wire Kokoro via the `kokoro` Python package and add voice selection.
