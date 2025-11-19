from common.schemas import ToolCall
from agora_openai.core.approval_logic import requires_human_approval


def test_high_risk_tool_pattern():
    """Test high-risk tool pattern detection."""
    tool_calls = [
        ToolCall(tool_name="delete_company_data", parameters={}),
    ]

    requires_approval, reason = requires_human_approval(tool_calls, {})

    assert requires_approval
    assert "High-risk operation" in reason


def test_high_amount_threshold():
    """Test high amount threshold detection."""
    tool_calls = [
        ToolCall(tool_name="process_payment", parameters={"amount": 20000}),
    ]

    requires_approval, reason = requires_human_approval(tool_calls, {})

    assert requires_approval
    assert "threshold" in reason.lower()


def test_company_wide_scope():
    """Test company-wide scope detection."""
    tool_calls = [
        ToolCall(tool_name="update_policy", parameters={"scope": "company_wide"}),
    ]

    requires_approval, reason = requires_human_approval(tool_calls, {})

    assert requires_approval
    assert "scope" in reason.lower()


def test_safe_tool_call():
    """Test safe tool call doesn't require approval."""
    tool_calls = [
        ToolCall(tool_name="search_regulations", parameters={"query": "FDA"}),
    ]

    requires_approval, reason = requires_human_approval(tool_calls, {})

    assert not requires_approval
    assert reason is None


def test_multiple_tool_calls():
    """Test multiple tool calls with one high-risk."""
    tool_calls = [
        ToolCall(tool_name="search_regulations", parameters={}),
        ToolCall(tool_name="delete_record", parameters={}),
        ToolCall(tool_name="generate_report", parameters={}),
    ]

    requires_approval, reason = requires_human_approval(tool_calls, {})

    assert requires_approval
    assert "delete_record" in reason
