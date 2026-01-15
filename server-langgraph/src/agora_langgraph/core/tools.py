"""Handoff tools and agent tool configuration for LangGraph orchestration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, StructuredTool, tool
from langgraph.types import interrupt

if TYPE_CHECKING:
    from agora_langgraph.adapters.user_manager import UserManager

log = logging.getLogger(__name__)


# Module-level reference to UserManager (set during graph build)
_user_manager: "UserManager | None" = None


def set_user_manager(user_manager: "UserManager | None") -> None:
    """Set the UserManager instance for settings tools."""
    global _user_manager
    _user_manager = user_manager
    log.info(f"UserManager set: {user_manager is not None}")


@tool
async def transfer_to_history() -> str:
    """Transfer the conversation to the Company and Inspection History Specialist.

    Use this when the user asks about:
    - Company information or KVK numbers
    - Inspection history
    - Past violations
    - Company verification
    """
    return "Transferring to history-agent"


@tool
async def transfer_to_regulation() -> str:
    """Transfer the conversation to the Regulation Analysis Expert.

    Use this when the user asks about:
    - Regulations and rules
    - Compliance requirements
    - Legal requirements
    - Regulatory questions
    """
    return "Transferring to regulation-agent"


@tool
async def transfer_to_reporting() -> str:
    """Transfer the conversation to the HAP Inspection Report Specialist.

    Use this when the user wants to:
    - Generate an inspection report
    - Create documentation
    - Finalize an inspection
    """
    return "Transferring to reporting-agent"


@tool
async def transfer_to_general() -> str:
    """Transfer the conversation back to the General Assistant.

    Use this when:
    - The specialist task is complete
    - The user has a general question
    - A handoff to another specialist is needed
    """
    return "Transferring to general-agent"


@tool
def request_clarification(questions: list[dict[str, Any]]) -> str:
    """Request clarification from the user during report creation.

    Use this tool when you need additional information from the inspector
    to complete the report. The graph will pause and wait for the user's
    response before continuing.

    Args:
        questions: List of question objects from verify_inspection_data tool.
                   Each has 'question', 'field', 'importance', and optional 'options'.

    Returns:
        The user's response to the questions.
    """
    # Format questions for display
    formatted = []
    for i, q in enumerate(questions, 1):
        formatted.append(f"{i}. {q.get('question', '')}")

    question_text = "\n".join(formatted)

    # This will pause the graph and return the user's response when resumed
    user_response = interrupt({
        "type": "clarification_request",
        "questions": questions,
        "display_text": question_text,
    })

    return user_response


async def _update_user_settings_impl(
    user_id: str,
    spoken_text_type: str | None = None,
    interaction_mode: str | None = None,
) -> str:
    """Implementation of update_user_settings that uses the module-level UserManager.

    Args:
        user_id: The ID of the user whose settings to update
        spoken_text_type: Set to 'dictate' for full text reading or 'summarize' for
                         AI-generated TTS summaries. Leave empty to not change.
        interaction_mode: Set to 'feedback' for active suggestions or 'listen' for
                         passive note-taking. Leave empty to not change.

    Returns:
        Confirmation message with the updated settings
    """
    if not _user_manager:
        return "Error: Instellingen service is niet beschikbaar."

    if not user_id:
        return "Error: Geen gebruikers-ID opgegeven. Kan instellingen niet bijwerken."

    # Validate spoken_text_type
    valid_spoken_types = {"dictate", "summarize"}
    if spoken_text_type and spoken_text_type not in valid_spoken_types:
        return (
            f"Error: Ongeldige waarde '{spoken_text_type}' voor spraakweergave. "
            f"Geldige opties: 'dictate' (dicteren) of 'summarize' (samenvatten)."
        )

    # Validate interaction_mode
    valid_interaction_modes = {"feedback", "listen"}
    if interaction_mode and interaction_mode not in valid_interaction_modes:
        return (
            f"Error: Ongeldige waarde '{interaction_mode}' voor interactiemodus. "
            f"Geldige opties: 'feedback' (actief meedenken) of 'listen' (alleen noteren)."
        )

    # Build updates dict with only provided values
    updates: dict[str, Any] = {}
    if spoken_text_type:
        updates["spoken_text_type"] = spoken_text_type
    if interaction_mode:
        updates["interaction_mode"] = interaction_mode

    if not updates:
        return "Geen instellingen om bij te werken opgegeven."

    try:
        await _user_manager.update_preferences(user_id, updates)

        # Build confirmation message
        changes = []
        if spoken_text_type:
            mode_nl = "dicteren" if spoken_text_type == "dictate" else "samenvatten"
            changes.append(f"spraakweergave naar '{mode_nl}'")
        if interaction_mode:
            mode_nl = "feedback" if interaction_mode == "feedback" else "luisteren"
            changes.append(f"interactiemodus naar '{mode_nl}'")

        return f"Instellingen bijgewerkt: {', '.join(changes)}."

    except Exception as e:
        log.error(f"Failed to update user settings: {e}")
        return f"Error: Kon instellingen niet bijwerken: {e}"


def create_update_user_settings_tool() -> StructuredTool:
    """Create the update_user_settings tool with proper schema."""
    return StructuredTool.from_function(
        coroutine=_update_user_settings_impl,
        name="update_user_settings",
        description=(
            "Update user preferences/settings. Use this when the user wants to change "
            "their settings like speech mode (dictate vs summarize). "
            "The user_id should be obtained from the conversation context metadata."
        ),
    )


HANDOFF_TOOLS = [
    transfer_to_history,
    transfer_to_regulation,
    transfer_to_reporting,
    transfer_to_general,
]


AGENT_MCP_MAPPING = {
    "general-agent": [],
    "regulation-agent": ["regulation"],
    "reporting-agent": ["reporting"],
    "history-agent": ["history"],
}


def get_tools_for_agent(
    agent_id: str,
    mcp_tools_by_server: dict[str, list[BaseTool]],
) -> list[Any]:
    """Get the appropriate tools for an agent.

    Args:
        agent_id: Agent identifier
        mcp_tools_by_server: MCP tools organized by server (from MCPClientManager)

    Returns:
        List of tools for the agent
    """
    tools: list[Any] = []

    if agent_id == "general-agent":
        tools.extend(
            [transfer_to_history, transfer_to_regulation, transfer_to_reporting]
        )
        # Add settings tool for general-agent
        settings_tool = create_update_user_settings_tool()
        tools.append(settings_tool)
        log.info(
            f"{agent_id} gets handoff tools: transfer_to_history, "
            "transfer_to_regulation, transfer_to_reporting + update_user_settings"
        )
    elif agent_id == "reporting-agent":
        # Reporting agent gets the clarification tool for multi-turn workflows
        tools.append(request_clarification)
        log.info(f"{agent_id} gets request_clarification tool")
    # Specialist agents only get their MCP tools - no transfer_to_general
    # They provide the final answer and don't need to hand back

    mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
    for server_name in mcp_server_names:
        if server_name in mcp_tools_by_server:
            mcp_tools = mcp_tools_by_server[server_name]
            tools.extend(mcp_tools)
            tool_names = [getattr(t, "name", str(t)) for t in mcp_tools]
            log.info(f"{agent_id} gets MCP tools from {server_name}: {tool_names}")

    log.info(f"{agent_id} total tools: {len(tools)}")
    return tools
