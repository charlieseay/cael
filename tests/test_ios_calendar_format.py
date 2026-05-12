"""Regression tests for the calendar tool format bug.

Bug history: the LLM-reported "calendar tool: returns format error" was caused
by a chain of date-format mismatches between the Python backend, the Dart
bridge, and Swift's ``ISO8601DateFormatter`` on iOS. The Python side was
emitting date-only strings ("2026-04-28"); Dart re-emitted them as
"2026-04-28T00:00:00.000" (no timezone, fractional seconds); Swift's strict
ISO8601 parser rejected that and silently fell back to ``Date()``. A
single-day query (start == end) also collapsed to a zero-width predicate.

These tests pin the Python-side normalisation that fixes the chain.
"""

from __future__ import annotations

import datetime as dt
import re

from caal.integrations.ios_bridge_tools import iOSBridgeTools


# ── _normalize_calendar_range ─────────────────────────────────────────────


def test_normalize_calendar_range_accepts_date_only():
    start, end = iOSBridgeTools._normalize_calendar_range("2026-04-28", "2026-04-30")
    assert start == "2026-04-28"
    assert end == "2026-04-30"


def test_normalize_calendar_range_accepts_full_iso_datetime():
    # Previously raised ValueError because date.fromisoformat rejected the
    # full timestamp; we now take the leading date portion.
    start, end = iOSBridgeTools._normalize_calendar_range(
        "2026-04-28T00:00:00Z", "2026-04-28T23:59:59Z"
    )
    assert start == "2026-04-28"
    assert end == "2026-04-28"


def test_normalize_calendar_range_blanks_become_today():
    start, end = iOSBridgeTools._normalize_calendar_range("", "")
    today = dt.date.today().isoformat()
    assert start == today
    assert end == today


def test_normalize_calendar_range_inverted_collapses_to_start():
    start, end = iOSBridgeTools._normalize_calendar_range("2026-04-30", "2026-04-28")
    assert start == "2026-04-30"
    assert end == "2026-04-30"


# ── to_rfc3339_calendar_range ─────────────────────────────────────────────


_RFC3339_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_rfc3339_range_for_single_day_is_full_day_window():
    start, end = iOSBridgeTools.to_rfc3339_calendar_range("2026-04-28", "2026-04-28")
    # The exact strings matter — Swift's ISO8601DateFormatter rejects anything
    # without a timezone marker, so the trailing Z is load-bearing.
    assert start == "2026-04-28T00:00:00Z"
    assert end == "2026-04-28T23:59:59Z"
    assert _RFC3339_Z.match(start)
    assert _RFC3339_Z.match(end)


def test_rfc3339_range_for_multi_day():
    start, end = iOSBridgeTools.to_rfc3339_calendar_range("2026-04-28", "2026-04-30")
    assert start == "2026-04-28T00:00:00Z"
    assert end == "2026-04-30T23:59:59Z"


def test_rfc3339_range_handles_blanks_using_today():
    start, end = iOSBridgeTools.to_rfc3339_calendar_range("", "")
    today = dt.date.today().isoformat()
    assert start == f"{today}T00:00:00Z"
    assert end == f"{today}T23:59:59Z"


def test_rfc3339_range_emits_format_that_strict_iso_parsers_accept():
    """Sanity check: every RFC3339 string we emit must parse with Python's own
    strict ISO8601 parser. If this regresses, Swift's parser will reject it too.
    """
    start, end = iOSBridgeTools.to_rfc3339_calendar_range("2026-04-28", "2026-04-28")
    # Python 3.11+ accepts the trailing Z; replace to be explicit.
    dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    dt.datetime.fromisoformat(end.replace("Z", "+00:00"))


# ── _result_needs_calendar_fallback ───────────────────────────────────────


def test_fallback_triggers_for_known_ios_failure_modes():
    needs = iOSBridgeTools._result_needs_calendar_fallback
    assert needs('{"error": "iOS calendar query timed out — device may not be connected."}')
    assert needs('{"error": "Failed to request iOS calendar: ..."}')
    assert needs('{"error": "iOS calendar integration is not configured."}')


def test_fallback_skipped_for_successful_payload():
    needs = iOSBridgeTools._result_needs_calendar_fallback
    assert not needs('{"success": true, "message": "2 events today: ..."}')
    assert not needs('{"success": false, "message": "Calendar permission denied."}')
