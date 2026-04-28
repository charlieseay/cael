"""Generic context classes for non-LiveKit callers of llm_node().

These provide duck-typed stand-ins for LiveKit's ChatContext and Agent,
enabling llm_node() to be called from the Chat API, ESP32 satellites,
or any other non-LiveKit entry point.

The key insight: llm_node() is fully duck-typed. It checks
type(item).__name__ == "ChatMessage" and reads agent._* attributes
via hasattr(). No actual LiveKit types are required.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

# Seconds of inactivity before a direct MCP server connection is closed and
# re-opened on the next call. Keeps the connection pool lean between sessions
# and ensures stale connections don't silently fail.
_SERVER_IDLE_TTL = 300.0  # 5 minutes

from .integrations import (
    EXPLAIN_ROUTE_DECISION_TOOL_DEF,
    MEMORY_SHORT_TOOL_DEF,
    ROUTER_MEMORY_TOOL_DEF,
    ROUTE_METRICS_TOOL_DEF,
    ROUTE_TASK_TOOL_DEF,
    WEB_SEARCH_TOOL_DEF,
    create_hass_tools,
    detect_hass_tool_prefix,
    discover_n8n_workflows,
    execute_explain_route_decision,
    execute_memory_short,
    execute_route_metrics,
    execute_route_task,
    execute_router_memory,
    execute_web_search,
    initialize_mcp_servers,
)
from .integrations.mcp_loader import MCPServerConfig

if TYPE_CHECKING:
    from .llm.providers import LLMProvider
    from .memory import ShortTermMemory

logger = logging.getLogger(__name__)


class ChatMessage:
    """Minimal chat message matching llm_node's duck-typing contract.

    llm_node's _build_messages_from_context checks:
        type(item).__name__ == "ChatMessage"  (llm_node.py:311)
        item.role                              (llm_node.py:312)
        item.text_content                      (llm_node.py:312)
    """

    def __init__(self, role: str, text: str) -> None:
        self.role = role
        self._text = text

    @property
    def text_content(self) -> str:
        return self._text


class ChatContext:
    """Minimal chat context matching llm_node's duck-typing contract.

    llm_node's _build_messages_from_context iterates chat_ctx.items
    (llm_node.py:308).
    """

    def __init__(
        self, system_prompt: str, messages: list[dict] | None = None
    ) -> None:
        self.items: list[ChatMessage] = [ChatMessage(role="system", text=system_prompt)]
        if messages:
            for msg in messages:
                self.items.append(
                    ChatMessage(role=msg["role"], text=msg["content"])
                )


class ToolContext:
    """Duck-typed agent providing all attributes llm_node reads.

    _discover_tools() reads:
        agent._llm_tools_cache, agent._tools, agent._caal_mcp_servers,
        agent._n8n_workflow_tools, agent._hass_tool_definitions,
        agent._agent_tool_definitions

    _execute_single_tool() reads:
        agent._hass_tool_callables, agent._n8n_workflow_name_map,
        agent._n8n_base_url, agent._caal_mcp_servers
        + hasattr(agent, tool_name) for agent methods (memory_short, web_search)

    MCP connections are lazily initialized on first async use to avoid
    the "cancel scope in different task" issue when initializing sync.
    """

    def __init__(
        self,
        *,
        mcp_configs: list[MCPServerConfig] | None = None,
        on_tool_status: Callable | None = None,
        short_term_memory: ShortTermMemory | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self._tools: list = []  # No @function_tool methods
        self._mcp_configs = mcp_configs or []
        self._caal_mcp_servers: dict = {}
        self._server_last_used: dict[str, float] = {}  # server_name -> last call timestamp
        self._n8n_workflow_tools: list[dict] = []
        self._n8n_workflow_name_map: dict[str, str] = {}
        self._n8n_base_url: str | None = None
        self._hass_tool_definitions: list[dict] = []
        self._hass_tool_callables: dict = {}
        self._on_tool_status = on_tool_status
        self._on_usage = None
        self._llm_tools_cache: list[dict] | None = None
        self._llm_tools_cache_time: float = 0.0
        self._mcp_initialized = False

        # Agent-level tools (memory_short, web_search)
        self._short_term_memory = short_term_memory
        self._provider = provider
        self._agent_tool_definitions: list[dict] = [
            MEMORY_SHORT_TOOL_DEF,
            WEB_SEARCH_TOOL_DEF,
            ROUTE_TASK_TOOL_DEF,
            ROUTE_METRICS_TOOL_DEF,
            ROUTER_MEMORY_TOOL_DEF,
            EXPLAIN_ROUTE_DECISION_TOOL_DEF,
        ]

    async def ensure_mcp_initialized(self) -> None:
        """Lazily initialize MCP servers, n8n workflows, and HASS tools."""
        if self._mcp_initialized:
            return

        if not self._mcp_configs:
            self._mcp_initialized = True
            return

        try:
            servers, errors = await initialize_mcp_servers(self._mcp_configs)
            self._caal_mcp_servers = servers

            if errors:
                for err in errors:
                    logger.warning(f"MCP '{err.name}' failed: {err.error}")

            # Discover n8n workflows
            n8n_mcp = servers.get("n8n")
            if n8n_mcp:
                n8n_config = next(
                    (c for c in self._mcp_configs if c.name == "n8n"), None
                )
                if n8n_config:
                    # URL format: http://HOST:PORT/mcp-server/http → http://HOST:PORT
                    url_parts = n8n_config.url.rsplit("/", 2)
                    self._n8n_base_url = (
                        url_parts[0] if len(url_parts) >= 2 else n8n_config.url
                    )

                    workflows, name_map = await discover_n8n_workflows(
                        n8n_mcp, self._n8n_base_url
                    )
                    self._n8n_workflow_tools = workflows
                    self._n8n_workflow_name_map = name_map
                    logger.info(f"Discovered {len(workflows)} n8n workflows")

            # Create HASS tools
            hass_server = servers.get("home_assistant")
            if hass_server:
                prefix = await detect_hass_tool_prefix(hass_server)
                if prefix:
                    logger.info(f"Home Assistant MCP uses '{prefix}' prefix")
                self._hass_tool_definitions, self._hass_tool_callables = (
                    create_hass_tools(hass_server, tool_prefix=prefix)
                )
                logger.info("HASS tools ready: hass")

            # Clear tool cache so _discover_tools rebuilds with new MCP tools
            self._llm_tools_cache = None

            logger.info(f"MCP initialized ({len(servers)} servers)")

        except Exception as e:
            logger.error(f"MCP lazy init error: {e}", exc_info=True)

        self._mcp_initialized = True

    async def ensure_server_live(self, server_name: str):
        """Return a live server connection, reconnecting if idle too long.

        Called by _execute_single_tool before making any MCP server call so
        stale connections are refreshed transparently rather than failing.
        """
        from .integrations.mcp_loader import _init_single_mcp

        server = self._caal_mcp_servers.get(server_name)
        last_used = self._server_last_used.get(server_name, 0.0)
        idle_s = time.time() - last_used

        if server is not None and idle_s < _SERVER_IDLE_TTL:
            return server

        # Server is stale or not yet initialized — find its config and (re)init
        config = next((c for c in self._mcp_configs if c.name == server_name), None)
        if config is None:
            return server  # Not in our config — return whatever we have

        if server is not None:
            logger.info(
                f"MCP '{server_name}' idle {idle_s:.0f}s > {_SERVER_IDLE_TTL:.0f}s — reconnecting"
            )

        _, new_server, error = await _init_single_mcp(config)
        if new_server:
            self._caal_mcp_servers[server_name] = new_server
            self._server_last_used[server_name] = time.time()
            # Bust tool cache so the reconnected server's tools are re-discovered
            self._llm_tools_cache = None
            logger.info(f"MCP '{server_name}' reconnected")
            return new_server

        if error:
            logger.error(f"MCP '{server_name}' reconnect failed: {error.error}")
        return server  # Return stale connection as last resort

    def touch_server(self, server_name: str) -> None:
        """Update last-used timestamp after a successful tool call."""
        self._server_last_used[server_name] = time.time()

    # -----------------------------------------------------------------
    # Agent-level tools (called via _execute_single_tool hasattr path)
    # -----------------------------------------------------------------

    async def memory_short(
        self,
        action: str,
        key: str = "",
        value: str = "",
        ttl: str = "",
    ) -> str:
        """Delegate to shared execute_memory_short()."""
        return await execute_memory_short(
            memory=self._short_term_memory,
            action=action,
            key=key,
            value=value,
            ttl=ttl,
        )

    async def web_search(self, query: str) -> str:
        """Delegate to shared execute_web_search()."""
        return await execute_web_search(
            query=query,
            provider=self._provider,
        )

    async def route_task(self, task: str, context: str = "") -> str:
        """Delegate to shared execute_route_task()."""
        return await execute_route_task(task=task, context=context)

    async def route_metrics(self) -> str:
        """Delegate to shared execute_route_metrics()."""
        return await execute_route_metrics()

    async def router_memory(self, query: str = "") -> str:
        """Delegate to shared execute_router_memory()."""
        return await execute_router_memory(query=query)

    async def explain_route_decision(self, task: str) -> str:
        """Delegate to shared execute_explain_route_decision()."""
        return await execute_explain_route_decision(task=task)
