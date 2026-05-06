"""session_briefing.py — generate a spoken brief when Cael connects.

Enabled by setting CAAL_SESSION_BRIEFING=true in the environment (or in
settings.json as "session_briefing_enabled": true).

Fetches from Helmsman task queue and Docker, formats a concise spoken brief.
Delivered via session.say() right after the audio channel opens.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_HELMSMAN_URL = "http://localhost:5682"
_TIMEOUT = 3.0


def is_enabled(settings: dict) -> bool:
    """Return True if session briefing is enabled via env or settings."""
    if os.environ.get("CAAL_SESSION_BRIEFING", "").lower() in ("1", "true", "yes"):
        return True
    return bool(settings.get("session_briefing_enabled", False))


async def _fetch_json(url: str) -> list | dict | None:
    """Fetch JSON from a URL with a short timeout."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.debug("session_briefing fetch %s failed: %s", url, e)
    return None


async def _get_claude_tasks() -> list[dict]:
    """Fetch CLAUDE-owned pending tasks from Helmsman."""
    data = await _fetch_json(f"{_HELMSMAN_URL}/tasks?status=pending&owner=CLAUDE")
    if isinstance(data, list):
        return data[:5]  # cap at 5
    return []


async def _get_docker_health() -> tuple[int, int]:
    """Return (total_running, unhealthy_count) from docker ps."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "--format", "{{.Status}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
        lines = [l.strip() for l in stdout.decode().splitlines() if l.strip()]
        total = len(lines)
        unhealthy = sum(1 for l in lines if "unhealthy" in l.lower() or "restarting" in l.lower())
        return total, unhealthy
    except Exception as e:
        logger.debug("docker ps failed: %s", e)
        return 0, 0


def _greeting_for_hour(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


async def build_brief(settings: dict) -> str:
    """Build a spoken session brief. Returns empty string if nothing to report."""
    tz_name = os.environ.get("TIMEZONE", "America/Chicago")
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.datetime.now(tz)
    except Exception:
        now = datetime.datetime.now()

    greeting = _greeting_for_hour(now.hour)
    agent_name = settings.get("agent_name", "Cael")

    # Fetch data concurrently
    tasks, (docker_total, docker_unhealthy) = await asyncio.gather(
        _get_claude_tasks(),
        _get_docker_health(),
    )

    parts: list[str] = [f"{greeting}, Charlie."]

    # Task summary
    if tasks:
        if len(tasks) == 1:
            parts.append(f"You have one task waiting for me: {tasks[0].get('task', '')[:80]}.")
        else:
            task_titles = [t.get("task", "")[:60] for t in tasks[:3]]
            bullet = "; ".join(task_titles)
            parts.append(
                f"You have {len(tasks)} tasks in my queue. "
                f"Top items: {bullet}."
            )
    else:
        parts.append("No tasks in my queue right now.")

    # Docker health
    if docker_total > 0:
        if docker_unhealthy == 0:
            parts.append(f"All {docker_total} containers are running healthy.")
        else:
            parts.append(
                f"{docker_total} containers running, "
                f"{docker_unhealthy} {'is' if docker_unhealthy == 1 else 'are'} unhealthy — "
                "worth a look."
            )

    parts.append("What are we working on?")
    return " ".join(parts)
