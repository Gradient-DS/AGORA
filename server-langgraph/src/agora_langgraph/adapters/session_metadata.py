"""Session metadata manager for conversation history listing."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)


class SessionMetadataManager:
    """Manages session metadata for conversation history listing.

    This class handles the session_metadata table which stores:
    - Session identification and ownership (session_id, user_id)
    - Display information (title, first_message_preview)
    - Activity tracking (message_count, created_at, last_activity)

    The metadata table is separate from the LangGraph checkpointer storage
    to avoid coupling with framework internals.
    """

    def __init__(self, db_path: str = "sessions.db"):
        """Initialize the session metadata manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Initialize database connection and ensure tables exist.

        Must be called during application startup (lifespan).
        """
        self._connection = await aiosqlite.connect(self.db_path)
        await self._ensure_tables()
        log.info(f"SessionMetadataManager initialized with database: {self.db_path}")

    async def close(self) -> None:
        """Close database connection.

        Should be called during application shutdown.
        """
        if self._connection:
            await self._connection.close()
            self._connection = None
            log.info("SessionMetadataManager connection closed")

    async def _ensure_tables(self) -> None:
        """Create session_metadata table if it doesn't exist."""
        if not self._connection:
            raise RuntimeError("SessionMetadataManager not initialized")

        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS session_metadata (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                first_message_preview TEXT,
                message_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                last_activity TEXT DEFAULT (datetime('now'))
            )
        """)
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_metadata_user_activity
            ON session_metadata (user_id, last_activity DESC)
        """)
        await self._connection.commit()

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List all sessions for a user, ordered by last activity.

        Args:
            user_id: User identifier (inspector persona ID)
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip (for pagination)

        Returns:
            Tuple of (sessions list, total count)
        """
        if not self._connection:
            raise RuntimeError("SessionMetadataManager not initialized")

        # Get total count
        cursor = await self._connection.execute(
            "SELECT COUNT(*) FROM session_metadata WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        total_count = row[0] if row else 0

        # Get paginated sessions
        cursor = await self._connection.execute(
            """
            SELECT session_id, user_id, title, first_message_preview,
                   message_count, created_at, last_activity
            FROM session_metadata
            WHERE user_id = ?
            ORDER BY last_activity DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        )
        rows = await cursor.fetchall()

        sessions = []
        for row in rows:
            sessions.append({
                "sessionId": row[0],
                "userId": row[1],
                "title": row[2],
                "firstMessagePreview": row[3],
                "messageCount": row[4],
                "createdAt": row[5],
                "lastActivity": row[6],
            })

        return sessions, total_count

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session metadata by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session metadata dict or None if not found
        """
        if not self._connection:
            raise RuntimeError("SessionMetadataManager not initialized")

        cursor = await self._connection.execute(
            """
            SELECT session_id, user_id, title, first_message_preview,
                   message_count, created_at, last_activity
            FROM session_metadata
            WHERE session_id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return {
            "sessionId": row[0],
            "userId": row[1],
            "title": row[2],
            "firstMessagePreview": row[3],
            "messageCount": row[4],
            "createdAt": row[5],
            "lastActivity": row[6],
        }

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session's metadata.

        Note: This only deletes the metadata entry. The actual session
        data in the LangGraph checkpointer tables should be deleted
        separately if needed.

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if not found
        """
        if not self._connection:
            raise RuntimeError("SessionMetadataManager not initialized")

        cursor = await self._connection.execute(
            "DELETE FROM session_metadata WHERE session_id = ?",
            (session_id,),
        )
        await self._connection.commit()
        return cursor.rowcount > 0

    async def create_or_update_metadata(
        self,
        session_id: str,
        user_id: str,
        first_message: str | None = None,
    ) -> None:
        """Create session metadata entry or update if exists.

        On first message for a session:
        - Creates metadata entry with auto-generated title
        - Sets first_message_preview from message content

        On subsequent calls:
        - Updates last_activity timestamp

        Args:
            session_id: Session identifier
            user_id: User identifier (inspector persona ID)
            first_message: First user message (for title generation)
        """
        if not self._connection:
            raise RuntimeError("SessionMetadataManager not initialized")

        now = datetime.now(timezone.utc).isoformat()

        # Check if session already exists
        cursor = await self._connection.execute(
            "SELECT session_id FROM session_metadata WHERE session_id = ?",
            (session_id,),
        )
        existing = await cursor.fetchone()

        if existing:
            # Update last_activity only
            await self._connection.execute(
                """
                UPDATE session_metadata
                SET last_activity = ?
                WHERE session_id = ?
                """,
                (now, session_id),
            )
        else:
            # Create new entry
            title = self._generate_title(first_message) if first_message else "New Conversation"
            preview = first_message[:200] if first_message else None

            await self._connection.execute(
                """
                INSERT INTO session_metadata
                (session_id, user_id, title, first_message_preview, message_count, created_at, last_activity)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (session_id, user_id, title, preview, now, now),
            )

        await self._connection.commit()

    async def increment_message_count(self, session_id: str) -> None:
        """Increment message count and update last_activity.

        Args:
            session_id: Session identifier
        """
        if not self._connection:
            raise RuntimeError("SessionMetadataManager not initialized")

        now = datetime.now(timezone.utc).isoformat()
        await self._connection.execute(
            """
            UPDATE session_metadata
            SET message_count = message_count + 1,
                last_activity = ?
            WHERE session_id = ?
            """,
            (now, session_id),
        )
        await self._connection.commit()

    def _generate_title(self, first_message: str) -> str:
        """Generate a title from the first message.

        Takes the first 100 characters, truncated at word boundary,
        with ellipsis if truncated.

        Args:
            first_message: The first user message

        Returns:
            Generated title string
        """
        if not first_message:
            return "New Conversation"

        # Clean up whitespace
        message = " ".join(first_message.split())

        if len(message) <= 100:
            return message

        # Truncate at word boundary
        truncated = message[:100]
        last_space = truncated.rfind(" ")

        if last_space > 50:  # Only use word boundary if reasonable
            truncated = truncated[:last_space]

        return truncated + "..."
