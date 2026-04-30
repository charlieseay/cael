"""Network connectivity tool.

Lets the agent answer questions about the user's current network state
(connection type, metered/constrained status). State is pushed by the iOS
client to POST /api/network-state and cached in caal.network_state.
"""

from __future__ import annotations

import logging
import time

from livekit.agents import function_tool

from .. import network_state
from ..network_state import NetworkState

logger = logging.getLogger(__name__)


def build_network_response(state: NetworkState, now: float) -> dict:
    """Pure function — compose the check_network response from a state + clock.

    Separated from the @function_tool wrapper so logic is testable without
    stubbing the livekit decorator or touching the module-level cache.
    """
    seconds_ago = int(now - state.received_at)

    if state.connection == "unknown":
        return {
            "connection_type": "unknown",
            "is_expensive": False,
            "is_constrained": False,
            "voice_summary": (
                "Connection status isn't available in telemetry yet."
            ),
            "last_update_seconds_ago": seconds_ago,
            "is_stale": seconds_ago > stale_threshold_seconds,
        }

    parts = [f"You're on {state.connection}"]
    if state.is_expensive:
        parts.append("metered connection")
    if state.is_constrained:
        parts.append("constrained mode")
    voice_summary = ", ".join(parts) + "."

    return {
        "connection_type": state.connection,
        "is_expensive": state.is_expensive,
        "is_constrained": state.is_constrained,
        "voice_summary": voice_summary,
        "last_update_seconds_ago": seconds_ago,
    }


class NetworkTools:
    """Mixin that exposes the check_network tool to the voice agent."""

    @function_tool
    async def check_network(self) -> dict:
        """Check the user's current network connection status.

        Returns connection type (wifi, cellular, wired, none, etc.), whether the
        connection is metered or constrained, a human-readable voice summary from
        the iOS client, and how recently the status was updated.

        Use when the user asks about their network, Wi-Fi, cellular signal,
        internet connection, or anything connectivity-related.

        Returns:
            Dict with connection_type, is_expensive, is_constrained,
            voice_summary, and last_update_seconds_ago.
        """
        return build_network_response(network_state.get(), time.time())
