"""Tests for approval logic."""

import pytest
from agora_langgraph.common.schemas import ToolCall
from agora_langgraph.core.approval_logic import requires_human_approval


class TestApprovalLogic:
    """Tests for tool approval logic."""

    def test_low_risk_tool_no_approval(self):
        """Low risk tools should not require approval."""
        tool_calls = [ToolCall(tool_name="search_regulations", parameters={})]
        requires, reason, level = requires_human_approval(tool_calls, {})

        assert requires is False
        assert reason is None
        assert level == "low"

    def test_generate_final_report_requires_approval(self):
        """generate_final_report should always require approval."""
        tool_calls = [ToolCall(tool_name="generate_final_report", parameters={})]
        requires, reason, level = requires_human_approval(tool_calls, {})

        assert requires is True
        assert "Critical operation" in reason
        assert level == "critical"

    def test_delete_pattern_requires_approval(self):
        """Tools with 'delete' pattern should require approval."""
        tool_calls = [ToolCall(tool_name="delete_record", parameters={})]
        requires, reason, level = requires_human_approval(tool_calls, {})

        assert requires is True
        assert "High-risk operation" in reason
        assert level == "high"

    def test_high_amount_requires_approval(self):
        """High amounts should require approval."""
        tool_calls = [
            ToolCall(tool_name="process_payment", parameters={"amount": 15000})
        ]
        requires, reason, level = requires_human_approval(tool_calls, {})

        assert requires is True
        assert "Amount exceeds threshold" in reason
        assert level == "high"

    def test_company_wide_scope_requires_approval(self):
        """Company-wide scope should require approval."""
        tool_calls = [
            ToolCall(tool_name="update_settings", parameters={"scope": "company_wide"})
        ]
        requires, reason, level = requires_human_approval(tool_calls, {})

        assert requires is True
        assert "Company-wide" in reason
        assert level == "high"
