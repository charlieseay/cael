"""Persona context loader for CAAL.

Loads the persistent persona files (IDENTITY.md, SOUL.md, recent conversation
turns) from CAAL_MEMORY_DIR and formats them for injection into the system
prompt at session start. Cached per process — the files are read once and
reused for all subsequent turns in the same session.

Memory directory layout (all files managed by SoniqueBar + memory janitor):
    IDENTITY.md          — who Charlie and Cal are (stable profile)
    SOUL.md              — evolving persona traits/preferences
    conversation-turns.json — rolling recent turns
    short_term_memory.json  — key-value session store (managed by ShortTermMemory)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level cache — load once per process
_cached_context: str | None = None
_cached_at: float = 0.0
_CACHE_TTL = 300.0  # refresh every 5 minutes (picks up janitor persona updates)

# How many recent turns to include in session context
_RECENT_TURNS_TO_INCLUDE = 10


def _memory_dir() -> Path:
    from .base import MEMORY_DIR
    return MEMORY_DIR


def _load_file(path: Path) -> str | None:
    """Read a file, returning None on any error."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _recent_turns_summary(turns_path: Path) -> str | None:
    """Load recent conversation turns and format as a compact summary."""
    try:
        with open(turns_path, encoding="utf-8") as f:
            data = json.load(f)

        # Support both list-of-turns and {turns: [...]} shapes
        if isinstance(data, list):
            turns = data
        elif isinstance(data, dict):
            turns = data.get("turns", [])
        else:
            return None

        if not turns:
            return None

        # Take the most recent N turns
        recent = turns[-_RECENT_TURNS_TO_INCLUDE:]
        lines = []
        for t in recent:
            role = t.get("role", "?")
            content = t.get("content", "")
            if content:
                # Truncate very long turns for context efficiency
                if len(content) > 200:
                    content = content[:197] + "..."
                lines.append(f"  [{role}]: {content}")

        if not lines:
            return None

        return "Recent conversation (most recent {} turns):\n{}".format(
            len(lines), "\n".join(lines)
        )
    except Exception as e:
        logger.debug(f"persona: could not load conversation turns: {e}")
        return None


def load_persona_context(force_refresh: bool = False) -> str | None:
    """Return formatted persona context for system prompt injection.

    Reads IDENTITY.md, SOUL.md, and recent conversation turns from CAAL_MEMORY_DIR.
    Results are cached for _CACHE_TTL seconds so repeated calls within a session
    don't hit disk on every turn.

    Returns None if the memory directory isn't set or no files are found.
    """
    global _cached_context, _cached_at

    now = time.monotonic()
    if not force_refresh and _cached_context is not None and (now - _cached_at) < _CACHE_TTL:
        return _cached_context

    memory_dir = _memory_dir()

    # Only load if CAAL_MEMORY_DIR was explicitly set — don't assume the
    # project root is a valid memory directory (it won't have these files).
    if not os.getenv("CAAL_MEMORY_DIR"):
        return None

    if not memory_dir.is_dir():
        logger.debug(f"persona: memory dir not found: {memory_dir}")
        return None

    sections: list[str] = []

    # Load all persona files — Cal's stable identity and behavioral contracts
    for fname in ("IDENTITY.md", "SOUL.md", "RULES.md", "TOOLS.md"):
        content = _load_file(memory_dir / fname)
        if content:
            sections.append(content)

    # Recent conversation summary — last N turns for cross-session continuity
    turns_summary = _recent_turns_summary(memory_dir / "conversation-turns.json")
    if turns_summary:
        sections.append(turns_summary)

    if not sections:
        _cached_context = None
        _cached_at = now
        return None

    header = (
        "[PERSONA CONTEXT — loaded from persistent memory. "
        "Use silently. Do not read aloud or announce.]"
    )
    result = header + "\n\n" + "\n\n---\n\n".join(sections)

    _cached_context = result
    _cached_at = now
    logger.debug(
        f"persona: loaded context ({len(result)} chars) from {memory_dir}"
    )
    return result


def invalidate_cache() -> None:
    """Force the next load_persona_context() call to re-read from disk."""
    global _cached_context, _cached_at
    _cached_context = None
    _cached_at = 0.0
