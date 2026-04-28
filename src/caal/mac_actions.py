"""Mac action queue for SoniqueBar's local system control feature.

The CAAL voice/chat agent queues actions here via mac_action().
SoniqueBar polls GET /api/mac-actions/pending, executes them via
NSWorkspace + NSAppleScript, and posts completion back to
POST /api/mac-actions/{id}/complete.

Supported action types:
    open_url        params: {"url": "https://..."}
    open_app        params: {"app": "Notes"}  (app name or bundle ID)
    run_applescript params: {"script": "tell application ..."}
    key_press       params: {"keys": "cmd+space"}  (via AppleScript keystroke)
    shell_command   params: {"command": "ls -la"}  (via AppleScript do shell script)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any


# Single in-memory queue — single-user, single-Mac design.
_queue: list[dict[str, Any]] = []
_events: dict[str, asyncio.Event] = {}


def enqueue(action_type: str, params: dict[str, Any], source: str = "voice") -> str:
    """Add an action to the queue. Returns the action ID."""
    action_id = str(uuid.uuid4())[:8]
    _queue.append(
        {
            "id": action_id,
            "action_type": action_type,
            "params": params,
            "source": source,
            "status": "pending",
            "queued_at": time.time(),
        }
    )
    _events[action_id] = asyncio.Event()
    _evict_old()
    return action_id


def get_pending() -> list[dict[str, Any]]:
    """Return all pending actions (snapshot copy)."""
    return [dict(a) for a in _queue if a["status"] == "pending"]


def complete(
    action_id: str,
    result: str | None = None,
    error: str | None = None,
) -> bool:
    """Mark an action complete or errored. Returns False if not found."""
    for action in _queue:
        if action["id"] == action_id:
            action["status"] = "error" if error else "done"
            action["result"] = result
            action["error"] = error
            action["completed_at"] = time.time()
            if action_id in _events:
                _events[action_id].set()
            return True
    return False


async def wait_for_completion(action_id: str, timeout: float = 10.0) -> dict[str, Any]:
    """Wait for an action to be completed by SoniqueBar.

    Returns the action dict (including result/error) or raises TimeoutError.
    """
    if action_id not in _events:
        # Check if it's already done
        for a in _queue:
            if a["id"] == action_id and a["status"] in ("done", "error"):
                return a
        raise ValueError(f"No event tracker for action {action_id}")

    event = _events[action_id]
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    finally:
        _events.pop(action_id, None)

    for a in _queue:
        if a["id"] == action_id:
            return a
    raise ValueError(f"Action {action_id} disappeared from queue")


def _evict_old() -> None:
    """Remove completed/errored actions older than 60 seconds."""
    cutoff = time.time() - 60
    to_remove = [
        a
        for a in _queue
        if a["status"] in ("done", "error")
        and a.get("completed_at", time.time()) < cutoff
    ]
    for a in to_remove:
        _queue.remove(a)
