"""LangGraph state definition for multi-agent orchestration."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def accumulate_messages(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Custom reducer for message buffer accumulation.

    Accumulates message dicts. The buffer is cleared by returning an empty
    list from the process_buffer node (via Overwrite).
    """
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


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
    # Listen mode fields
    interaction_mode: str  # "feedback" | "listen"
    message_buffer: Annotated[list[dict[str, Any]], accumulate_messages]
    buffer_context: str  # Processed summary from buffered messages


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
