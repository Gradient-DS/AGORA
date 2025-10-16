from typing import Any
from common.schemas import ToolCall


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

HIGH_RISK_PARAMETERS = {
    "amount": 10000,
    "scope": ["company_wide", "global"],
}


def requires_human_approval(
    tool_calls: list[ToolCall],
    context: dict[str, Any],
) -> tuple[bool, str | None]:
    """Determine if tool execution requires human approval.
    
    Pure business logic - no I/O.
    
    Args:
        tool_calls: List of tool calls to evaluate
        context: Additional context for decision making
    
    Returns:
        Tuple of (requires_approval, reason)
    """
    for tool_call in tool_calls:
        tool_name_lower = tool_call.tool_name.lower()
        
        for pattern in HIGH_RISK_TOOL_PATTERNS:
            if pattern in tool_name_lower:
                return True, f"High-risk operation detected: {tool_call.tool_name}"
        
        params = tool_call.parameters or {}
        if "amount" in params and params["amount"] > HIGH_RISK_PARAMETERS["amount"]:
            return True, f"Amount exceeds threshold: {params['amount']}"
        
        if "scope" in params and params["scope"] in HIGH_RISK_PARAMETERS["scope"]:
            return True, "Company-wide scope requires approval"
    
    return False, None

