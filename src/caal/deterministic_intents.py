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
    timezone_id = os.getenv("TIMEZONE", "America/Los_Angeles")
    timezone_display = os.getenv("TIMEZONE_DISPLAY", "Pacific Time")
    try:
        now = datetime.now(ZoneInfo(timezone_id))
    except Exception:
        now = datetime.now()
    # Portable 12-hour formatting (avoids %-I platform differences).
    hour = now.hour % 12 or 12
    return f"It's {hour}:{now.minute:02d} {now.strftime('%p')} {timezone_display}."


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
    except httpx.ConnectError as e:
        import logging
        logging.getLogger(__name__).warning(f"Connection error fetching project inventory: {e}")
        return "Project inventory is unavailable right now due to a connection error."
    except httpx.TimeoutException as e:
        import logging
        logging.getLogger(__name__).warning(f"Timeout fetching project inventory: {e}")
        return "Project inventory is unavailable right now due to a timeout."
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Unexpected error fetching project inventory: {e}")
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
