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

import time
import uuid
from typing import Any


# Single in-memory queue — single-user, single-Mac design.
_queue: list[dict[str, Any]] = []


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
            return True
    return False


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
