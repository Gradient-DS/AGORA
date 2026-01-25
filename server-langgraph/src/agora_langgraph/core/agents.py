"""Agent node functions for LangGraph orchestration."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from agora_langgraph.config import get_settings
from agora_langgraph.core.agent_definitions import get_agent_by_id
from agora_langgraph.core.state import AgentState
from agora_langgraph.core.tools import AGENT_MCP_MAPPING

log = logging.getLogger(__name__)

# Friendly Dutch names for agents (used in error messages)
AGENT_FRIENDLY_NAMES = {
    "regulation-agent": "de Regelgeving Expert",
    "reporting-agent": "de Rapportage Specialist",
    "history-agent": "de Bedrijfshistorie Specialist",
}

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
            api_key=settings.openai_api_key.get_secret_value(),  # type: ignore[arg-type]
            base_url=settings.openai_base_url,
        )

    return _llm_cache[agent_id]


_spoken_llm: ChatOpenAI | None = None


def get_llm_for_spoken() -> ChatOpenAI:
    """Get LLM instance for spoken text generation.

    Uses separate config if LANGGRAPH_SPOKEN_* env vars are set,
    otherwise falls back to the default OpenAI config.
    """
    global _spoken_llm
    if _spoken_llm is None:
        settings = get_settings()

        # Use spoken-specific config if available, otherwise fall back to defaults
        model = settings.spoken_model or settings.openai_model
        base_url = settings.spoken_base_url or settings.openai_base_url
        api_key = (
            settings.spoken_api_key.get_secret_value()
            if settings.spoken_api_key
            else settings.openai_api_key.get_secret_value()
        )

        _spoken_llm = ChatOpenAI(
            model=model,
            temperature=0.7,
            streaming=True,
            api_key=api_key,  # type: ignore[arg-type]
            base_url=base_url,
        )

        log.info(f"Initialized spoken LLM: model={model}, base_url={base_url}")

    return _spoken_llm


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

    # Check if specialist agent is missing its required MCP tools (server down)
    required_mcp_servers = AGENT_MCP_MAPPING.get(agent_id, [])
    if required_mcp_servers and not tools:
        # This specialist agent needs MCP tools but has none - server is down
        friendly_name = AGENT_FRIENDLY_NAMES.get(agent_id, agent_id)
        log.warning(f"{agent_id} has no tools - MCP server(s) {required_mcp_servers} unavailable")
        error_message = (
            f"⚠️ **Service Niet Beschikbaar**\n\n"
            f"Helaas is {friendly_name} momenteel niet beschikbaar. "
            f"De achterliggende service is offline.\n\n"
            f"Probeer het later opnieuw of neem contact op met de beheerder "
            f"als het probleem aanhoudt."
        )
        return {
            "messages": [AIMessage(content=error_message)],
            "current_agent": agent_id,
        }

    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    # Build system message with optional user context
    instructions = config["instructions"]
    metadata = state.get("metadata", {})
    user_id = metadata.get("user_id")

    # Inject user_id into system message for general-agent so it can use settings tool
    if agent_id == "general-agent" and user_id:
        instructions = (
            f"{instructions}\n\n"
            f"CURRENT USER CONTEXT:\n"
            f"- user_id: {user_id}\n"
            f"Use this user_id when calling the update_user_settings tool."
        )

    # Inject user context for reporting-agent so it can include email info when generating reports
    if agent_id == "reporting-agent":
        user_email = metadata.get("user_email")
        user_name = metadata.get("user_name")
        email_reports = metadata.get("email_reports", True)

        context_parts = ["CURRENT USER CONTEXT:"]
        if user_name:
            context_parts.append(f"- inspector_name: {user_name}")
        if user_email:
            context_parts.append(f"- inspector_email: {user_email}")
        context_parts.append(f"- email_reports_enabled: {email_reports}")
        context_parts.append("")
        context_parts.append(
            "When calling start_inspection_report, include inspector_name and inspector_email."
        )
        context_parts.append(
            "When calling generate_final_report, set send_email based on email_reports_enabled."
        )

        instructions = f"{instructions}\n\n" + "\n".join(context_parts)

    system_message = {"role": "system", "content": instructions}
    messages_with_system = [system_message] + list(state["messages"])

    try:
        response = await llm_with_tools.ainvoke(messages_with_system)

        # Add agent_id to additional_kwargs for history tracking
        if hasattr(response, "additional_kwargs"):
            response.additional_kwargs["agent_id"] = agent_id

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
