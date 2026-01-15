"""LangGraph state definition for multi-agent orchestration."""

from __future__ import annotations

import operator
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
    # Parallel output accumulators - use operator.add to concatenate results from branches
    written: Annotated[list[str], operator.add]
    spoken: Annotated[list[str], operator.add]
    # Final merged outputs
    final_written: str
    final_spoken: str


class GeneratorState(TypedDict):
    """State passed to parallel generator nodes via Send API.

    Each parallel generator receives this independent state with different prompts
    but identical message context.
    """

    messages: list[BaseMessage]
    system_prompt: str
    stream_type: str  # "written" or "spoken"
    agent_id: str
    session_id: str
    metadata: dict[str, Any]
