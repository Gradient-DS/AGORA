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
from services import is_email_configured, send_report_email

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
async def extract_inspection_data(
    session_id: str,
    inspection_summary: str,
    company_name: str | None = None,
    company_address: str | None = None,
    inspector_name: str | None = None,
    inspector_email: str | None = None,
    max_questions: int = 3,
) -> dict:
    """Extract structured HAP inspection data and generate verification questions.

    This is the main entry point for report generation. It:
    1. Creates/updates the session with metadata
    2. Extracts structured data from the inspection summary
    3. Generates verification questions for missing/uncertain fields

    IMPORTANT: The inspection_summary should contain ONLY:
    - User messages (inspector observations and responses)
    - Assistant messages (agent responses)
    - DO NOT include tool call results - these bloat the prompt unnecessarily

    Args:
        session_id: Unique session identifier for this inspection
        inspection_summary: Summary of user/assistant conversation about the inspection.
            Include: company details, inspection findings, violations, observations.
            Exclude: tool call results, regulation lookups, history data.
        company_name: Name of the inspected company
        company_address: Address of the inspected company
        inspector_name: Name of the inspector conducting the inspection
        inspector_email: Email address of the inspector for report delivery
        max_questions: Maximum number of verification questions to generate (default: 3)

    Returns:
        Extracted data, completeness info, and verification questions to ask
    """
    if not extractor:
        return {
            "success": False,
            "error": "OpenAI API key not configured",
            "message": "Kan conversatie niet analyseren zonder OpenAI API sleutel."
        }

    try:
        if not inspection_summary or len(inspection_summary.strip()) < 50:
            return {
                "success": False,
                "error": "Insufficient inspection summary",
                "message": "De inspectie samenvatting is te kort of ontbreekt. Geef een uitgebreide samenvatting met: bedrijfsgegevens, inspectiedatum, overtredingen, en vervolgacties."
            }

        # Create or update session with metadata
        session = session_manager.get_session(session_id)
        if not session:
            logger.info(f"Creating new session for {session_id}")
            session_manager.create_session(
                session_id=session_id,
                company_name=company_name,
                inspector_name=inspector_name,
                inspector_email=inspector_email,
            )
        else:
            # Update session with any new metadata
            if company_name:
                session["company_name"] = company_name
            if company_address:
                session["company_address"] = company_address
            if inspector_name:
                session["inspector_name"] = inspector_name
            if inspector_email:
                session["inspector_email"] = inspector_email
            session_manager._save_session(session_id, session)

        logger.info(f"Extracting data from inspection summary for session {session_id}")

        # Log summary size to detect bloated prompts
        summary_size = len(inspection_summary)
        logger.info(f"Inspection summary size: {summary_size} chars ({summary_size / 1000:.1f}KB)")
        if summary_size > 20000:
            logger.warning(f"Large inspection summary ({summary_size} chars) - ensure only user/assistant messages are included, not tool results")

        # Convert summary to message format for the extractor
        messages = [
            {"role": "user", "content": "Genereer een HAP rapport op basis van de volgende inspectie:"},
            {"role": "assistant", "content": inspection_summary}
        ]

        draft = storage.load_draft(session_id)
        existing_data = draft.get("extracted_data", {}) if draft else {}

        # Step 1: Extract structured data
        extracted_data = await extractor.extract_from_conversation(
            messages=messages,
            existing_data=existing_data
        )

        # Merge in session metadata
        if company_name and not extracted_data.get("company_name"):
            extracted_data["company_name"] = company_name
        if company_address and not extracted_data.get("company_address"):
            extracted_data["company_address"] = company_address

        session_manager.update_extracted_data(session_id, extracted_data)

        completeness = verifier.check_completeness(extracted_data) if verifier else {}

        # Step 2: Generate verification questions
        questions = []
        if verifier:
            logger.info(f"Generating verification questions for session {session_id}")
            questions = await verifier.generate_verification_questions(
                extracted_data=extracted_data,
                max_questions=max_questions
            )
            session_manager.add_verification_questions(session_id, [q["question"] for q in questions])

        session_manager.update_session_status(session_id, "data_extracted", "verification")

        return {
            "success": True,
            "session_id": session_id,
            "extracted_data": extracted_data,
            "completeness": completeness,
            "overall_confidence": extracted_data.get("overall_confidence", 0.0),
            "fields_needing_verification": extracted_data.get("fields_needing_verification", []),
            "verification_questions": questions,
            "question_count": len(questions),
            "message": f"Data geëxtraheerd met {completeness.get('completion_percentage', 0):.1f}% compleetheid. {len(questions)} verificatievragen gegenereerd."
        }

    except Exception as e:
        logger.error(f"Error extracting inspection data: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het extraheren van inspectiegegevens."
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
    send_email: bool = True,
) -> dict:
    """Generate final HAP inspection report in JSON and PDF formats.

    Args:
        session_id: Session identifier
        send_email: Whether to send the report via email (default: True)

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
        
        json_data = json_generator.generate(hap_report)
        pdf_content = pdf_generator.generate(hap_report)
        
        paths = session_manager.finalize_report(session_id, json_data, pdf_content)

        summary = json_generator.generate_summary(hap_report)

        # Generate download URLs
        # Use REPORTING_PUBLIC_URL for production, fall back to localhost for development
        base_url = os.getenv("REPORTING_PUBLIC_URL", "http://localhost:5003")
        download_urls = {
            "json": f"{base_url}/reports/{session_id}/json",
            "pdf": f"{base_url}/reports/{session_id}/pdf"
        }

        # Send email if requested and configured
        email_sent = False
        email_error = None
        if send_email and is_email_configured():
            inspector_email = session.get("inspector_email")
            inspector_name = session.get("inspector_name", "Inspecteur")
            company_name = session.get("company_name", "Onbekend bedrijf")

            if inspector_email:
                try:
                    send_report_email(
                        to_email=inspector_email,
                        report_id=report_id,
                        company_name=company_name,
                        inspector_name=inspector_name,
                        pdf_content=pdf_content,
                        download_url=download_urls["pdf"],
                    )
                    email_sent = True
                    logger.info(f"Report email sent to {inspector_email}")
                except Exception as e:
                    email_error = str(e)
                    logger.error(f"Failed to send report email: {e}")
            else:
                logger.info("No inspector email provided, skipping email notification")

        # Build response message
        message = f"Rapport {report_id} succesvol gegenereerd."
        if email_sent:
            message += f" E-mail verzonden naar {session.get('inspector_email')}."
        elif send_email and not is_email_configured():
            message += " E-mail niet verzonden (niet geconfigureerd)."
        elif send_email and not session.get("inspector_email"):
            message += " E-mail niet verzonden (geen e-mailadres bekend)."

        return {
            "success": True,
            "session_id": session_id,
            "report_id": report_id,
            "paths": paths,
            "download_urls": download_urls,
            "summary": summary,
            "email_sent": email_sent,
            "email_error": email_error,
            "message": message
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
        "version": "2.0.0",
        "description": "Automated HAP inspection report generation",
        "capabilities": {
            "tools": [
                "extract_inspection_data",
                "submit_verification_answers",
                "generate_final_report",
                "get_report_status"
            ],
            "resources": ["server://info"],
            "features": [
                "Conversation analysis with GPT-4",
                "Structured data extraction",
                "Integrated verification workflow (3 tool calls)",
                "Dual-format report generation (JSON + PDF)",
                "File-based session management"
            ],
            "workflow": [
                "1. extract_inspection_data - extracts data + generates verification questions",
                "2. submit_verification_answers - processes inspector's answers",
                "3. generate_final_report - creates JSON and PDF report"
            ]
        }
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set. Some features will be disabled.")
    
    logger.info("Starting HAP Reporting MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
