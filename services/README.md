# services/

Lean Python microservices that replace the general-purpose STT and TTS containers (Speaches, Kokoro) for single-user deployments.

Each service follows the same pattern: `python:3.12-slim` base, `server.py`, `/health`, one primary endpoint. No auth, no batching, no multi-model — only what Sonique needs.

## Why

The existing Speaches and Kokoro containers are built for general use. Sonique uses a tiny slice of their surface. Slimming them down:

- Shrinks bundled install size for SoniqueBar (Option D — Python sidecar).
- Lowers idle resource use on Fly or any hosted deployment.
- Lets the native-MLX migration (Option C) happen one service at a time by keeping a stable HTTP contract.

## Deployment modes

Each service reads `HOST` and `PORT` from env.

| Mode | `HOST` | Consumer |
|---|---|---|
| Networked server (current CAAL, in containers) | `0.0.0.0` | sonique-ios over Tailscale, power users |
| Embedded sidecar (new, SoniqueBar.app) | `127.0.0.1` | Mac menubar app, single user |

## Services

- [caal-stt](caal-stt/) — speech-to-text (replaces the STT half of Speaches)
- [caal-tts](caal-tts/) — text-to-speech (wraps Piper — matches what SoniqueBar configures today)

caal-agent (orchestration) stays in its current location for now; it's already lean. It continues to call out to host Ollama for the LLM.

## Usage with CAAL

A dedicated overlay, `docker-compose.slim.yml`, swaps the GPU `speaches` and `kokoro` containers out for these microservices and re-points the agent's `SPEACHES_URL` / `PIPER_URL` to them:

```bash
docker compose -f docker-compose.yaml -f docker-compose.slim.yml up -d
```

This runs the full CAAL stack (livekit + agent + frontend) on CPU only. The agent already reads `SPEACHES_URL` and `PIPER_URL` from env, so no agent code changes are required — the overlay handles the flip.

## Endpoint compatibility

Both services expose two shapes:

| Shape | Purpose |
|---|---|
| OpenAI-compat (`/v1/audio/transcriptions`, `/v1/audio/speech`, `/v1/models`) | Drop-in for Speaches. What caal-agent's `openai.STT` and `synthesizer.py` call today. |
| Minimal (`/transcribe`, `/synthesize`) | Simpler JSON surface for direct callers and future SoniqueBar sidecar use. |

## Status

Backends wired and runtime-verified end-to-end:

- Round-trip test: Piper-synthesized WAV → faster-whisper returns the exact input text with 1.0 language probability.
- Both images build cleanly (`caal-stt` on native arch; `caal-tts` on `linux/amd64` because `piper-phonemize` ships no arm64 Linux wheel).
- `docker compose -f docker-compose.yaml -f docker-compose.slim.yml config` validates and produces the expected agent env + depends_on.

Not yet done: running the full slim stack end-to-end with a live LiveKit voice session against Ollama. That's the next integration step.
