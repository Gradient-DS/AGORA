"""Checkpointer setup for LangGraph session persistence."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aiosqlite
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

    async with aiosqlite.connect(db_path) as conn:
        checkpointer = AsyncSqliteSaver(conn)
        await checkpointer.setup()
        log.info("Checkpointer initialized successfully")
        yield checkpointer

    log.info("Checkpointer connection closed")
