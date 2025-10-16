import json
import logging
from datetime import datetime, timedelta
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Utilities Server", stateless_http=True)

MOCK_TRANSLATIONS = {
    "en": {
        "Goedemorgen": "Good morning",
        "Dank u wel": "Thank you",
        "Voedselproduct": "Food product",
        "Inspectie rapport": "Inspection report",
        "Voedselveiligheid": "Food safety",
        "Temperatuurcontrole": "Temperature control",
        "Allergeneninformatie": "Allergen information",
        "Houdbaarheidsdatum": "Expiration date",
        "Ingrediënten": "Ingredients",
        "Productlabel": "Product label"
    },
    "de": {
        "Good morning": "Guten Morgen",
        "Thank you": "Danke schön",
        "Food product": "Lebensmittelprodukt",
        "Inspection report": "Inspektionsbericht",
        "Food safety": "Lebensmittelsicherheit",
        "Temperature control": "Temperaturkontrolle",
        "Allergen information": "Allergeninformation",
        "Expiration date": "Verfallsdatum",
        "Ingredients": "Zutaten",
        "Product label": "Produktetikett"
    },
    "fr": {
        "Good morning": "Bonjour",
        "Thank you": "Merci",
        "Food product": "Produit alimentaire",
        "Inspection report": "Rapport d'inspection",
        "Food safety": "Sécurité alimentaire",
        "Temperature control": "Contrôle de la température",
        "Allergen information": "Information sur les allergènes",
        "Expiration date": "Date d'expiration",
        "Ingredients": "Ingrédients",
        "Product label": "Étiquette du produit"
    },
    "nl": {
        "Good morning": "Goedemorgen",
        "Thank you": "Dank u wel",
        "Food product": "Voedselproduct",
        "Inspection report": "Inspectie rapport",
        "Food safety": "Voedselveiligheid",
        "Temperature control": "Temperatuurcontrole",
        "Allergen information": "Allergeneninformatie",
        "Expiration date": "Houdbaarheidsdatum",
        "Ingredients": "Ingrediënten",
        "Product label": "Productlabel"
    }
}


def simple_translate(text: str, target_language: str) -> str:
    """Simple mock translation helper."""
    target_lang = target_language.lower()
    
    if target_lang not in MOCK_TRANSLATIONS:
        return f"[Translation to {target_language}] {text}"
    
    translation_dict = MOCK_TRANSLATIONS[target_lang]
    
    for source_text, translated_text in translation_dict.items():
        if source_text.lower() in text.lower():
            text = text.replace(source_text, translated_text)
            text = text.replace(source_text.lower(), translated_text.lower())
            text = text.replace(source_text.upper(), translated_text.upper())
    
    return text


@mcp.tool
async def translate_text(text: str, target_language: str) -> dict:
    """Translate text to a target language (supports en, de, fr, es, nl).
    
    Args:
        text: Text to translate
        target_language: Target language code
    """
    translated = simple_translate(text, target_language)
    
    return {
        "original_text": text,
        "translated_text": translated,
        "target_language": target_language,
        "source_detected": "auto",
        "confidence": 0.85 if target_language.lower() in MOCK_TRANSLATIONS else 0.5
    }


@mcp.tool
async def format_date(date_str: str, format_type: str = "iso") -> dict:
    """Format a date string according to Dutch or ISO standards.
    
    Args:
        date_str: Date string to format
        format_type: Format type ('iso', 'dutch', 'european')
    """
    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return {
                "error": "Invalid date format",
                "date_str": date_str
            }
    
    formats = {
        "iso": parsed.strftime("%Y-%m-%d"),
        "dutch": parsed.strftime("%d-%m-%Y"),
        "european": parsed.strftime("%d/%m/%Y"),
        "long": parsed.strftime("%d %B %Y"),
        "timestamp": parsed.timestamp()
    }
    
    return {
        "original": date_str,
        "formatted": formats.get(format_type, formats["iso"]),
        "format_type": format_type,
        "all_formats": formats
    }


@mcp.tool
async def calculate_due_date(start_date: str, days: int) -> dict:
    """Calculate a due date by adding days to a start date.
    
    Args:
        start_date: Start date (ISO format)
        days: Number of days to add
    """
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        due = start + timedelta(days=days)
        
        return {
            "start_date": start.strftime("%Y-%m-%d"),
            "days_added": days,
            "due_date": due.strftime("%Y-%m-%d"),
            "due_date_dutch": due.strftime("%d-%m-%Y"),
            "weekday": due.strftime("%A")
        }
    except Exception as e:
        return {
            "error": "Invalid date format",
            "start_date": start_date,
            "message": str(e)
        }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "utilities",
        "timestamp": datetime.now().isoformat()
    }, status_code=200)


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "Utilities Server",
        "version": "1.0.0",
        "description": "Provides translation, date formatting, and utility functions",
        "capabilities": {
            "tools": ["translate_text", "format_date", "calculate_due_date"],
            "resources": ["server://info"]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    logger.info("Starting Utilities MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
