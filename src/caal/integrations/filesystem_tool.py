"""filesystem_tool.py — scoped read-only filesystem access for the voice agent.

Provides read_file and list_dir tools constrained to a set of trusted path
prefixes. No writes — this is for inspection and context-gathering only.

Trusted paths:
  ~/Projects/                   — all local repos
  ~/Library/Application Support/SoniqueBar/  — sidecar config, memory, logs
  /Volumes/data/                — infrastructure data
  ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet/  — vault
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

_FILE_LIMIT = 8192     # 8 KB read cap
_DIR_ENTRY_LIMIT = 200 # max entries returned in a directory listing

_TRUSTED_PREFIXES: list[str] = [
    os.path.expanduser("~/Projects/"),
    os.path.expanduser("~/Library/Application Support/SoniqueBar/"),
    "/Volumes/data/",
    os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/SeaynicNet/"
    ),
]

# ── Tool definitions (for non-LiveKit ToolContext path) ──────────────────────

READ_FILE_TOOL_DEF: dict = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the contents of a file on the Mac Mini. "
            "Scoped to trusted paths: ~/Projects/, "
            "~/Library/Application Support/SoniqueBar/, "
            "/Volumes/data/, and the SeaynicNet vault. "
            "Output is capped at 8 KB. Use list_dir first if unsure of the path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Absolute or home-relative path to the file. "
                        "Examples: '~/Projects/sonique-ios/README.md', "
                        "'/Volumes/data/containers/homepage/services.yaml'"
                    ),
                },
            },
            "required": ["path"],
        },
    },
}

LIST_DIR_TOOL_DEF: dict = {
    "type": "function",
    "function": {
        "name": "list_dir",
        "description": (
            "List the contents of a directory on the Mac Mini. "
            "Scoped to the same trusted paths as read_file. "
            "Returns file names, sizes, and modification dates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Absolute or home-relative path to the directory. "
                        "Examples: '~/Projects/', '/Volumes/data/containers/'"
                    ),
                },
            },
            "required": ["path"],
        },
    },
}


def _resolve_trusted(raw: str) -> Path | None:
    """Expand and resolve a path; return None if outside trusted prefixes."""
    expanded = os.path.expanduser(raw.strip())
    resolved = str(Path(expanded).resolve())
    for prefix in _TRUSTED_PREFIXES:
        resolved_prefix = str(Path(prefix).resolve())
        if resolved == resolved_prefix or resolved.startswith(resolved_prefix + os.sep):
            return Path(resolved)
    return None


async def execute_read_file(path: str) -> str:
    """Read a file within trusted paths."""
    p = _resolve_trusted(path)
    if p is None:
        return (
            f"Access denied: '{path}' is outside trusted paths. "
            "Trusted: ~/Projects/, ~/Library/Application Support/SoniqueBar/, "
            "/Volumes/data/, SeaynicNet vault."
        )

    if not p.exists():
        return f"File not found: {p}"
    if p.is_dir():
        return f"'{p}' is a directory. Use list_dir instead."

    try:
        size = p.stat().st_size
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > _FILE_LIMIT:
            text = text[:_FILE_LIMIT] + f"\n... [truncated — file is {size} bytes]"
        return text if text.strip() else "(empty file)"
    except PermissionError:
        return f"Permission denied reading {p}"
    except Exception as e:
        logger.error("read_file error for %s: %s", p, e)
        return f"[error] {e}"


async def execute_list_dir(path: str) -> str:
    """List a directory within trusted paths."""
    p = _resolve_trusted(path)
    if p is None:
        return (
            f"Access denied: '{path}' is outside trusted paths."
        )

    if not p.exists():
        return f"Path not found: {p}"
    if not p.is_dir():
        return f"'{p}' is a file, not a directory. Use read_file instead."

    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return f"Permission denied listing {p}"
    except Exception as e:
        logger.error("list_dir error for %s: %s", p, e)
        return f"[error] {e}"

    if not entries:
        return f"{p}/ (empty)"

    lines: list[str] = [f"{p}/"]
    for entry in entries[:_DIR_ENTRY_LIMIT]:
        try:
            st = entry.stat()
            if entry.is_dir():
                lines.append(f"  {entry.name}/")
            else:
                kb = st.st_size / 1024
                size_str = f"{kb:.1f}KB" if kb >= 1 else f"{st.st_size}B"
                import datetime
                mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                lines.append(f"  {entry.name}  ({size_str}, {mtime})")
        except Exception:
            lines.append(f"  {entry.name}  (?)")

    if len(entries) > _DIR_ENTRY_LIMIT:
        lines.append(f"  ... [{len(entries) - _DIR_ENTRY_LIMIT} more entries]")

    return "\n".join(lines)


class FilesystemTools:
    """Mixin providing read_file and list_dir as @function_tool on the voice agent."""

    @function_tool
    async def read_file(self, path: str) -> str:
        """Read a file from the Mac Mini (scoped to trusted paths).

        Trusted paths: ~/Projects/, ~/Library/Application Support/SoniqueBar/,
        /Volumes/data/, and the SeaynicNet vault. Output capped at 8 KB.

        Args:
            path: Absolute or home-relative path to the file.

        Returns:
            File contents or an error message.
        """
        return await execute_read_file(path=path)

    @function_tool
    async def list_dir(self, path: str) -> str:
        """List a directory on the Mac Mini (scoped to trusted paths).

        Returns file names, sizes, and modification dates.

        Args:
            path: Absolute or home-relative path to the directory.

        Returns:
            Directory listing or an error message.
        """
        return await execute_list_dir(path=path)
