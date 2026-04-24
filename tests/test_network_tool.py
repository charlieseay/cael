"""Unit tests for the check_network tool's pure logic.

The @function_tool decorated method is a thin wrapper around
build_network_response; these tests exercise the logic directly so they
don't need the livekit agent framework or the module-level state cache.
"""

from __future__ import annotations

from caal.integrations.network_tool import build_network_response
from caal.network_state import NetworkState


def _state(**overrides) -> NetworkState:
    """Helper: build a NetworkState with sensible defaults that tests can override."""
    defaults = {
        "connection": "wifi",
        "is_expensive": False,
        "is_constrained": False,
        "timestamp": "2026-04-24T15:00:00Z",
        "received_at": 1000.0,
    }
    defaults.update(overrides)
    return NetworkState(**defaults)


def test_unknown_state_returns_not_reported_yet_message():
    state = NetworkState()  # default = connection='unknown', received_at=now
    out = build_network_response(state, now=state.received_at + 5)

    assert out["connection_type"] == "unknown"
    assert out["is_expensive"] is False
    assert out["is_constrained"] is False
    assert "iOS client hasn't reported in" in out["voice_summary"]
    assert out["last_update_seconds_ago"] == 5


def test_wifi_healthy_voice_summary():
    state = _state(connection="wifi")
    out = build_network_response(state, now=1000.0)

    assert out["connection_type"] == "wifi"
    assert out["is_expensive"] is False
    assert out["is_constrained"] is False
    assert out["voice_summary"] == "You're on wifi."
    assert out["last_update_seconds_ago"] == 0


def test_cellular_expensive_appends_metered():
    state = _state(connection="cellular", is_expensive=True)
    out = build_network_response(state, now=1042.0)

    assert out["voice_summary"] == "You're on cellular, metered connection."
    assert out["is_expensive"] is True
    assert out["last_update_seconds_ago"] == 42


def test_wifi_constrained_appends_constrained_mode():
    state = _state(connection="wifi", is_constrained=True)
    out = build_network_response(state, now=1000.0)

    assert out["voice_summary"] == "You're on wifi, constrained mode."
    assert out["is_constrained"] is True


def test_both_flags_chain_in_voice_summary():
    state = _state(connection="cellular", is_expensive=True, is_constrained=True)
    out = build_network_response(state, now=1000.0)

    assert out["voice_summary"] == "You're on cellular, metered connection, constrained mode."


def test_seconds_ago_rounds_down_to_int():
    # received_at=1000.0, now=1005.8 → should report 5, not 5.8 or 6
    state = _state(received_at=1000.0)
    out = build_network_response(state, now=1005.8)

    assert out["last_update_seconds_ago"] == 5
    assert isinstance(out["last_update_seconds_ago"], int)


def test_seconds_ago_zero_when_clock_hasnt_advanced():
    state = _state(received_at=1000.0)
    out = build_network_response(state, now=1000.0)

    assert out["last_update_seconds_ago"] == 0


def test_response_shape_is_stable_across_states():
    # The LLM contract depends on these exact keys being present in every path.
    expected_keys = {
        "connection_type", "is_expensive", "is_constrained",
        "voice_summary", "last_update_seconds_ago",
    }
    for state in [NetworkState(), _state(connection="wifi"), _state(connection="cellular", is_expensive=True)]:
        out = build_network_response(state, now=state.received_at + 10)
        assert set(out.keys()) == expected_keys, f"mismatch for {state}"
