from pydantic import BaseModel, Field
from typing import Literal


class AgentSelection(BaseModel):
    """Structured output for intelligent agent routing."""
    selected_agent: Literal[
        "regulation-agent",
        "reporting-agent",
        "kvk-agent",
        "history-agent",
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


ROUTING_SYSTEM_PROMPT = """You are an intelligent routing system for AGORA compliance platform.

🇳🇱 CRITICAL: All selected agents will respond in Dutch to NVWA inspectors.

Analyze the user's request and select the most appropriate specialized agent:

**regulation-agent**: 
- Regulatory compliance questions
- Legal requirements and regulations
- Standards and certifications
- Import/export regulations
- Industry-specific rules
- Risk assessment and analysis
- Threat identification
- Security concerns
- Will respond in DUTCH about regulations

**reporting-agent**:
- Report generation (HAP inspection reports)
- Data extraction from conversations
- Report verification and validation
- PDF and JSON report creation
- Inspection documentation
- Will respond in DUTCH with report status

**kvk-agent**:
- Company information lookup (KVK number)
- Company existence verification
- Business activities (SBI codes)
- Company active status checks
- Contact and location details
- Will respond in DUTCH with company information

**history-agent**:
- Inspection history for companies
- Past violations and trends
- Repeat violation checks
- Follow-up action status
- Inspector search and past inspections
- Will respond in DUTCH with historical analysis

Consider:
1. Primary topic and domain
2. Required expertise level
3. Whether multiple agents might be needed
4. User's apparent intent

Return your selection with reasoning and confidence score."""

