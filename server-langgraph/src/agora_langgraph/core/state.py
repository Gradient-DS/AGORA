"""LangGraph state definition for multi-agent orchestration."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State shared across all agent nodes.

    This state flows through the entire graph and maintains conversation context.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    current_agent: str
    pending_approval: dict[str, Any] | None
    metadata: dict[str, Any]
