"""Checkpointer setup for LangGraph session persistence."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

log = logging.getLogger(__name__)


@asynccontextmanager
async def create_checkpointer(
    db_path: str = "sessions.db",
) -> AsyncGenerator[AsyncSqliteSaver, None]:
    """Create an async SQLite checkpointer for session persistence.

    Args:
        db_path: Path to the SQLite database file

    Yields:
        Configured AsyncSqliteSaver instance
    """
    log.info(f"Creating SQLite checkpointer at {db_path}")

    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        # Set busy_timeout so the checkpointer waits instead of failing
        # immediately when another connection holds the SQLite write lock.
        # The SessionMetadataManager and UserManager share this database
        # file with their own connections.
        await checkpointer.conn.execute("PRAGMA busy_timeout=5000")
        log.info("Checkpointer initialized successfully")
        yield checkpointer

    log.info("Checkpointer connection closed")
