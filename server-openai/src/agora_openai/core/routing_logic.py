from pydantic import BaseModel, Field
from typing import Literal


class AgentSelection(BaseModel):
    """Structured output for intelligent agent routing."""
    selected_agent: Literal[
        "regulation-agent",
        "risk-agent",
        "reporting-agent",
    ] = Field(description="The most appropriate agent for this request")
    
    reasoning: str = Field(
        description="Brief explanation of why this agent was selected"
    )
    
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this selection"
    )
    
    requires_multiple_agents: bool = Field(
        default=False,
        description="Whether this request requires multiple specialized agents"
    )
    
    suggested_follow_up_agents: list[str] = Field(
        default_factory=list,
        description="Additional agents to consult if needed"
    )


ROUTING_SYSTEM_PROMPT = """You are an intelligent routing system for a compliance platform.

Analyze the user's request and select the most appropriate specialized agent:

**regulation-agent**: 
- Regulatory compliance questions
- Legal requirements
- Standards and certifications
- Import/export regulations
- Industry-specific rules

**risk-agent**:
- Risk assessment and analysis
- Threat identification
- Vulnerability assessment
- Security concerns
- Incident analysis

**reporting-agent**:
- Report generation
- Data analysis and visualization
- Compliance summaries
- Trend analysis
- Performance metrics

Consider:
1. Primary topic and domain
2. Required expertise level
3. Whether multiple agents might be needed
4. User's apparent intent

Return your selection with reasoning and confidence score."""

