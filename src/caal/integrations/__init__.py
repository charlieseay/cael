"""
MCP integrations for voice assistant.
"""

from .hass import create_hass_tools, detect_hass_tool_prefix
from .hass_rest import create_hass_rest_tools
from .helmsman_tool import HelmsmanTools
from .ios_bridge_tools import iOSBridgeTools
from .lightrag_tool import LightRAGTools
from .mac_control_tool import MacControlTools
from .mcp_hub_tool import (
    MCPHubTools,
    LIST_TOOLS_TOOL_DEF,
    CALL_TOOL_TOOL_DEF,
    execute_list_tools,
    execute_call_tool,
)
from .mcp_loader import MCPServerConfig, initialize_mcp_servers, load_mcp_config, prepare_lazy_mcp_servers
from .network_tool import NetworkTools
from .memory_tool import (
    MEMORY_SHORT_TOOL_DEF,
    MemoryTools,
    execute_memory_short,
)
from .n8n import discover_n8n_workflows, execute_n8n_workflow
from .router_tool import (
    EXPLAIN_ROUTE_DECISION_TOOL_DEF,
    ROUTER_MEMORY_TOOL_DEF,
    ROUTE_METRICS_TOOL_DEF,
    ROUTE_TASK_TOOL_DEF,
    RouterTools,
    execute_explain_route_decision,
    execute_route_metrics,
    execute_route_task,
    execute_router_memory,
)
from .persona_tool import PERSONA_MEMORY_TOOL_DEF, PersonaMemoryTools, execute_persona_memory
from .web_search import WEB_SEARCH_TOOL_DEF, WebSearchTools, execute_web_search
from .shell_tool import SHELL_TOOL_DEF, ShellTools, execute_run_shell
from .filesystem_tool import (
    READ_FILE_TOOL_DEF,
    LIST_DIR_TOOL_DEF,
    FilesystemTools,
    execute_read_file,
    execute_list_dir,
)
from .clipboard_tool import (
    GET_CLIPBOARD_TOOL_DEF,
    SET_CLIPBOARD_TOOL_DEF,
    ClipboardTools,
    execute_get_clipboard,
    execute_set_clipboard,
)
from .vision_tool import (
    TAKE_SCREENSHOT_TOOL_DEF,
    CAPTURE_REGION_TOOL_DEF,
    DISMISS_SCREEN_TOOL_DEF,
    ANALYZE_IMAGE_TOOL_DEF,
    VisionTools,
    execute_take_screenshot,
    execute_capture_region,
    execute_dismiss_screen,
    execute_analyze_image,
)

__all__ = [
    "create_hass_rest_tools",
    "create_hass_tools",
    "detect_hass_tool_prefix",
    "discover_n8n_workflows",
    "execute_memory_short",
    "execute_n8n_workflow",
    "execute_explain_route_decision",
    "execute_route_metrics",
    "execute_route_task",
    "execute_router_memory",
    "execute_web_search",
    "EXPLAIN_ROUTE_DECISION_TOOL_DEF",
    "HelmsmanTools",
    "initialize_mcp_servers",
    "prepare_lazy_mcp_servers",
    "iOSBridgeTools",
    "LightRAGTools",
    "load_mcp_config",
    "MacControlTools",
    "MCPHubTools",
    "LIST_TOOLS_TOOL_DEF",
    "CALL_TOOL_TOOL_DEF",
    "execute_list_tools",
    "execute_call_tool",
    "MCPServerConfig",
    "NetworkTools",
    "ROUTER_MEMORY_TOOL_DEF",
    "ROUTE_METRICS_TOOL_DEF",
    "ROUTE_TASK_TOOL_DEF",
    "RouterTools",
    "MEMORY_SHORT_TOOL_DEF",
    "MemoryTools",
    "PERSONA_MEMORY_TOOL_DEF",
    "PersonaMemoryTools",
    "execute_persona_memory",
    "WEB_SEARCH_TOOL_DEF",
    "WebSearchTools",
    "SHELL_TOOL_DEF",
    "ShellTools",
    "execute_run_shell",
    "READ_FILE_TOOL_DEF",
    "LIST_DIR_TOOL_DEF",
    "FilesystemTools",
    "execute_read_file",
    "execute_list_dir",
    "GET_CLIPBOARD_TOOL_DEF",
    "SET_CLIPBOARD_TOOL_DEF",
    "ClipboardTools",
    "execute_get_clipboard",
    "execute_set_clipboard",
    "TAKE_SCREENSHOT_TOOL_DEF",
    "CAPTURE_REGION_TOOL_DEF",
    "DISMISS_SCREEN_TOOL_DEF",
    "ANALYZE_IMAGE_TOOL_DEF",
    "VisionTools",
    "execute_take_screenshot",
    "execute_capture_region",
    "execute_dismiss_screen",
    "execute_analyze_image",
]
