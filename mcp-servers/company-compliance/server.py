import json
import logging
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Company Compliance Server", stateless_http=True)

MOCK_COMPANIES = {
    "C001": {
        "name": "De Verse Bakker BV",
        "address": "Hoofdstraat 123, 1234 AB Amsterdam",
        "permit_status": "active",
        "business_activities": ["bakery", "retail", "food_production"],
        "registration_date": "2015-03-15"
    },
    "C002": {
        "name": "FreshMart Supermarkt",
        "address": "Winkelcentrum 45, 5678 CD Rotterdam",
        "permit_status": "active",
        "business_activities": ["retail", "food_sales"],
        "registration_date": "2018-07-22"
    },
    "C003": {
        "name": "Import Foods International",
        "address": "Havenweg 789, 3000 EF Utrecht",
        "permit_status": "suspended",
        "business_activities": ["import", "wholesale", "food_distribution"],
        "registration_date": "2012-11-08"
    }
}

MOCK_INSPECTIONS = {
    "C001": [
        {
            "date": "2024-09-15",
            "type": "routine",
            "findings": "Minor temperature control issue in storage area",
            "sanctions": None
        },
        {
            "date": "2024-03-10",
            "type": "routine",
            "findings": "All regulations complied with",
            "sanctions": None
        }
    ],
    "C002": [
        {
            "date": "2024-08-22",
            "type": "complaint_follow_up",
            "findings": "Expired products found on shelf, inadequate stock rotation",
            "sanctions": "Warning issued, follow-up inspection scheduled"
        }
    ],
    "C003": [
        {
            "date": "2024-10-01",
            "type": "targeted",
            "findings": "Improper labeling on imported products, missing allergen information",
            "sanctions": "Administrative fine €5000, permit suspended pending corrective action"
        },
        {
            "date": "2024-06-15",
            "type": "routine",
            "findings": "Documentation incomplete for product origin verification",
            "sanctions": "Official warning"
        }
    ]
}


@mcp.tool
async def get_company_profile(company_id: str) -> dict:
    """Fetch core business, permit, and registration info for a company."""
    if company_id in MOCK_COMPANIES:
        return MOCK_COMPANIES[company_id]
    else:
        return {
            "error": "Company not found",
            "company_id": company_id,
            "message": f"No company profile exists for ID: {company_id}"
        }


@mcp.tool
async def fetch_inspection_history(company_id: str, limit: int = 10) -> dict:
    """Retrieve past inspection records for a company."""
    if company_id in MOCK_INSPECTIONS:
        records = MOCK_INSPECTIONS[company_id][:limit]
        return {"records": records}
    else:
        return {
            "records": [],
            "message": f"No inspection history found for company: {company_id}"
        }


@mcp.resource("company_profile://{company_id}")
async def get_company_resource(company_id: str) -> str:
    """Get company profile as a resource."""
    if company_id in MOCK_COMPANIES:
        return json.dumps(MOCK_COMPANIES[company_id], indent=2)
    return json.dumps({"error": "Company not found"}, indent=2)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "company-compliance",
        "timestamp": datetime.now().isoformat()
    }, status_code=200)


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "Company Compliance Server",
        "version": "1.0.0",
        "description": "Provides company profiles and inspection history",
        "capabilities": {
            "tools": ["get_company_profile", "fetch_inspection_history"],
            "resources": ["company_profile://{company_id}", "server://info"]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    logger.info("Starting Company Compliance MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
