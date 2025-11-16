import logging
from datetime import datetime
from typing import Optional
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Company Information & Inspection History", stateless_http=True)

# KVK API base URL for company lookups
KVK_BASE_URL = "https://opendata.kvk.nl/api/v1/hvds"

# Dutch language messages for better inspector experience
DUTCH_MESSAGES = {
    "invalid_kvk": "Ongeldig KVK nummer formaat. Moet 8 cijfers zijn.",
    "not_found": "Geen inspectiegeschiedenis gevonden voor dit bedrijf. Dit kan een eerste inspectie zijn.",
    "no_violations": "Er zijn geen overtredingen gevonden voor dit bedrijf.",
    "repeat_warning": "⚠️ WAARSCHUWING: Dit is een herhaalde overtreding.",
    "escalation_advised": "ESCALATIE_GEADVISEERD",
    "immediate_action": "DIRECTE_ACTIE_VEREIST",
    "no_history": "Geen geschiedenis gevonden. Dit lijkt een eerste inspectie te zijn.",
}

# Demo data for testing scenarios
# Using KVK numbers that can be looked up via KVK Lookup MCP server
DEMO_INSPECTIONS = {
    "92251854": {  # Restaurant Bella Rosa (Koen scenario)
        "company_name": "Restaurant Bella Rosa",
        "kvk_number": "92251854",
        "inspections": [
            {
                "inspection_id": "INS-2022-001234",
                "date": "2022-05-15",
                "inspector": "Jan Pietersen",
                "inspection_type": "hygiene_routine",
                "location": "Den Haag",
                "overall_score": "voldoende_met_opmerkingen",
                "violations": [
                    {
                        "violation_id": "VIO-2022-001234-01",
                        "category": "hygiene_measures",
                        "severity": "warning",
                        "description": "Onvoldoende hygiënemaatregelen in de keuken",
                        "specific_finding": "Schoonmaakschema niet volledig ingevuld, keukenvloer had vlekken",
                        "regulation": "Hygiënecode Horeca artikel 4.2",
                        "regulation_article": "Artikel 4.2 - Hygiënische werkwijze",
                        "resolved": False,
                        "follow_up_required": True,
                        "follow_up_date": "2022-08-15",
                        "follow_up_completed": False
                    }
                ],
                "notes": "Bedrijfsleider was coöperatief maar leek niet volledig op de hoogte van alle hygiënevoorschriften."
            },
            {
                "inspection_id": "INS-2020-005432",
                "date": "2020-09-10",
                "inspector": "Maria de Vries",
                "inspection_type": "hygiene_routine",
                "location": "Den Haag",
                "overall_score": "voldoende",
                "violations": [],
                "notes": "Geen bijzonderheden. Restaurant voldeed aan alle eisen."
            }
        ]
    },
    "92262856": {  # SpeelgoedPlaza (Fatima scenario)
        "company_name": "SpeelgoedPlaza Den Haag",
        "kvk_number": "92262856",
        "inspections": [
            {
                "inspection_id": "INS-2023-005678",
                "date": "2023-08-22",
                "inspector": "Maria de Vries",
                "inspection_type": "product_safety",
                "location": "Den Haag",
                "overall_score": "voldoende_met_opmerkingen",
                "violations": [
                    {
                        "violation_id": "VIO-2023-005678-01",
                        "category": "product_labeling",
                        "severity": "warning",
                        "description": "Producten zonder Nederlandstalige gebruiksaanwijzing",
                        "specific_finding": "8 speelgoedartikelen zonder NL handleiding aangetroffen",
                        "regulation": "Speelgoedrichtlijn 2009/48/EG artikel 11",
                        "regulation_article": "Artikel 11 - Waarschuwingen en veiligheidsinformatie",
                        "products_affected": [
                            "Bouwset Galaxy Explorer (EAN: 8712345678901)",
                            "Knuffel Beer XL (EAN: 8712345678902)"
                        ],
                        "resolved": True,
                        "resolution_date": "2023-09-15",
                        "resolution_notes": "Bedrijf heeft alle producten voorzien van NL handleiding",
                        "follow_up_required": False
                    }
                ],
                "notes": "Winkelmanager was coöperatief en heeft direct actie ondernomen."
            }
        ]
    },
    "34084173": {  # Slagerij de Boer (Jan scenario)
        "company_name": "Slagerij de Boer",
        "kvk_number": "34084173",
        "inspections": [
            {
                "inspection_id": "INS-2021-009876",
                "date": "2021-11-10",
                "inspector": "Kees Bakker",
                "inspection_type": "food_safety_labeling",
                "location": "Groningen",
                "overall_score": "onvoldoende",
                "violations": [
                    {
                        "violation_id": "VIO-2021-009876-01",
                        "category": "food_labeling",
                        "severity": "warning",
                        "description": "Onvolledige ingrediëntenvermelding bij zelfgemaakte vleeswaren",
                        "specific_finding": "5 producten zonder volledige ingrediëntenlijst: rookworst, leverworst, gehaktballen",
                        "regulation": "EU Verordening 1169/2011 artikel 9",
                        "regulation_article": "Artikel 9 - Verplichte vermeldingen",
                        "resolved": False,
                        "follow_up_required": True,
                        "follow_up_date": "2022-02-10",
                        "follow_up_completed": False,
                        "follow_up_notes": "Bedrijf heeft aangegeven labels te zullen aanpassen maar follow-up inspectie heeft niet plaatsgevonden"
                    }
                ],
                "notes": "Eigenaar gaf aan 'altijd zo gewerkt te hebben' en vond etikettering overdreven voor lokale klanten."
            },
            {
                "inspection_id": "INS-2019-003421",
                "date": "2019-06-15",
                "inspector": "Kees Bakker",
                "inspection_type": "hygiene_routine",
                "location": "Groningen",
                "overall_score": "voldoende",
                "violations": [],
                "notes": "Geen bijzonderheden. Hygiëne was op orde."
            }
        ]
    },
    # Additional demo company for testing
    "92267548": {
        "company_name": "Café Het Bruine Paard",
        "kvk_number": "92267548",
        "inspections": [
            {
                "inspection_id": "INS-2024-001111",
                "date": "2024-01-20",
                "inspector": "Sophie van Dijk",
                "inspection_type": "hygiene_routine",
                "location": "Amsterdam",
                "overall_score": "goed",
                "violations": [],
                "notes": "Uitstekende hygiëne. Alle procedures zijn op orde."
            }
        ]
    }
}


# ============================================================================
# COMPANY INFORMATION TOOLS (KVK Integration)
# ============================================================================

@mcp.tool()
async def check_company_exists(kvk_number: str) -> dict:
    """Check if a company exists in the KVK register.
    
    Use this as the first step when an inspector provides a KVK number.
    Verifies the company exists before retrieving detailed information.
    
    Args:
        kvk_number: 8-digit KVK (Chamber of Commerce) number
    
    Returns:
        Dictionary with exists status and basic validation
    """
    logger.info(f"Checking existence for KVK number: {kvk_number}")
    
    try:
        if not kvk_number.isdigit() or len(kvk_number) != 8:
            return {
                "status": "error",
                "exists": False,
                "error": "KVK number must be exactly 8 digits",
                "code": "INVALID_FORMAT"
            }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{KVK_BASE_URL}/basisbedrijfsgegevens/kvknummer/{kvk_number}"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "success",
                    "exists": True,
                    "kvk_number": kvk_number,
                    "active": data.get("actief") == "J",
                }
            elif response.status_code == 404:
                return {
                    "status": "success",
                    "exists": False,
                    "kvk_number": kvk_number,
                    "message": "Company not found in KVK register"
                }
            else:
                return {
                    "status": "error",
                    "exists": False,
                    "error": f"KVK API returned status {response.status_code}",
                    "code": "API_ERROR"
                }
                
    except httpx.TimeoutException:
        logger.error(f"Timeout checking company: {kvk_number}")
        return {
            "status": "error",
            "exists": False,
            "error": "Request timed out",
            "code": "TIMEOUT"
        }
    except Exception as e:
        logger.error(f"Error checking company {kvk_number}: {e}")
        return {
            "status": "error",
            "exists": False,
            "error": str(e),
            "code": "INTERNAL_ERROR"
        }


# ============================================================================
# INSPECTION HISTORY TOOLS
# ============================================================================


@mcp.tool()
async def get_inspection_history(kvk_number: str, limit: int = 10) -> dict:
    """
    Haal inspectiegeschiedenis op voor een bedrijf op basis van KVK nummer.
    
    Geeft een lijst van eerdere inspecties inclusief data, inspecteurs, bevindingen en overtredingen.
    Handig voor het begrijpen van het nalevingsverleden van een bedrijf.
    """
    logger.info(f"Getting inspection history for KVK: {kvk_number}")
    
    if not kvk_number or len(kvk_number) != 8:
        return {
            "status": "error",
            "error": DUTCH_MESSAGES["invalid_kvk"],
            "kvk_number": kvk_number
        }
    
    company_data = DEMO_INSPECTIONS.get(kvk_number)
    
    if not company_data:
        return {
            "status": "not_found",
            "kvk_number": kvk_number,
            "message": DUTCH_MESSAGES["not_found"],
            "inspections": []
        }
    
    # Limit inspections
    inspections = company_data["inspections"][:limit]
    
    return {
        "status": "success",
        "kvk_number": kvk_number,
        "company_name": company_data["company_name"],
        "total_inspections": len(company_data["inspections"]),
        "returned_inspections": len(inspections),
        "inspections": inspections
    }


@mcp.tool()
async def get_company_violations(kvk_number: str, limit: int = 10, severity: Optional[str] = None) -> dict:
    """
    Get all violations for a company across all inspections.
    
    Filters can be applied by severity: 'warning', 'serious', 'minor'.
    Useful for identifying patterns of non-compliance.
    """
    logger.info(f"Getting violations for KVK: {kvk_number}, severity filter: {severity}")
    
    if not kvk_number or len(kvk_number) != 8:
        return {
            "status": "error",
            "error": "Invalid KVK number format. Must be 8 digits.",
            "kvk_number": kvk_number
        }
    
    company_data = DEMO_INSPECTIONS.get(kvk_number)
    
    if not company_data:
        return {
            "status": "not_found",
            "kvk_number": kvk_number,
            "message": "No violation history found for this company.",
            "violations": []
        }
    
    # Collect all violations across inspections
    all_violations = []
    for inspection in company_data["inspections"]:
        for violation in inspection["violations"]:
            # Add inspection context to each violation
            violation_with_context = {
                **violation,
                "inspection_id": inspection["inspection_id"],
                "inspection_date": inspection["date"],
                "inspector": inspection["inspector"]
            }
            all_violations.append(violation_with_context)
    
    # Filter by severity if provided
    if severity:
        all_violations = [v for v in all_violations if v["severity"] == severity]
    
    # Limit results
    violations = all_violations[:limit]
    
    return {
        "status": "success",
        "kvk_number": kvk_number,
        "company_name": company_data["company_name"],
        "total_violations": len(all_violations),
        "returned_violations": len(violations),
        "violations": violations,
        "severity_filter": severity
    }


@mcp.tool()
async def check_repeat_violation(kvk_number: str, violation_category: str) -> dict:
    """
    Check if a violation category has occurred before for this company.
    
    Returns whether this is a repeat violation and details of previous occurrences.
    Critical for determining enforcement escalation.
    
    Common categories: hygiene_measures, food_labeling, product_labeling, 
    temperature_control, pest_control, allergen_information
    """
    logger.info(f"Checking repeat violation for KVK: {kvk_number}, category: {violation_category}")
    
    if not kvk_number or len(kvk_number) != 8:
        return {
            "status": "error",
            "error": "Invalid KVK number format. Must be 8 digits.",
            "kvk_number": kvk_number
        }
    
    company_data = DEMO_INSPECTIONS.get(kvk_number)
    
    if not company_data:
        return {
            "status": "not_found",
            "kvk_number": kvk_number,
            "is_repeat": False,
            "message": "No history found. This appears to be a first inspection."
        }
    
    # Find all violations in this category
    matching_violations = []
    for inspection in company_data["inspections"]:
        for violation in inspection["violations"]:
            if violation["category"] == violation_category:
                matching_violations.append({
                    "violation_id": violation["violation_id"],
                    "inspection_date": inspection["date"],
                    "inspector": inspection["inspector"],
                    "description": violation["description"],
                    "severity": violation["severity"],
                    "resolved": violation["resolved"],
                    "regulation": violation["regulation"]
                })
    
    is_repeat = len(matching_violations) > 0
    
    result = {
        "status": "success",
        "kvk_number": kvk_number,
        "company_name": company_data["company_name"],
        "violation_category": violation_category,
        "is_repeat": is_repeat,
        "previous_occurrences": len(matching_violations),
        "previous_violations": matching_violations
    }
    
    if is_repeat:
        result["enforcement_recommendation"] = "ESCALATION_ADVISED"
        result["escalation_reason"] = f"This company has {len(matching_violations)} previous violation(s) in category '{violation_category}'"
        
        # Check if any previous violations are unresolved
        unresolved = [v for v in matching_violations if not v["resolved"]]
        if unresolved:
            result["unresolved_count"] = len(unresolved)
            result["enforcement_recommendation"] = "IMMEDIATE_ACTION_REQUIRED"
            result["escalation_reason"] += f". {len(unresolved)} violation(s) remain unresolved."
    
    return result


@mcp.tool()
async def get_follow_up_status(kvk_number: str, inspection_id: Optional[str] = None) -> dict:
    """
    Get follow-up status for inspections requiring additional action.
    
    If inspection_id is provided, returns status for that specific inspection.
    Otherwise returns all pending follow-ups for the company.
    """
    logger.info(f"Getting follow-up status for KVK: {kvk_number}, inspection: {inspection_id}")
    
    if not kvk_number or len(kvk_number) != 8:
        return {
            "status": "error",
            "error": "Invalid KVK number format. Must be 8 digits.",
            "kvk_number": kvk_number
        }
    
    company_data = DEMO_INSPECTIONS.get(kvk_number)
    
    if not company_data:
        return {
            "status": "not_found",
            "kvk_number": kvk_number,
            "message": "No inspection history found.",
            "follow_ups": []
        }
    
    follow_ups = []
    
    for inspection in company_data["inspections"]:
        # Filter by specific inspection if requested
        if inspection_id and inspection["inspection_id"] != inspection_id:
            continue
        
        for violation in inspection["violations"]:
            if violation.get("follow_up_required"):
                follow_up_info = {
                    "inspection_id": inspection["inspection_id"],
                    "inspection_date": inspection["date"],
                    "violation_id": violation["violation_id"],
                    "violation_category": violation["category"],
                    "violation_description": violation["description"],
                    "severity": violation["severity"],
                    "follow_up_date": violation.get("follow_up_date"),
                    "follow_up_completed": violation.get("follow_up_completed", False),
                    "resolved": violation["resolved"]
                }
                
                if "follow_up_notes" in violation:
                    follow_up_info["notes"] = violation["follow_up_notes"]
                
                # Calculate if follow-up is overdue
                if follow_up_info["follow_up_date"]:
                    follow_up_datetime = datetime.strptime(follow_up_info["follow_up_date"], "%Y-%m-%d")
                    is_overdue = datetime.now() > follow_up_datetime and not follow_up_info["follow_up_completed"]
                    follow_up_info["is_overdue"] = is_overdue
                
                follow_ups.append(follow_up_info)
    
    return {
        "status": "success",
        "kvk_number": kvk_number,
        "company_name": company_data["company_name"],
        "total_follow_ups": len(follow_ups),
        "follow_ups": follow_ups
    }


@mcp.tool()
async def search_inspections_by_inspector(inspector_name: str, limit: int = 20) -> dict:
    """
    Search for inspections conducted by a specific inspector.
    
    Useful for reviewing inspector workload and finding similar cases.
    """
    logger.info(f"Searching inspections by inspector: {inspector_name}")
    
    matching_inspections = []
    
    for kvk_number, company_data in DEMO_INSPECTIONS.items():
        for inspection in company_data["inspections"]:
            if inspector_name.lower() in inspection["inspector"].lower():
                matching_inspections.append({
                    "kvk_number": kvk_number,
                    "company_name": company_data["company_name"],
                    "inspection_id": inspection["inspection_id"],
                    "inspection_date": inspection["date"],
                    "inspector": inspection["inspector"],
                    "inspection_type": inspection["inspection_type"],
                    "overall_score": inspection["overall_score"],
                    "violation_count": len(inspection["violations"])
                })
    
    # Sort by date (newest first)
    matching_inspections.sort(key=lambda x: x["inspection_date"], reverse=True)
    
    # Limit results
    inspections = matching_inspections[:limit]
    
    return {
        "status": "success",
        "inspector_name": inspector_name,
        "total_found": len(matching_inspections),
        "returned_inspections": len(inspections),
        "inspections": inspections
    }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker health checks."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": "inspection-history",
            "timestamp": datetime.now().isoformat(),
            "demo_companies": len(DEMO_INSPECTIONS)
        },
        status_code=200
    )


@mcp.resource("server://info")
def server_info() -> str:
    """Server capabilities and information."""
    return f'''{{
        "name": "Inspection History",
        "version": "1.0.0",
        "description": "Mock inspection history database for AGORA demo",
        "mode": "demo",
        "demo_companies": {len(DEMO_INSPECTIONS)},
        "capabilities": [
            "get_inspection_history",
            "get_company_violations",
            "check_repeat_violation",
            "get_follow_up_status",
            "search_inspections_by_inspector"
        ],
        "demo_kvk_numbers": {list(DEMO_INSPECTIONS.keys())}
    }}'''


if __name__ == "__main__":
    logger.info("Starting Inspection History MCP server on http://0.0.0.0:8000")
    logger.info(f"Demo data loaded for {len(DEMO_INSPECTIONS)} companies")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")

