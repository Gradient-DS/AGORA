"""Agent node functions for LangGraph orchestration."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from agora_langgraph.config import get_settings
from agora_langgraph.core.state import AgentState
from agora_langgraph.core.agent_definitions import AGENT_CONFIGS, get_agent_by_id

log = logging.getLogger(__name__)

_agent_tools: dict[str, list[Any]] = {}
_llm_cache: dict[str, ChatOpenAI] = {}


def set_agent_tools(agent_id: str, tools: list[Any]) -> None:
    """Set tools for an agent."""
    _agent_tools[agent_id] = tools


def get_agent_tools(agent_id: str) -> list[Any]:
    """Get tools for an agent."""
    return _agent_tools.get(agent_id, [])


def get_llm_for_agent(agent_id: str) -> ChatOpenAI:
    """Get or create LLM instance for an agent."""
    if agent_id not in _llm_cache:
        settings = get_settings()
        config = get_agent_by_id(agent_id)

        if config:
            # Use model from config if specified, otherwise fall back to settings
            model = config.get("model") or settings.openai_model
            temperature = config.get("temperature", 0.7)
        else:
            model = settings.openai_model
            temperature = 0.7

        _llm_cache[agent_id] = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=True,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
        )

    return _llm_cache[agent_id]


async def _run_agent_node(
    state: AgentState,
    agent_id: str,
) -> dict[str, Any]:
    """Generic agent node execution.

    Args:
        state: Current graph state
        agent_id: ID of the agent to run

    Returns:
        State updates
    """
    config = get_agent_by_id(agent_id)
    if not config:
        log.error(f"Agent config not found: {agent_id}")
        return {
            "messages": [AIMessage(content="Agent configuration error.")],
            "current_agent": agent_id,
        }

    llm = get_llm_for_agent(agent_id)
    tools = get_agent_tools(agent_id)

    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    system_message = {"role": "system", "content": config["instructions"]}
    messages_with_system = [system_message] + list(state["messages"])

    log.info(f"Running agent: {agent_id} with {len(tools)} tools")

    log.info("=" * 60)
    log.info(f"DEBUG: Agent {agent_id} - Message history before LLM call:")
    for i, msg in enumerate(state["messages"]):
        msg_type = type(msg).__name__
        content_preview = str(getattr(msg, "content", ""))[:100]
        tool_calls = getattr(msg, "tool_calls", None)
        tool_call_id = getattr(msg, "tool_call_id", None)
        log.info(
            f"  [{i}] {msg_type}: content={content_preview!r}, "
            f"tool_calls={tool_calls}, tool_call_id={tool_call_id}"
        )
    log.info("=" * 60)

    try:
        response = await llm_with_tools.ainvoke(messages_with_system)

        response_tool_calls = getattr(response, "tool_calls", None)
        log.info(
            f"Agent {agent_id} response: content={str(response.content)[:100]!r}, "
            f"tool_calls={response_tool_calls}"
        )

        return {
            "messages": [response],
            "current_agent": agent_id,
        }
    except Exception as e:
        log.error(f"Error running agent {agent_id}: {e}")
        return {
            "messages": [AIMessage(content=f"Error: {str(e)}")],
            "current_agent": agent_id,
        }


async def general_agent(state: AgentState) -> dict[str, Any]:
    """General agent - entry point and triage."""
    return await _run_agent_node(state, "general-agent")


async def regulation_agent(state: AgentState) -> dict[str, Any]:
    """Regulation analysis specialist agent."""
    return await _run_agent_node(state, "regulation-agent")


async def reporting_agent(state: AgentState) -> dict[str, Any]:
    """HAP inspection report specialist agent."""
    return await _run_agent_node(state, "reporting-agent")


async def history_agent(state: AgentState) -> dict[str, Any]:
    """Company and inspection history specialist agent."""
    return await _run_agent_node(state, "history-agent")


AGENT_NODES = {
    "general-agent": general_agent,
    "regulation-agent": regulation_agent,
    "reporting-agent": reporting_agent,
    "history-agent": history_agent,
}
