"""Persona memory tool for CAAL.

Provides read/write access to persona memory files stored in the SoniqueBar
memory directory (IDENTITY.md, SOUL.md, RULES.md, TOOLS.md, MEMORY.md).

Used by the LLM to read current persona context and append learned preferences
or identity signals to the persona files.
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(
    os.path.expanduser(
        "~/Library/Application Support/SoniqueBar/memory"
    )
)

ALLOWED_FILES = {"IDENTITY", "SOUL", "RULES", "TOOLS", "MEMORY", "CONVERSATIONS"}

PERSONA_MEMORY_TOOL_DEF: dict = {
    "type": "function",
    "function": {
        "name": "persona_memory",
        "description": (
            "Read or append to Sonique's persona memory files "
            "(IDENTITY, SOUL, RULES, TOOLS, MEMORY, CONVERSATIONS).\n"
            "\n"
            "Actions:\n"
            "  read — return the full contents of a persona file.\n"
            "  append — add a new line or section to a persona file.\n"
            "  list — list available persona file names.\n"
            "\n"
            "Rules:\n"
            "- Use read before append so you don't duplicate content.\n"
            "- Only append when the user explicitly wants to update "
            "a persona or preference.\n"
            "- Keep appended content concise and factual."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "One of: read, append, list",
                },
                "file": {
                    "type": "string",
                    "description": (
                        "Persona file name without extension: "
                        "IDENTITY, SOUL, RULES, TOOLS, MEMORY, CONVERSATIONS. "
                        "Required for: read, append"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Text to append to the file. "
                        "Required for: append"
                    ),
                },
            },
            "required": ["action"],
        },
    },
}


async def execute_persona_memory(
    action: str,
    file: str = "",
    content: str = "",
) -> str:
    """Execute a persona_memory operation."""
    logger.info(f"persona_memory: action={action}, file={file}")

    if action == "list":
        files = sorted(MEMORY_DIR.glob("*.md")) if MEMORY_DIR.exists() else []
        if not files:
            return "No persona memory files found"
        return "Persona files: " + ", ".join(f.stem for f in files)

    if not file:
        return "file is required for read and append actions"

    stem = file.upper().replace(".MD", "")
    if stem not in ALLOWED_FILES:
        return (
            f"Unknown persona file: {file}. "
            f"Valid files: {', '.join(sorted(ALLOWED_FILES))}"
        )

    path = MEMORY_DIR / f"{stem}.md"

    if action == "read":
        if not path.exists():
            return f"{stem}.md not found"
        return path.read_text(encoding="utf-8")

    elif action == "append":
        if not content:
            return "content is required for append action"
        if not MEMORY_DIR.exists():
            return "Memory directory not found"
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n{content.rstrip()}\n")
        return f"Appended to {stem}.md"

    else:
        return (
            f"Unknown action: {action}. "
            "Valid actions: read, append, list"
        )


class PersonaMemoryTools:
    """Mixin providing persona_memory tool for reading and updating persona files."""

    @function_tool
    async def persona_memory(
        self,
        action: str,
        file: str = "",
        content: str = "",
    ) -> str:
        """Read or update Sonique's persona memory files.

        Use this to access or update identity, soul, rules, and memory files
        that define Sonique's personality and learned preferences.

        Args:
            action: One of "read", "append", "list"
            file: Persona file name: IDENTITY, SOUL, RULES, TOOLS, MEMORY, CONVERSATIONS
            content: Text to append (only for action="append")

        Returns:
            File contents, confirmation message, or list of available files
        """
        return await execute_persona_memory(
            action=action,
            file=file,
            content=content,
        )
