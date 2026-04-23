"""Helmsman closed-loop tools.

Three direct tools that let Sonique dispatch work and capture ideas without
routing through the MCP proxy. Each one is a single HTTP call to a known,
stable endpoint on the Mac Mini:

  report_issue(title, description, issue_type)
      File a bug or feature request. Dispatches an investigation task to
      Helmsman's queue. Use after a tool call fails, when the user describes
      something broken, or when they request a new capability.

  dispatch_task(task, brief, project, owner, effort)
      Add concrete actionable work to the task queue. Use for "build X",
      "update Y", "investigate Z" type requests.

  capture_idea(title, description, tags)
      Append to the vault's ideas backlog. Use when the user says "we should
      build X someday" — anything that isn't yet concrete work.

Why these are direct tools (not routed through MCP hub):
  - They're Sonique's own operational plumbing, not generic capabilities.
  - They must keep working even if the MCP proxy is down.
  - Closed-loop recovery from tool errors depends on them.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from livekit.agents import function_tool

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


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "idea"


class HelmsmanTools:
    """Three closed-loop tools for bug reports, task dispatch, and idea capture."""

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
