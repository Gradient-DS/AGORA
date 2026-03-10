"""LangGraph StateGraph construction with conditional routing."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Overwrite

from agora_langgraph.common.message_utils import extract_text
from agora_langgraph.core.agents import (
    general_agent,
    get_agent_tools,
    history_agent,
    regulation_agent,
    reporting_agent,
    set_agent_tools,
)
from agora_langgraph.core.state import AgentState
from agora_langgraph.core.tools import get_tools_for_agent

log = logging.getLogger(__name__)


VALID_AGENTS = {
    "general-agent",
    "regulation-agent",
    "reporting-agent",
    "history-agent",
}

# Wake word to switch from listen mode to feedback mode
# Just "AGORA" (case-insensitive) anywhere in the message
WAKE_WORD = "agora"


def detect_wake_word(content: str) -> bool:
    """Detect if message contains the AGORA wake word.

    Returns True if wake word found, False otherwise.
    Only used to switch FROM listen mode TO feedback mode.
    """
    return WAKE_WORD in content.lower()


def buffer_message_node(state: AgentState) -> dict[str, Any]:
    """Store incoming message in buffer without agent processing.

    In listen mode, messages are stored for later batch processing.
    Returns minimal acknowledgment without LLM call.
    """
    messages = state.get("messages", [])

    # Get latest human message to buffer
    latest_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_human = msg
            break

    if latest_human:
        buffer_count = len(state.get("message_buffer", [])) + 1
        return {
            "message_buffer": [{
                "content": latest_human.content,
                "timestamp": time.time(),
            }],
            # Minimal acknowledgment - no full response generation
            "final_written": f"[Luistermodus actief - bericht {buffer_count} opgeslagen]",
            "final_spoken": "",
        }

    return {}


def process_buffer_node(state: AgentState) -> dict[str, Any]:
    """Process all buffered messages and prepare context for agent.

    Called when transitioning from listen to feedback mode.
    Summarizes accumulated context and clears buffer.
    """
    buffer = state.get("message_buffer", [])

    if not buffer:
        return {}

    # Build context summary from buffered messages
    buffer_lines = []
    for i, msg in enumerate(buffer, 1):
        content = msg.get("content", "")
        buffer_lines.append(f"{i}. {content}")

    buffer_content = "\n".join(buffer_lines)

    context_summary = (
        f"--- Context verzameld tijdens luistermodus ({len(buffer)} berichten) ---\n"
        f"{buffer_content}\n"
        f"--- Einde luistermodus context ---"
    )

    log.info(f"process_buffer_node: Processed {len(buffer)} buffered messages")

    return {
        "buffer_context": context_summary,
        # Clear buffer using Overwrite to bypass reducer
        "message_buffer": Overwrite([]),
    }


def wake_word_handler_node(state: AgentState) -> dict[str, Any]:
    """Handle wake word detection - switch from listen to feedback mode.

    When "AGORA" is detected in a message while in listen mode:
    1. Switches interaction_mode to "feedback"
    2. Processes any buffered messages into buffer_context
    3. Strips the wake word and passes remaining content for processing

    Note: The preference is also persisted via user_manager in the orchestrator
    after this node runs (see Phase 3).
    """
    messages = state.get("messages", [])
    buffer = state.get("message_buffer", [])

    if not messages:
        return {}

    latest = messages[-1]
    if not isinstance(latest, HumanMessage):
        return {}

    # Remove "AGORA" from message (case-insensitive) and get remaining content
    remaining_content = re.sub(
        r'\bagora\b', '', extract_text(latest.content), flags=re.IGNORECASE
    ).strip()

    result: dict[str, Any] = {
        "interaction_mode": "feedback",
    }

    # Process buffer if we have buffered messages
    if buffer:
        buffer_lines = [f"{i+1}. {m['content']}" for i, m in enumerate(buffer)]
        result["buffer_context"] = (
            f"Context uit luistermodus ({len(buffer)} berichten):\n"
            + "\n".join(buffer_lines)
        )
        result["message_buffer"] = Overwrite([])

    result["final_written"] = (
        f"[Feedback modus geactiveerd - {len(buffer)} berichten verwerkt]"
    )
    result["final_spoken"] = "Feedback modus geactiveerd"

    # If there's content after removing the wake word, update message for processing
    if remaining_content:
        result["messages"] = [HumanMessage(content=remaining_content)]

    log.info(
        f"wake_word_handler: Switching to feedback mode, {len(buffer)} messages buffered"
    )
    return result


def route_from_start(state: AgentState) -> str:
    """Route from START based on interaction mode and wake word.

    Priority:
    1. If in listen mode AND wake word detected → wake_word_handler
    2. If in listen mode (no wake word) → buffer_message
    3. If buffer exists and in feedback mode → process_buffer first
    4. Otherwise → general-agent for triage (decides handoffs)

    Args:
        state: Current graph state

    Returns:
        Target node ID to start execution
    """
    messages = state.get("messages", [])
    mode = state.get("interaction_mode", "feedback")
    buffer = state.get("message_buffer", [])

    # In listen mode, check for wake word to switch back to feedback
    if mode == "listen":
        if messages:
            latest = messages[-1]
            if isinstance(latest, HumanMessage) and detect_wake_word(extract_text(latest.content)):
                log.info(
                    "route_from_start: Wake word 'AGORA' detected, "
                    "routing to wake_word_handler"
                )
                return "wake_word_handler"

        # No wake word - buffer the message
        log.info("route_from_start: Listen mode active, routing to buffer_message")
        return "buffer_message"

    # Feedback mode with buffer - process buffer first
    if mode == "feedback" and buffer:
        log.info(f"route_from_start: Processing {len(buffer)} buffered messages")
        return "process_buffer"

    # Feedback mode - always route to general-agent for triage
    # general-agent will hand off to specialists as needed based on message content
    # This ensures proper routing decisions for each new user message
    log.info("route_from_start: Feedback mode, routing to general-agent for triage")
    return "general-agent"


def detect_handoff_target(tool_name: str) -> str | None:
    """Detect target agent from a handoff tool call.

    Args:
        tool_name: Name of the tool being called

    Returns:
        Target agent ID or None if not a handoff
    """
    tool_lower = tool_name.lower()

    if "transfer_to_history" in tool_lower:
        return "history-agent"
    elif "transfer_to_regulation" in tool_lower:
        return "regulation-agent"
    elif "transfer_to_reporting" in tool_lower:
        return "reporting-agent"
    elif "transfer_to_general" in tool_lower:
        return "general-agent"

    return None


def is_handoff_tool(tool_name: str) -> bool:
    """Check if a tool is a handoff/transfer tool."""
    return "transfer_to_" in tool_name.lower()


def route_from_agent(
    state: AgentState,
) -> Literal["tools", "finalize_response"]:
    """Route from any agent based on the last message."""
    current_agent = state.get("current_agent", "unknown")
    messages = state.get("messages", [])

    log.info(
        f"route_from_agent: current_agent={current_agent}, num_messages={len(messages)}"
    )

    if not messages:
        return "finalize_response"

    last_message = messages[-1]

    if not isinstance(last_message, AIMessage):
        return "finalize_response"

    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        log.info("route_from_agent: No tool calls, finalizing response")
        return "finalize_response"

    tool_name = tool_calls[0].get("name", "")
    log.info(f"route_from_agent: Tool call '{tool_name}' → routing to ToolNode first")
    return "tools"


def route_after_tools(state: AgentState) -> str:
    """Route after tool execution - handles handoffs.

    Checks if the executed tool was a handoff tool. If so, routes to
    the target agent. Otherwise returns to the current agent.

    Args:
        state: Current graph state

    Returns:
        Target agent ID
    """
    messages = state.get("messages", [])
    current = state.get("current_agent", "general-agent")

    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = tool_call.get("name", "")
                handoff_target = detect_handoff_target(tool_name)
                if handoff_target:
                    log.info(f"route_after_tools: Handoff detected → {handoff_target}")
                    return handoff_target
            break

    log.info(f"route_after_tools: Returning to {current}")
    return current


def finalize_response(state: AgentState) -> dict[str, Any]:
    """Mark the agent's response as final and set final_written.

    This replaces the old merge_parallel_outputs node. It stamps
    is_final_response on the agent's AIMessage (used by _build_agent_messages
    for context filtering) and sets final_written for listen-mode fallback.
    """
    messages = state.get("messages", [])
    written_content = ""
    agent_msg = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            written_content = extract_text(msg.content)
            agent_msg = msg
            break

    log.info(f"finalize_response: {len(written_content)} chars")

    result: dict[str, Any] = {
        "final_written": written_content,
    }

    # Update the agent's AIMessage with is_final_response marker
    # Using the same ID triggers add_messages reducer to REPLACE (not append)
    if agent_msg:
        updated_kwargs = {**agent_msg.additional_kwargs}
        updated_kwargs["is_final_response"] = True
        updated_msg = AIMessage(
            content=agent_msg.content,
            id=agent_msg.id,
            additional_kwargs=updated_kwargs,
        )
        result["messages"] = [updated_msg]

    return result


def build_agent_graph(
    mcp_tools_by_server: dict[str, list[Any]] | None = None,
) -> StateGraph[AgentState]:
    """Build the multi-agent StateGraph.

    Args:
        mcp_tools_by_server: Optional pre-discovered MCP tools

    Returns:
        Configured StateGraph (not compiled)
    """

    if mcp_tools_by_server is None:
        mcp_tools_by_server = {}

    for agent_id in [
        "general-agent",
        "regulation-agent",
        "reporting-agent",
        "history-agent",
    ]:
        tools = get_tools_for_agent(agent_id, mcp_tools_by_server)
        set_agent_tools(agent_id, tools)
        log.info(f"Configured {len(tools)} tools for {agent_id}")

    all_tools = []
    for agent_id in [
        "general-agent",
        "regulation-agent",
        "reporting-agent",
        "history-agent",
    ]:
        all_tools.extend(get_agent_tools(agent_id))
    unique_tools = list({id(t): t for t in all_tools}.values())

    graph = StateGraph(AgentState)

    # Listen mode nodes (add BEFORE agent nodes)
    graph.add_node("buffer_message", buffer_message_node)
    graph.add_node("process_buffer", process_buffer_node)
    graph.add_node("wake_word_handler", wake_word_handler_node)

    # Agent nodes
    graph.add_node("general-agent", general_agent)
    graph.add_node("regulation-agent", regulation_agent)
    graph.add_node("reporting-agent", reporting_agent)
    graph.add_node("history-agent", history_agent)

    # Tool node
    if unique_tools:
        tool_node = ToolNode(unique_tools, handle_tool_errors=True)
        graph.add_node("tools", tool_node)

    # Finalize node — stamps is_final_response on agent's AIMessage
    graph.add_node("finalize_response", finalize_response)

    # Entry point - dynamic routing based on interaction mode and current_agent
    # Priority: listen mode → wake word → buffer, feedback mode → process buffer → agent
    graph.add_conditional_edges(
        START,
        route_from_start,
        {
            "buffer_message": "buffer_message",
            "process_buffer": "process_buffer",
            "wake_word_handler": "wake_word_handler",
            "general-agent": "general-agent",
            "regulation-agent": "regulation-agent",
            "reporting-agent": "reporting-agent",
            "history-agent": "history-agent",
        },
    )

    # Agent routing - routes to tools or finalize_response
    for agent_id in [
        "general-agent",
        "regulation-agent",
        "reporting-agent",
        "history-agent",
    ]:
        if unique_tools:
            graph.add_conditional_edges(
                agent_id,
                route_from_agent,
                ["tools", "finalize_response"],
            )
        else:
            graph.add_conditional_edges(
                agent_id,
                route_from_agent,
                ["finalize_response"],
            )

    # Tools routing back to agents
    if unique_tools:
        graph.add_conditional_edges(
            "tools",
            route_after_tools,
            {
                "general-agent": "general-agent",
                "regulation-agent": "regulation-agent",
                "reporting-agent": "reporting-agent",
                "history-agent": "history-agent",
            },
        )

    # Listen mode edges
    # Buffer goes directly to END (no response generation)
    graph.add_edge("buffer_message", END)

    # Process buffer then continues to general-agent
    graph.add_edge("process_buffer", "general-agent")

    # Wake word handler routes to general-agent if content, otherwise END
    def route_after_wake(state: AgentState) -> str:
        messages = state.get("messages", [])
        if messages:
            latest = messages[-1]
            # Check if there's content after stripping AGORA
            if hasattr(latest, 'content') and extract_text(latest.content).strip():
                return "general-agent"
        return END

    graph.add_conditional_edges(
        "wake_word_handler",
        route_after_wake,
        {
            "general-agent": "general-agent",
            END: END,
        },
    )

    # Finalize response then end
    graph.add_edge("finalize_response", END)

    log.info("Agent graph built successfully")
    return graph
