"""Handoff tools and agent tool configuration for LangGraph orchestration."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool, tool

log = logging.getLogger(__name__)


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
        log.info(
            f"{agent_id} gets handoff tools: transfer_to_history, "
            "transfer_to_regulation, transfer_to_reporting"
        )
    else:
        tools.append(transfer_to_general)
        log.info(f"{agent_id} gets transfer_to_general tool")

    mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
    for server_name in mcp_server_names:
        if server_name in mcp_tools_by_server:
            mcp_tools = mcp_tools_by_server[server_name]
            tools.extend(mcp_tools)
            tool_names = [getattr(t, "name", str(t)) for t in mcp_tools]
            log.info(f"{agent_id} gets MCP tools from {server_name}: {tool_names}")

    log.info(f"{agent_id} total tools: {len(tools)}")
    return tools
