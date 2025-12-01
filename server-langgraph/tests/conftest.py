"""Pytest configuration and fixtures for AGORA LangGraph tests."""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing AG-UI Protocol."""
    ws = MagicMock()
    # AG-UI format: RunAgentInput
    ws.receive_text = AsyncMock(
        return_value=json.dumps(
            {
                "threadId": "test-123",
                "runId": "run-456",
                "messages": [{"role": "user", "content": "test"}],
            }
        )
    )
    ws.send_text = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def sample_run_input():
    """Create a sample AG-UI run input."""
    from agora_langgraph.common.ag_ui_types import RunAgentInput

    return RunAgentInput(
        threadId="test-session-123",
        runId="run-789",
        messages=[{"role": "user", "content": "Hallo, hoe gaat het?"}],
        context={},
    )


@pytest.fixture
def sample_tool_call():
    """Create a sample tool call."""
    from agora_langgraph.common.schemas import ToolCall

    return ToolCall(
        tool_name="search_regulations",
        parameters={"query": "HACCP", "top_k": 5},
    )


@pytest.fixture
def sample_approval_response():
    """Create a sample tool approval response."""
    from agora_langgraph.common.ag_ui_types import ToolApprovalResponsePayload

    return ToolApprovalResponsePayload(
        approvalId="approval-123",
        approved=True,
        feedback="Approved by user",
    )
