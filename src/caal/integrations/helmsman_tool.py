"""Helmsman closed-loop tools.

Direct tools that let Sonique dispatch work, query the queue, and capture
ideas without routing through the MCP proxy. Each one is a single HTTP call
to a known, stable endpoint on the Mac Mini:

  report_issue(title, description, issue_type)
      File a bug or feature request. Dispatches an investigation task to
      Helmsman's queue. Use after a tool call fails, when the user describes
      something broken, or when they request a new capability.

  dispatch_task(task, brief, project, owner, effort)
      Add concrete actionable work to the task queue. Use for "build X",
      "update Y", "investigate Z" type requests.

  update_task(task_num, task, brief, owner, project, effort)
      Modify fields on a task that is still in pending status. Prevents
      duplicate tasks when the user wants to clarify or expand scope.

  get_task_queue_status(status_filter, owner_filter, task_num)
      Query the queue for counts, breakdowns, and pending tasks — or look up
      a single task by number. Returns a voice_summary for spoken output.

  capture_idea(title, description, tags)
      Append to the vault's ideas backlog. Use when the user says "we should
      build X someday" — anything that isn't yet concrete work.

Why these are direct tools (not routed through MCP hub):
  - They're Sonique's own operational plumbing, not generic capabilities.
  - They must keep working even if the MCP proxy is down.
  - Closed-loop recovery from tool errors depends on them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from typing import Any, Optional

import httpx
from livekit.agents import function_tool

from .. import mac_actions

logger = logging.getLogger(__name__)

DISPATCH_URL = os.getenv("DISPATCH_URL", "http://host.docker.internal:5680/webhook/task-dispatch")
DISPATCH_SECRET = os.getenv("DISPATCH_SECRET", "")
HELMSMAN_DB_URL = os.getenv("HELMSMAN_DB_URL", "http://host.docker.internal:5682")
VAULT_PATH = Path(os.getenv("VAULT_PATH", "/vault"))
IDEAS_DIR = VAULT_PATH / "Ideas"

_HTTP_TIMEOUT = 10.0

# Owners the Helmsman dispatch queue will accept. These map to humans, AI
# operators, and specialized agents defined in the vault's Agents/ folder.
ACCEPTED_OWNERS: set[str] = {
    # Humans / primary operators
    "CLAUDE", "GEM", "CURSOR", "HELMSMAN", "C+C", "C+G", "CHARLIE",
    # Specialized agents
    "BOSUN",         # infrastructure health + investigations
    "B3CK",          # wiki / lessons / teachable moments
    "ASSAYER",       # lessons extraction, idea scoring (aka Casey)
    "QA",            # pre-deploy audits
    "SCRIBE",        # docs / vault notes
    "EDITOR",        # editorial pass
    "PROJECTMANAGER",
    "CODEREVIEW",
    "SECURITYAUDITOR",
    "RESEARCH",
    "TECHSPEC",
}

# Friendly aliases the LLM might use — normalize to ACCEPTED_OWNERS.
_OWNER_ALIASES: dict[str, str] = {
    "CASEY": "ASSAYER",
    "BECK": "B3CK",
    "HELMSMAN-TEAM": "HELMSMAN",
    "HELMSMAN_TEAM": "HELMSMAN",
    "PROJECT-MANAGER": "PROJECTMANAGER",
    "PROJECT_MANAGER": "PROJECTMANAGER",
    "CODE-REVIEW": "CODEREVIEW",
    "SECURITY-AUDITOR": "SECURITYAUDITOR",
    "TECH-SPEC": "TECHSPEC",
}


def _normalize_owner(raw: str | None) -> str:
    o = (raw or "CLAUDE").upper().strip()
    o = _OWNER_ALIASES.get(o, o)
    return o if o in ACCEPTED_OWNERS else "CLAUDE"


async def _dispatch(
    task: str,
    brief: str,
    owner: str,
    project: str,
    effort: str,
) -> tuple[bool, int | None, str]:
    """POST to the Helmsman dispatch webhook.

    Returns (ok, task_num, message). task_num is the integer the queue assigned,
    or None on failure. The message is short-form: a confirmation or a failure
    reason suitable to surface to the user.
    """
    if not DISPATCH_SECRET:
        return False, None, "Dispatch secret not configured; can't queue tasks."

    headers = {
        "Content-Type": "application/json",
        "X-Dispatch-Secret": DISPATCH_SECRET,
    }
    payload = {
        "task": task[:120],
        "owner": owner,
        "project": project,
        "effort": effort,
        "brief_text": brief,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(DISPATCH_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return False, None, f"Dispatch rejected ({e.response.status_code})."
    except Exception as e:
        return False, None, f"Dispatch failed: {e}"

    if not data.get("dispatched"):
        return False, None, f"Dispatch not accepted: {data}"

    task_num = data.get("task_num")

    # Push-trigger the dispatch watcher so work starts within ~1s instead of
    # waiting for the next 10s launchd poll. Fire two triggers staggered by
    # ~700ms: the first covers the fast path where n8n has already flushed the
    # task into task-state.json; the second catches the race where n8n's write
    # lands *after* the first trigger fired and that cycle saw nothing new.
    # Best-effort — the 10s launchd fallback covers us if both triggers fail.
    async def _fire():
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{HELMSMAN_DB_URL}/dispatch/trigger")
        except Exception:
            pass

    await _fire()
    # Schedule the second trigger in the background — don't block the return.
    async def _fire_delayed():
        await asyncio.sleep(0.7)
        await _fire()
    asyncio.create_task(_fire_delayed())

    return True, task_num if isinstance(task_num, int) else None, "Queued."


async def _patch_task(task_num: int, fields: dict[str, Any]) -> tuple[bool, str]:
    """PATCH a pending task's fields via the Helmsman DB REST service.

    Returns (ok, message). Only fields present in *fields* are updated;
    the service ignores keys it doesn't recognise. The DB service rejects
    patches to tasks that are no longer pending — that error is surfaced
    directly as the message.
    """
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.patch(
                f"{HELMSMAN_DB_URL}/tasks/{task_num}",
                json=fields,
            )
            resp.raise_for_status()
            return True, "Updated."
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = e.response.json().get("detail", "")
        except Exception:
            pass
        return False, body or f"Server rejected update ({e.response.status_code})."
    except Exception as e:
        return False, f"Update failed: {e}"


def build_task_update_fields(
    task: Optional[str] = None,
    brief: Optional[str] = None,
    owner: Optional[str] = None,
    project: Optional[str] = None,
    effort: Optional[str] = None,
) -> dict[str, Any]:
    """Build the PATCH payload for update_task, applying validation/normalization.

    Returns an empty dict when no fields were supplied (caller should reject).
    Separated from the tool method so it can be tested without httpx.
    """
    fields: dict[str, Any] = {}
    if task is not None:
        fields["task"] = task[:120]
    if brief is not None:
        fields["brief_text"] = brief
    if owner is not None:
        fields["owner"] = _normalize_owner(owner)
    if project is not None:
        fields["project"] = project
    if effort is not None:
        e = effort.upper().strip()
        fields["effort"] = e if e in ("S", "M", "L", "XL") else "M"
    return fields


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "idea"


# ── Pure helpers for queue status, separated so tests don't need httpx/livekit ──

def filter_tasks(
    rows: list[dict[str, Any]],
    status_filter: Optional[str] = None,
    owner_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Apply case-insensitive status / owner filters to a task list."""
    out = rows
    if status_filter:
        sf = status_filter.lower().strip()
        out = [r for r in out if (r.get("status") or "").lower() == sf]
    if owner_filter:
        of = owner_filter.upper().strip()
        out = [r for r in out if (r.get("owner") or "").upper() == of]
    return out


def build_single_task_response(task_num: int, row: dict[str, Any] | None) -> dict[str, Any]:
    """Compose the single-task response when the caller passes task_num."""
    if not row:
        return {"voice_summary": f"No task number {task_num} found."}
    brief = (row.get("brief_text") or "")[:200]
    return {
        "num": row.get("num"),
        "task": row.get("task", ""),
        "owner": row.get("owner", ""),
        "status": row.get("status", "unknown"),
        "project": row.get("project", ""),
        "effort": row.get("effort", ""),
        "brief_text": brief,
        "created_at": row.get("created_at", ""),
        "voice_summary": (
            f"Task {task_num} is {row.get('status', 'unknown')}, "
            f"owned by {row.get('owner', 'unknown')}. "
            f"{(row.get('task') or '')[:80]}"
        ),
    }


def build_queue_status_response(
    rows: list[dict[str, Any]],
    status_filter: Optional[str] = None,
    owner_filter: Optional[str] = None,
    pending_cap: int = 20,
) -> dict[str, Any]:
    """Compose the aggregated queue status response from a filtered task list."""
    filtered = filter_tasks(rows, status_filter, owner_filter)
    total = len(filtered)
    by_status: dict[str, int] = dict(Counter(
        (r.get("status") or "unknown").lower() for r in filtered
    ))
    by_owner: dict[str, int] = dict(Counter(
        (r.get("owner") or "unknown").upper() for r in filtered
    ))

    pending = [
        {
            "num": r.get("num"),
            "task": (r.get("task") or "")[:100],
            "owner": r.get("owner", ""),
            "project": r.get("project", ""),
            "effort": r.get("effort", ""),
        }
        for r in filtered
        if (r.get("status") or "").lower() == "pending"
    ][:pending_cap]

    status_parts = ", ".join(
        f"{count} {status}" for status, count in sorted(by_status.items())
    )
    summary = f"There are {total} tasks"
    if status_parts:
        summary += f": {status_parts}"
    summary += "."
    if pending:
        pending_owners = ", ".join(sorted({p["owner"] for p in pending if p["owner"]}))
        summary += f" Pending tasks are owned by {pending_owners}."

    return {
        "total": total,
        "by_status": by_status,
        "by_owner": by_owner,
        "pending_tasks": pending,
        "voice_summary": summary,
    }


class HelmsmanTools:
    """Closed-loop tools for bug reports, task dispatch, queue status, and idea capture."""

    @function_tool
    async def report_issue(
        self,
        title: str,
        description: str,
        issue_type: str = "bug",
    ) -> str:
        """File a bug report or feature request for the Sonique/CAAL/Helmsman stack.

        Use this WHENEVER:
        - A tool call you just made failed with an error (auto-capture the symptom)
        - The user describes something not working as expected
        - The user asks for a new capability or feature

        The ticket is queued for the engineering team — you do not need to fix it yourself.
        After filing, briefly confirm to the user that it's logged.

        Args:
            title: Short title (under 80 chars). Start with the subsystem, e.g. "calendar tool: returns format error".
            description: What happened, what the user was trying to do, any error text.
                         Include enough context that a new engineer could reproduce it.
            issue_type: "bug" for broken behavior, "feature" for a new capability request.

        Returns:
            Confirmation string or a short error if dispatch fails.
        """
        kind = issue_type.lower().strip() if issue_type else "bug"
        if kind not in ("bug", "feature"):
            kind = "bug"

        tag = "BUG" if kind == "bug" else "FEATURE"
        logger.info(f"report_issue ({tag}): {title!r}")

        brief = (
            f"Filed via Sonique voice.\n\n"
            f"Type: {kind}\n"
            f"Title: {title}\n\n"
            f"Description:\n{description}\n\n"
            f"Reported: {datetime.now(timezone.utc).isoformat()}"
        )
        ok, task_num, msg = await _dispatch(
            task=f"[{tag}] {title}",
            brief=brief,
            owner="CLAUDE",
            project="Sonique",
            effort="S",
        )
        if ok:
            ref = f" task #{task_num}" if task_num else ""
            return f"Logged as {kind}{ref}. Engineering has it."
        return f"Could not file the ticket — {msg}"

    @function_tool
    async def dispatch_task(
        self,
        task: str,
        brief: str,
        project: str = "General",
        owner: str = "CLAUDE",
        effort: str = "M",
    ) -> str:
        """Queue a concrete work item for the team or a specialized agent.

        Use when the user asks for concrete actionable work — "build X", "update Y",
        "investigate Z", "write the spec for W". Different from report_issue because
        report_issue is for bugs/features you hit during a conversation; dispatch_task
        is for proactive work the user is requesting.

        Pick the right owner based on what the work needs:
          CLAUDE           — general code / infra / most tasks (default)
          GEM              — research-heavy or web-grounded work
          CURSOR           — frontend / UI / refactor work
          HELMSMAN         — autonomous queue-runner
          BOSUN            — technical system health investigations (HA/n8n/Docker/network)
          B3CK             — wiki pages, lessons-learned, teachable moments
          ASSAYER (Casey)  — operational pattern extraction, idea scoring
          QA               — pre-deploy audit
          SCRIBE           — documentation / blog / vault notes
          EDITOR           — editorial pass on drafts
          CODEREVIEW       — diff review
          SECURITYAUDITOR  — security scan
          RESEARCH         — market / viability / competitive analysis
          TECHSPEC         — turn an idea into a formal spec

        Args:
            task: Short title (under 100 chars).
            brief: Full context — what to do, why, acceptance criteria, file paths if known.
            project: Project name (Sonique, CAAL, Helmsman, Hone, Enchapter, Bosun, etc.).
            owner: One of the owners listed above.
            effort: One of S, M, L, XL. Default M.

        Returns:
            "Task #N queued for OWNER." on success, or a short error. Remember the
            number — you can look the task up later with check_task.
        """
        o = _normalize_owner(owner)
        logger.info(f"dispatch_task: {task!r} → {o}/{project}")
        e = effort.upper().strip() if effort else "M"
        if e not in ("S", "M", "L", "XL"):
            e = "M"

        ok, task_num, msg = await _dispatch(
            task=task,
            brief=brief or task,
            owner=o,
            project=project or "General",
            effort=e,
        )
        if ok:
            ref = f"#{task_num} " if task_num else ""
            return f"Task {ref}queued for {o}."
        return f"Could not queue the task — {msg}"

    @function_tool
    async def update_task(
        self,
        task_num: int,
        task: Optional[str] = None,
        brief: Optional[str] = None,
        owner: Optional[str] = None,
        project: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> str:
        """Modify fields on a task that is still in pending status.

        Use instead of dispatch_task when the user wants to clarify, expand
        scope, or correct details on a task they just described — anything that
        would otherwise result in a duplicate. Only pass the fields you need to
        change; unset fields are left as-is.

        The DB service will reject this if the task is no longer pending (i.e.
        already picked up or shipped). In that case tell the user and offer to
        dispatch a follow-up task instead.

        Args:
            task_num: The integer task number returned by dispatch_task or report_issue.
            task: Replacement short title (under 100 chars). Omit to keep current.
            brief: Replacement full brief. Omit to keep current.
            owner: New owner. Must be one of the accepted owner values.
            project: New project name.
            effort: New effort size — S, M, L, or XL.

        Returns:
            "Task #N updated." on success, or an explanation of why it failed.
        """
        fields = build_task_update_fields(task, brief, owner, project, effort)

        if not fields:
            return "Nothing to update — provide at least one field to change."

        logger.info("update_task: #%d fields=%s", task_num, list(fields))
        ok, msg = await _patch_task(task_num, fields)
        if ok:
            return f"Task #{task_num} updated."
        return f"Could not update task #{task_num} — {msg}"

    @function_tool
    async def check_task(self, task_num: int) -> str:
        """Look up the current status of a task you previously dispatched.

        Use when the user asks "what happened with the task you filed?" or when you
        want to confirm an earlier dispatch moved forward. Works with the number
        returned from dispatch_task or report_issue.

        Args:
            task_num: The integer task number from a previous dispatch.

        Returns:
            A short status summary, or a message that the task isn't found.
        """
        logger.info(f"check_task: #{task_num}")
        # The REST service doesn't support filtering by num — it only filters
        # by status and owner. We fetch the full list (~150 rows, small) and
        # scan. Cheap and avoids depending on an endpoint that doesn't exist.
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(f"{HELMSMAN_DB_URL}/tasks")
                resp.raise_for_status()
                rows = resp.json()
        except Exception as e:
            logger.warning(f"check_task failed: {e}")
            return f"Couldn't reach the task database: {e}"

        t = next((r for r in rows if r.get("num") == task_num), None)
        if not t:
            return f"No task #{task_num} found."
        status = t.get("status", "unknown")
        owner = t.get("owner", "?")
        project = t.get("project", "?")
        title = (t.get("task") or "")[:80]
        started = t.get("agent_started_at")
        shipped = t.get("shipped_at")

        bits = [f"Task #{task_num}: {status}", f"owner {owner}", f"project {project}"]
        if started:
            bits.append(f"started {started[:16]}")
        if shipped:
            bits.append(f"shipped {shipped[:16]}")
        summary = ", ".join(bits)
        if title:
            summary += f". Title: {title}"
        return summary

    @function_tool
    async def get_task_queue_status(
        self,
        status_filter: Optional[str] = None,
        owner_filter: Optional[str] = None,
        task_num: Optional[int] = None,
    ) -> dict[str, Any]:
        """Get an overview of the task queue, or look up a single task by number.

        Use when the user asks about the queue without a specific task number:
        "what are we working on", "what's in the queue", "how many open tasks",
        "what does Charlie have pending", "status of task 42".

        Different from check_task: check_task returns a short one-liner for a
        known task number. This tool returns counts, breakdowns, and a
        voice_summary — better for broad questions.

        Args:
            status_filter: Optional status to filter by (e.g. "pending",
                "in_progress", "shipped", "qa_failed"). Case-insensitive.
            owner_filter: Optional owner to filter by (e.g. "CLAUDE", "CHARLIE").
                Case-insensitive.
            task_num: If set, return details for this single task instead of
                the aggregated view.

        Returns:
            A dict with voice_summary (speakable sentence) plus either single-task
            fields or aggregated counts and a pending_tasks list.
        """
        logger.info(
            "get_task_queue_status: status=%s owner=%s num=%s",
            status_filter, owner_filter, task_num,
        )
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(f"{HELMSMAN_DB_URL}/tasks")
                resp.raise_for_status()
                rows: list[dict[str, Any]] = resp.json()
        except Exception as e:
            logger.warning("get_task_queue_status failed: %s", e)
            return {"voice_summary": f"I couldn't reach the task database: {e}"}

        if task_num is not None:
            t = next((r for r in rows if r.get("num") == task_num), None)
            return build_single_task_response(task_num, t)

        return build_queue_status_response(rows, status_filter, owner_filter)

    @function_tool
    async def capture_idea(
        self,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> str:
        """Save an idea to the vault's Ideas/ backlog for later review.

        Use when the user mentions something they want to explore or build
        "someday" — anything that isn't a concrete action but is worth
        remembering. The idea is written to a dated markdown file in the vault.

        Args:
            title: Short title. Becomes the filename slug and H1 heading.
            description: The idea in the user's own words — what it is, why it
                         matters, anything they mentioned about shape or scope.
            tags: Optional tags (e.g. ["voice", "product"]).

        Returns:
            Confirmation string with the filename, or an error.
        """
        logger.info(f"capture_idea: {title!r}")
        try:
            IDEAS_DIR.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            slug = _slugify(title)
            path = IDEAS_DIR / f"{today}-{slug}.md"

            # Avoid overwriting if same slug lands twice in a day
            if path.exists():
                n = 2
                while (IDEAS_DIR / f"{today}-{slug}-{n}.md").exists():
                    n += 1
                path = IDEAS_DIR / f"{today}-{slug}-{n}.md"

            tag_list = tags or []
            if "idea" not in tag_list:
                tag_list = ["idea", *tag_list]
            tag_str = ", ".join(tag_list)

            body = (
                f"---\n"
                f"tags: [{tag_str}]\n"
                f"created: {today}\n"
                f"updated: {today}\n"
                f"status: pending\n"
                f"source: sonique-voice\n"
                f"---\n\n"
                f"# {title}\n\n"
                f"{description}\n"
            )
            path.write_text(body, encoding="utf-8")
            return f"Captured in Ideas/{path.name}."
        except Exception as e:
            logger.warning(f"capture_idea failed: {e}")
            return f"Could not save the idea: {e}"

    @function_tool
    async def dispatch_tasks_bulk(self, tasks_json: str) -> str:
        """Dispatch multiple tasks in a single call from a JSON array.

        Useful for bulk operations — e.g. "queue these 5 tasks" where the user
        provides a JSON array of task objects. Each object must have: task, brief,
        project, owner, effort. Dispatch them one by one and return a summary.

        Args:
            tasks_json: JSON string containing an array of task objects.
                        Each object: {"task": "...", "brief": "...", "project": "...",
                                      "owner": "...", "effort": "..."}

        Returns:
            Voice-friendly summary of how many tasks were queued and any failures.
        """
        logger.info("dispatch_tasks_bulk called")
        try:
            tasks = json.loads(tasks_json)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        if not isinstance(tasks, list):
            return "tasks_json must be a JSON array, not a single object."

        if not tasks:
            return "No tasks provided."

        queued = []
        failed = []

        for idx, task_obj in enumerate(tasks):
            try:
                task_title = task_obj.get("task", "")
                brief = task_obj.get("brief", "")
                project = task_obj.get("project", "General")
                owner = task_obj.get("owner", "CLAUDE")
                effort = task_obj.get("effort", "M")

                if not task_title:
                    failed.append(f"Task {idx+1}: missing 'task' field")
                    continue

                ok, task_num, msg = await _dispatch(
                    task=task_title,
                    brief=brief or task_title,
                    owner=_normalize_owner(owner),
                    project=project,
                    effort=effort.upper() if effort else "M",
                )
                if ok:
                    queued.append(task_num or idx + 1)
                else:
                    failed.append(f"Task {idx+1} ({task_title[:40]}): {msg}")
            except Exception as e:
                failed.append(f"Task {idx+1}: {e}")

        summary = f"Queued {len(queued)} task"
        if len(queued) != 1:
            summary += "s"
        summary += "."
        if failed:
            summary += f" {len(failed)} failed: {'; '.join(failed[:3])}"
            if len(failed) > 3:
                summary += f" and {len(failed) - 3} more."
        return summary

    @function_tool
    async def dispatch_task_conditional(
        self,
        trigger_task_num: int,
        task: str,
        brief: str,
        project: str = "General",
        owner: str = "CLAUDE",
        effort: str = "M",
    ) -> str:
        """Dispatch a task with a blocking dependency on another task.

        Use when a task should only execute after a prerequisite task ships.
        The new task's brief will include a note that it depends on the trigger task.

        Args:
            trigger_task_num: The task number that must ship before this one runs.
            task: Short title of the new task.
            brief: Full context for the new task.
            project: Project name (default "General").
            owner: Task owner (default "CLAUDE").
            effort: Effort size S/M/L/XL (default "M").

        Returns:
            Confirmation with the new task number, or an error.
        """
        logger.info(f"dispatch_task_conditional: depends on #{trigger_task_num}")
        enhanced_brief = (
            f"{brief}\n\n"
            f"NOTE: This task should only be actioned after task #{trigger_task_num} ships."
        )
        o = _normalize_owner(owner)
        e = effort.upper().strip() if effort else "M"
        if e not in ("S", "M", "L", "XL"):
            e = "M"

        ok, task_num, msg = await _dispatch(
            task=task,
            brief=enhanced_brief,
            owner=o,
            project=project or "General",
            effort=e,
        )
        if ok:
            ref = f"#{task_num} " if task_num else ""
            return f"Task {ref}queued for {o} (depends on #{trigger_task_num})."
        return f"Could not queue the task — {msg}"

    @function_tool
    async def edit_vault_note(self, vault_relative_path: str, new_content: str) -> str:
        """Write new content to a vault note, replacing the entire file.

        Vault root: /Users/charlieseay/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet/

        Args:
            vault_relative_path: Path relative to vault root (e.g. "Projects/MyProject/notes.md").
                                 Must not contain ".." or be an absolute path.
            new_content: The new file content.

        Returns:
            Success confirmation or error message.
        """
        logger.info(f"edit_vault_note: {vault_relative_path}")
        if ".." in vault_relative_path or vault_relative_path.startswith("/"):
            return "Path safety check failed: no absolute paths or '..' allowed."

        vault_root = Path(
            "/Users/charlieseay/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet"
        )
        full_path = vault_root / vault_relative_path

        # Ensure the final path is within vault_root (prevent symlink escapes)
        try:
            full_path.resolve().relative_to(vault_root.resolve())
        except ValueError:
            return "Path resolves outside vault root — operation rejected."

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(new_content, encoding="utf-8")
            return f"Wrote to {vault_relative_path}."
        except Exception as e:
            logger.warning(f"edit_vault_note failed: {e}")
            return f"Could not write to vault: {e}"

    @function_tool
    async def append_to_vault_note(self, vault_relative_path: str, content: str) -> str:
        """Append content to the end of a vault note.

        Same vault root and path safety rules as edit_vault_note.

        Args:
            vault_relative_path: Path relative to vault root.
            content: Text to append.

        Returns:
            Success confirmation or error message.
        """
        logger.info(f"append_to_vault_note: {vault_relative_path}")
        if ".." in vault_relative_path or vault_relative_path.startswith("/"):
            return "Path safety check failed: no absolute paths or '..' allowed."

        vault_root = Path(
            "/Users/charlieseay/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet"
        )
        full_path = vault_root / vault_relative_path

        # Ensure the final path is within vault_root
        try:
            full_path.resolve().relative_to(vault_root.resolve())
        except ValueError:
            return "Path resolves outside vault root — operation rejected."

        try:
            if full_path.exists():
                current = full_path.read_text(encoding="utf-8")
                full_path.write_text(current + content, encoding="utf-8")
            else:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
            return f"Appended to {vault_relative_path}."
        except Exception as e:
            logger.warning(f"append_to_vault_note failed: {e}")
            return f"Could not append to vault: {e}"

    async def _run_osascript(self, script: str, timeout: float = 10.0) -> tuple[int, str, str]:
        """Run AppleScript locally if possible, otherwise use mac_actions bridge."""
        osascript_path = shutil.which("osascript")
        if osascript_path:
            try:
                result = subprocess.run(
                    [osascript_path, "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                logger.info("osascript timed out; routing via mac_actions bridge")
            except (FileNotFoundError, OSError) as e:
                logger.info(f"osascript not available at runtime ({e}); routing via mac_actions bridge")
            except Exception as e:
                logger.warning(f"osascript error: {e}")
        else:
            logger.info("osascript not found in PATH; routing via mac_actions bridge")

        # Fallback to mac_actions bridge (via SoniqueBar)
        try:
            action_id = mac_actions.enqueue("run_applescript", {"script": script})
            # SoniqueBar polls every ~1-2s. Wait up to timeout + buffer.
            action = await mac_actions.wait_for_completion(action_id, timeout=timeout + 10.0)
            if action["status"] == "done":
                return 0, action.get("result", "") or "", ""
            else:
                return 1, "", action.get("error") or "Remote execution failed."
        except Exception as e:
            logger.warning(f"mac_actions bridge failure: {e}")
            return -1, "", f"Bridge failure: {e}"

    @function_tool
    async def create_calendar_event(
        self,
        title: str,
        start_datetime: str,
        end_datetime: str,
        notes: str = "",
    ) -> str:
        """Create an Apple Calendar event via osascript.

        Args:
            title: Event title.
            start_datetime: Start time in ISO8601 format (e.g. "2026-05-01T14:00:00").
            end_datetime: End time in ISO8601 format.
            notes: Optional event notes or description.

        Returns:
            Success or failure message.
        """
        logger.info(f"create_calendar_event: {title}")
        try:
            # Convert ISO8601 to a format osascript understands.
            # AppleScript expects "Friday, May 1, 2026 at 2:00:00 PM"
            start_dt = datetime.fromisoformat(start_datetime)
            end_dt = datetime.fromisoformat(end_datetime)
            start_str = start_dt.strftime("%A, %B %d, %Y at %I:%M:%S %p")
            end_str = end_dt.strftime("%A, %B %d, %Y at %I:%M:%S %p")
        except ValueError as e:
            return f"Invalid datetime format: {e}"

        # Build the AppleScript command
        applescript = f"""
tell application "Calendar"
    tell calendar "Calendar"
        make new event with properties {{summary:"{title}", start date:date "{start_str}", end date:date "{end_str}"}}
    end tell
end tell
"""
        if notes:
            applescript = f"""
tell application "Calendar"
    tell calendar "Calendar"
        set evt to make new event with properties {{summary:"{title}", start date:date "{start_str}", end date:date "{end_str}"}}
        set description of evt to "{notes}"
    end tell
end tell
"""

        try:
            return_code, stdout, stderr = await self._run_osascript(applescript, timeout=5)
            if return_code == 0:
                return f"Created event: {title}."
            else:
                return f"Calendar error: {stderr or 'Unknown error'}"
        except Exception as e:
            logger.warning(f"create_calendar_event failed: {e}")
            return f"Could not create calendar event: {e}"

    @function_tool
    async def get_calendar_events(self, days_ahead: int = 1) -> str:
        """List calendar events for the next N days via osascript.

        Args:
            days_ahead: Number of days to look ahead (default 1).

        Returns:
            Voice-readable summary of upcoming events.
        """
        logger.info(f"get_calendar_events: next {days_ahead} days")
        applescript = f"""
set eventList to ""
set now to current date
set endDate to (now + {days_ahead} * days)
tell application "Calendar"
    repeat with evt in events of calendar "Calendar" whose start date is greater than or equal to now and whose start date is less than or equal to endDate
        set summary to summary of evt
        set startTime to start date of evt
        set eventList to eventList & summary & " at " & (time string of startTime) & "; "
    end repeat
end tell
eventList
"""
        try:
            return_code, stdout, stderr = await self._run_osascript(applescript, timeout=5)
            if return_code == 0:
                events_text = stdout.strip()
                if events_text:
                    return f"Calendar events for the next {days_ahead} day(s): {events_text}"
                else:
                    return f"No calendar events in the next {days_ahead} day(s)."
            else:
                return f"Calendar error: {stderr or 'Unknown error'}"
        except Exception as e:
            logger.warning(f"get_calendar_events failed: {e}")
            return f"Could not fetch calendar events: {e}"

    @function_tool
    async def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email via Apple Mail using osascript.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body text.

        Returns:
            Success or failure message.
        """
        logger.info(f"send_email: to={to}, subject={subject[:50]}")
        applescript = f"""
tell application "Mail"
    set newMessage to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:true}}
    tell newMessage
        make new to recipient at end of to recipients with properties {{address:"{to}"}}
        send
    end tell
end tell
"""
        try:
            return_code, stdout, stderr = await self._run_osascript(applescript, timeout=5)
            if return_code == 0:
                return f"Email sent to {to}."
            else:
                return f"Mail error: {stderr or 'Unknown error'}"
        except Exception as e:
            logger.warning(f"send_email failed: {e}")
            return f"Could not send email: {e}"

    @function_tool
    async def send_slack_message(self, channel: str, message: str) -> str:
        """Send a message to a Slack channel via Slack API.

        Requires /Volumes/data/secrets/slack_bot_token to exist.

        Args:
            channel: Channel name (with or without #).
            message: Message text.

        Returns:
            Success confirmation or error message.
        """
        logger.info(f"send_slack_message: {channel}")
        token_path = Path("/Volumes/data/secrets/slack_bot_token")
        if not token_path.exists():
            return "Slack not configured — no bot token found at expected path."

        try:
            token = token_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"Could not read slack token: {e}")
            return f"Could not read Slack token: {e}"

        # Ensure channel starts with #
        if not channel.startswith("#"):
            channel = f"#{channel}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "channel": channel,
            "text": message,
        }

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    return f"Message sent to {channel}."
                else:
                    return f"Slack rejected the message: {data.get('error', 'Unknown error')}"
        except Exception as e:
            logger.warning(f"send_slack_message failed: {e}")
            return f"Could not send Slack message: {e}"

    @function_tool
    async def read_file_contents(self, path: str) -> str:
        """Read and return the contents of a file.

        Paths must be within ~/Projects/ or the vault root. Rejects absolute paths.

        Args:
            path: File path (relative or absolute within allowed roots).

        Returns:
            File contents or an error message.
        """
        logger.info(f"read_file_contents: {path}")
        file_path = Path(path)

        # Allow relative paths within ~/Projects or vault
        if not file_path.is_absolute():
            projects_root = Path.home() / "Projects"
            file_path = projects_root / path

        # Validate the resolved path is within allowed roots
        vault_root = Path(
            "/Users/charlieseay/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet"
        )
        projects_root = Path.home() / "Projects"

        try:
            resolved = file_path.resolve()
            resolved.relative_to(projects_root.resolve())
        except ValueError:
            try:
                resolved.relative_to(vault_root.resolve())
            except ValueError:
                return "File path must be within ~/Projects/ or the vault root."

        try:
            contents = file_path.read_text(encoding="utf-8")
            return contents
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as e:
            logger.warning(f"read_file_contents failed: {e}")
            return f"Could not read file: {e}"

    @function_tool
    async def list_directory_contents(self, path: str) -> str:
        """List files and directories in a directory.

        Paths must be within ~/Projects/ or the vault root.

        Args:
            path: Directory path (relative or absolute within allowed roots).

        Returns:
            Voice-readable list of directory contents or an error message.
        """
        logger.info(f"list_directory_contents: {path}")
        dir_path = Path(path)

        # Allow relative paths within ~/Projects
        if not dir_path.is_absolute():
            projects_root = Path.home() / "Projects"
            dir_path = projects_root / path

        # Validate the resolved path
        vault_root = Path(
            "/Users/charlieseay/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet"
        )
        projects_root = Path.home() / "Projects"

        try:
            resolved = dir_path.resolve()
            resolved.relative_to(projects_root.resolve())
        except ValueError:
            try:
                resolved.relative_to(vault_root.resolve())
            except ValueError:
                return "Directory path must be within ~/Projects/ or the vault root."

        try:
            items = sorted(dir_path.iterdir())
            if not items:
                return f"Directory is empty: {path}"
            file_list = ", ".join(item.name for item in items[:20])
            summary = f"Contents of {path}: {file_list}"
            if len(items) > 20:
                summary += f" and {len(items) - 20} more."
            return summary
        except FileNotFoundError:
            return f"Directory not found: {path}"
        except Exception as e:
            logger.warning(f"list_directory_contents failed: {e}")
            return f"Could not list directory: {e}"
