"""MCP Hub tool — lazy tool discovery and invocation.

Instead of auto-registering every MCP tool at session start (which burns tokens
on schemas the user may never need), we expose two meta-tools:

  list_tools(search)        -- search across all connected MCP servers and
                               return matching tool names + descriptions
  call_tool(server, tool, arguments)
                            -- invoke a specific tool via the MCP proxy

Claude discovers what's available on demand, then calls only what it needs.
Net result: base context stays slim (2 schemas vs 40+), tools are always reachable.

The hub is tbxark/mcp-proxy running on the host (port 3700 by default). Each
child MCP server is exposed under /<server_name>/mcp using the streamable-http
transport.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx
from livekit.agents import function_tool

logger = logging.getLogger(__name__)

MCP_PROXY_URL = os.getenv("MCP_PROXY_URL", "http://host.docker.internal:3700")
_DISCOVERY_TIMEOUT = 6.0
_CALL_TIMEOUT = 30.0
_CACHE_TTL = 300.0  # 5 minutes

# Tool list cache: server_name -> (timestamp, [tool_dict, ...])
_tools_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

# Known servers. Keep this in sync with ~/.config/mcp-proxy/config.json mcpServers keys.
# This list is consulted by list_tools() to decide where to search.
KNOWN_SERVERS: list[str] = [
    "bench",       # USB / ESP32 hardware diagnostics
    "berth",       # database schema
    "lathe",       # file + document operations
    "mooring",     # git + repo operations
    "sounding",    # network diagnostics (Keel)
    "stem",        # Apple Music (Sound)
    "binnacle",    # macOS calendar + reminders
    "bearing",     # project navigation
    "homelab",     # homelab infrastructure control
    "stripe",      # Stripe payments (read-only)
    "ha",          # Home Assistant device control
    "vault",       # Obsidian vault read/write
    "github",      # GitHub repos, issues, PRs
    "cloudflare",  # Cloudflare DNS, zones, Workers
    "mem0",        # persistent semantic memory
    "contacts",    # macOS Contacts read
    "calendar",    # macOS Calendar + Reminders
    "miniflux",    # RSS feed reader (Miniflux)
    "portainer",   # Docker container management
    "grafana",     # Grafana dashboards + alerts
    "influxdb",    # InfluxDB metrics + write
    "umami",       # Umami web analytics
    "lightrag",    # vault semantic/graph RAG search
    "resend",      # transactional email via Resend
]


async def _fetch_server_tools(server: str) -> list[dict[str, Any]]:
    """Fetch the tool list for a single MCP server via the proxy. Honors cache."""
    now = time.monotonic()
    cached = _tools_cache.get(server)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    url = f"{MCP_PROXY_URL}/{server}/mcp"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = _parse_mcp_response(resp.text)
            tools = data.get("result", {}).get("tools", []) or []
    except Exception as e:
        logger.warning(f"MCP tools/list failed for {server}: {e}")
        return []

    _tools_cache[server] = (now, tools)
    return tools


def _parse_mcp_response(body: str) -> dict[str, Any]:
    """Parse an MCP proxy response (may be plain JSON or SSE `data: ...` frame)."""
    body = body.strip()
    if body.startswith("{"):
        return json.loads(body)
    # SSE framing: look for "data: {...}" line
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload and payload.startswith("{"):
                return json.loads(payload)
    return {}


def _match(text: str, terms: list[str]) -> bool:
    """All non-empty search terms must appear somewhere in text (AND match)."""
    text = text.lower()
    return all(t in text for t in terms if t)


class MCPHubTools:
    """Mixin that exposes lazy MCP tool discovery + invocation.

    Adds two tools: list_tools and call_tool. No other tool schemas are
    registered, so the per-turn context stays tiny even though 40+ MCP tools
    are reachable on demand.
    """

    @function_tool
    async def list_tools(self, search: str) -> str:
        """Search for available tools across connected MCP servers.

        Call this FIRST whenever the user asks to do something that might be
        handled by an installed tool (home automation, calendar, reminders,
        music, files, git, GitHub, databases, network checks, hardware, etc.).
        You will get back a list of matching tools with their server and
        description. Then call `call_tool` with the right one.

        Known servers: bench, berth, lathe, mooring, sounding, stem, binnacle,
        bearing, homelab, stripe, ha, vault, github, cloudflare, mem0,
        contacts, calendar, miniflux, portainer, grafana, influxdb, umami,
        lightrag, resend.

        Args:
            search: Space-separated keywords. Broader is fine — "lights" will
                    match "turn_on_light", "set_brightness", etc. Leave empty
                    to list the first few tools per server.

        Returns:
            Lines in the form "[server.tool_name] description", or a hint that
            nothing matched.
        """
        terms = [t.strip().lower() for t in (search or "").split() if t.strip()]
        logger.info(f"list_tools: {search!r} (terms={terms})")

        # Parallel fetch from every known server
        results = await asyncio.gather(
            *(_fetch_server_tools(s) for s in KNOWN_SERVERS),
            return_exceptions=True,
        )

        matches: list[tuple[str, str, str]] = []  # (server, name, desc)
        for server, tools in zip(KNOWN_SERVERS, results):
            if isinstance(tools, BaseException) or not tools:
                continue
            for t in tools:
                name = t.get("name", "")
                desc = (t.get("description") or "").strip().replace("\n", " ")
                haystack = f"{server} {name} {desc}"
                if terms and not _match(haystack, terms):
                    continue
                matches.append((server, name, desc))

        if not matches:
            return (
                f"No tools matched '{search}'. "
                f"Searched {', '.join(KNOWN_SERVERS)}. "
                f"Try a broader keyword."
            )

        # Cap the response so we don't blow context on a broad query
        cap = 20
        shown = matches[:cap]
        lines = [f"[{server}.{name}] {desc[:180]}" for server, name, desc in shown]
        trailer = ""
        if len(matches) > cap:
            trailer = f"\n... {len(matches) - cap} more. Narrow the search for a shorter list."
        return "\n".join(lines) + trailer

    @function_tool
    async def call_tool(
        self,
        server: str,
        tool: str,
        arguments: Any = None,
    ) -> str:
        """Invoke a specific MCP tool. You MUST call `list_tools` first to find
        the exact server and tool name — do not guess or reuse names from training.

        Args:
            server: Server name exactly as returned by list_tools (e.g. "ha", "binnacle").
            tool: Tool name exactly as returned by list_tools.
            arguments: JSON object of arguments. {} if none.

        Returns:
            The tool's response content, or an error pointing you back to list_tools.
        """
        # Claude sometimes passes arguments as a JSON string instead of an object.
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return (
                    "Tool error: arguments must be a JSON object, not a string. "
                    f"Got: {arguments[:120]!r}"
                )
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return f"Tool error: arguments must be a JSON object; got {type(arguments).__name__}."

        logger.info(f"call_tool: {server}.{tool}({arguments!r})")

        # Validate server and tool before hitting the network — catches hallucinated
        # names up front and steers Claude back to list_tools.
        if server not in KNOWN_SERVERS:
            return (
                f"Unknown server '{server}'. Valid servers: {', '.join(KNOWN_SERVERS)}. "
                f"Call list_tools() first to discover the right one."
            )
        tools = await _fetch_server_tools(server)
        known_names = {t.get("name") for t in tools}
        if tool not in known_names:
            # Show a short sample so Claude can self-correct
            sample = sorted(n for n in known_names if n)[:8]
            return (
                f"Server '{server}' has no tool '{tool}'. "
                f"Sample tools on {server}: {', '.join(sample) or '(none listed)'}. "
                f"Call list_tools() with a keyword to see the full match set."
            )

        url = f"{MCP_PROXY_URL}/{server}/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_CALL_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = _parse_mcp_response(resp.text)
        except httpx.HTTPStatusError as e:
            return f"Tool call failed ({e.response.status_code}). Check server and tool name."
        except Exception as e:
            logger.warning(f"call_tool failed: {e}")
            return f"Tool call failed: {e}"

        if "error" in data:
            err = data["error"]
            return f"Tool error: {err.get('message', err)}"

        result = data.get("result", {})
        content = result.get("content", [])
        if isinstance(content, list) and content:
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
            if parts:
                return "\n".join(parts).strip()
        return json.dumps(result) if result else "Tool returned no content."
