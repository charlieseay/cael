"""Global in-memory cache for client network state.

Phase 1: single-user, no session keying. The iOS client pushes state via
POST /api/network-state and the agent reads it through the check_network tool.

No auth on the ingest endpoint — it's internal-only, reachable from iOS on
the same LAN or over Tailscale. Auth lands in Phase 2 with multi-user support.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class NetworkState:
    connection: str = "unknown"
    is_expensive: bool = False
    is_constrained: bool = False
    timestamp: str = ""
    received_at: float = field(default_factory=time.time)


# Single global instance — Phase 1, one user, no session keying.
_state = NetworkState()


def update(connection: str, is_expensive: bool, is_constrained: bool, timestamp: str) -> None:
    global _state
    _state = NetworkState(
        connection=connection,
        is_expensive=is_expensive,
        is_constrained=is_constrained,
        timestamp=timestamp,
        received_at=time.time(),
    )


def get() -> NetworkState:
    return _state
