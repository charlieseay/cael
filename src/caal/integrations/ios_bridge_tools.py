"""iOSBridgeTools mixin — on-device iOS actions via the Siri intent bridge.

These tools let the LLM agent delegate native iOS operations (calendar reads,
iMessage compose) to the user's iPhone without breaking conversation flow.
They are device-local fallbacks: host/SoniqueBar connected-service tools should
be preferred when both paths are available.

The bridge works over the LiveKit data channel:
  query_ios_calendar  → publishes `request_ios_calendar` to the room,
                         waits up to 5s for `ios_calendar_result` from Flutter
  compose_ios_message → fires tool_status so Flutter can open the Messages
                         compose sheet; returns immediately (fire-and-forget)

Both tools are always registered. `query_ios_calendar` times out gracefully
when no iOS client is connected. `compose_ios_message` is a no-op on non-iOS
clients (Flutter checks `Platform.isIOS` before acting on tool_status).

The capability manifest below lists all available iOS bridge capabilities.
On session start, this is sent to the iOS client so it knows what's active.
Adding new capabilities requires:
  1. Add entry to CAPABILITY_MANIFEST
  2. Add handler method in iOSBridgeTools
  3. Add case in AppDelegate.handleCapability() (snake_case method name)
  4. Add typed convenience wrapper in siri_intent_bridge.dart
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

# Canonical capability registry — sent to iOS client on session start.
# Each entry maps the snake_case method name to its metadata.
CAPABILITY_MANIFEST = {
    "contacts_query": {
        "description": "Look up contacts by name, returning phone numbers and email addresses"
    },
    "directions_query": {
        "description": "Get travel distance and estimated time to a destination"
    },
    "location_query": {
        "description": "Get current location coordinates and reverse-geocoded address"
    },
    "calendar_query": {
        "description": "Read calendar events within a date range"
    },
    "reminder_create": {
        "description": "Create a reminder with title, due date, and optional notes"
    },
    "phone_call": {
        "description": "Initiate a phone call to a number"
    },
    "message_send": {
        "description": "Open the Messages compose sheet to send a text or iMessage"
    },
    "directions_navigate": {
        "description": "Resolve a destination and prepare for navigation in Maps"
    },
}


class iOSBridgeTools:
    """Mixin providing native iOS on-device tools for the voice/chat agent.

    Routing intent:
    - Prefer host/SoniqueBar tools for connected services.
    - Use iOS bridge tools for iPhone-local resources or explicit iPhone actions.
    """

    @function_tool
    async def query_ios_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> str:
        """Read calendar events from the user's iPhone for a date range.

        Use this to answer questions like "what's on my calendar today?" or
        "do I have anything tomorrow morning?". Returns a JSON list of events
        with title, start, end, location, and calendar name.

        Args:
            start_date: Start of the range in ISO 8601 format (e.g. 2026-04-27).
                        Use today's date if the user asks about today.
            end_date: End of the range in ISO 8601 format (e.g. 2026-04-28).
                      Use the same day as start_date for a single-day query.

        Returns:
            JSON string with an "events" array, or an error message if the
            iOS device is unavailable or times out.
        """
        if not hasattr(self, "_on_ios_calendar_query") or self._on_ios_calendar_query is None:
            return await self._fallback_calendar_query(start_date, end_date)

        logger.info(f"query_ios_calendar: {start_date!r} → {end_date!r}")
        result = await self._on_ios_calendar_query(start_date, end_date)
        if self._result_needs_calendar_fallback(result):
            logger.info("query_ios_calendar: iOS bridge unavailable, using server-side fallback")
            return await self._fallback_calendar_query(start_date, end_date)
        return result

    @staticmethod
    def _result_needs_calendar_fallback(raw_result: str) -> bool:
        """True when iOS bridge could not satisfy the calendar request."""
        try:
            payload = json.loads(raw_result)
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False
        error = str(payload.get("error", "")).lower()
        return any(
            hint in error
            for hint in (
                "not configured",
                "timed out",
                "device may not be connected",
                "failed to request i",
            )
        )

    async def _fallback_calendar_query(self, start_date: str, end_date: str) -> str:
        """Fallback to host/server-side calendar tooling when iOS bridge fails."""
        if not hasattr(self, "get_calendar_events"):
            return '{"error": "No calendar provider is currently available."}'
        try:
            start = dt.date.fromisoformat(start_date)
            end = dt.date.fromisoformat(end_date)
            if end < start:
                end = start
            days_ahead = max(1, (end - dt.date.today()).days + 1)
            host_result = await self.get_calendar_events(days_ahead=days_ahead)
            return json.dumps(
                {
                    "source": "host_calendar_fallback",
                    "result": host_result,
                }
            )
        except Exception as e:
            logger.warning(f"calendar fallback failed: {e}")
            return json.dumps({"error": f"Calendar fallback failed: {e}"})

    @function_tool
    async def compose_ios_message(
        self,
        recipient: str,
        body: str,
    ) -> str:
        """Open an iMessage compose sheet on the user's iPhone.

        This opens the Messages compose sheet directly on the device — the
        user sees it overlaid on the conversation UI, taps Send, and returns
        to the conversation without leaving the app.

        Use when the user asks to send a text or iMessage to someone.

        Args:
            recipient: Contact name or phone number to address the message to.
            body: The pre-filled message text. The user can edit before sending.

        Returns:
            Confirmation that the compose sheet was triggered.
        """
        logger.info(f"compose_ios_message: recipient={recipient!r}, body={body!r}")
        # The actual compose sheet is opened by Flutter's ToolStatusCtrl when
        # it detects this tool name in the tool_status data packet.
        return (
            f"Message compose sheet opened for {recipient}. "
            "The user can review the pre-filled message and tap Send."
        )

    @function_tool
    async def query_ios_contacts(self, name: str) -> str:
        """Look up a contact by name on the user's iPhone.

        Returns phone numbers and email addresses for matching contacts.
        Use this when the user asks for someone's contact information.

        Args:
            name: The contact name to search for (partial matches supported,
                  case-insensitive).

        Returns:
            JSON string with a "contacts" array containing matching contacts,
            or an error message if unavailable or times out.
        """
        if not hasattr(self, "_on_ios_contacts_query") or self._on_ios_contacts_query is None:
            return '{"error": "iOS contacts integration is not configured."}'

        logger.info(f"query_ios_contacts: {name!r}")
        return await self._on_ios_contacts_query(name)

    @function_tool
    async def query_ios_directions(self, destination: str, transport_type: str = "driving") -> str:
        """Get travel distance and estimated time to a destination from the user's current location.

        Use for 'how far is X' or 'how long to get to Y' questions.

        Args:
            destination: The destination address or place name.
            transport_type: "driving" (default) or "walking" for travel mode.

        Returns:
            JSON string with destination_name, distance_meters, travel_time_seconds,
            or an error message if unavailable or times out.
        """
        if not hasattr(self, "_on_ios_directions_query") or self._on_ios_directions_query is None:
            return '{"error": "iOS directions integration is not configured."}'

        logger.info(f"query_ios_directions: {destination!r}, transport_type={transport_type!r}")
        return await self._on_ios_directions_query(destination, transport_type)

    @function_tool
    async def query_ios_location(self) -> str:
        """Get the user's current location as coordinates and address.

        Returns latitude, longitude, and a human-readable address.

        Returns:
            JSON string with latitude, longitude, address, or an error message
            if location access is denied or times out.
        """
        if not hasattr(self, "_on_ios_location_query") or self._on_ios_location_query is None:
            return '{"error": "iOS location integration is not configured."}'

        logger.info("query_ios_location")
        return await self._on_ios_location_query()

    @function_tool
    async def make_ios_phone_call(self, phone_number: str) -> str:
        """Initiate a phone call on the user's iPhone.

        Args:
            phone_number: The phone number to call (any format).

        Returns:
            Confirmation that the phone call was initiated.
        """
        logger.info(f"make_ios_phone_call: {phone_number!r}")
        # The actual phone call is initiated by Flutter's ToolStatusCtrl when
        # it detects this tool name in the tool_status data packet.
        return f"Phone call initiated to {phone_number}."
