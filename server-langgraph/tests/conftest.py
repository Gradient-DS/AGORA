"""Pytest configuration and fixtures for AGORA LangGraph tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    ws = MagicMock()
    ws.receive_text = AsyncMock(
        return_value='{"type": "user_message", "content": "test", "session_id": "test-123"}'
    )
    ws.send_text = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def sample_user_message():
    """Create a sample user message."""
    from agora_langgraph.common.hai_types import UserMessage

    return UserMessage(
        content="Hallo, hoe gaat het?",
        session_id="test-session-123",
        metadata={},
    )


@pytest.fixture
def sample_tool_call():
    """Create a sample tool call."""
    from agora_langgraph.common.schemas import ToolCall

    return ToolCall(
        tool_name="search_regulations",
        parameters={"query": "HACCP", "top_k": 5},
    )
