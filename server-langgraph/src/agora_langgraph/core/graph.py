"""LangGraph StateGraph construction with conditional routing."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

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
) -> Literal["tools", "end"]:
    """Route from any agent based on the last message.

    ALL tool calls (including handoffs) go to ToolNode first.
    This ensures a proper ToolMessage response is added to the history,
    which OpenAI API requires before the next agent can run.

    Args:
        state: Current graph state

    Returns:
        Next node to execute ("tools" or "end")
    """
    current_agent = state.get("current_agent", "unknown")
    messages = state.get("messages", [])

    log.info(
        f"route_from_agent: current_agent={current_agent}, num_messages={len(messages)}"
    )

    if not messages:
        return "end"

    last_message = messages[-1]

    if not isinstance(last_message, AIMessage):
        return "end"

    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        log.info("route_from_agent: No tool calls, ending turn")
        return "end"

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

    graph.add_node("general-agent", general_agent)
    graph.add_node("regulation-agent", regulation_agent)
    graph.add_node("reporting-agent", reporting_agent)
    graph.add_node("history-agent", history_agent)

    if unique_tools:
        tool_node = ToolNode(unique_tools)
        graph.add_node("tools", tool_node)

    graph.add_edge(START, "general-agent")

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
                {
                    "tools": "tools",
                    "end": END,
                },
            )
        else:
            graph.add_edge(agent_id, END)

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

    log.info("Agent graph built successfully")
    return graph
