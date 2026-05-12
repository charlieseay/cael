#!/usr/bin/env bash
# launcher.sh — start all four sidecar processes bound to 0.0.0.0 (accessible over network)
# Invoked by SoniqueBar's SidecarManager. First argument is the sidecar root.
set -euo pipefail

ROOT="${1:?launcher requires sidecar root as first arg}"
SERVICE="${2:?launcher requires service name as second arg}"

export PATH="$ROOT/python/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONUNBUFFERED=1

case "$SERVICE" in
  livekit)
    exec "$ROOT/livekit-server" \
      --config "$ROOT/config/livekit.yaml"
    ;;
  stt)
    export HOST=0.0.0.0 PORT=8081
    export STT_MODEL=small.en STT_DEVICE=cpu STT_COMPUTE=int8 STT_BEAM_SIZE=1
    export HF_HOME="$ROOT/models/whisper"
    cd "$ROOT/services/caal-stt"
    exec python -m uvicorn server:app --host 0.0.0.0 --port 8081 --log-level warning
    ;;
  tts)
    # Real Piper (caal-tts) on 8082 — OpenAI-compatible POST /v1/audio/speech.
    # A previous stub only answered GET, which made every Piper TTS call 404.
    export HOST=0.0.0.0 PORT=8082
    export TTS_VOICE_DIR="${TTS_VOICE_DIR:-$ROOT/models/piper-voices}"
    mkdir -p "$TTS_VOICE_DIR"
    cd "$ROOT/services/caal-tts"
    exec python -m uvicorn server:app --host 0.0.0.0 --port 8082 --log-level warning
    ;;
  agent)
    # Evict any stale voice_agent process before binding its ports.
    # Target the process by name rather than by port holder — lsof returns Docker
    # Desktop's port-proxy PID on systems running Docker, not the actual agent.
    pkill -9 -f "voice_agent.py" 2>/dev/null || true
    sleep 1.5
    export LIVEKIT_URL="${LIVEKIT_URL:-ws://127.0.0.1:7880}"
    # Detect LAN IP so iOS clients receive a reachable WebSocket URL
    _LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
    export LIVEKIT_EXTERNAL_URL="${LIVEKIT_EXTERNAL_URL:-ws://${_LAN_IP}:7880}"
    # Keys are set by SidecarManager from generated UUIDs; only fall back if somehow missing
    export LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-devkey}"
    export LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-devlocalsecret}"
    export SPEACHES_URL=http://127.0.0.1:8081
    export PIPER_URL=http://127.0.0.1:8082
    export KOKORO_URL=http://127.0.0.1:8880
    # Respect TTS_PROVIDER set by SidecarManager (user preference); default to auto-detect
    export TTS_PROVIDER="${TTS_PROVIDER:-auto}"
    export TTS_MODEL="${TTS_MODEL:-auto}"
    export WHISPER_MODEL=small.en
    export TIMEZONE="${TIMEZONE:-America/Chicago}"
    export TIMEZONE_DISPLAY="${TIMEZONE_DISPLAY:-Central Time}"
    export WEBHOOK_PORT=8891
    export CAAL_WORKER_PORT=8892
    export CAAL_SESSION_BRIEFING=true
    export CAAL_NETWORK_STATE_PATH="$ROOT/../caal-network-state.json"
    export CAAL_MEMORY_DIR="$ROOT/../memory"
    # Point settings.json at a stable sidecar-local path so settings persist across launches
    export CAAL_SETTINGS_PATH="$ROOT/services/caal-agent/settings.json"
    export DYLD_LIBRARY_PATH="$ROOT/piper:${DYLD_LIBRARY_PATH:-}"
    # Export API keys from settings.json as env var fallbacks so provider SDKs
    # can always find them even if the router config loads before settings are warm.
    _SETTINGS="$ROOT/services/caal-agent/settings.json"
    if [ -f "$_SETTINGS" ]; then
        _ANTHROPIC=$(python3 -c "import json,sys; d=json.load(open('$_SETTINGS')); print(d.get('anthropic_api_key',''))" 2>/dev/null || true)
        _NVIDIA=$(python3 -c "import json,sys; d=json.load(open('$_SETTINGS')); print(d.get('nvidia_api_key',''))" 2>/dev/null || true)
        [ -n "$_ANTHROPIC" ] && export ANTHROPIC_API_KEY="$_ANTHROPIC"
        [ -n "$_NVIDIA" ] && export NVIDIA_API_KEY="$_NVIDIA"
    fi
    cd "$ROOT/services/caal-agent"
    exec python voice_agent.py start
    ;;
  *)
    echo "unknown service: $SERVICE" >&2
    exit 2
    ;;
esac
