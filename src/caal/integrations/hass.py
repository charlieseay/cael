"""Home Assistant MCP integration for CAAL.

Provides domain-aware intent mapping and automatic tool prefix detection
for reliable Home Assistant device control via voice commands.

Features:
- Automatic detection of MCP tool prefixes (assist__ vs bare names)
- Device cache with domain information from GetLiveContext
- Domain-specific intent mapping (cover -> HassOpenCover, not HassTurnOn)
- Unified hass() tool interface for LLM (single tool, action-based)

Usage:
    hass_server = mcp_servers.get("home_assistant")
    if hass_server:
        prefix = await detect_hass_tool_prefix(hass_server)
        tool_defs, tool_callables = create_hass_tools(hass_server, prefix)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from livekit.agents import mcp

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
DEVICE_CACHE_TTL = 300


@dataclass
class HADevice:
    """Cached Home Assistant device information."""

    name: str
    domain: str
    state: str
    area: str | None = None
    entity_id: str | None = None


@dataclass
class HADeviceCache:
    """Cache for Home Assistant device information.

    Parses GetLiveContext response to extract device names and domains,
    enabling domain-aware intent mapping.
    """

    devices: dict[str, HADevice] = field(default_factory=dict)
    last_updated: float = 0.0

    def is_stale(self) -> bool:
        """Check if cache needs refresh."""
        return time.time() - self.last_updated > DEVICE_CACHE_TTL

    def parse_live_context(self, text: str) -> None:
        """Parse GetLiveContext response to extract device information.

        Expected format from Home Assistant MCP:
        ```
        entity_id: cover.garage_door_left
        names: Garage Door Left
        state: closed
        area: Garage
        ...
        ```
        """
        self.devices.clear()

        # Parse entities from the context text
        current_entity: dict[str, str] = {}

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                # End of entity block - save if valid
                if current_entity.get("names") and current_entity.get("entity_id"):
                    entity_id = current_entity["entity_id"]
                    # Extract domain from entity_id (e.g., "cover" from "cover.garage_door")
                    domain = entity_id.split(".")[0] if "." in entity_id else "unknown"

                    # Use first name only (names field may have comma-separated aliases)
                    primary_name = current_entity["names"].split(",")[0].strip()
                    device = HADevice(
                        name=primary_name,
                        domain=domain,
                        state=current_entity.get("state", "unknown"),
                        area=current_entity.get("area"),
                        entity_id=entity_id,
                    )
                    # Store by lowercase name for case-insensitive lookup
                    self.devices[device.name.lower()] = device

                current_entity = {}
                continue

            # Parse key: value lines
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if key in ("entity_id", "names", "state", "area"):
                    current_entity[key] = value

        # Handle last entity if no trailing newline
        if current_entity.get("names") and current_entity.get("entity_id"):
            entity_id = current_entity["entity_id"]
            domain = entity_id.split(".")[0] if "." in entity_id else "unknown"
            primary_name = current_entity["names"].split(",")[0].strip()
            device = HADevice(
                name=primary_name,
                domain=domain,
                state=current_entity.get("state", "unknown"),
                area=current_entity.get("area"),
                entity_id=entity_id,
            )
            self.devices[device.name.lower()] = device

        self.last_updated = time.time()
        logger.debug(f"Parsed {len(self.devices)} devices from GetLiveContext")

    def find_device(self, target: str) -> HADevice | None:
        """Find device by name or entity_id (case-insensitive, with fuzzy matching).

        Args:
            target: Device name or entity_id to search for

        Returns:
            HADevice if found, None otherwise
        """
        target_lower = target.lower()

        # Entity ID match (e.g., "light.bedroom_light")
        if "." in target_lower:
            for device in self.devices.values():
                if device.entity_id and device.entity_id.lower() == target_lower:
                    return device

        # Exact name match
        if target_lower in self.devices:
            return self.devices[target_lower]

        # Partial match (target contained in device name or vice versa)
        for name, device in self.devices.items():
            if target_lower in name or name in target_lower:
                return device

        # Word-based fuzzy match
        target_words = set(target_lower.split())
        best_match: HADevice | None = None
        best_score = 0

        for name, device in self.devices.items():
            name_words = set(name.split())
            # Count matching words
            common = len(target_words & name_words)
            if common > best_score:
                best_score = common
                best_match = device

        return best_match if best_score > 0 else None


# Domain-aware action remapping: correct common LLM mistakes
# When LLM sends set_volume for a light, remap to set_brightness, etc.
DOMAIN_ACTION_REMAP: dict[tuple[str, str], str] = {
    ("set_volume", "light"): "set_brightness",
    ("set_volume", "climate"): "set_temperature",
    ("set_brightness", "media_player"): "set_volume",
    ("set_brightness", "climate"): "set_temperature",
    ("set_temperature", "light"): "set_brightness",
    ("set_temperature", "media_player"): "set_volume",
}

# Intent mapping: (action, domain) -> (intent_name, extra_args)
# Domain-specific mappings take priority over generic ones
INTENT_MAP: dict[tuple[str, str | None], tuple[str, dict]] = {
    # Cover-specific intents (domain takes priority)
    ("turn_on", "cover"): ("HassOpenCover", {}),
    ("turn_off", "cover"): ("HassCloseCover", {}),
    ("open", "cover"): ("HassOpenCover", {}),
    ("close", "cover"): ("HassCloseCover", {}),
    ("stop", "cover"): ("HassStopMoving", {}),
    # Light-specific intents
    ("set_brightness", "light"): ("HassLightSet", {}),
    # Climate-specific intents
    ("set_temperature", "climate"): ("HassClimateSetTemperature", {}),
    # Generic intents (fallback when no domain-specific match)
    ("turn_on", None): ("HassTurnOn", {}),
    ("turn_off", None): ("HassTurnOff", {}),
    ("toggle", None): ("HassToggle", {}),
    ("open", None): ("HassTurnOn", {}),  # Fallback for non-covers
    ("close", None): ("HassTurnOff", {}),  # Fallback for non-covers
    # Media intents (work across domains)
    ("pause", None): ("HassMediaPause", {}),
    ("play", None): ("HassMediaUnpause", {}),
    ("next", None): ("HassMediaNext", {}),
    ("previous", None): ("HassMediaPrevious", {}),
    ("volume_up", None): ("HassSetVolumeRelative", {"volume_step": "up"}),
    ("volume_down", None): ("HassSetVolumeRelative", {"volume_step": "down"}),
    ("set_volume", None): ("HassSetVolume", {}),
    ("mute", None): ("HassMediaPlayerMute", {}),
    ("unmute", None): ("HassMediaPlayerUnmute", {}),
}


async def detect_hass_tool_prefix(hass_server: mcp.MCPServerHTTP) -> str:
    """Detect the tool prefix used by the Home Assistant MCP server.

    Some HA MCP implementations use 'assist__' prefix (e.g., assist__HassTurnOn),
    while others use bare names (HassTurnOn). This function detects which is in use.

    Args:
        hass_server: Connected Home Assistant MCP server

    Returns:
        Tool prefix string ('assist__' or '')
    """
    if not hass_server or not hasattr(hass_server, "_client"):
        return ""

    try:
        # List available tools
        result = await hass_server._client.list_tools()
        tool_names = [tool.name for tool in result.tools]

        # Check for assist__ prefix
        for name in tool_names:
            if name.startswith("assist__"):
                logger.info("Detected Home Assistant MCP with 'assist__' prefix")
                return "assist__"

        logger.info("Detected Home Assistant MCP with bare tool names")
        return ""

    except Exception as e:
        logger.warning(f"Failed to detect HASS tool prefix: {e}")
        return ""


def create_hass_tools(
    hass_server: mcp.MCPServerHTTP,
    tool_prefix: str = "",
) -> tuple[list[dict], dict]:
    """Create Home Assistant tools bound to the given MCP server.

    Args:
        hass_server: Connected Home Assistant MCP server
        tool_prefix: Tool name prefix (e.g., 'assist__' or '')

    Returns:
        tuple: (tool_definitions, tool_callables)
        - tool_definitions: List of tool definitions in OpenAI format for LLM
        - tool_callables: Dict mapping tool name to callable function
    """
    # Device cache shared between tools
    device_cache = HADeviceCache()

    def _apply_prefix(tool_name: str) -> str:
        """Apply the detected prefix to a tool name."""
        return f"{tool_prefix}{tool_name}"

    def _resolve_intent(action: str, domain: str | None) -> tuple[str, dict]:
        """Resolve action + domain to the correct HA intent and extra args.

        Tries domain-specific mapping first, then falls back to generic.
        """
        # Try domain-specific mapping first
        if domain:
            key = (action, domain)
            if key in INTENT_MAP:
                return INTENT_MAP[key]

        # Fall back to generic mapping
        key = (action, None)
        if key in INTENT_MAP:
            return INTENT_MAP[key]

        # Unknown action
        return ("", {})

    async def _refresh_device_cache() -> None:
        """Refresh device cache from GetLiveContext."""
        if not device_cache.is_stale():
            return

        try:
            result = await hass_server._client.call_tool(
                _apply_prefix("GetLiveContext"), {}
            )

            if not result.isError:
                texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                if texts:
                    device_cache.parse_live_context("\n".join(texts))

        except Exception as e:
            logger.warning(f"Failed to refresh device cache: {e}")

    async def hass(action: str, target: str = None, value: int = None) -> str:
        """Control Home Assistant devices or get their status.

        Parameters:
            action: status, turn_on, turn_off, toggle, open, close, stop,
                   set_brightness, set_temperature, set_volume, volume_up,
                   volume_down, mute, unmute, pause, play, next, previous
            target: Device name in plain English (e.g., "office lamp").
                   Optional for status (omit for all devices).
            value: brightness 0-100 (%), temperature in degrees, volume 0-100
        """
        if not hass_server or not hasattr(hass_server, "_client"):
            return "Home Assistant is not connected"

        # Handle status action (query device state)
        if action == "status":
            return await _get_status(target)

        # All other actions require a target
        if not target:
            return f"Target device name is required for '{action}'"

        # Refresh device cache if stale
        await _refresh_device_cache()

        # Look up device to get domain
        device = device_cache.find_device(target)
        domain = device.domain if device else None
        if device:
            logger.info(
                f"hass: resolved '{target}' -> name='{device.name}', "
                f"entity_id={device.entity_id}, domain={domain}"
            )
        else:
            logger.warning(
                f"hass: no cache match for '{target}' "
                f"(cache has {len(device_cache.devices)} devices)"
            )

        # Remap mismatched actions based on domain (e.g., set_volume on a light -> set_brightness)
        if domain:
            remap_key = (action, domain)
            if remap_key in DOMAIN_ACTION_REMAP:
                corrected = DOMAIN_ACTION_REMAP[remap_key]
                logger.info(f"Remapped {action} -> {corrected} for {domain} domain")
                action = corrected

        # Resolve action to intent
        intent_name, extra_args = _resolve_intent(action, domain)

        if not intent_name:
            valid_actions = sorted(set(a for a, _ in INTENT_MAP.keys()) | {"status"})
            return f"Unknown action: {action}. Valid actions: {', '.join(valid_actions)}"

        # Build arguments — use cached friendly name when available
        # (HA intent matching requires the exact friendly name)
        if device:
            device_name = device.name
        elif "." in target and target.split(".")[0].isalpha():
            # Target looks like an entity_id (e.g., "light.bedroom_light") but
            # cache missed — convert to a plausible friendly name so HA intent
            # matching has a chance instead of receiving a raw entity_id.
            device_name = target.split(".", 1)[1].replace("_", " ").title()
            logger.info(f"hass: entity_id fallback '{target}' -> '{device_name}'")
        else:
            device_name = target
        args = {"name": device_name}

        # Include area if available (critical for HA entity disambiguation)
        if device and device.area:
            args["area"] = device.area

        # Include domain if we found one (improves HA intent matching)
        if domain:
            args["domain"] = [domain]

        # Add extra args from intent mapping
        args.update(extra_args)

        # Handle value parameter for specific actions
        if action == "set_volume" and value is not None:
            args["volume_level"] = value
        elif action == "set_brightness" and value is not None:
            # HassLightSet intent expects 0-100 percentage.
            # LLM sometimes sends 0-255 (from GetLiveContext state data),
            # so auto-scale values >100 down to percentage.
            if value > 100:
                value = round(value * 100 / 255)
            args["brightness"] = value
        elif action == "set_temperature" and value is not None:
            args["temperature"] = value

        # Apply prefix and call tool
        tool_name = _apply_prefix(intent_name)
        logger.info(f"hass: calling {tool_name} with args={args}")

        try:
            result = await hass_server._client.call_tool(tool_name, args)

            # Progressive retry on targeting failures:
            # 1. Drop domain constraint (broadens entity search)
            # 2. Drop area constraint (removes location filter)
            if result.isError:
                error_texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                error_msg = " ".join(error_texts)
                if "cannot target" in error_msg.lower():
                    if "domain" in args:
                        logger.info(f"Retry 1: {tool_name} without domain constraint")
                        args.pop("domain", None)
                        result = await hass_server._client.call_tool(tool_name, args)

                    if result.isError and "area" in args:
                        error_texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                        error_msg = " ".join(error_texts)
                        if "cannot target" in error_msg.lower():
                            logger.info(f"Retry 2: {tool_name} without area constraint")
                            args.pop("area", None)
                            result = await hass_server._client.call_tool(tool_name, args)

                    # Last resort: force-refresh the device cache and rebuild
                    # args with fresh friendly name + area. Handles the case
                    # where the original call used a stale or empty cache.
                    if result.isError:
                        error_texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                        error_msg = " ".join(error_texts)
                        if "cannot target" in error_msg.lower():
                            device_cache.last_updated = 0.0  # force stale
                            await _refresh_device_cache()
                            fresh_device = device_cache.find_device(target)
                            if fresh_device and fresh_device.name != args["name"]:
                                logger.info(
                                    f"Retry 3: fresh cache resolved "
                                    f"'{target}' -> '{fresh_device.name}'"
                                )
                                args["name"] = fresh_device.name
                                if fresh_device.area:
                                    args["area"] = fresh_device.area
                                result = await hass_server._client.call_tool(
                                    tool_name, args
                                )

            # Check for errors
            if result.isError:
                error_texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                return f"Error: {' '.join(error_texts)}"

            # Extract success message
            texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
            return " ".join(texts) if texts else f"Done: {action} {target}"

        except Exception as e:
            logger.error(f"hass error: {e}")
            return f"Failed to {action} {target}: {e}"

    async def _get_status(target: str = None) -> str:
        """Get the current state of Home Assistant devices."""
        try:
            tool_name = _apply_prefix("GetLiveContext")
            result = await hass_server._client.call_tool(tool_name, {})

            # Check for errors
            if result.isError:
                error_texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
                return f"Error: {' '.join(error_texts)}"

            # Extract content -- join with newlines to preserve entity block boundaries
            texts = [c.text for c in result.content if hasattr(c, "text") and c.text]
            full_context = "\n".join(texts) if texts else "No devices found"

            # Update device cache while we have the data
            device_cache.parse_live_context(full_context)

            # If target specified, filter to just that device
            if target:
                target_lower = target.lower()
                lines = full_context.split("\n")
                filtered = []
                capturing = False
                for line in lines:
                    if "names:" in line.lower() and target_lower in line.lower():
                        capturing = True
                    elif "names:" in line.lower() and capturing:
                        capturing = False
                    if capturing:
                        filtered.append(line)
                if filtered:
                    return "\n".join(filtered)
                return f"Device '{target}' not found"

            return full_context

        except Exception as e:
            logger.error(f"hass status error: {e}")
            return f"Failed to get status: {e}"

    # Tool definition in OpenAI format for LLM
    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "hass",
                "description": (
                    "Home Assistant — control smart home "
                    "devices or check their status.\n"
                    "\n"
                    "Action routing:\n"
                    "  status — check device state.\n"
                    "  turn_on / turn_off / toggle — "
                    "power control.\n"
                    "  open / close / stop — covers, "
                    "blinds, garage.\n"
                    "  set_brightness — light level "
                    "0-100%.\n"
                    "  set_temperature — thermostat.\n"
                    "  set_volume — media volume 0-100.\n"
                    "  volume_up / volume_down — "
                    "relative volume.\n"
                    "  mute / unmute — mute toggle.\n"
                    "  pause / play / next / previous — "
                    "playback control.\n"
                    "\n"
                    "Rules:\n"
                    "- target is the device name in "
                    "plain English.\n"
                    "- value is an integer: brightness "
                    "0-100, temp in degrees, volume 0-100."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": (
                                "One of: status, turn_on, "
                                "turn_off, toggle, open, "
                                "close, stop, set_brightness,"
                                " set_temperature, set_volume"
                                ", volume_up, volume_down, "
                                "mute, unmute, pause, play, "
                                "next, previous"
                            ),
                        },
                        "target": {
                            "type": "string",
                            "description": (
                                "Device name, e.g. "
                                "office lamp, garage door"
                            ),
                        },
                        "value": {
                            "type": "integer",
                            "description": (
                                "brightness 0-100, temp "
                                "in degrees, volume 0-100"
                            ),
                        },
                    },
                    "required": ["action", "target"],
                },
            },
        },
    ]

    # Callable function for tool execution
    tool_callables = {
        "hass": hass,
    }

    return tool_definitions, tool_callables
