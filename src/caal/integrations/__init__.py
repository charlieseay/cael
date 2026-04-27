"""
MCP integrations for voice assistant.
"""

from .hass import create_hass_tools, detect_hass_tool_prefix
from .hass_rest import create_hass_rest_tools
from .helmsman_tool import HelmsmanTools
from .ios_bridge_tools import iOSBridgeTools
from .lightrag_tool import LightRAGTools
from .mac_control_tool import MacControlTools
from .mcp_hub_tool import MCPHubTools
from .mcp_loader import MCPServerConfig, initialize_mcp_servers, load_mcp_config, prepare_lazy_mcp_servers
from .network_tool import NetworkTools
from .memory_tool import (
    MEMORY_SHORT_TOOL_DEF,
    MemoryTools,
    execute_memory_short,
)
from .n8n import discover_n8n_workflows, execute_n8n_workflow
from .web_search import WEB_SEARCH_TOOL_DEF, WebSearchTools, execute_web_search

__all__ = [
    "create_hass_rest_tools",
    "create_hass_tools",
    "detect_hass_tool_prefix",
    "discover_n8n_workflows",
    "execute_memory_short",
    "execute_n8n_workflow",
    "execute_web_search",
    "HelmsmanTools",
    "initialize_mcp_servers",
    "prepare_lazy_mcp_servers",
    "iOSBridgeTools",
    "LightRAGTools",
    "load_mcp_config",
    "MacControlTools",
    "MCPHubTools",
    "MCPServerConfig",
    "NetworkTools",
    "MEMORY_SHORT_TOOL_DEF",
    "MemoryTools",
    "WEB_SEARCH_TOOL_DEF",
    "WebSearchTools",
]
