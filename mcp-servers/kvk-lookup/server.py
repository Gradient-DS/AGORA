import logging
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP
import httpx
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("KVK Lookup", stateless_http=True)

KVK_BASE_URL = "https://opendata.kvk.nl/api/v1/hvds"


@mcp.tool()
async def check_company_exists(kvk_number: str) -> dict:
    """Check if a company exists in the KVK register.
    
    Use this tool to verify if a KVK number is valid and the company exists.
    
    Args:
        kvk_number: 8-digit KVK (Chamber of Commerce) number
    
    Returns:
        Dictionary with existence status and basic info if found
    """
    logger.info(f"Checking existence for KVK number: {kvk_number}")
    
    try:
        if not kvk_number.isdigit() or len(kvk_number) != 8:
            return {
                "status": "error",
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
                    "legal_form": data.get("rechtsvormCode"),
                    "country": data.get("lidstaat")
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
                    "error": f"KVK API returned status {response.status_code}",
                    "code": "API_ERROR"
                }
                
    except httpx.TimeoutException:
        logger.error(f"Timeout checking KVK number: {kvk_number}")
        return {
            "status": "error",
            "error": "Request timed out",
            "code": "TIMEOUT"
        }
    except Exception as e:
        logger.error(f"Error checking KVK number {kvk_number}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "code": "INTERNAL_ERROR"
        }


@mcp.tool()
async def get_company_info(kvk_number: str) -> dict:
    """Get detailed company information from KVK register.
    
    Use this tool to retrieve comprehensive information about a company including
    legal form, activities, status, and more.
    
    Args:
        kvk_number: 8-digit KVK (Chamber of Commerce) number
    
    Returns:
        Dictionary with complete company information
    """
    logger.info(f"Getting company info for KVK number: {kvk_number}")
    
    try:
        if not kvk_number.isdigit() or len(kvk_number) != 8:
            return {
                "status": "error",
                "error": "KVK number must be exactly 8 digits",
                "code": "INVALID_FORMAT"
            }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{KVK_BASE_URL}/basisbedrijfsgegevens/kvknummer/{kvk_number}"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                insolvency_map = {
                    "FAIL": "Bankruptcy (Faillissement)",
                    "SSAN": "Debt Restructuring (Schuldsanering)",
                    "SURS": "Suspension of Payments (Surseance van betaling)"
                }
                
                return {
                    "status": "success",
                    "kvk_number": kvk_number,
                    "start_date": data.get("datumAanvang"),
                    "active": data.get("actief") == "J",
                    "legal_form": data.get("rechtsvormCode"),
                    "postal_region": data.get("postcodeRegio"),
                    "country": data.get("lidstaat"),
                    "insolvency_status": insolvency_map.get(data.get("insolventieCode")) if data.get("insolventieCode") else None,
                    "activities": [
                        {
                            "sbi_code": activity.get("sbiCode"),
                            "type": activity.get("soortActiviteit")
                        }
                        for activity in data.get("activiteiten", [])
                    ]
                }
            elif response.status_code == 404:
                return {
                    "status": "error",
                    "error": "Company not found in KVK register",
                    "code": "NOT_FOUND"
                }
            else:
                return {
                    "status": "error",
                    "error": f"KVK API returned status {response.status_code}",
                    "code": "API_ERROR"
                }
                
    except httpx.TimeoutException:
        logger.error(f"Timeout getting company info: {kvk_number}")
        return {
            "status": "error",
            "error": "Request timed out",
            "code": "TIMEOUT"
        }
    except Exception as e:
        logger.error(f"Error getting company info {kvk_number}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "code": "INTERNAL_ERROR"
        }


@mcp.tool()
async def check_company_active(kvk_number: str) -> dict:
    """Check if a company is currently active in the KVK register.
    
    Use this tool to quickly verify if a company is actively operating.
    
    Args:
        kvk_number: 8-digit KVK (Chamber of Commerce) number
    
    Returns:
        Dictionary with active status and insolvency information
    """
    logger.info(f"Checking active status for KVK number: {kvk_number}")
    
    try:
        if not kvk_number.isdigit() or len(kvk_number) != 8:
            return {
                "status": "error",
                "error": "KVK number must be exactly 8 digits",
                "code": "INVALID_FORMAT"
            }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{KVK_BASE_URL}/basisbedrijfsgegevens/kvknummer/{kvk_number}"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                is_active = data.get("actief") == "J"
                insolvency = data.get("insolventieCode")
                
                status_details = {
                    "status": "success",
                    "kvk_number": kvk_number,
                    "active": is_active,
                    "has_insolvency": bool(insolvency)
                }
                
                if insolvency:
                    insolvency_map = {
                        "FAIL": "Bankruptcy",
                        "SSAN": "Debt Restructuring",
                        "SURS": "Suspension of Payments"
                    }
                    status_details["insolvency_type"] = insolvency_map.get(insolvency, insolvency)
                
                if not is_active:
                    status_details["warning"] = "Company is registered as inactive"
                
                return status_details
                
            elif response.status_code == 404:
                return {
                    "status": "error",
                    "error": "Company not found in KVK register",
                    "code": "NOT_FOUND"
                }
            else:
                return {
                    "status": "error",
                    "error": f"KVK API returned status {response.status_code}",
                    "code": "API_ERROR"
                }
                
    except httpx.TimeoutException:
        logger.error(f"Timeout checking active status: {kvk_number}")
        return {
            "status": "error",
            "error": "Request timed out",
            "code": "TIMEOUT"
        }
    except Exception as e:
        logger.error(f"Error checking active status {kvk_number}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "code": "INTERNAL_ERROR"
        }


@mcp.tool()
async def get_company_activities(kvk_number: str) -> dict:
    """Get business activities (SBI codes) for a company.
    
    Use this tool to retrieve the primary and secondary business activities
    of a company as classified by SBI (Standard Business Classification) codes.
    
    Args:
        kvk_number: 8-digit KVK (Chamber of Commerce) number
    
    Returns:
        Dictionary with primary and secondary activities with SBI codes
    """
    logger.info(f"Getting activities for KVK number: {kvk_number}")
    
    try:
        if not kvk_number.isdigit() or len(kvk_number) != 8:
            return {
                "status": "error",
                "error": "KVK number must be exactly 8 digits",
                "code": "INVALID_FORMAT"
            }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{KVK_BASE_URL}/basisbedrijfsgegevens/kvknummer/{kvk_number}"
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                activities = data.get("activiteiten", [])
                
                primary = [
                    {"sbi_code": act.get("sbiCode"), "type": act.get("soortActiviteit")}
                    for act in activities
                    if act.get("soortActiviteit") == "Hoofdactiviteit"
                ]
                
                secondary = [
                    {"sbi_code": act.get("sbiCode"), "type": act.get("soortActiviteit")}
                    for act in activities
                    if act.get("soortActiviteit") == "Nevenactiviteit"
                ]
                
                return {
                    "status": "success",
                    "kvk_number": kvk_number,
                    "primary_activities": primary,
                    "secondary_activities": secondary,
                    "total_activities": len(activities)
                }
                
            elif response.status_code == 404:
                return {
                    "status": "error",
                    "error": "Company not found in KVK register",
                    "code": "NOT_FOUND"
                }
            else:
                return {
                    "status": "error",
                    "error": f"KVK API returned status {response.status_code}",
                    "code": "API_ERROR"
                }
                
    except httpx.TimeoutException:
        logger.error(f"Timeout getting activities: {kvk_number}")
        return {
            "status": "error",
            "error": "Request timed out",
            "code": "TIMEOUT"
        }
    except Exception as e:
        logger.error(f"Error getting activities {kvk_number}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "code": "INTERNAL_ERROR"
        }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker health checks."""
    return JSONResponse(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "KVK Lookup"
        },
        status_code=200
    )


@mcp.resource("server://info")
def server_info() -> str:
    """Server capabilities and metadata."""
    import json
    return json.dumps({
        "name": "KVK Lookup",
        "version": "1.0.0",
        "description": "Dutch Chamber of Commerce (KVK) company information lookup",
        "tools": [
            "check_company_exists",
            "get_company_info",
            "check_company_active",
            "get_company_activities"
        ],
        "api_endpoint": KVK_BASE_URL
    })


if __name__ == "__main__":
    logger.info("Starting KVK Lookup MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")

