"""Global in-memory cache for client network state.

Phase 1: single-user, no session keying. The iOS client pushes state via
POST /api/network-state and the agent reads it through the check_network tool.

No auth on the ingest endpoint — it's internal-only, reachable from iOS on
the same LAN or over Tailscale. Auth lands in Phase 2 with multi-user support.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NetworkState:
    connection: str = "unknown"
    is_expensive: bool = False
    is_constrained: bool = False
    timestamp: str = ""
    received_at: float = field(default_factory=time.time)


# Single global instance — Phase 1, one user, no session keying.
_state = NetworkState()
_STATE_PATH = Path(os.getenv("CAAL_NETWORK_STATE_PATH", "/tmp/caal-network-state.json"))


def update(connection: str, is_expensive: bool, is_constrained: bool, timestamp: str) -> None:
    global _state
    _state = NetworkState(
        connection=connection,
        is_expensive=is_expensive,
        is_constrained=is_constrained,
        timestamp=timestamp,
        received_at=time.time(),
    )
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(
            json.dumps(
                {
                    "connection": _state.connection,
                    "is_expensive": _state.is_expensive,
                    "is_constrained": _state.is_constrained,
                    "timestamp": _state.timestamp,
                    "received_at": _state.received_at,
                }
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def get() -> NetworkState:
    """Return latest state; prefer on-disk file so LiveKit worker subprocesses
    stay in sync with the webhook process that receives POST /api/network-state.
    """
    global _state
    if _STATE_PATH.exists():
        try:
            raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
            _state = NetworkState(
                connection=raw.get("connection", "unknown"),
                is_expensive=bool(raw.get("is_expensive", False)),
                is_constrained=bool(raw.get("is_constrained", False)),
                timestamp=raw.get("timestamp", ""),
                received_at=float(raw.get("received_at", time.time())),
            )
        except Exception:
            pass
    return _state
