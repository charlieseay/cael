"""shell_tool.py — sandboxed shell execution for the voice agent.

Commands are validated against an allowlist before execution. Blocked patterns
are checked first, then the base command must appear in the approved set.
Write operations (git push, docker rm, rm, etc.) are blocked.

Timeouts: 15s for most commands, 60s for build commands (npm, xcodebuild).
Output is capped at 4 KB to keep LLM context manageable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

# ── Output / timeout limits ───────────────────────────────────────────────────
_OUTPUT_LIMIT = 4096   # 4 KB
_DEFAULT_TIMEOUT = 15.0
_BUILD_TIMEOUT = 60.0
_BUILD_COMMANDS = {"npm", "xcodebuild", "swiftc", "swift", "cargo", "make"}

# ── Allowed base commands ─────────────────────────────────────────────────────
# None = any args permitted; set = only these subcommands allowed
_ALLOWED_BASE: dict[str, set[str] | None] = {
    "git": {
        "status", "log", "diff", "show", "branch", "remote",
        "stash", "ls-files", "shortlog", "describe", "rev-parse",
        "fetch", "tag",
    },
    "docker": {
        "ps", "logs", "stats", "images", "inspect",
        "network", "volume", "info", "version", "compose",
    },
    "ls": None, "ll": None,
    "cat": None, "head": None, "tail": None,
    "grep": None, "rg": None, "ag": None,
    "find": None,
    "wc": None, "sort": None, "uniq": None,
    "awk": None, "sed": None, "cut": None,
    "ps": None, "pgrep": None,
    "df": None, "du": None, "free": None,
    "ping": None,
    "curl": None,     # extra flag check below
    "brew": {"list", "info", "outdated", "deps", "uses", "search", "ls"},
    "which": None, "type": None, "whereis": None,
    "echo": None, "printf": None,
    "env": None, "printenv": None,
    "python": None, "python3": None,
    "node": None, "bun": None,
    "npm": {"list", "outdated", "run", "ls", "audit", "test"},
    "xcodebuild": None,
    "swiftc": None, "swift": None,
    "pbpaste": None,
    "open": None,
    "date": None, "uptime": None, "uname": None,
    "hostname": None,
    "netstat": None, "lsof": None,
    "dscl": None,
    "sw_vers": None,
    "system_profiler": None,
    "defaults": None,
    "plutil": None,
    "jq": None,
}

# ── Blocked patterns — checked against the full command string first ──────────
_BLOCKED_RE = [re.compile(p, re.I) for p in [
    r"\brm\b",
    r"\bsudo\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bkill\s+-9\b",
    r"\bgit\s+(commit|push|reset|checkout|restore|rebase|clean|merge|am)\b",
    r"\bdocker\s+(rm|rmi|stop|kill|restart|exec|run|pull|push)\b",
    r"\beval\b",
    r">\s*[^>]",              # output redirection (> file), but allow >>
    r"curl\s+.*(-X\s*(POST|PUT|DELETE|PATCH)|--data\b|-d\s|--request\s*(POST|PUT|DELETE|PATCH))",
    r"\bnpm\s+(install|uninstall|ci)\b",
    r"\bpip\s+install\b",
    r"\bbrew\s+(install|uninstall|upgrade|update)\b",
    r"\bmv\s+\S",
    r"\bcp\s+.*\s+\S",
    r"\bfind\s+.*-delete\b",
    r"\bfind\s+.*-exec\s+rm\b",
    r"\blaunchctl\s+(unload|remove|stop)\b",
    r"\bpkill\b",
    r"\bkillall\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bdiskutil\b",
    r"\bformat\b",
]]


SHELL_TOOL_DEF: dict = {
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": (
            "Run an approved read-only shell command on the Mac Mini. "
            "Approved: git status/log/diff, docker ps/logs/stats, ls, cat, grep, find, "
            "curl (GET only), brew list/info, npm list/run/test, xcodebuild, "
            "ps, df, ping, node, python3, jq, and more. "
            "Blocked: rm, sudo, git push/commit, docker stop/rm, curl POST, "
            "and any other write or destructive operation. "
            "Use this to inspect code, container health, build output, and system state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The shell command to run. "
                        "Examples: 'git status', 'docker ps -a', "
                        "'ls ~/Projects/', 'cat ~/.zshrc'"
                    ),
                },
            },
            "required": ["command"],
        },
    },
}


def _validate(command: str) -> str | None:
    """Return None if allowed, or an error string if blocked."""
    for pat in _BLOCKED_RE:
        if pat.search(command):
            return f"Blocked: matches restricted pattern."

    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"Cannot parse command: {e}"

    if not parts:
        return "Empty command."

    # Handle env var prefixes like SOME_VAR=x git status
    idx = 0
    while idx < len(parts) and "=" in parts[idx] and not parts[idx].startswith("-"):
        idx += 1
    if idx >= len(parts):
        return "No command found after environment variables."

    base = os.path.basename(parts[idx])

    if base not in _ALLOWED_BASE:
        return (
            f"'{base}' is not in the approved command list. "
            "Allowed: git, docker, ls, cat, grep, find, curl, brew, npm, "
            "xcodebuild, ps, df, ping, python3, node, jq, and others."
        )

    allowed_subs = _ALLOWED_BASE[base]
    if allowed_subs is not None:
        sub = next(
            (p for p in parts[idx + 1:] if not p.startswith("-")),
            None,
        )
        if sub and sub not in allowed_subs:
            return (
                f"'{base} {sub}' is not approved. "
                f"Allowed subcommands for {base}: {', '.join(sorted(allowed_subs))}"
            )

    return None


async def execute_run_shell(command: str) -> str:
    """Validate and execute a shell command, returning truncated output."""
    command = command.strip()
    if not command:
        return "[error] Empty command."

    err = _validate(command)
    if err:
        return f"[blocked] {err}"

    try:
        parts = shlex.split(command)
        base = os.path.basename(parts[0]) if parts else ""
    except ValueError:
        base = ""
    timeout = _BUILD_TIMEOUT if base in _BUILD_COMMANDS else _DEFAULT_TIMEOUT

    logger.info("run_shell: %r (timeout=%.0fs)", command, timeout)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return f"[timeout] Command exceeded {timeout:.0f}s limit."

        output = stdout.decode("utf-8", errors="replace")
        if len(output) > _OUTPUT_LIMIT:
            output = output[:_OUTPUT_LIMIT] + f"\n... [truncated at {_OUTPUT_LIMIT} bytes]"

        rc = proc.returncode or 0
        prefix = f"[exit {rc}]\n" if rc != 0 else ""
        return f"{prefix}{output}" if output.strip() else (
            f"[exit {rc}] (no output)" if rc != 0 else "(no output)"
        )

    except Exception as e:
        logger.error("run_shell error for %r: %s", command, e)
        return f"[error] {e}"


class ShellTools:
    """Mixin providing run_shell as a @function_tool on the voice agent."""

    @function_tool
    async def run_shell(self, command: str) -> str:
        """Run an approved shell command on the Mac Mini.

        Use this to inspect code, container health, build output, and system
        state. Read-only commands only — write and destructive operations are
        blocked. Examples: 'git status', 'docker ps -a', 'ls ~/Projects/'.

        Args:
            command: The shell command to run.

        Returns:
            Command output (truncated at 4 KB) or a blocked/error message.
        """
        return await execute_run_shell(command=command)
