import pytest
from agora_openai.core.routing_logic import AgentSelection


def test_agent_selection_schema():
    """Test agent selection schema validation."""
    selection = AgentSelection(
        selected_agent="regulation-agent",
        reasoning="This is a regulatory compliance question",
        confidence=0.95,
    )
    
    assert selection.selected_agent == "regulation-agent"
    assert selection.confidence == 0.95
    assert selection.requires_multiple_agents is False


def test_agent_selection_with_follow_ups():
    """Test agent selection with follow-up agents."""
    selection = AgentSelection(
        selected_agent="risk-agent",
        reasoning="Risk assessment required",
        confidence=0.85,
        requires_multiple_agents=True,
        suggested_follow_up_agents=["reporting-agent"],
    )
    
    assert selection.requires_multiple_agents
    assert len(selection.suggested_follow_up_agents) == 1


def test_confidence_bounds():
    """Test confidence score bounds."""
    with pytest.raises(Exception):
        AgentSelection(
            selected_agent="regulation-agent",
            reasoning="Test",
            confidence=1.5,
        )
    
    with pytest.raises(Exception):
        AgentSelection(
            selected_agent="regulation-agent",
            reasoning="Test",
            confidence=-0.1,
        )

