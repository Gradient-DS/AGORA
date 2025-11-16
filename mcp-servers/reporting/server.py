import json
import logging
import os
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

from storage import FileStorage, SessionManager
from analyzers import ConversationExtractor, FieldMapper
from verification import Verifier, ResponseParser
from generators import JSONGenerator, PDFGenerator
from models.hap_schema import HAPReport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Reporting Server", stateless_http=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("MCP_OPENAI_API_KEY", "")

storage = FileStorage(base_path="./storage")
session_manager = SessionManager(storage)
extractor = ConversationExtractor(OPENAI_API_KEY) if OPENAI_API_KEY else None
field_mapper = FieldMapper()
verifier = Verifier(OPENAI_API_KEY) if OPENAI_API_KEY else None
response_parser = ResponseParser(OPENAI_API_KEY) if OPENAI_API_KEY else None
json_generator = JSONGenerator()
pdf_generator = PDFGenerator()


@mcp.tool
async def start_inspection_report(
    session_id: str,
    company_id: str = None,
    company_name: str = None,
    company_address: str = None,
    inspector_name: str = None,
) -> dict:
    """Initialize a new HAP inspection report session.
    
    Args:
        session_id: Unique session identifier for this inspection
        company_id: Optional company identifier
        company_name: Name of the inspected company
        company_address: Address of the inspected company
        inspector_name: Name of the inspector conducting the inspection
    
    Returns:
        Session information including report_id and status
    """
    try:
        logger.info(f"Starting inspection report for session {session_id}")
        
        session_data = session_manager.create_session(
            session_id=session_id,
            company_id=company_id,
            company_name=company_name,
            inspector_name=inspector_name,
        )
        
        draft_data = storage.load_draft(session_id)
        if draft_data and company_name:
            draft_data["company_name"] = company_name
        if draft_data and company_address:
            draft_data["company_address"] = company_address
        
        if draft_data:
            storage.save_draft(session_id, draft_data)
        
        return {
            "success": True,
            "session_id": session_id,
            "report_id": session_data["report_id"],
            "status": "initialized",
            "message": f"Inspection report {session_data['report_id']} geïnitialiseerd voor {company_name or 'bedrijf'}."
        }
        
    except Exception as e:
        logger.error(f"Error starting inspection report: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het initialiseren van het inspectierapport."
        }


@mcp.tool
async def extract_inspection_data(
    session_id: str,
    conversation_history: list[dict] = None,
) -> dict:
    """Extract structured HAP inspection data from conversation history.
    
    The conversation history can be provided or will be retrieved from session storage.
    
    Args:
        session_id: Session identifier
        conversation_history: Optional list of conversation messages with 'role' and 'content'
    
    Returns:
        Extracted data with confidence scores and fields needing verification
    """
    if not extractor:
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "message": "Kan conversatie niet analyseren zonder OpenAI API sleutel."
        }
    
    try:
        # Ensure session exists
        session = session_manager.get_session(session_id)
        if not session:
            logger.info(f"Creating new session for {session_id}")
            session_manager.create_session(session_id=session_id)
        
        # Use provided conversation history or retrieve from storage
        if not conversation_history:
            draft = storage.load_draft(session_id)
            conversation_history = draft.get("conversation_history", []) if draft else []
        
        if not conversation_history:
            return {
                "success": False,
                "error": "No conversation history found",
                "message": f"Geen gespreksgeschiedenis gevonden voor sessie {session_id}. Zorg ervoor dat de sessie is gestart en er gesprekken zijn gevoerd."
            }
        
        logger.info(f"Extracting data from {len(conversation_history)} messages for session {session_id}")
        
        session_manager.store_conversation(session_id, conversation_history)
        
        draft = storage.load_draft(session_id)
        existing_data = draft.get("extracted_data", {}) if draft else {}
        
        extracted_data = await extractor.extract_from_conversation(
            messages=conversation_history,
            existing_data=existing_data
        )
        
        session_manager.update_extracted_data(session_id, extracted_data)
        session_manager.update_session_status(session_id, "data_extracted", "verification")
        
        completeness = verifier.check_completeness(extracted_data) if verifier else {}
        
        return {
            "success": True,
            "session_id": session_id,
            "extracted_data": extracted_data,
            "completeness": completeness,
            "overall_confidence": extracted_data.get("overall_confidence", 0.0),
            "fields_needing_verification": extracted_data.get("fields_needing_verification", []),
            "message": f"Data geëxtraheerd met {completeness.get('completion_percentage', 0):.1f}% compleetheid."
        }
        
    except Exception as e:
        logger.error(f"Error extracting inspection data: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het extraheren van inspectiegegevens."
        }


@mcp.tool
async def verify_inspection_data(
    session_id: str,
    max_questions: int = 5,
) -> dict:
    """Generate verification questions for missing or uncertain inspection data.
    
    Args:
        session_id: Session identifier
        max_questions: Maximum number of verification questions to generate
    
    Returns:
        List of verification questions to ask the inspector
    """
    if not verifier:
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "message": "Kan verificatievragen niet genereren zonder OpenAI API sleutel."
        }
    
    try:
        logger.info(f"Generating verification questions for session {session_id}")
        
        draft = storage.load_draft(session_id)
        if not draft or "extracted_data" not in draft:
            return {
                "success": False,
                "error": "No extracted data found",
                "message": "Geen geëxtraheerde gegevens gevonden. Voer eerst extract_inspection_data uit."
            }
        
        extracted_data = draft["extracted_data"]
        
        questions = await verifier.generate_verification_questions(
            extracted_data=extracted_data,
            max_questions=max_questions
        )
        
        session_manager.add_verification_questions(session_id, [q["question"] for q in questions])
        
        return {
            "success": True,
            "session_id": session_id,
            "questions": questions,
            "count": len(questions),
            "message": f"{len(questions)} verificatievragen gegenereerd."
        }
        
    except Exception as e:
        logger.error(f"Error generating verification questions: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het genereren van verificatievragen."
        }


@mcp.tool
async def submit_verification_answers(
    session_id: str,
    answers: dict | str,
) -> dict:
    """Submit answers to verification questions and update the report data.
    
    Args:
        session_id: Session identifier
        answers: Dictionary of field: value pairs or natural language responses
    
    Returns:
        Updated extraction data with verification answers incorporated
    """
    if not response_parser:
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "message": "Kan antwoorden niet verwerken zonder OpenAI API sleutel."
        }
    
    try:
        logger.info(f"Processing verification answers for session {session_id}")
        
        draft = storage.load_draft(session_id)
        if not draft or "extracted_data" not in draft:
            return {
                "success": False,
                "error": "No extracted data found",
                "message": "Geen geëxtraheerde gegevens gevonden."
            }
        
        extracted_data = draft["extracted_data"]
        questions = draft.get("verification_questions", [])
        
        updated_data = await response_parser.parse_verification_responses(
            questions=[{"question": q} for q in questions],
            responses=answers,
            existing_data=extracted_data
        )
        
        session_manager.update_extracted_data(session_id, updated_data)
        session_manager.add_verification_answers(session_id, answers)
        session_manager.update_session_status(session_id, "verified", "generation")
        
        completeness = verifier.check_completeness(updated_data) if verifier else {}
        
        return {
            "success": True,
            "session_id": session_id,
            "updated_data": updated_data,
            "completeness": completeness,
            "message": f"Verificatie-antwoorden verwerkt. Compleetheid: {completeness.get('completion_percentage', 0):.1f}%"
        }
        
    except Exception as e:
        logger.error(f"Error processing verification answers: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het verwerken van verificatie-antwoorden."
        }


@mcp.tool
async def generate_final_report(
    session_id: str,
) -> dict:
    """Generate final HAP inspection report in JSON and PDF formats.
    
    Args:
        session_id: Session identifier
    
    Returns:
        Paths to generated report files and report summary
    """
    try:
        logger.info(f"Generating final report for session {session_id}")
        
        draft = storage.load_draft(session_id)
        if not draft or "extracted_data" not in draft:
            return {
                "success": False,
                "error": "No extracted data found",
                "message": "Geen geëxtraheerde gegevens gevonden."
            }
        
        session = session_manager.get_session(session_id)
        if not session:
            return {
                "success": False,
                "error": "Session not found",
                "message": "Sessie niet gevonden."
            }
        
        extracted_data = draft["extracted_data"]
        report_id = session["report_id"]
        
        hap_report = field_mapper.map_to_hap_report(
            extracted_data=extracted_data,
            session_id=session_id,
            report_id=report_id
        )
        
        hap_report.conversation_history = draft.get("conversation_history", [])
        
        json_data = json_generator.generate(hap_report)
        pdf_content = pdf_generator.generate(hap_report)
        
        paths = session_manager.finalize_report(session_id, json_data, pdf_content)
        
        summary = json_generator.generate_summary(hap_report)
        
        # Generate download URLs
        download_urls = {
            "json": f"http://localhost:5003/reports/{session_id}/json",
            "pdf": f"http://localhost:5003/reports/{session_id}/pdf"
        }
        
        return {
            "success": True,
            "session_id": session_id,
            "report_id": report_id,
            "paths": paths,
            "download_urls": download_urls,
            "summary": summary,
            "message": f"Rapport {report_id} succesvol gegenereerd. Download via: JSON: {download_urls['json']} | PDF: {download_urls['pdf']}"
        }
        
    except Exception as e:
        logger.error(f"Error generating final report: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het genereren van het eindrapport."
        }


@mcp.tool
async def get_report_status(
    session_id: str,
) -> dict:
    """Get the current status and completion percentage of an inspection report.
    
    Args:
        session_id: Session identifier
    
    Returns:
        Report status, completion percentage, and file paths
    """
    try:
        status_info = session_manager.get_report_status(session_id)
        
        if not status_info["exists"]:
            return {
                "success": False,
                "error": "Session not found",
                "message": f"Geen rapport gevonden voor sessie {session_id}."
            }
        
        return {
            "success": True,
            **status_info,
            "message": f"Rapport {status_info.get('report_id', 'N/A')} is {status_info['completion_percentage']:.1f}% compleet."
        }
        
    except Exception as e:
        logger.error(f"Error getting report status: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het ophalen van rapportstatus."
        }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "reporting",
        "timestamp": datetime.now().isoformat(),
        "openai_configured": bool(OPENAI_API_KEY)
    }, status_code=200)


@mcp.custom_route("/reports/{session_id}/json", methods=["GET"])
async def download_json_report(request: Request) -> JSONResponse:
    """Download JSON report for a session."""
    from starlette.responses import FileResponse
    
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Session ID required"}, status_code=400)
    
    paths = storage.get_report_paths(session_id)
    json_path = paths.get("final_json")
    
    if not json_path or not os.path.exists(json_path):
        return JSONResponse({
            "error": "Report not found",
            "message": f"Geen rapport gevonden voor sessie {session_id}"
        }, status_code=404)
    
    return FileResponse(
        json_path,
        media_type="application/json",
        filename=f"rapport_{session_id}.json"
    )


@mcp.custom_route("/reports/{session_id}/pdf", methods=["GET"])
async def download_pdf_report(request: Request) -> JSONResponse:
    """Download PDF report for a session."""
    from starlette.responses import FileResponse
    
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Session ID required"}, status_code=400)
    
    paths = storage.get_report_paths(session_id)
    pdf_path = paths.get("final_pdf")
    
    if not pdf_path or not os.path.exists(pdf_path):
        return JSONResponse({
            "error": "Report not found",
            "message": f"Geen PDF rapport gevonden voor sessie {session_id}"
        }, status_code=404)
    
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"rapport_{session_id}.pdf"
    )


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "HAP Reporting Server",
        "version": "1.0.0",
        "description": "Automated HAP inspection report generation",
        "capabilities": {
            "tools": [
                "start_inspection_report",
                "extract_inspection_data",
                "verify_inspection_data",
                "submit_verification_answers",
                "generate_final_report",
                "get_report_status"
            ],
            "resources": ["server://info"],
            "features": [
                "Conversation analysis with GPT-4",
                "Structured data extraction",
                "Smart verification workflow",
                "Dual-format report generation (JSON + PDF)",
                "File-based session management"
            ]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set. Some features will be disabled.")
    
    logger.info("Starting HAP Reporting MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
