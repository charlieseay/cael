"""Chat session management with per-session history and auto-expiry.

Each ChatSession maintains independent conversation history and tool data
cache, preventing cross-session bleed. ChatSessionManager handles lifecycle
with 30-minute inactivity expiry.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from ..llm import ToolDataCache

logger = logging.getLogger(__name__)

# Sessions expire after 30 minutes of inactivity
SESSION_TTL_SECONDS = 30 * 60

# Cleanup runs every 60 seconds
CLEANUP_INTERVAL_SECONDS = 60


class ChatSession:
    """Per-session conversation history and tool data cache.

    Each session maintains its own sliding window of messages and a
    ToolDataCache for structured tool response data. This matches the
    voice path where each LiveKit session has its own agent instance.
    """

    def __init__(self, session_id: str, max_turns: int = 20) -> None:
        self.session_id = session_id
        self.max_turns = max_turns
        self.messages: list[dict] = []
        self.tool_data_cache = ToolDataCache(max_entries=3)
        self.created_at = time.time()
        self.last_activity = time.time()

    def add_message(self, role: str, content: str) -> None:
        """Add a message and apply sliding window."""
        self.messages.append({"role": role, "content": content})
        self.last_activity = time.time()

        # Apply sliding window (max_turns * 2 for user + assistant pairs)
        max_messages = self.max_turns * 2
        if len(self.messages) > max_messages:
            trimmed = len(self.messages) - max_messages
            self.messages = self.messages[-max_messages:]
            logger.debug(
                f"Session {self.session_id}: trimmed {trimmed} old messages"
            )

    def get_messages(self) -> list[dict]:
        """Return a copy of the message history."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear history and cache."""
        self.messages.clear()
        self.tool_data_cache.clear()
        self.last_activity = time.time()

    @property
    def is_expired(self) -> bool:
        """Check if session has exceeded the inactivity TTL."""
        return (time.time() - self.last_activity) > SESSION_TTL_SECONDS


class ChatSessionManager:
    """Manages multiple chat sessions with auto-expiry.

    Runs a background asyncio task that periodically evicts expired
    sessions (30-minute inactivity TTL).
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._cleanup_task: asyncio.Task | None = None

    def get_or_create(
        self, session_id: str | None = None, max_turns: int = 20
    ) -> ChatSession:
        """Get an existing session or create a new one.

        Args:
            session_id: Session identifier. Auto-generated if None.
            max_turns: Max conversation turns for new sessions.

        Returns:
            ChatSession instance with updated last_activity.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]

        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_activity = time.time()
            return session

        session = ChatSession(session_id=session_id, max_turns=max_turns)
        self._sessions[session_id] = session
        logger.info(f"Created chat session: {session_id}")
        return session

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted chat session: {session_id}")
            return True
        return False

    def get_latest_session(self) -> ChatSession | None:
        """Return the most recently active non-expired session, or None."""
        active = [s for s in self._sessions.values() if not s.is_expired]
        if not active:
            return None
        return max(active, key=lambda s: s.last_activity)

    def list_sessions(self) -> list[dict]:
        """List active sessions with metadata."""
        return [
            {
                "session_id": s.session_id,
                "message_count": len(s.messages),
                "last_activity": s.last_activity,
                "created_at": s.created_at,
            }
            for s in self._sessions.values()
            if not s.is_expired
        ]

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(), name="chat_session_cleanup"
            )
            logger.info("Chat session cleanup started")

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Chat session cleanup stopped")

    async def _cleanup_loop(self) -> None:
        """Periodically evict expired sessions."""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                expired = [
                    sid
                    for sid, session in self._sessions.items()
                    if session.is_expired
                ]
                for sid in expired:
                    del self._sessions[sid]
                    logger.info(f"Expired chat session: {sid}")
                if expired:
                    logger.info(
                        f"Cleaned up {len(expired)} expired session(s), "
                        f"{len(self._sessions)} active"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")
