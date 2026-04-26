"""Home Assistant REST API integration for CAAL.

Direct HTTP alternative to the MCP-based hass.py integration. Used by the
embedded sidecar where a host-side MCP proxy is not available.

Requires:
    HA_URL   — e.g. http://192.168.0.128:8123
    HA_TOKEN — long-lived access token from HA profile page
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEVICE_CACHE_TTL = 300  # seconds


@dataclass
class HADevice:
    entity_id: str
    name: str
    domain: str
    state: str
    area: str | None = None


@dataclass
class HADeviceCache:
    devices: dict[str, HADevice] = field(default_factory=dict)
    last_updated: float = 0.0

    def is_stale(self) -> bool:
        return time.time() - self.last_updated > DEVICE_CACHE_TTL

    def parse_states(self, states: list[dict]) -> None:
        self.devices.clear()
        for s in states:
            entity_id = s.get("entity_id", "")
            domain = entity_id.split(".")[0] if "." in entity_id else "unknown"
            attrs = s.get("attributes", {})
            name = attrs.get("friendly_name") or entity_id.replace("_", " ").title()
            area = attrs.get("area_id")
            device = HADevice(
                entity_id=entity_id,
                name=name,
                domain=domain,
                state=s.get("state", "unknown"),
                area=area,
            )
            self.devices[name.lower()] = device
        self.last_updated = time.time()
        logger.debug("HA REST cache: %d entities", len(self.devices))

    def find(self, target: str) -> HADevice | None:
        t = target.lower()
        # Entity ID exact match
        for d in self.devices.values():
            if d.entity_id.lower() == t:
                return d
        # Friendly name exact
        if t in self.devices:
            return self.devices[t]
        # Substring
        for name, d in self.devices.items():
            if t in name or name in t:
                return d
        # Word overlap
        t_words = set(t.split())
        best, best_score = None, 0
        for name, d in self.devices.items():
            score = len(t_words & set(name.split()))
            if score > best_score:
                best_score, best = score, d
        return best if best_score > 0 else None


# (action, domain | None) → (ha_domain, ha_service, extra_data_keys)
# extra_data_keys lists which kwargs to pass through as service data
_SERVICE_MAP: dict[tuple[str, str | None], tuple[str, str]] = {
    ("turn_on",  "cover"):        ("cover",        "open_cover"),
    ("turn_off", "cover"):        ("cover",        "close_cover"),
    ("open",     "cover"):        ("cover",        "open_cover"),
    ("close",    "cover"):        ("cover",        "close_cover"),
    ("stop",     "cover"):        ("cover",        "stop_cover"),
    ("set_brightness", "light"):  ("light",        "turn_on"),
    ("set_temperature", "climate"): ("climate",    "set_temperature"),
    ("pause",    None):           ("media_player", "media_pause"),
    ("play",     None):           ("media_player", "media_play"),
    ("next",     None):           ("media_player", "media_next_track"),
    ("previous", None):           ("media_player", "media_previous_track"),
    ("mute",     None):           ("media_player", "volume_mute"),
    ("unmute",   None):           ("media_player", "volume_mute"),
    ("set_volume", None):         ("media_player", "volume_set"),
    ("volume_up", None):          ("media_player", "volume_up"),
    ("volume_down", None):        ("media_player", "volume_down"),
    ("run_automation", None):     ("automation",   "trigger"),
    ("run_script", None):         ("script",       "turn_on"),
    ("run",      None):           ("automation",   "trigger"),
    ("toggle",   None):           ("homeassistant", "toggle"),
    ("turn_on",  None):           ("homeassistant", "turn_on"),
    ("turn_off", None):           ("homeassistant", "turn_off"),
}


def _resolve_service(action: str, domain: str | None) -> tuple[str, str] | None:
    if domain:
        result = _SERVICE_MAP.get((action, domain))
        if result:
            return result
    return _SERVICE_MAP.get((action, None))


def create_hass_rest_tools(ha_url: str, ha_token: str) -> tuple[list[dict], dict]:
    """Return (tool_definitions, tool_callables) using direct HA REST API."""

    ha_url = ha_url.rstrip("/")
    headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}
    cache = HADeviceCache()

    async def _refresh() -> None:
        if not cache.is_stale():
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{ha_url}/api/states", headers=headers)
                r.raise_for_status()
                cache.parse_states(r.json())
        except Exception as exc:
            logger.warning("HA REST states refresh failed: %s", exc)

    async def _call_service(
        ha_domain: str,
        ha_service: str,
        data: dict[str, Any],
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{ha_url}/api/services/{ha_domain}/{ha_service}",
                    headers=headers,
                    json=data,
                )
                r.raise_for_status()
                return "Done"
        except httpx.HTTPStatusError as exc:
            return f"HA error {exc.response.status_code}: {exc.response.text[:200]}"
        except Exception as exc:
            return f"HA request failed: {exc}"

    async def hass(action: str, target: str = None, value: int = None) -> str:
        """Control Home Assistant devices or query their status."""

        if action == "status":
            await _refresh()
            if not target:
                summary = [f"{d.name}: {d.state}" for d in cache.devices.values()]
                return "\n".join(summary[:40]) or "No devices in cache"
            device = cache.find(target)
            if device:
                return f"{device.name} ({device.entity_id}): {device.state}"
            return f"Device '{target}' not found"

        if not target:
            return f"Target device name required for '{action}'"

        await _refresh()
        device = cache.find(target)

        if device is None:
            return f"Could not find a device matching '{target}'"

        logger.info(
            "hass REST: '%s' → %s (%s) action=%s",
            target, device.name, device.entity_id, action,
        )

        mapping = _resolve_service(action, device.domain)
        if not mapping:
            valid = sorted({a for a, _ in _SERVICE_MAP})
            return f"Unknown action '{action}'. Valid: {', '.join(valid)}"

        ha_domain, ha_service = mapping
        data: dict[str, Any] = {"entity_id": device.entity_id}

        if action == "set_brightness" and value is not None:
            data["brightness_pct"] = min(100, value if value <= 100 else round(value * 100 / 255))
        elif action == "set_temperature" and value is not None:
            data["temperature"] = value
        elif action == "set_volume" and value is not None:
            data["volume_level"] = round(value / 100, 2)
        elif action == "mute":
            data["is_volume_muted"] = True
        elif action == "unmute":
            data["is_volume_muted"] = False

        result = await _call_service(ha_domain, ha_service, data)

        # Invalidate cache so next status call reflects the change
        if result == "Done":
            cache.last_updated = 0.0

        return result

    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "hass",
                "description": (
                    "Control Home Assistant smart home devices or query their status. "
                    "Actions: status, turn_on, turn_off, toggle, open, close, stop, "
                    "set_brightness, set_temperature, set_volume, volume_up, volume_down, "
                    "mute, unmute, pause, play, next, previous, run_automation, run_script. "
                    "Use plain English for target (e.g. 'bedroom light', 'garage door')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "target": {
                            "type": "string",
                            "description": "Device name in plain English",
                        },
                        "value": {
                            "type": "integer",
                            "description": "brightness 0-100, temperature in degrees, volume 0-100",
                        },
                    },
                    "required": ["action"],
                },
            },
        }
    ]

    return tool_definitions, {"hass": hass}
