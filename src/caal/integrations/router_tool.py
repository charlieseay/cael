"""Quarterdeck router tools for SoniqueBar/CAAL.

Provides deterministic wrappers for Quarterdeck's routing APIs so the model can:
- request a routing recommendation for a task
- inspect weekly routing metrics
- run the `/router memory` command bridge
- explain routing decisions for a task

HTTP contract (base URL = ``settings.quarterdeck_router_url``, env ``QUARTERDECK_ROUTER_URL``,
or ``http://localhost:5681``):

- ``POST {base}/route`` — JSON body ``task_description`` (required), optional
  ``task_type_hint`` (mapped from tool ``context``), plus ``explain`` / ``source`` for
  explanations. Quarterdeck responds with fields such as ``recommended_model``,
  ``routing_class``, ``confidence``.
- ``GET {base}/route/metrics`` — weekly routing statistics JSON.
- Router KB / "memory" — ``GET {base}/route/memory`` first; if that returns 404/405,
  ``POST {base}/router`` with ``{"command": "memory", "query": "<optional>"}``; if that
  also 404/405, ``GET {base}/router/memory`` with optional ``query`` param.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from livekit.agents import function_tool

from .. import settings as settings_module

logger = logging.getLogger(__name__)

_DEFAULT_ROUTER_URL = "http://localhost:5681"
_ROUTER_TIMEOUT_S = 8.0


ROUTE_TASK_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "route_task",
        "description": (
            "Get Quarterdeck routing recommendations for a task via /route. "
            "Use when deciding which model/agent/path should handle the task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task text; sent to Quarterdeck as task_description.",
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional routing hint; sent to Quarterdeck as task_type_hint."
                    ),
                },
            },
            "required": ["task"],
        },
    },
}

ROUTE_METRICS_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "route_metrics",
        "description": "Fetch weekly Quarterdeck router metrics from /route/metrics.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

ROUTER_MEMORY_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "router_memory",
        "description": (
            "Inspect Quarterdeck router KB memory: tries GET /route/memory, then "
            "POST /router (command bridge), then GET /router/memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Optional memory query/filter. Empty means full memory check."
                    ),
                }
            },
            "required": [],
        },
    },
}

EXPLAIN_ROUTE_DECISION_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "explain_route_decision",
        "description": (
            "Explain why Quarterdeck would route a SoniqueBar task a certain way. "
            "Uses /route with explanation hints and falls back to local summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task text; sent as task_description to /route.",
                }
            },
            "required": ["task"],
        },
    },
}


def _router_base_url() -> str:
    settings = settings_module.load_settings()
    return (
        settings.get("quarterdeck_router_url")
        or os.getenv("QUARTERDECK_ROUTER_URL")
        or _DEFAULT_ROUTER_URL
    ).rstrip("/")


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value)
    except Exception:
        return str(value)


def _json_from_response(resp: httpx.Response) -> Any:
    return resp.json() if resp.content else {"ok": True}


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
) -> Any:
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return _json_from_response(resp)


async def _route_post(payload: dict[str, Any]) -> Any:
    base = _router_base_url()
    async with httpx.AsyncClient(timeout=_ROUTER_TIMEOUT_S) as client:
        return await _post_json(client, f"{base}/route", payload)


async def _route_get(path_suffix: str) -> Any:
    base = _router_base_url()
    async with httpx.AsyncClient(timeout=_ROUTER_TIMEOUT_S) as client:
        resp = await client.get(f"{base}{path_suffix}")
        resp.raise_for_status()
        return _json_from_response(resp)


async def execute_route_task(task: str, context: str = "") -> str:
    if not task.strip():
        return "Task is required."

    payload: dict[str, Any] = {"task_description": task.strip()}
    if context.strip():
        payload["task_type_hint"] = context.strip()

    try:
        data = await _route_post(payload)
        return _safe_json(data)
    except Exception as e:
        logger.warning("route_task failed: %s", e)
        return f"Quarterdeck route request failed: {e}"


async def execute_route_metrics() -> str:
    try:
        data = await _route_get("/route/metrics")
        return _safe_json(data)
    except Exception as e:
        logger.warning("route_metrics failed: %s", e)
        return f"Quarterdeck route metrics request failed: {e}"


async def execute_router_memory(query: str = "") -> str:
    base = _router_base_url()
    q = query.strip()
    params = {"query": q} if q else None
    try:
        async with httpx.AsyncClient(timeout=_ROUTER_TIMEOUT_S) as client:
            r = await client.get(f"{base}/route/memory", params=params)
            if r.status_code not in (404, 405):
                r.raise_for_status()
                return _safe_json(_json_from_response(r))

            payload: dict[str, Any] = {"command": "memory"}
            if q:
                payload["query"] = q
            try:
                data = await _post_json(client, f"{base}/router", payload)
                return _safe_json(data)
            except httpx.HTTPStatusError as err:
                if err.response.status_code not in (404, 405):
                    raise

            r2 = await client.get(f"{base}/router/memory", params=params)
            r2.raise_for_status()
            return _safe_json(_json_from_response(r2))
    except Exception as e:
        logger.warning("router_memory failed: %s", e)
        return f"Quarterdeck router memory check failed: {e}"


async def execute_explain_route_decision(task: str) -> str:
    if not task.strip():
        return "Task is required."

    payload = {
        "task_description": task.strip(),
        "explain": True,
        "source": "soniquebar",
    }

    try:
        data = await _route_post(payload)
    except Exception as e:
        logger.warning("explain_route_decision failed: %s", e)
        return f"Quarterdeck route explanation failed: {e}"

    if isinstance(data, dict):
        if any(k in data for k in ("explanation", "reason", "rationale", "why")):
            return _safe_json(data)
        recommendation = (
            data.get("recommended_model")
            or data.get("recommendation")
            or data.get("route")
            or "unknown"
        )
        confidence = data.get("confidence")
        explanation = (
            f"Quarterdeck recommended '{recommendation}'"
            + (f" with confidence {confidence}." if confidence is not None else ".")
            + " Full payload: "
            + _safe_json(data)
        )
        return explanation

    return _safe_json(data)


class RouterTools:
    """LiveKit mixin exposing Quarterdeck router wrappers."""

    @function_tool
    async def route_task(self, task: str, context: str = "") -> str:
        """Query Quarterdeck /route for task routing recommendations."""
        return await execute_route_task(task=task, context=context)

    @function_tool
    async def route_metrics(self) -> str:
        """View weekly Quarterdeck router metrics from /route/metrics."""
        return await execute_route_metrics()

    @function_tool
    async def router_memory(self, query: str = "") -> str:
        """Check Quarterdeck KB memory via `/router memory`."""
        return await execute_router_memory(query=query)

    @function_tool
    async def explain_route_decision(self, task: str) -> str:
        """Explain Quarterdeck routing decisions for SoniqueBar tasks."""
        return await execute_explain_route_decision(task=task)
