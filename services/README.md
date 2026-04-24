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

## Status

Scaffolding. Neither backend is wired yet. See the packaging plan vault note for phasing.
