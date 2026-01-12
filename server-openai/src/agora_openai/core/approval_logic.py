from typing import Any

from agora_openai.common.schemas import ToolCall

HIGH_RISK_TOOL_PATTERNS = [
    "delete",
    "remove",
    "destroy",
    "drop",
    "submit_final",
    "approve_compliance",
    "publish_report",
    "certify",
]

# Tools that ALWAYS require approval regardless of parameters
ALWAYS_APPROVE_TOOLS = {
    "generate_final_report",
}

HIGH_RISK_PARAMETERS = {
    "amount": 10000,
    "scope": ["company_wide", "global"],
}


def requires_human_approval(
    tool_calls: list[ToolCall],
    context: dict[str, Any],
) -> tuple[bool, str | None, str]:
    """Determine if tool execution requires human approval.

    Pure business logic - no I/O.

    Args:
        tool_calls: List of tool calls to evaluate
        context: Additional context for decision making

    Returns:
        Tuple of (requires_approval, reason, risk_level)
    """
    for tool_call in tool_calls:
        tool_name_lower = tool_call.tool_name.lower()

        # Check specific tools that always require approval
        # We use endswith to handle potential SDK prefixes (e.g. reporting_generate_final_report)
        if any(tool_name_lower.endswith(t) for t in ALWAYS_APPROVE_TOOLS):
            return (
                True,
                f"Critical operation requires approval: {tool_call.tool_name}",
                "critical",
            )

        for pattern in HIGH_RISK_TOOL_PATTERNS:
            if pattern in tool_name_lower:
                return (
                    True,
                    f"High-risk operation detected: {tool_call.tool_name}",
                    "high",
                )

        params = tool_call.parameters or {}
        if "amount" in params and params["amount"] > HIGH_RISK_PARAMETERS["amount"]:
            return True, f"Amount exceeds threshold: {params['amount']}", "high"

        if "scope" in params and params["scope"] in HIGH_RISK_PARAMETERS["scope"]:
            return True, "Company-wide scope requires approval", "high"

    return False, None, "low"
