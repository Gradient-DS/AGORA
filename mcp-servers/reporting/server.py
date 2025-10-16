import json
import logging
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Reporting Server", stateless_http=True)

MOCK_REPORTS = {}
REPORT_COUNTER = 1


@mcp.tool
async def generate_inspection_report(
    company_id: str,
    inspection_data: dict,
    history: list[dict],
    notes: str = ""
) -> dict:
    """Generate a draft inspection report based on inspection data, history, and notes.
    
    Args:
        company_id: Company identifier
        inspection_data: Current inspection findings and observations
        history: Historical inspection records
        notes: Additional notes from the inspector
    """
    global REPORT_COUNTER, MOCK_REPORTS
    
    report_id = f"REP-{REPORT_COUNTER:04d}"
    REPORT_COUNTER += 1
    
    inspection_date = inspection_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    inspection_type = inspection_data.get("type", "routine")
    findings = inspection_data.get("findings", [])
    
    observations_content = ""
    compliance_issues = []
    recommendations = []
    
    if isinstance(findings, list):
        for finding in findings:
            observations_content += f"• {finding}\n"
            if "violation" in str(finding).lower() or "non-compliant" in str(finding).lower():
                compliance_issues.append(finding)
    else:
        observations_content = str(findings)
    
    if compliance_issues:
        for issue in compliance_issues:
            recommendations.append(f"Corrective action required for: {issue}")
    else:
        recommendations.append("Continue current food safety practices")
        recommendations.append("Maintain regular temperature monitoring")
    
    if len(history) > 2:
        history_summary = f"Company has {len(history)} previous inspections on record. "
        recent_issues = [h for h in history if h.get("sanctions")]
        if recent_issues:
            history_summary += f"{len(recent_issues)} previous inspection(s) resulted in sanctions."
        else:
            history_summary += "No significant compliance issues in recent history."
    else:
        history_summary = "Limited inspection history available for this company."
    
    report_text = f"""NVWA INSPECTION REPORT
{'=' * 50}

Report ID: {report_id}
Company ID: {company_id}
Inspection Date: {inspection_date}
Inspection Type: {inspection_type.upper()}

OBSERVATIONS:
{observations_content}

COMPLIANCE ASSESSMENT:
{history_summary}

RECOMMENDATIONS:
{chr(10).join(f"• {rec}" for rec in recommendations)}

INSPECTOR NOTES:
{notes if notes else "(No additional notes)"}

FOLLOW-UP REQUIRED: {"YES" if compliance_issues else "NO"}
"""
    
    report = {
        "report_id": report_id,
        "company_id": company_id,
        "inspection_date": inspection_date,
        "inspection_type": inspection_type,
        "report_text": report_text,
        "compliance_issues": compliance_issues,
        "recommendations": recommendations,
        "requires_follow_up": len(compliance_issues) > 0
    }
    
    MOCK_REPORTS[report_id] = report
    
    return report


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "reporting",
        "timestamp": datetime.now().isoformat()
    }, status_code=200)


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "Reporting Server",
        "version": "1.0.0",
        "description": "Generates inspection reports",
        "capabilities": {
            "tools": ["generate_inspection_report"],
            "resources": ["server://info"]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    logger.info("Starting Reporting MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
