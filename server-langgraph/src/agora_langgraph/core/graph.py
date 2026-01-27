"""LangGraph StateGraph construction with conditional routing."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Overwrite, Send

from agora_langgraph.core.agent_definitions import get_agent_by_id, get_spoken_prompt
from agora_langgraph.core.agents import (
    general_agent,
    get_agent_tools,
    get_llm_for_agent,
    get_llm_for_spoken,
    history_agent,
    regulation_agent,
    reporting_agent,
    set_agent_tools,
)
from agora_langgraph.core.state import AgentState, GeneratorState
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
        r'\bagora\b', '', str(latest.content), flags=re.IGNORECASE
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
            if isinstance(latest, HumanMessage) and detect_wake_word(str(latest.content)):
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
) -> Literal["tools"] | list[Send]:
    """Route from any agent based on the last message.

    ALL tool calls (including handoffs) go to ToolNode first.
    This ensures a proper ToolMessage response is added to the history,
    which OpenAI API requires before the next agent can run.

    When no more tool calls, returns Send commands for parallel
    spoken/written text generation.

    Args:
        state: Current graph state

    Returns:
        "tools" or list of Send commands for parallel generation
    """
    current_agent = state.get("current_agent", "unknown")
    messages = state.get("messages", [])

    log.info(
        f"route_from_agent: current_agent={current_agent}, num_messages={len(messages)}"
    )

    if not messages:
        return _create_parallel_sends(state)

    last_message = messages[-1]

    if not isinstance(last_message, AIMessage):
        return _create_parallel_sends(state)

    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        log.info("route_from_agent: No tool calls, forking to parallel generation")
        return _create_parallel_sends(state)

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


def _create_parallel_sends(state: AgentState) -> list[Send]:
    """Create Send commands for parallel spoken and written generation.

    This is used by route_from_agent to dispatch parallel generator instances with:
    - Same message context (all tool results included)
    - Different system prompts (written vs spoken)

    The agent's final response (if any) is filtered out since we regenerate
    it with separate written/spoken prompts.

    Args:
        state: Current agent state after tool execution

    Returns:
        List of Send commands for parallel generator dispatch
    """
    agent_id = state.get("current_agent", "general-agent")

    # Get prompts for both streams
    agent_config = get_agent_by_id(agent_id)
    written_prompt = agent_config["instructions"] if agent_config else ""
    spoken_prompt = get_spoken_prompt(agent_id) or ""

    # Filter out system messages - we'll add our own per-stream
    raw_messages = state.get("messages", [])
    messages: list[BaseMessage] = [
        m for m in raw_messages if not isinstance(m, SystemMessage)
    ]

    # Filter out the last AI message if it has no tool calls
    # This is the "wasted" response from the agent that we're regenerating
    if messages and isinstance(messages[-1], AIMessage):
        last_msg = messages[-1]
        if not getattr(last_msg, "tool_calls", None):
            log.info("_create_parallel_sends: Filtering out agent's final response")
            messages = messages[:-1]

    log.info(
        f"_create_parallel_sends: Dispatching parallel streams for {agent_id} "
        f"with {len(messages)} messages"
    )

    # Get common state fields
    session_id = state.get("session_id", "")
    metadata = state.get("metadata", {})

    # Dispatch to separate nodes for easy identification in astream_events
    return [
        Send(
            "generate_written",
            GeneratorState(
                messages=messages,
                system_prompt=written_prompt,
                stream_type="written",
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
            ),
        ),
        Send(
            "generate_spoken",
            GeneratorState(
                messages=messages,
                system_prompt=spoken_prompt,
                stream_type="spoken",
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
            ),
        ),
    ]


async def _generate_stream(
    state: GeneratorState, stream_type: str
) -> dict[str, list[str]]:
    """Internal: Generate a stream with the given type.

    Args:
        state: Generator-specific state from Send API
        stream_type: "written" or "spoken"

    Returns:
        Dict with stream_type key containing generated content list
    """
    agent_id = state["agent_id"]
    system_prompt = state["system_prompt"]
    messages = state["messages"]

    start_time = time.time()
    log.info(
        f"_generate_stream: Starting {stream_type} generation for {agent_id} "
        f"at t={start_time:.3f}"
    )

    # Use separate LLM for spoken (can be faster model via LANGGRAPH_SPOKEN_* config)
    llm = get_llm_for_spoken() if stream_type == "spoken" else get_llm_for_agent(agent_id)

    # Build message list with system prompt
    full_messages: list[BaseMessage] = [SystemMessage(content=system_prompt)] + list(
        messages
    )

    # Stream - astream_events will capture on_chat_model_stream events
    # which the orchestrator can use to stream to frontend
    full_content: list[str] = []
    first_chunk_time: float | None = None
    async for chunk in llm.astream(full_messages):
        if hasattr(chunk, "content") and chunk.content:
            if first_chunk_time is None:
                first_chunk_time = time.time()
            content = str(chunk.content)
            full_content.append(content)

    end_time = time.time()
    total_content = "".join(full_content)
    time_to_first = (first_chunk_time - start_time) if first_chunk_time else 0
    total_duration = end_time - start_time

    log.info(
        f"_generate_stream: Completed {stream_type} for {agent_id} - "
        f"{len(total_content)} chars, "
        f"time_to_first_chunk={time_to_first:.2f}s, "
        f"total_duration={total_duration:.2f}s"
    )

    # Return with stream_type as key - reducer will accumulate
    return {stream_type: [total_content]}


async def generate_written_node(state: GeneratorState) -> dict[str, list[str]]:
    """Generate written text stream.

    This node is easily identifiable in astream_events by name,
    allowing the orchestrator to route chunks to the written channel.
    """
    return await _generate_stream(state, "written")


async def generate_spoken_node(state: GeneratorState) -> dict[str, list[str]]:
    """Generate spoken text stream.

    This node is easily identifiable in astream_events by name,
    allowing the orchestrator to route chunks to the spoken channel.
    """
    return await _generate_stream(state, "spoken")


def merge_parallel_outputs(state: AgentState) -> dict[str, Any]:
    """Combine parallel generation outputs into final state.

    Takes accumulated written/spoken lists from parallel branches
    and produces final merged output. Also adds written response
    as AIMessage to conversation history.

    Args:
        state: State with accumulated written/spoken lists

    Returns:
        Dict with final outputs and updated messages
    """
    written_parts = state.get("written", [])
    spoken_parts = state.get("spoken", [])

    written_content = "".join(written_parts)
    spoken_content = "".join(spoken_parts)

    log.info(
        f"merge_parallel_outputs: written={len(written_content)} chars, "
        f"spoken={len(spoken_content)} chars"
    )

    # Log full content to terminal for debugging
    print("\n" + "=" * 80)
    print("WRITTEN OUTPUT:")
    print("=" * 80)
    print(written_content)
    print("\n" + "=" * 80)
    print("SPOKEN OUTPUT:")
    print("=" * 80)
    print(spoken_content)
    print("=" * 80 + "\n")

    return {
        "messages": [AIMessage(content=written_content)],
        "final_written": written_content,
        "final_spoken": spoken_content,
    }


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
        tool_node = ToolNode(unique_tools)
        graph.add_node("tools", tool_node)

    # Parallel generation nodes (fork happens via Send in route_from_agent)
    graph.add_node("generate_written", generate_written_node)
    graph.add_node("generate_spoken", generate_spoken_node)
    graph.add_node("merge", merge_parallel_outputs)

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

    # Agent routing - routes to tools or directly dispatches parallel generation via Send
    for agent_id in [
        "general-agent",
        "regulation-agent",
        "reporting-agent",
        "history-agent",
    ]:
        if unique_tools:
            # route_from_agent returns "tools" or list[Send] for parallel generation
            # When returning list[Send], the Send objects specify targets directly
            graph.add_conditional_edges(
                agent_id,
                route_from_agent,
                ["tools", "generate_written", "generate_spoken"],
            )
        else:
            # No tools - use conditional edges for Send-based fan-out
            graph.add_conditional_edges(
                agent_id,
                route_from_agent,
                ["generate_written", "generate_spoken"],
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
            if hasattr(latest, 'content') and str(latest.content).strip():
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

    # Parallel generation edges
    # fork_generation uses Send API - edges are implicit from Send targets
    # Both generator nodes merge their outputs
    graph.add_edge("generate_written", "merge")
    graph.add_edge("generate_spoken", "merge")
    graph.add_edge("merge", END)

    log.info("Agent graph built successfully with parallel generation support")
    return graph
