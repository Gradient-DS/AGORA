import json
import logging
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Regulation Analysis Server", stateless_http=True)

MOCK_REGULATIONS = {
    "food_safety": [
        {
            "id": "REG-FS-001",
            "title": "Temperature Control Requirements for Perishable Foods",
            "text": "All perishable food items must be stored at temperatures below 7°C for refrigerated items and below -18°C for frozen items. Regular temperature monitoring and documentation is required.",
            "url": "https://nvwa.nl/regulations/food-safety/temperature-control"
        },
        {
            "id": "REG-FS-002",
            "title": "HACCP Implementation Guidelines",
            "text": "Food business operators must implement and maintain a Hazard Analysis and Critical Control Points (HACCP) system. This includes identifying critical control points, establishing critical limits, and maintaining records.",
            "url": "https://nvwa.nl/regulations/food-safety/haccp"
        },
        {
            "id": "REG-FS-003",
            "title": "Allergen Labeling Requirements",
            "text": "All packaged food products must clearly label the presence of the 14 major allergens: cereals containing gluten, crustaceans, eggs, fish, peanuts, soybeans, milk, nuts, celery, mustard, sesame, sulphites, lupin, and molluscs.",
            "url": "https://nvwa.nl/regulations/food-safety/allergens"
        }
    ],
    "product_safety": [
        {
            "id": "REG-PS-001",
            "title": "General Product Safety Directive",
            "text": "All products placed on the market must be safe under normal or reasonably foreseeable conditions of use. Producers must provide consumers with relevant information to assess risks.",
            "url": "https://nvwa.nl/regulations/product-safety/general"
        },
        {
            "id": "REG-PS-002",
            "title": "CE Marking Requirements",
            "text": "Products subject to EU harmonization legislation must bear CE marking before being placed on the market. This indicates conformity with applicable requirements.",
            "url": "https://nvwa.nl/regulations/product-safety/ce-marking"
        }
    ],
    "animal_welfare": [
        {
            "id": "REG-AW-001",
            "title": "Transport of Live Animals",
            "text": "Animals must be transported in a way that does not cause injury or unnecessary suffering. Transport time must be minimized and appropriate rest, food, and water must be provided.",
            "url": "https://nvwa.nl/regulations/animal-welfare/transport"
        }
    ]
}


@mcp.tool
async def lookup_regulation_articles(domain: str, keywords: list[str]) -> dict:
    """Search for relevant regulation articles by domain and keywords.
    
    Args:
        domain: Regulation domain ('food_safety', 'product_safety', 'animal_welfare')
        keywords: Keywords to search for in regulations
    """
    if domain not in MOCK_REGULATIONS:
        return {
            "error": f"Unknown domain: {domain}",
            "available_domains": list(MOCK_REGULATIONS.keys())
        }
    
    regulations = MOCK_REGULATIONS[domain]
    matching = []
    
    for reg in regulations:
        text_lower = (reg["title"] + " " + reg["text"]).lower()
        if any(keyword.lower() in text_lower for keyword in keywords):
            matching.append(reg)
    
    return {
        "domain": domain,
        "keywords": keywords,
        "found": len(matching),
        "regulations": matching
    }


@mcp.tool
async def analyze_document(document_uri: str, analysis_type: str) -> dict:
    """Analyze a document for summary, risks, or non-compliance issues.
    
    Args:
        document_uri: URI or path to the document to analyze
        analysis_type: Type of analysis ('summary', 'risks', 'noncompliance')
    """
    return {
        "document_uri": document_uri,
        "analysis_type": analysis_type,
        "result": f"Mock analysis of type '{analysis_type}' for document: {document_uri}",
        "findings": [
            "This is a mock analysis result",
            "In production, this would analyze the actual document"
        ]
    }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "regulation-analysis",
        "timestamp": datetime.now().isoformat()
    }, status_code=200)


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "Regulation Analysis Server",
        "version": "1.0.0",
        "description": "Provides regulation lookups and document analysis",
        "capabilities": {
            "tools": ["lookup_regulation_articles", "analyze_document"],
            "resources": ["server://info"]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    logger.info("Starting Regulation Analysis MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
