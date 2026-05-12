#!/usr/bin/env bash
# Sonique / CAAL embedded sidecar smoke checks (< ~10 min including first-time Piper HF download).
# Usage:
#   export CAAL_HOST=http://LAN_IP:8891   # webhook + chat API (SoniqueBar sidecar)
#   export STT_URL=http://LAN_IP:8081
#   export TTS_URL=http://LAN_IP:8082
#   ./scripts/sonique_smoke_check.sh
set -euo pipefail

CAAL_HOST="${CAAL_HOST:-http://127.0.0.1:8891}"
STT_URL="${STT_URL:-http://127.0.0.1:8081}"
TTS_URL="${TTS_URL:-http://127.0.0.1:8082}"

retry_curl() {
  local label="$1" max="${2:-16}" delay="${3:-0.75}"
  shift 3
  local i=1
  while (( i <= max )); do
    if "$@"; then
      return 0
    fi
    echo "[$label] attempt $i/$max failed; sleeping ${delay}s"
    sleep "$delay"
    delay=$(awk -v d="$delay" 'BEGIN { printf "%.2f", (d * 2 > 8) ? 8 : d * 2 }')
    i=$((i + 1))
  done
  return 1
}

echo "== 1) Cold-sidecar readiness: STT /health (model may take 60–120s first boot) =="
retry_curl stt-health 24 1 curl -fsS --max-time 8 "${STT_URL}/health" | tee /tmp/caal-stt-health.json
python3 - <<'PY'
import json, sys
d=json.load(open("/tmp/caal-stt-health.json"))
assert d.get("ok") is True, d
PY

echo "== 2) Piper /health (process up; first synthesis may still download voice) =="
curl -fsS --max-time 8 "${TTS_URL}/health" | tee /tmp/caal-tts-health.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/caal-tts-health.json"))
assert d.get("ok") is True, d
PY

echo "== 3) Webhook API /health =="
curl -fsS --max-time 8 "${CAAL_HOST}/health"

echo "== 4) LiveKit token mint (same path as iOS) =="
curl -fsS --max-time 15 -X POST "${CAAL_HOST}/api/connection-details" \
  -H "Content-Type: application/json" \
  -d '{}' | tee /tmp/caal-conn.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/caal-conn.json"))
assert d.get("participantToken"), d
assert d.get("serverUrl", "").startswith("ws"), d
PY

echo "== 5) Piper speech (trigger-sized utterance → WAV; allow long timeout on first voice download) =="
curl -fsS --max-time 180 -X POST "${TTS_URL}/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d '{"model":"piper","input":"Ready.","voice":"speaches-ai/piper-en_US-ryan-high","response_format":"wav"}' \
  | tee /tmp/caal-tts-smoke.wav >/dev/null
python3 - <<'PY'
p=open("/tmp/caal-tts-smoke.wav","rb").read(12)
assert p[:4]==b"RIFF", p
PY

echo "== 6) Chat path (LLM + same pipeline as voice text) — simple greeting =="
curl -fsS --max-time 120 -X POST "${CAAL_HOST}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello","session_id":"smoke-cli"}' | tee /tmp/caal-chat-smoke.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/caal-chat-smoke.json"))
text=(d.get("response") or "").strip().lower()
assert len(text) > 0, d
PY

echo ""
echo "OK — all automated probes passed."
echo "Manual (device): open Sonique → confirm server URL → Talk to CAAL."
echo "  Expect: connect, then session briefing or reply audio (wake word optional)."
