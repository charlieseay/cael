"""MacControlTools mixin — local Mac system control via SoniqueBar.

Gives the voice/chat agent the ability to trigger actions on the Mac
where SoniqueBar is running. SoniqueBar polls /api/mac-actions/pending,
executes via NSWorkspace + NSAppleScript, and posts completion back.

Supported action_type values (SoniqueBar executes these):
    open_url        Open a URL in the default browser.
    open_app        Launch a macOS application by name.
    run_applescript Run arbitrary AppleScript code.
    shell_command   Run a shell command (via AppleScript do shell script).
    key_press       Send a key combination (via AppleScript keystroke).
"""

from __future__ import annotations

import logging

from livekit.agents import function_tool

from ..mac_actions import enqueue

logger = logging.getLogger(__name__)


class MacControlTools:
    """Mixin providing local Mac control tools for the voice/chat agent."""

    @function_tool
    async def mac_open_url(self, url: str) -> str:
        """Open a URL in the user's default browser on their Mac.

        Use for opening websites, deep links, or any URL the user asks Cael
        to open on their computer.

        Args:
            url: The URL to open (must include scheme, e.g. https://).

        Returns:
            Confirmation that the action was queued.
        """
        logger.info(f"mac_open_url: {url!r}")
        action_id = enqueue("open_url", {"url": url})
        return f"Opening {url} on your Mac. (action {action_id})"

    @function_tool
    async def mac_open_app(self, app: str) -> str:
        """Launch an application on the user's Mac by name.

        Use when the user asks Cael to open an app — Notes, Safari, Chess,
        Finder, Calendar, Mail, Music, or any macOS application.

        Args:
            app: Application name as it appears in /Applications
                 (e.g. "Notes", "Chess", "Safari", "Finder").

        Returns:
            Confirmation that the action was queued.
        """
        logger.info(f"mac_open_app: {app!r}")
        action_id = enqueue("open_app", {"app": app})
        return f"Opening {app} on your Mac. (action {action_id})"

    @function_tool
    async def mac_run_applescript(self, script: str) -> str:
        """Run AppleScript on the user's Mac for complex automation.

        Use for anything that requires deeper macOS control: typing text into
        apps, interacting with UI elements, creating calendar events, sending
        messages, controlling music playback, etc.

        Args:
            script: Valid AppleScript code. Be precise — errors are returned
                    back to you so you can retry with a corrected script.

        Returns:
            Confirmation that the action was queued.
        """
        logger.info(f"mac_run_applescript: script length={len(script)}")
        action_id = enqueue("run_applescript", {"script": script})
        return f"AppleScript queued on your Mac. (action {action_id})"

    @function_tool
    async def mac_shell_command(self, command: str) -> str:
        """Run a shell command on the user's Mac.

        Use for terminal-level tasks: file operations, system queries,
        running scripts, checking status, etc.

        Args:
            command: Shell command string. Runs via /bin/zsh.

        Returns:
            Confirmation that the action was queued.
        """
        logger.info(f"mac_shell_command: {command!r}")
        action_id = enqueue("shell_command", {"command": command})
        return f"Shell command queued on your Mac. (action {action_id})"
