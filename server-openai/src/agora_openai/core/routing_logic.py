from pydantic import BaseModel, Field
from typing import Literal


class AgentSelection(BaseModel):
    """Structured output for intelligent agent routing."""
    selected_agent: Literal[
        "general-agent",
        "regulation-agent",
        "reporting-agent",
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

Analyze the user's request and select the most appropriate agent:

**general-agent** (DEFAULT - use this most often):
- General questions and greetings
- Multi-step inspection workflows
- "Start inspectie" commands
- "Geef me het dossier" requests
- Questions requiring multiple tools/domains
- Clarifying questions in conversations
- Coordinating complex inspections
- Synthesizing information from multiple sources
- ALWAYS use for inspection start/coordination

**regulation-agent** (only for SPECIFIC regulation questions):
 
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

**history-agent**:
- Company existence verification (KVK number)
- Inspection history for companies (includes company details)
- Past violations and trends
- Repeat violation checks
- Follow-up action status
- Inspector search and past inspections
- Will respond in DUTCH with company and historical analysis

Consider:
1. Primary topic and domain
2. Required expertise level
3. Whether multiple agents might be needed
4. User's apparent intent

Return your selection with reasoning and confidence score."""

