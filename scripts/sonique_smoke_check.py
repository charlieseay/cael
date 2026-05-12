#!/usr/bin/env python3
"""Sonique / CAAL sidecar smoke checks (< ~10 minutes including first-time HF voice pull).

Run with the sidecar up (SoniqueBar or manual launcher.sh for stt/tts/agent).

Environment (defaults match launcher.sh / embedded sidecar):
  PIPER_URL       default http://127.0.0.1:8082
  SPEACHES_URL    default http://127.0.0.1:8081  (caal-stt)
  WEBHOOK_BASE    default http://127.0.0.1:8891  (voice_agent webhooks + /api/chat)

Exit code 0 only if all executed checks pass.

Checklist (what this script proves):
  1) Readiness backoff — HTTP GET retries until TTS /health returns 200.
  2) Piper TTS — POST /v1/audio/speech returns WAV with RIFF header (audible reply path).
  3) STT service — GET /health on SPEACHES_URL reports model loaded (caal-stt).
  4) Chat LLM — POST /api/chat returns JSON with non-empty response (needs working provider).
  5) Voice bridge — POST /api/chat/voice returns audio/wav (LLM + Piper end-to-end).

Skip chat/voice with SONIQUE_SMOKE_SKIP_LLM=1 if Ollama/cloud LLM is not running.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _env(name: str, default: str) -> str:
    v = os.environ.get(name, "").strip()
    return v or default


def _http_json(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ct = (resp.headers.get("Content-Type") or "").lower()
            if "application/json" in ct:
                return resp.status, json.loads(body)
            return resp.status, body
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed  # type: ignore[return-value]


def _http_bytes(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 180.0,
) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp.read(), hdrs
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def wait_ready(
    label: str,
    url: str,
    *,
    max_wait_s: float = 120.0,
    initial_delay: float = 0.5,
    max_delay: float = 8.0,
) -> None:
    """Poll URL with exponential backoff until HTTP 200 or timeout."""
    deadline = time.monotonic() + max_wait_s
    delay = initial_delay
    attempt = 0
    last_err: str | None = None
    while time.monotonic() < deadline:
        attempt += 1
        try:
            code, _ = _http_json("GET", url, timeout=5.0)
            if code == 200:
                print(f"  [ok] {label} ready after {attempt} attempt(s)")
                return
            last_err = f"HTTP {code}"
        except OSError as e:
            last_err = str(e)
        time.sleep(delay)
        delay = min(max_delay, delay * 1.6 + 0.1 * attempt)
    raise SystemExit(f"FAIL: {label} not ready within {max_wait_s:.0f}s ({last_err})")


def main() -> None:
    piper = _env("PIPER_URL", "http://127.0.0.1:8082").rstrip("/")
    stt = _env("SPEACHES_URL", "http://127.0.0.1:8081").rstrip("/")
    hook = _env("WEBHOOK_BASE", "http://127.0.0.1:8891").rstrip("/")
    skip_llm = _env("SONIQUE_SMOKE_SKIP_LLM", "").lower() in ("1", "true", "yes")

    print("Sonique smoke — TTS/STT readiness + optional LLM/voice pipeline")
    print(f"  PIPER_URL={piper}  SPEACHES_URL={stt}  WEBHOOK_BASE={hook}")

    # 1) TTS readiness with backoff
    wait_ready("Piper (caal-tts)", f"{piper}/health")

    # 2) Audible-path surrogate: WAV from Piper (same surface as voice_agent / Siri voice)
    voice = _env("SONIQUE_SMOKE_VOICE", "speaches-ai/piper-en_US-ryan-high")
    payload = json.dumps(
        {
            "model": "piper",
            "input": "Cael online. Short test.",
            "voice": voice,
            "response_format": "wav",
        }
    ).encode("utf-8")
    code, wav, hdrs = _http_bytes(
        "POST",
        f"{piper}/v1/audio/speech",
        data=payload,
        headers={"Content-Type": "application/json"},
        timeout=300.0,
    )
    if code != 200:
        raise SystemExit(f"FAIL: Piper speech HTTP {code} body[:200]={wav[:200]!r}")
    if not wav.startswith(b"RIFF"):
        raise SystemExit(f"FAIL: Piper returned non-WAV ({wav[:16]!r})")
    print(f"  [ok] Piper speech: {len(wav)} bytes WAV (content-type={hdrs.get('content-type')})")

    # 3) STT (caal-stt) model loaded
    code, st = _http_json("GET", f"{stt}/health", timeout=10.0)
    if code != 200:
        raise SystemExit(f"FAIL: STT health HTTP {code}: {st}")
    if isinstance(st, dict) and st.get("ok") is not True:
        raise SystemExit(f"FAIL: STT model not loaded: {st}")
    print(f"  [ok] STT health: {st}")

    if skip_llm:
        print("  [--] Skipping /api/chat and /api/chat/voice (SONIQUE_SMOKE_SKIP_LLM set)")
        print("PASS (TTS + STT only)")
        return

    # 4) Text chat (LLM)
    chat_body = json.dumps(
        {"text": "Reply with exactly: smoke-ok", "session_id": "sonique-smoke"}
    ).encode("utf-8")
    code, chat = _http_json(
        "POST",
        f"{hook}/api/chat",
        data=chat_body,
        headers={"Content-Type": "application/json"},
        timeout=120.0,
    )
    if code != 200:
        raise SystemExit(
            f"FAIL: /api/chat HTTP {code} — {chat!r}\n"
            "Fix LLM (e.g. Ollama model pulled, settings.json llm_provider) or set "
            "SONIQUE_SMOKE_SKIP_LLM=1 for TTS-only checks."
        )
    if not isinstance(chat, dict) or not (chat.get("response") or "").strip():
        raise SystemExit(f"FAIL: empty chat response: {chat!r}")
    print(f"  [ok] /api/chat: {chat.get('response', '')[:120]!r}")

    # 5) Voice endpoint: LLM + Piper
    voice_body = json.dumps(
        {"text": "One word only: hello.", "session_id": "sonique-smoke-voice"}
    ).encode("utf-8")
    code, wav2, vhdrs = _http_bytes(
        "POST",
        f"{hook}/api/chat/voice",
        data=voice_body,
        headers={"Content-Type": "application/json"},
        timeout=180.0,
    )
    if code != 200:
        detail = wav2[:500].decode("utf-8", errors="replace")
        raise SystemExit(
            f"FAIL: /api/chat/voice HTTP {code} — {detail}\n"
            "If detail mentions TTS, Piper must be up; if LLM, fix provider."
        )
    if not wav2.startswith(b"RIFF"):
        raise SystemExit(f"FAIL: /api/chat/voice not WAV ({wav2[:24]!r})")
    print(f"  [ok] /api/chat/voice: {len(wav2)} bytes WAV")
    rt = vhdrs.get("x-response-text", "")
    if rt:
        print(f"       X-Response-Text: {rt[:200]!r}")

    print("PASS (TTS + STT + chat + voice)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
