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
    export HOST=0.0.0.0 PORT=8082
    export TTS_VOICE=en_US-ryan-high
    export TTS_VOICE_DIR="$ROOT/models/piper"
    export PIPER_BIN="$ROOT/piper/piper"
    export DYLD_LIBRARY_PATH="$ROOT/piper:${DYLD_LIBRARY_PATH:-}"
    cd "$ROOT/services/caal-tts"
    exec python -m uvicorn server:app --host 0.0.0.0 --port 8082 --log-level warning
    ;;
  agent)
    export LIVEKIT_URL="${LIVEKIT_URL:-ws://127.0.0.1:7880}"
    # Detect LAN IP so iOS clients receive a reachable WebSocket URL
    _LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
    export LIVEKIT_EXTERNAL_URL="${LIVEKIT_EXTERNAL_URL:-ws://${_LAN_IP}:7880}"
    export LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-devkey}"
    export LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-secret}"
    export SPEACHES_URL=http://127.0.0.1:8081
    export PIPER_URL=http://127.0.0.1:8082
    export KOKORO_URL=http://127.0.0.1:8880
    export TTS_PROVIDER=auto
    export TTS_MODEL=auto
    export WHISPER_MODEL=small.en
    export TIMEZONE="${TIMEZONE:-America/Chicago}"
    export TIMEZONE_DISPLAY="${TIMEZONE_DISPLAY:-Central Time}"
    export WEBHOOK_PORT=8891
    export CAAL_WORKER_PORT=8892
    export CAAL_SESSION_BRIEFING=true
    export CAAL_NETWORK_STATE_PATH="$ROOT/../caal-network-state.json"
    export CAAL_MEMORY_DIR="$ROOT/../memory"
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
