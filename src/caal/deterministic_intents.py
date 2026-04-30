"""Short-circuit intents shared by HTTP chat and LiveKit voice.

Avoids LLM/tool noise for simple operational questions (network, project list).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from . import network_state


def _normalize_intent_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return " ".join(cleaned.split())


def looks_like_network_status_request(text: str) -> bool:
    q = _normalize_intent_text(text)
    if not q:
        return False
    triggers = [
        "network",
        "connection status",
        "wifi",
        "wi-fi",
        "cellular",
        "internet",
        "connectivity",
        "online",
        "reported in",
        "my connection",
        "what's my connection",
        "what is my connection",
        "connection type",
        "type of connection",
    ]
    return any(t in q for t in triggers)


def network_status_summary() -> str:
    state = network_state.get()
    seconds_ago = int(max(0, datetime.now().timestamp() - state.received_at))
    if state.connection == "unknown":
        return "Connection status isn't available in telemetry yet."
    text = f"You're on {state.connection}."
    if seconds_ago > 180:
        text += (
            f" Last network update was about {seconds_ago} seconds ago, "
            "so this may be stale."
        )
    return text


def looks_like_time_request(text: str) -> bool:
    q = _normalize_intent_text(text)
    if not q:
        return False
    triggers = [
        "what time is it",
        "current time",
        "time is it",
        "what's the time",
        "whats the time",
        "tell me the time",
    ]
    return any(t in q for t in triggers)


def current_time_summary() -> str:
    timezone_id, timezone_display = _resolve_timezone()
    try:
        now = datetime.now(ZoneInfo(timezone_id))
    except Exception:
        now = datetime.now()
    # Portable 12-hour formatting (avoids %-I platform differences).
    hour = now.hour % 12 or 12
    return f"It's {hour}:{now.minute:02d} {now.strftime('%p')} {timezone_display}."


def _resolve_timezone() -> tuple[str, str]:
    timezone_id = (os.getenv("TIMEZONE") or "").strip()
    timezone_display = (os.getenv("TIMEZONE_DISPLAY") or "").strip()
    if timezone_id and timezone_display:
        return timezone_id, timezone_display

    settings_path = os.getenv("CAAL_SETTINGS_PATH")
    if not settings_path:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_path = os.path.abspath(
            os.path.join(script_dir, "..", "..", "..", "settings.json")
        )
    try:
        import json
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        tz_id = str(settings.get("timezone_id", "")).strip()
        tz_name = str(settings.get("timezone_display", "")).strip()
        if tz_id and tz_name:
            return tz_id, tz_name
    except Exception:
        pass

    local_tz = datetime.now().astimezone().tzinfo
    tz_id = getattr(local_tz, "key", None) or "America/Chicago"
    tz_name = "Central Time" if tz_id == "America/Chicago" else tz_id.replace("_", " ")
    return tz_id, tz_name


def looks_like_simple_greeting(text: str) -> bool:
    q = _normalize_intent_text(text)
    if not q:
        return False
    greetings = {
        "hello",
        "hello cael",
        "hi",
        "hi cael",
        "hey",
        "hey cael",
    }
    return q in greetings


def simple_greeting_response() -> str:
    return "Hey Charlie, I'm here."


def looks_like_model_request(text: str) -> bool:
    q = _normalize_intent_text(text)
    if not q:
        return False
    triggers = [
        "what model are you using",
        "which model are you using",
        "what llm are you using",
        "what provider are you using",
        "are you using gemini",
        "are you using ollama",
    ]
    return any(t in q for t in triggers)


def current_model_summary() -> str:
    provider = (os.getenv("LLM_PROVIDER", "ollama") or "ollama").strip().lower()
    ollama_model = (os.getenv("OLLAMA_MODEL", "gemma4") or "gemma4").strip()
    if provider == "ollama":
        return f"I'm using Ollama with {ollama_model} right now."
    return f"I'm currently using {provider} as the LLM provider."


def looks_like_project_list_request(text: str) -> bool:
    q = (text or "").strip().lower()
    if not q:
        return False
    triggers = [
        "what projects exist",
        "which projects exist",
        "list projects",
        "show projects",
        "projects in the vault",
        "projects do we have",
    ]
    return any(t in q for t in triggers)


async def try_projects_inventory_fallback(text: str) -> str | None:
    if not looks_like_project_list_request(text):
        return None
    base = (os.getenv("HELMSMAN_DB_URL") or "http://127.0.0.1:5682").rstrip("/")
    url = f"{base}/api/inventory?type=projects&format=json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        return "Project inventory is unavailable right now."

    rows = payload.get("rows") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    names: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("project") or row.get("id") or ""
        if isinstance(name, str):
            name = name.strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return "No projects were returned by the inventory source."
    sample = ", ".join(names[:8])
    more = max(0, len(names) - 8)
    text = f"I found {len(names)} projects. Examples: {sample}."
    if more:
        text += f" I can list {more} more."
    return text
