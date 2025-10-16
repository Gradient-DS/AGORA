import json
import logging
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Risk Enforcement Server", stateless_http=True)

RISK_WEIGHTS = {
    "history": 0.35,
    "business_activities": 0.25,
    "region": 0.15,
    "compliance_record": 0.25
}

BUSINESS_ACTIVITY_RISKS = {
    "food_production": 0.8,
    "import": 0.75,
    "wholesale": 0.6,
    "retail": 0.5,
    "bakery": 0.6,
    "restaurant": 0.7,
    "catering": 0.75,
    "food_sales": 0.5,
    "food_distribution": 0.7
}

REGION_RISKS = {
    "amsterdam": 0.5,
    "rotterdam": 0.6,
    "utrecht": 0.5,
    "den_haag": 0.55,
    "eindhoven": 0.5,
    "border_region": 0.8,
    "port_area": 0.85
}


@mcp.tool
async def calculate_risk_score(
    history: list[dict],
    business_activities: list[str],
    region: str
) -> dict:
    """Calculate risk score based on history, business activities, and region.
    
    Args:
        history: Historical inspection records
        business_activities: List of business activities
        region: Geographic region of operation
    """
    region_normalized = region.lower().replace(" ", "_")
    
    history_score = 0.0
    if history:
        violations = sum(1 for h in history if h.get("sanctions"))
        history_score = min(violations / len(history), 1.0)
    
    activity_scores = []
    for activity in business_activities:
        activity_normalized = activity.lower().replace(" ", "_")
        risk = BUSINESS_ACTIVITY_RISKS.get(activity_normalized, 0.5)
        activity_scores.append(risk)
    
    if activity_scores:
        activity_score = sum(activity_scores) / len(activity_scores)
    else:
        activity_score = 0.5
    
    region_score = REGION_RISKS.get(region_normalized, 0.5)
    
    compliance_score = 1.0 - history_score
    
    total_risk = (
        history_score * RISK_WEIGHTS["history"] +
        activity_score * RISK_WEIGHTS["business_activities"] +
        region_score * RISK_WEIGHTS["region"] +
        (1.0 - compliance_score) * RISK_WEIGHTS["compliance_record"]
    )
    
    if total_risk < 0.3:
        risk_level = "LOW"
        recommendation = "Standard monitoring frequency"
    elif total_risk < 0.6:
        risk_level = "MEDIUM"
        recommendation = "Increased inspection frequency"
    else:
        risk_level = "HIGH"
        recommendation = "Priority for inspection and enforcement"
    
    return {
        "risk_score": round(total_risk, 2),
        "risk_level": risk_level,
        "components": {
            "history": round(history_score, 2),
            "business_activities": round(activity_score, 2),
            "region": round(region_score, 2),
            "compliance": round(compliance_score, 2)
        },
        "recommendation": recommendation,
        "calculated_at": datetime.now().isoformat()
    }


@mcp.tool
async def flag_for_enforcement(
    company_id: str,
    violation_id: str,
    severity: str,
    justification: str
) -> dict:
    """Flag a company for enforcement action based on violations.
    
    Args:
        company_id: Company identifier
        violation_id: Violation identifier
        severity: Severity level ('low', 'medium', 'high')
        justification: Justification for enforcement action
    """
    enforcement_id = f"ENF-{company_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    enforcement_actions = {
        "low": ["Warning letter", "Follow-up inspection in 3 months"],
        "medium": ["Official warning", "Administrative fine €500-€2000", "Follow-up inspection in 1 month"],
        "high": ["Permit suspension", "Administrative fine €2000-€10000", "Immediate corrective action required"]
    }
    
    actions = enforcement_actions.get(severity.lower(), enforcement_actions["medium"])
    
    return {
        "enforcement_id": enforcement_id,
        "company_id": company_id,
        "violation_id": violation_id,
        "severity": severity.upper(),
        "justification": justification,
        "recommended_actions": actions,
        "flagged_at": datetime.now().isoformat(),
        "status": "pending_review"
    }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "risk-enforcement",
        "timestamp": datetime.now().isoformat()
    }, status_code=200)


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "Risk Enforcement Server",
        "version": "1.0.0",
        "description": "Calculates risk scores and flags enforcement actions",
        "capabilities": {
            "tools": ["calculate_risk_score", "flag_for_enforcement"],
            "resources": ["server://info"]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    logger.info("Starting Risk Enforcement MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
