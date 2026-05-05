"""CAAL Memory System.

Provides memory capabilities for the voice agent:
    - Short-term: Session/task context with TTL-based expiry
    - Long-term (future): Knowledge graph with semantic search

Example:
    >>> from caal.memory import ShortTermMemory
    >>> memory = ShortTermMemory()
    >>> memory.store("flight_number", "UA1234")
    >>> memory.get("flight_number")
    'UA1234'
"""

from .base import (
    DEFAULT_TTL_SECONDS,
    MEMORY_DIR,
    MemoryEntry,
    MemorySource,
    MemoryStore,
)
from .persona import invalidate_cache as invalidate_persona_cache
from .persona import load_persona_context
from .short_term import ShortTermMemory

__all__ = [
    # Classes
    "ShortTermMemory",
    # Functions
    "load_persona_context",
    "invalidate_persona_cache",
    # Types
    "MemoryEntry",
    "MemorySource",
    "MemoryStore",
    # Constants
    "DEFAULT_TTL_SECONDS",
    "MEMORY_DIR",
]
