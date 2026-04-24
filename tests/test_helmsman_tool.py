"""Unit tests for get_task_queue_status' pure logic.

The @function_tool decorated method handles the httpx call and then delegates
to filter_tasks / build_single_task_response / build_queue_status_response.
These tests cover those helpers directly so we don't need a running REST
service or to stub the livekit decorator.
"""

from __future__ import annotations

from caal.integrations.helmsman_tool import (
    build_queue_status_response,
    build_single_task_response,
    filter_tasks,
)


def _row(num: int, status: str = "pending", owner: str = "CLAUDE", **kw) -> dict:
    base = {
        "num": num,
        "task": f"Task {num} title",
        "status": status,
        "owner": owner,
        "project": "Sonique",
        "effort": "M",
        "brief_text": f"Brief for {num}",
        "created_at": "2026-04-24",
    }
    base.update(kw)
    return base


# ── filter_tasks ──────────────────────────────────────────────────────────

def test_filter_tasks_status_is_case_insensitive():
    rows = [_row(1, status="Pending"), _row(2, status="SHIPPED"), _row(3, status="pending")]

    assert [r["num"] for r in filter_tasks(rows, status_filter="pending")] == [1, 3]
    assert [r["num"] for r in filter_tasks(rows, status_filter="PENDING")] == [1, 3]
    assert [r["num"] for r in filter_tasks(rows, status_filter="shipped")] == [2]


def test_filter_tasks_owner_is_case_insensitive():
    rows = [_row(1, owner="claude"), _row(2, owner="CURSOR"), _row(3, owner="Claude")]

    assert [r["num"] for r in filter_tasks(rows, owner_filter="claude")] == [1, 3]
    assert [r["num"] for r in filter_tasks(rows, owner_filter="CLAUDE")] == [1, 3]


def test_filter_tasks_both_filters_combine():
    rows = [
        _row(1, status="pending", owner="CLAUDE"),
        _row(2, status="shipped", owner="CLAUDE"),
        _row(3, status="pending", owner="CURSOR"),
    ]

    out = filter_tasks(rows, status_filter="pending", owner_filter="CLAUDE")
    assert [r["num"] for r in out] == [1]


def test_filter_tasks_handles_none_status_and_owner_fields():
    # Rows with missing / None fields must not blow up — REST can return either.
    rows = [_row(1), {"num": 2}, {"num": 3, "status": None, "owner": None}]

    # No filter → all rows pass through unchanged.
    assert len(filter_tasks(rows)) == 3
    # Status filter → only explicit "pending" matches; the missing/None ones are skipped.
    assert [r["num"] for r in filter_tasks(rows, status_filter="pending")] == [1]


def test_filter_tasks_no_filters_returns_input_unchanged():
    rows = [_row(1), _row(2)]
    assert filter_tasks(rows) == rows


# ── build_single_task_response ────────────────────────────────────────────

def test_single_task_found_returns_full_fields():
    row = _row(42, status="shipped", owner="CURSOR", project="Hone")
    out = build_single_task_response(42, row)

    assert out["num"] == 42
    assert out["status"] == "shipped"
    assert out["owner"] == "CURSOR"
    assert out["project"] == "Hone"
    assert "Task 42 is shipped" in out["voice_summary"]
    assert "owned by CURSOR" in out["voice_summary"]


def test_single_task_missing_returns_not_found_voice_summary():
    out = build_single_task_response(999, None)

    assert out == {"voice_summary": "No task number 999 found."}


def test_single_task_brief_text_truncated_to_200_chars():
    row = _row(1, brief_text="x" * 500)
    out = build_single_task_response(1, row)

    assert len(out["brief_text"]) == 200
    assert out["brief_text"] == "x" * 200


def test_single_task_truncates_task_title_in_voice_summary():
    row = _row(1)
    row["task"] = "A" * 200
    out = build_single_task_response(1, row)

    # The voice_summary embeds task[:80] — the full 200-char title must not appear.
    assert "A" * 200 not in out["voice_summary"]
    assert ("A" * 80) in out["voice_summary"]


# ── build_queue_status_response ───────────────────────────────────────────

def test_aggregated_counts_by_status_and_owner():
    rows = [
        _row(1, status="pending", owner="CLAUDE"),
        _row(2, status="pending", owner="CURSOR"),
        _row(3, status="shipped", owner="CLAUDE"),
    ]

    out = build_queue_status_response(rows)

    assert out["total"] == 3
    assert out["by_status"] == {"pending": 2, "shipped": 1}
    assert out["by_owner"] == {"CLAUDE": 2, "CURSOR": 1}


def test_pending_tasks_list_only_contains_pending_rows():
    rows = [
        _row(1, status="pending"),
        _row(2, status="shipped"),
        _row(3, status="pending"),
    ]

    out = build_queue_status_response(rows)

    pending_nums = [p["num"] for p in out["pending_tasks"]]
    assert pending_nums == [1, 3]


def test_pending_tasks_list_capped_at_20():
    # 25 pending rows — the cap must hold.
    rows = [_row(i, status="pending") for i in range(1, 26)]

    out = build_queue_status_response(rows)

    assert out["total"] == 25
    assert len(out["pending_tasks"]) == 20
    # Cap takes the first 20 (in input order, post-filter).
    assert [p["num"] for p in out["pending_tasks"]] == list(range(1, 21))


def test_pending_cap_is_configurable():
    rows = [_row(i, status="pending") for i in range(1, 10)]

    out = build_queue_status_response(rows, pending_cap=3)

    assert len(out["pending_tasks"]) == 3


def test_voice_summary_leads_with_total():
    rows = [_row(1, status="pending"), _row(2, status="shipped")]
    out = build_queue_status_response(rows)

    assert out["voice_summary"].startswith("There are 2 tasks")


def test_voice_summary_lists_pending_owners_when_pending_exists():
    rows = [
        _row(1, status="pending", owner="CLAUDE"),
        _row(2, status="pending", owner="CURSOR"),
        _row(3, status="shipped", owner="GEM"),
    ]
    out = build_queue_status_response(rows)

    assert "Pending tasks are owned by CLAUDE, CURSOR" in out["voice_summary"]
    # Shipped owners must not be mentioned in the pending-owners clause.
    assert "GEM" not in out["voice_summary"]


def test_voice_summary_skips_pending_clause_when_no_pending():
    rows = [_row(1, status="shipped"), _row(2, status="shipped")]
    out = build_queue_status_response(rows)

    assert "Pending tasks are owned by" not in out["voice_summary"]


def test_filter_applied_before_aggregation():
    rows = [
        _row(1, status="pending", owner="CLAUDE"),
        _row(2, status="pending", owner="CURSOR"),
        _row(3, status="shipped", owner="CLAUDE"),
    ]

    out = build_queue_status_response(rows, owner_filter="CLAUDE")

    assert out["total"] == 2  # only CLAUDE rows counted
    assert out["by_owner"] == {"CLAUDE": 2}
    assert "CURSOR" not in out["voice_summary"]


def test_empty_input_returns_zero_totals_and_clean_summary():
    out = build_queue_status_response([])

    assert out["total"] == 0
    assert out["by_status"] == {}
    assert out["by_owner"] == {}
    assert out["pending_tasks"] == []
    assert out["voice_summary"] == "There are 0 tasks."
