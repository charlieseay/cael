"""ambient_monitor.py — background monitoring loop for the voice agent.

Watches Docker container health and Helmsman task staleness, then queues
alerts for delivery to the iOS app via the LiveKit data channel.

Alerts are NOT spoken mid-session — they accumulate and are either:
  - Delivered via data channel push to iOS (for notification display), or
  - Included in the next session briefing.

The monitor runs as a background asyncio task started at session open and
cancelled at session close.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

_DOCKER_POLL_INTERVAL = 120   # seconds between Docker health checks
_HELMSMAN_POLL_INTERVAL = 300 # seconds between Helmsman task staleness checks
_TASK_STALE_HOURS = 48        # hours before a task is considered stuck


@dataclass
class Alert:
    kind: str             # "container_unhealthy", "container_stopped", "task_stale"
    title: str
    body: str
    priority: str = "normal"  # "low", "normal", "high"
    seen_at: float = field(default_factory=time.time)


class AmbientMonitor:
    """Runs lightweight health checks in the background and queues alerts.

    Usage:
        monitor = AmbientMonitor(publish_data_fn=ctx.room.local_participant.publish_data)
        task = asyncio.create_task(monitor.run())
        ...
        task.cancel()
    """

    def __init__(self, publish_data_fn: Callable | None = None) -> None:
        self._publish = publish_data_fn
        self._pending_alerts: list[Alert] = []
        self._known_unhealthy: set[str] = set()
        self._known_stopped: set[str] = set()

    async def run(self) -> None:
        """Main loop — runs until cancelled."""
        logger.info("ambient_monitor: started")
        docker_task = asyncio.create_task(self._docker_loop())
        helmsman_task = asyncio.create_task(self._helmsman_loop())
        try:
            await asyncio.gather(docker_task, helmsman_task)
        except asyncio.CancelledError:
            docker_task.cancel()
            helmsman_task.cancel()
            logger.info("ambient_monitor: stopped")

    # ── Docker health ─────────────────────────────────────────────────────────

    async def _docker_loop(self) -> None:
        while True:
            try:
                await self._check_docker()
            except Exception as e:
                logger.debug("ambient_monitor docker check error: %s", e)
            await asyncio.sleep(_DOCKER_POLL_INTERVAL)

    async def _check_docker(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a",
            "--format", "{{.Names}}\t{{.Status}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        lines = stdout.decode().splitlines()

        current_unhealthy: set[str] = set()
        current_stopped: set[str] = set()

        for line in lines:
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            name, status = parts[0].strip(), parts[1].strip().lower()

            if "unhealthy" in status or "restarting" in status:
                current_unhealthy.add(name)
            if status.startswith("exited") or "dead" in status:
                current_stopped.add(name)

        # New unhealthy containers
        newly_unhealthy = current_unhealthy - self._known_unhealthy
        for name in newly_unhealthy:
            self._queue_alert(Alert(
                kind="container_unhealthy",
                title="Container Unhealthy",
                body=f"{name} is reporting unhealthy. Check logs with: docker logs {name}",
                priority="high",
            ))
        self._known_unhealthy = current_unhealthy

        # Containers that stopped unexpectedly (not in known stopped set)
        newly_stopped = current_stopped - self._known_stopped
        # Suppress common stopped containers (one-off runs, etc.)
        newly_stopped = {n for n in newly_stopped if not n.startswith("tmp-")}
        for name in newly_stopped:
            if name not in self._known_unhealthy:
                self._queue_alert(Alert(
                    kind="container_stopped",
                    title="Container Stopped",
                    body=f"{name} has exited unexpectedly.",
                    priority="normal",
                ))
        self._known_stopped = current_stopped

    # ── Helmsman staleness ────────────────────────────────────────────────────

    async def _helmsman_loop(self) -> None:
        # Initial delay so Docker gets its first pass first
        await asyncio.sleep(30)
        while True:
            try:
                await self._check_stale_tasks()
            except Exception as e:
                logger.debug("ambient_monitor helmsman check error: %s", e)
            await asyncio.sleep(_HELMSMAN_POLL_INTERVAL)

    async def _check_stale_tasks(self) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get("http://localhost:5682/tasks?status=pending")
                if r.status_code != 200:
                    return
                tasks = r.json()
        except Exception:
            return

        stale_threshold = time.time() - (_TASK_STALE_HOURS * 3600)
        stale = [
            t for t in tasks
            if isinstance(t.get("created_at"), (int, float))
            and t["created_at"] < stale_threshold
        ]

        if stale:
            owners = {}
            for t in stale:
                owner = t.get("owner", "?")
                owners[owner] = owners.get(owner, 0) + 1
            summary = ", ".join(f"{c} for {o}" for o, c in owners.items())
            self._queue_alert(Alert(
                kind="task_stale",
                title="Stale Tasks",
                body=f"{len(stale)} tasks stuck over {_TASK_STALE_HOURS}h: {summary}",
                priority="low",
            ))

    # ── Alert delivery ────────────────────────────────────────────────────────

    def _queue_alert(self, alert: Alert) -> None:
        self._pending_alerts.append(alert)
        logger.info(
            "ambient_monitor: alert [%s] %s — %s",
            alert.priority, alert.title, alert.body[:80],
        )
        asyncio.create_task(self._push_alert(alert))

    async def _push_alert(self, alert: Alert) -> None:
        """Push alert to iOS via LiveKit data channel if a publish function is set."""
        if self._publish is None:
            return
        payload = json.dumps({
            "type": "alert",
            "title": alert.title,
            "body": alert.body,
            "priority": alert.priority,
            "kind": alert.kind,
        })
        try:
            result = self._publish(
                payload.encode("utf-8"),
                reliable=True,
                topic="ambient_alert",
            )
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.debug("ambient_monitor push failed: %s", e)

    def drain_alerts(self) -> list[Alert]:
        """Return and clear all pending alerts (for session briefing injection)."""
        alerts = list(self._pending_alerts)
        self._pending_alerts.clear()
        return alerts
