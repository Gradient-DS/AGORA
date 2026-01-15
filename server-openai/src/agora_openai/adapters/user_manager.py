"""User manager for CRUD operations on users."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)


class UserManager:
    """Manages user CRUD operations.

    This class handles the users table which stores:
    - User identification (id, email)
    - Profile information (name, role)
    - Preferences (JSON blob)
    - Activity tracking (created_at, last_activity)

    The users table is stored in the same database as session metadata
    to enable cascade deletes when a user is deleted.
    """

    def __init__(self, db_path: str = "sessions.db"):
        """Initialize the user manager.

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
        log.info(f"UserManager initialized with database: {self.db_path}")

    async def close(self) -> None:
        """Close database connection.

        Should be called during application shutdown.
        """
        if self._connection:
            await self._connection.close()
            self._connection = None
            log.info("UserManager connection closed")

    async def _ensure_tables(self) -> None:
        """Create users table if it doesn't exist."""
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'inspector',
                preferences TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                last_activity TEXT DEFAULT (datetime('now'))
            )
        """
        )
        await self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
            ON users (email)
        """
        )
        await self._connection.commit()

    async def create_user(
        self,
        email: str,
        name: str,
        role: str = "inspector",
    ) -> dict[str, Any] | None:
        """Create a new user.

        Args:
            email: User's email address (must be unique)
            name: User's display name
            role: User's role (admin, inspector, viewer)

        Returns:
            Created user dict or None if email already exists
        """
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        user_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        try:
            await self._connection.execute(
                """
                INSERT INTO users (id, email, name, role, created_at, last_activity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, name, role, now, now),
            )
            await self._connection.commit()
            log.info(f"Created user: {user_id} ({email})")

            return {
                "id": user_id,
                "email": email,
                "name": name,
                "role": role,
                "preferences": None,
                "createdAt": now,
                "lastActivity": now,
            }
        except aiosqlite.IntegrityError:
            log.warning(f"User with email {email} already exists")
            return None

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Get user by ID.

        Args:
            user_id: User identifier

        Returns:
            User dict or None if not found
        """
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        cursor = await self._connection.execute(
            """
            SELECT id, email, name, role, preferences, created_at, last_activity
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Get user by email.

        Args:
            email: User's email address

        Returns:
            User dict or None if not found
        """
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        cursor = await self._connection.execute(
            """
            SELECT id, email, name, role, preferences, created_at, last_activity
            FROM users
            WHERE email = ?
            """,
            (email,),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return self._row_to_user(row)

    async def update_user(
        self,
        user_id: str,
        name: str | None = None,
        role: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update user profile.

        Args:
            user_id: User identifier
            name: New display name (optional)
            role: New role (optional)
            preferences: New preferences dict (optional)

        Returns:
            Updated user dict or None if not found
        """
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        # Build update query dynamically
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)

        if role is not None:
            updates.append("role = ?")
            params.append(role)

        if preferences is not None:
            updates.append("preferences = ?")
            params.append(json.dumps(preferences))

        if not updates:
            # Nothing to update, just return current user
            return await self.get_user(user_id)

        # Always update last_activity
        now = datetime.now(UTC).isoformat()
        updates.append("last_activity = ?")
        params.append(now)

        params.append(user_id)

        cursor = await self._connection.execute(
            f"""
            UPDATE users
            SET {', '.join(updates)}
            WHERE id = ?
            """,
            params,
        )
        await self._connection.commit()

        if cursor.rowcount == 0:
            return None

        return await self.get_user(user_id)

    async def update_preferences(
        self,
        user_id: str,
        preferences: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update user preferences by merging with existing preferences.

        This method performs a shallow merge, preserving existing preferences
        that are not specified in the update.

        Args:
            user_id: User identifier
            preferences: Preferences dict with fields to update

        Returns:
            Updated user dict or None if not found
        """
        # Get existing user to merge preferences
        user = await self.get_user(user_id)
        if not user:
            return None

        # Merge with existing preferences (new values override existing)
        existing_prefs = user.get("preferences") or {}
        merged_prefs = {**existing_prefs, **preferences}

        return await self.update_user(user_id, preferences=merged_prefs)

    async def delete_user(self, user_id: str) -> tuple[bool, int]:
        """Delete a user and their sessions.

        Performs cascade delete of all sessions owned by the user.

        Args:
            user_id: User identifier

        Returns:
            Tuple of (success, deleted_sessions_count)
        """
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        # Count sessions first
        cursor = await self._connection.execute(
            "SELECT COUNT(*) FROM session_metadata WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        session_count = row[0] if row else 0

        # Delete sessions
        await self._connection.execute(
            "DELETE FROM session_metadata WHERE user_id = ?",
            (user_id,),
        )

        # Delete user
        cursor = await self._connection.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        )
        await self._connection.commit()

        if cursor.rowcount == 0:
            return False, 0

        log.info(f"Deleted user {user_id} and {session_count} sessions")
        return True, session_count

    async def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List all users with pagination.

        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip (for pagination)

        Returns:
            Tuple of (users list, total count)
        """
        if not self._connection:
            raise RuntimeError("UserManager not initialized")

        # Get total count
        cursor = await self._connection.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        total_count = row[0] if row else 0

        # Get paginated users
        cursor = await self._connection.execute(
            """
            SELECT id, email, name, role, preferences, created_at, last_activity
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()

        users = [self._row_to_user(row) for row in rows]
        return users, total_count

    def _row_to_user(self, row: tuple) -> dict[str, Any]:
        """Convert a database row to a user dict.

        Args:
            row: Database row tuple

        Returns:
            User dict with camelCase keys
        """
        preferences = None
        if row[4]:
            try:
                preferences = json.loads(row[4])
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON in preferences for user {row[0]}")

        return {
            "id": row[0],
            "email": row[1],
            "name": row[2],
            "role": row[3],
            "preferences": preferences,
            "createdAt": row[5],
            "lastActivity": row[6],
        }
