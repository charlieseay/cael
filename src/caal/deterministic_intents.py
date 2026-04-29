"""Short-circuit intents shared by HTTP chat and LiveKit voice.

Avoids LLM/tool noise for simple operational questions (network, project list).
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx

from . import network_state


def looks_like_network_status_request(text: str) -> bool:
    q = (text or "").strip().lower()
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
        return (
            "Connection status not available yet - the iOS client hasn't reported in."
        )
    text = f"You're on {state.connection}."
    if seconds_ago > 180:
        text += (
            f" Last network update was about {seconds_ago} seconds ago, "
            "so this may be stale."
        )
    return text


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
