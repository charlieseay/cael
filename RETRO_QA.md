# RETRO QA — Security & Code Quality Audit

**Date:** 2026-05-06  
**Scope:** ~/Projects/cael/ Python source files (excluding venv/, node_modules/)  
**Auditor:** Claude Code

---

## Summary

**Total Findings:** 12  
**Critical:** 1 | **High:** 5 | **Medium:** 6

Audit covers security (hardcoded secrets, unvalidated input to LLM/services, missing auth), efficiency (max_tokens, prompt caching, blocking calls in async), and code quality. Existing file included 12 findings; this audit confirms and validates all but refines severity/recommendations based on current code state.

---

## CRITICAL

### C-1: API key written to `os.environ` at runtime
- **File:** `voice_agent.py:498`
- **Issue:** Groq API key injected into process environment during runtime configuration:
  ```python
  if runtime.get("groq_api_key"):
      os.environ["GROQ_API_KEY"] = runtime["groq_api_key"]
  ```
  Writing secrets to `os.environ` exposes them to all child processes, threading contexts, and stack traces.
- **Fix:** Pass the key directly to the provider constructor via dependency injection. Never write secrets to `os.environ` at runtime.

---

### C-2: All webhook endpoints unauthenticated
- **File:** `src/caal/webhooks.py:69`, `173–1158`
- **Issue:** CORS is `allow_origins=["*"]` and every route (`/announce`, `/reload-tools`, `/settings`, `/prompt`, `/wake`, etc.) has no auth check. Any host on the network can invoke them.
- **Fix:**
  1. Set `allow_origins` to specific frontend origin(s).
  2. Add shared-secret or JWT validation on every sensitive endpoint.
  3. At minimum, bind the listener to `127.0.0.1` if this is a local-only service.

---

## HIGH

### H-1: No input validation on `ChatRequest.text`
- **File:** `src/caal/chat/api.py:65`
- **Issue:** `text: str` accepts unlimited length with no sanitization before it reaches the LLM. Opens the door to prompt injection and memory exhaustion.
- **Fix:**
  ```python
  text: str = Field(..., min_length=1, max_length=10000)
  session_id: str | None = Field(None, max_length=256, pattern="^[a-zA-Z0-9_-]+$")
  ```

---

### H-2: TTS service URLs not validated before use
- **File:** `src/caal/tts/synthesizer.py:61,79,97`
- **Issue:** `KOKORO_URL`, `SPEACHES_URL`, and `PIPER_URL` are read from env and used directly in `httpx` calls with user text as the body. A tampered env var redirects audio payloads to an attacker-controlled host.
- **Fix:**
  ```python
  def _validate_service_url(url: str) -> str:
      parsed = urllib.parse.urlparse(url)
      if parsed.scheme not in ("http", "https") or not parsed.netloc:
          raise ValueError(f"Invalid service URL: {url}")
      return url
  ```
  Call this once at startup for each TTS URL constant.

---

### H-3: `HA_URL` and `HA_TOKEN` used without protocol validation
- **File:** `voice_agent.py:900–901`, `src/caal/integrations/hass_rest.py:124–146`
- **Issue:** Home Assistant URL is read from env without checking protocol. A `file://` or `gopher://` value would route requests to unintended destinations. Token is sent as a Bearer header with no TLS enforcement.
- **Fix:** Validate `HA_URL` scheme is `https` (or `http` for localhost only). Log a warning and skip HA tool creation if the URL is invalid; never pass a bad URL through.

---

### H-4: n8n webhook path not validated — path traversal risk
- **File:** `src/caal/integrations/n8n.py:138`
- **Issue:** `webhook_path` from workflow metadata is interpolated directly:
  ```python
  webhook_url = f"{base_url.rstrip('/')}/webhook/{webhook_path}"
  ```
  A malicious workflow definition with `../../admin` or `//attacker.com` as the path bypasses the base URL.
- **Fix:**
  ```python
  import re
  if not re.fullmatch(r"[a-zA-Z0-9_\-]+", webhook_path):
      raise ValueError(f"Unsafe webhook path: {webhook_path!r}")
  ```

---

## MEDIUM

### M-1: No prompt caching on system prompt (Anthropic provider)
- **File:** `src/caal/llm/providers/anthropic_provider.py:138`
- **Issue:** System prompt is sent as a plain string on every request. Anthropic supports `cache_control: ephemeral` on system messages, yielding ~90% cost reduction on repeated turns with the same prompt.
- **Fix:**
  ```python
  if system:
      req["system"] = [
          {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
      ]
  ```

---

### M-2: Blocking `requests.get()` inside async context
- **File:** `voice_agent.py:167` (also `preload_models` blocks at ~1268–1342)
- **Issue:** `_is_kokoro_healthy()` uses synchronous `requests.get()` and is called from an `async` entrypoint. This stalls the event loop for up to `timeout_s` seconds on every health check.
- **Fix:**
  ```python
  async def _is_kokoro_healthy(timeout_s: float = 1.5) -> bool:
      try:
          async with httpx.AsyncClient() as client:
              r = await client.get(health_url, timeout=timeout_s)
              return r.status_code == 200
      except Exception:
          return False
  ```

---

### M-3: LLM call without `max_tokens` in web search summarizer
- **File:** `src/caal/integrations/web_search.py:121`
- **Issue:** `provider.chat(messages=messages)` is called with no per-call `max_tokens`. Provider-level defaults cap this (1024 for Anthropic, 4096 for Groq/OpenAI), but OllamaProvider has no explicit limit and falls back to model default.
- **Fix:** Pass `max_tokens=500` for summarization; it's a short output task and doesn't need the provider ceiling.

---

### M-4: TTS endpoint URL built redundantly across the file
- **File:** `voice_agent.py:166,332,336,700,710,1332,1336`
- **Issue:** `KOKORO_URL.rstrip("/") + "/v1"` and similar patterns appear at least six times. One inconsistency and health checks will point to a different host than inference calls.
- **Fix:** Define URL constants once at module level (or in a small dataclass) and reference them everywhere:
  ```python
  _KOKORO_SPEECH_URL = f"{KOKORO_URL.rstrip('/')}/v1/audio/speech"
  _KOKORO_HEALTH_URL = f"{KOKORO_URL.rstrip('/')}/health"
  _PIPER_SPEECH_URL  = f"{PIPER_URL.rstrip('/')}/v1/audio/speech"
  ```

---

## LOW

### L-1: Per-session `ToolDataCache` allocation
- **File:** `src/caal/chat/session.py:48`
- **Issue:** Every `ChatSession` creates its own `ToolDataCache(max_entries=3)`, including short-lived ephemeral sessions. Minor memory overhead in multi-session workloads.
- **Fix:** Use `max_entries=1` for non-persistent sessions, or share a single cache at the manager level.

---

### L-2: Round-trip JSON serialization in n8n workflow discovery
- **File:** `src/caal/integrations/n8n.py:84,184,292`
- **Issue:** Schema text is parsed to a Python object, serialized back to JSON string, then parsed again at call time. Three passes for data that could be held as a dict.
- **Fix:** Store the parsed dict and serialize once at the point of use.

---

## No Findings

- **Hardcoded secrets:** None found. All credentials flow through environment variables or runtime config.
- **`max_tokens` coverage:** All direct Anthropic/Groq/OpenAI provider calls set `max_tokens` at the provider level. Only the `web_search` summarizer path (M-3) lacks a per-call override.

---

## Summary

| ID  | File | Line(s) | Severity |
|-----|------|---------|----------|
| C-1 | voice_agent.py | 498 | CRITICAL |
| C-2 | webhooks.py | 69, 173–1158 | CRITICAL |
| H-1 | chat/api.py | 65 | HIGH |
| H-2 | tts/synthesizer.py | 61, 79, 97 | HIGH |
| H-3 | voice_agent.py / hass_rest.py | 900–901, 124–146 | HIGH |
| H-4 | integrations/n8n.py | 138 | HIGH |
| M-1 | llm/providers/anthropic_provider.py | 138 | MEDIUM |
| M-2 | voice_agent.py | 167, ~1268–1342 | MEDIUM |
| M-3 | integrations/web_search.py | 121 | MEDIUM |
| M-4 | voice_agent.py | 166, 332, 336, 700, 710 | MEDIUM |
| L-1 | chat/session.py | 48 | LOW |
| L-2 | integrations/n8n.py | 84, 184, 292 | LOW |
