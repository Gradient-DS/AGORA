"""Agent node functions for LangGraph orchestration."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None  # type: ignore[assignment,misc]

from agora_langgraph.config import ProviderConfig, get_settings
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

# Exceptions that should trigger fallback to the next provider.
# In a cross-provider chain (different base URLs, models, and keys), any HTTP
# error from one provider may succeed on the next (e.g. Gemini-specific 400,
# model-not-found 404, rate limits 429, server errors 500+).
FALLBACK_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
)

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    FALLBACK_EXCEPTIONS = (
        *FALLBACK_EXCEPTIONS,
        APIStatusError,  # All HTTP errors (400, 401, 403, 404, 429, 500, etc.)
        APIConnectionError,
        APITimeoutError,
    )
except ImportError:
    pass

try:
    from google.api_core.exceptions import GoogleAPIError

    FALLBACK_EXCEPTIONS = (*FALLBACK_EXCEPTIONS, GoogleAPIError)
except ImportError:
    pass

_agent_tools: dict[str, list[Any]] = {}
_agent_llms_cache: dict[str, list[BaseChatModel]] = {}
_spoken_llms: list[BaseChatModel] | None = None

# Dedicated context window logger — writes to context_window.log
_context_log_path = Path(__file__).resolve().parents[3] / "context_window.log"
_context_logger = logging.getLogger("agora.context_window")
_context_logger.setLevel(logging.DEBUG)
_context_logger.propagate = False
if not _context_logger.handlers:
    _fh = logging.FileHandler(_context_log_path, mode="a", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _context_logger.addHandler(_fh)


def _log_context_window(
    call_site: str,
    agent_id: str,
    messages: list[Any],
    system_prompt_chars: int = 0,
) -> None:
    """Log a detailed breakdown of context window contents to context_window.log."""
    total_chars = system_prompt_chars
    msg_details: list[dict[str, Any]] = []

    if system_prompt_chars:
        msg_details.append({"role": "system", "chars": system_prompt_chars})

    for msg in messages:
        role = type(msg).__name__
        content = getattr(msg, "content", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        elif isinstance(content, list):
            # Google-style structured content
            content = json.dumps(content, ensure_ascii=False)
        elif not isinstance(content, str):
            content = str(content)

        chars = len(content)
        total_chars += chars

        detail: dict[str, Any] = {"role": role, "chars": chars}

        # Add tool-specific info
        if isinstance(msg, ToolMessage):
            detail["tool_name"] = getattr(msg, "name", "unknown")
        elif hasattr(msg, "tool_calls") and msg.tool_calls:
            detail["tool_calls"] = [tc.get("name", "?") for tc in msg.tool_calls]

        # Show preview for large messages
        if chars > 500:
            detail["preview"] = content[:200] + "..."

        msg_details.append(detail)

    # Count by role
    role_counts: dict[str, int] = {}
    role_chars: dict[str, int] = {}
    for d in msg_details:
        r = d["role"]
        role_counts[r] = role_counts.get(r, 0) + 1
        role_chars[r] = role_chars.get(r, 0) + d["chars"]

    summary = (
        f"\n{'='*80}\n"
        f"CONTEXT WINDOW — {call_site} | agent={agent_id}\n"
        f"{'='*80}\n"
        f"Total: {total_chars:,} chars | {len(messages)} messages\n"
        f"Breakdown by role:\n"
    )
    for role, count in role_counts.items():
        summary += f"  {role}: {count} msgs, {role_chars[role]:,} chars\n"

    summary += f"\nMessage details:\n"
    for i, d in enumerate(msg_details):
        line = f"  [{i}] {d['role']}: {d['chars']:,} chars"
        if "tool_name" in d:
            line += f" (tool: {d['tool_name']})"
        if "tool_calls" in d:
            line += f" (calls: {', '.join(d['tool_calls'])})"
        if "preview" in d:
            line += f"\n       preview: {d['preview']}"
        summary += line + "\n"

    summary += f"{'='*80}\n"
    _context_logger.info(summary)


def set_agent_tools(agent_id: str, tools: list[Any]) -> None:
    """Set tools for an agent."""
    _agent_tools[agent_id] = tools


def get_agent_tools(agent_id: str) -> list[Any]:
    """Get tools for an agent."""
    return _agent_tools.get(agent_id, [])


def _is_google_provider(base_url: str) -> bool:
    """Check if a base URL points to a Google API endpoint."""
    return "googleapis.com" in base_url


def _make_llm(provider: ProviderConfig, temperature: float) -> BaseChatModel:
    """Create an LLM instance from a provider config.

    Auto-detects Google providers from base_url and returns the appropriate
    ChatGoogleGenerativeAI or ChatOpenAI instance. Vertex AI providers
    (aiplatform.googleapis.com) use ADC for authentication.
    """
    if _is_google_provider(provider.base_url):
        if ChatGoogleGenerativeAI is None:
            raise ImportError(
                "langchain-google-genai is required for Google providers. "
                "Install it with: pip install langchain-google-genai>=4.0.0"
            )
        if provider.is_vertex:
            settings = get_settings()
            log.info(
                f"Creating Vertex AI LLM: {provider.model} "
                f"(project={settings.vertex_project}, location={settings.vertex_location})"
            )
            return ChatGoogleGenerativeAI(
                model=provider.model,
                temperature=temperature,
                streaming=True,
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location,
                max_retries=0,
            )
        return ChatGoogleGenerativeAI(
            model=provider.model,
            temperature=temperature,
            streaming=True,
            google_api_key=provider.api_key,
            max_retries=0,
        )
    return ChatOpenAI(
        model=provider.model,
        temperature=temperature,
        streaming=True,
        api_key=provider.api_key,  # type: ignore[arg-type]
        base_url=provider.base_url,
        max_retries=0,  # Disable built-in retries; fallback chain handles recovery
    )


def get_llms_for_agent(agent_id: str) -> list[BaseChatModel]:
    """Get LLM instances for an agent (primary + fallbacks).

    Returns a list where index 0 is the primary and the rest are fallbacks.
    Use build_fallback_chain() to wrap them after binding tools.
    """
    if agent_id not in _agent_llms_cache:
        settings = get_settings()
        config = get_agent_by_id(agent_id)
        temperature = config.get("temperature", 0.7) if config else 0.7
        providers = settings.agent_provider_chain

        _agent_llms_cache[agent_id] = [_make_llm(p, temperature) for p in providers]

        if len(providers) > 1:
            log.info(
                f"Agent {agent_id}: configured {len(providers)} providers "
                f"({', '.join(p.model for p in providers)})"
            )

    return _agent_llms_cache[agent_id]


def get_llms_for_spoken() -> list[BaseChatModel]:
    """Get LLM instances for spoken text generation (primary + fallbacks)."""
    global _spoken_llms
    if _spoken_llms is None:
        settings = get_settings()
        providers = settings.spoken_provider_chain

        _spoken_llms = [_make_llm(p, temperature=0.7) for p in providers]

        log.info(
            f"Spoken LLMs: {len(providers)} providers "
            f"({', '.join(p.model for p in providers)})"
        )

    return _spoken_llms


def build_fallback_chain(llms: Sequence[Runnable]) -> Runnable:  # type: ignore[type-arg]
    """Wrap a list of LLMs/runnables in a fallback chain.

    Args:
        llms: Sequence where index 0 is primary, rest are fallbacks.
              Can be raw ChatOpenAI or tool-bound versions.

    Returns:
        Single Runnable (with fallbacks if len > 1).
    """
    if len(llms) > 1:
        return llms[0].with_fallbacks(
            list(llms[1:]),
            exceptions_to_handle=FALLBACK_EXCEPTIONS,
        )
    return llms[0]


def get_llm_for_agent(agent_id: str) -> Runnable:  # type: ignore[type-arg]
    """Get LLM with fallback chain for agent (no tools bound)."""
    return build_fallback_chain(get_llms_for_agent(agent_id))


def get_llm_for_spoken() -> Runnable:  # type: ignore[type-arg]
    """Get LLM with fallback chain for spoken text."""
    return build_fallback_chain(get_llms_for_spoken())


def _filter_extra_tool_args(tool_calls: list[dict[str, Any]], tools: list[Any]) -> None:
    """Strip extra arguments from tool calls that aren't in the tool schema.

    Google Gemini doesn't support ``additionalProperties: false`` in JSON
    schemas, so it may add parameters the tool doesn't accept.  This mutates
    the tool_calls list in place, removing any unexpected arguments.
    """
    tool_schemas: dict[str, set[str]] = {}
    for tool in tools:
        schema = getattr(tool, "args_schema", None)
        if schema and hasattr(schema, "model_fields"):
            tool_schemas[tool.name] = set(schema.model_fields.keys())

    for tc in tool_calls:
        name = tc.get("name", "")
        args = tc.get("args")
        allowed = tool_schemas.get(name)
        if allowed and isinstance(args, dict):
            extra_keys = set(args.keys()) - allowed
            if extra_keys:
                log.warning(f"Stripping extra args from {name}: {extra_keys}")
                for key in extra_keys:
                    del args[key]


def _build_agent_messages(state: AgentState) -> list[BaseMessage]:
    """Build filtered message list for agent LLM invocation.

    Prior completed turns: only HumanMessages + final AI responses
    Current turn: everything (own tool calls, results, handoffs)

    This prevents cross-agent pollution — an agent doesn't need to see
    another agent's raw tool results when it already has the final answer.
    """
    raw = list(state["messages"])

    # Find the last completed turn boundary (last is_final_response AIMessage)
    last_final_idx = -1
    for i in range(len(raw) - 1, -1, -1):
        if (
            isinstance(raw[i], AIMessage)
            and raw[i].additional_kwargs.get("is_final_response")
        ):
            last_final_idx = i
            break

    if last_final_idx == -1:
        # No prior completed turns — this is the first turn, keep everything
        return raw

    # Prior history: only HumanMessages + final response AIMessages
    history: list[BaseMessage] = []
    for msg in raw[: last_final_idx + 1]:
        if isinstance(msg, HumanMessage):
            history.append(msg)
        elif (
            isinstance(msg, AIMessage)
            and msg.additional_kwargs.get("is_final_response")
        ):
            history.append(msg)
        # Skip: ToolMessages, AIMessages with tool_calls, raw agent responses

    # Current turn: everything after the last completed turn
    current_turn = raw[last_final_idx + 1 :]

    return history + current_turn


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

    llms = get_llms_for_agent(agent_id)
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
        bound: list[Runnable] = [llm.bind_tools(tools) for llm in llms]  # type: ignore[type-arg]
        llm_with_tools = build_fallback_chain(bound)
    else:
        llm_with_tools = build_fallback_chain(llms)

    # Build system message with optional user context
    instructions = config["instructions"]
    metadata = state.get("metadata", {})
    user_id = metadata.get("user_id")

    # Prepend buffer context if present (from listen mode)
    buffer_context = state.get("buffer_context", "")
    if buffer_context:
        instructions = f"{buffer_context}\n\n{instructions}"
        log.info(f"Injected buffer context ({len(buffer_context)} chars) into {agent_id}")

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

        session_id = state.get("session_id", "")

        context_parts = ["CURRENT USER CONTEXT:"]
        context_parts.append(f"- session_id: {session_id}")
        if user_name:
            context_parts.append(f"- inspector_name: {user_name}")
        if user_email:
            context_parts.append(f"- inspector_email: {user_email}")
        context_parts.append(f"- email_reports_enabled: {email_reports}")
        context_parts.append("")
        context_parts.append(
            "When calling generate_report, include inspector_name and inspector_email."
        )
        context_parts.append(
            "When calling generate_report, set send_email based on email_reports_enabled."
        )

        instructions = f"{instructions}\n\n" + "\n".join(context_parts)

    system_message = {"role": "system", "content": instructions}
    filtered_messages = _build_agent_messages(state)
    messages_with_system = [system_message] + filtered_messages

    # Log context window contents for debugging
    _log_context_window(
        call_site="agent_invoke",
        agent_id=agent_id,
        messages=filtered_messages,
        system_prompt_chars=len(instructions),
    )

    try:
        response = await llm_with_tools.ainvoke(messages_with_system)

        # Filter extra tool call arguments that aren't in the tool schema.
        # Google Gemini doesn't support additionalProperties: false, so it
        # may add parameters that the tool doesn't accept.
        if hasattr(response, "tool_calls") and response.tool_calls and tools:
            _filter_extra_tool_args(response.tool_calls, tools)

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
