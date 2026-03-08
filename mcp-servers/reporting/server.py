import base64
import json
import logging
import os
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

from storage import FileStorage, SessionManager
from analyzers import FieldMapper
from generators import JSONGenerator, PDFGenerator
from models.hap_schema import HAPReport
from services import is_email_configured, send_report_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Reporting Server")

storage = FileStorage(base_path="./storage")
session_manager = SessionManager(storage)
field_mapper = FieldMapper()
json_generator = JSONGenerator()
pdf_generator = PDFGenerator()


@mcp.tool
async def generate_report(
    session_id: str,
    report_data: str,
    company_name: str | None = None,
    company_address: str | None = None,
    inspector_name: str | None = None,
    inspector_email: str | None = None,
    send_email: bool = True,
) -> dict:
    """Generate a HAP inspection report from structured inspection data.

    Receives pre-extracted structured data from the reporting agent and generates
    the final HAP report as JSON + PDF.

    Args:
        session_id: Unique session identifier
        report_data: JSON string containing the structured inspection data matching
                     the HAP schema (hygiene_general, pest_control, food_safety,
                     allergen_info, additional_info sections)
        company_name: Company name (overrides value in report_data if provided)
        company_address: Company address (overrides value in report_data if provided)
        inspector_name: Inspector name for report metadata
        inspector_email: Inspector email for report delivery
        send_email: Whether to email the report (default True)

    Returns:
        Dict with report_id, download URLs, summary, and status
    """
    try:
        # 1. Parse report_data JSON string into dict
        try:
            extracted_data = json.loads(report_data)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON in report_data: {e}",
                "message": "Ongeldige JSON in rapport gegevens.",
            }

        if not isinstance(extracted_data, dict):
            return {
                "success": False,
                "error": "report_data must be a JSON object",
                "message": "Rapport gegevens moeten een JSON object zijn.",
            }

        # 2. Inject metadata as top-level keys if provided and not already present
        if company_name and not extracted_data.get("company_name"):
            extracted_data["company_name"] = company_name
        if company_address and not extracted_data.get("company_address"):
            extracted_data["company_address"] = company_address

        # 3. Create session via SessionManager (generates report ID)
        session = session_manager.get_session(session_id)
        if not session:
            logger.info(f"Creating new session for {session_id}")
            session = session_manager.create_session(
                session_id=session_id,
                company_name=company_name or extracted_data.get("company_name"),
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

        report_id = session["report_id"]

        # 4. Save extracted data to draft (for audit trail)
        session_manager.update_extracted_data(session_id, extracted_data)

        # 5. Map to HAPReport via FieldMapper
        hap_report = field_mapper.map_to_hap_report(
            extracted_data=extracted_data,
            session_id=session_id,
            report_id=report_id,
        )

        # Load evidence images for this session
        evidence_images = storage.load_images(session_id)
        if evidence_images:
            logger.info(f"Including {len(evidence_images)} evidence images in PDF report")

        # 6. Generate JSON + PDF via generators
        json_data = json_generator.generate(hap_report)
        pdf_content = pdf_generator.generate(
            hap_report,
            evidence_images=evidence_images if evidence_images else None,
        )

        # 7. Finalize and optionally email
        paths = session_manager.finalize_report(session_id, json_data, pdf_content)

        summary = json_generator.generate_summary(hap_report)

        # Generate download URLs
        base_url = os.getenv("REPORTING_PUBLIC_URL", "http://localhost:5003")
        download_urls = {
            "json": f"{base_url}/reports/{session_id}/json",
            "pdf": f"{base_url}/reports/{session_id}/pdf",
        }

        # Send email if requested and configured
        email_sent = False
        email_error = None
        if send_email and is_email_configured():
            recipient_email = inspector_email or session.get("inspector_email")
            recipient_name = inspector_name or session.get("inspector_name", "Inspecteur")
            report_company = company_name or session.get("company_name", "Onbekend bedrijf")

            if recipient_email:
                try:
                    send_report_email(
                        to_email=recipient_email,
                        report_id=report_id,
                        company_name=report_company,
                        inspector_name=recipient_name,
                        pdf_content=pdf_content,
                        download_url=download_urls["pdf"],
                    )
                    email_sent = True
                    logger.info(f"Report email sent to {recipient_email}")
                except Exception as e:
                    email_error = str(e)
                    logger.error(f"Failed to send report email: {e}")
            else:
                logger.info("No inspector email provided, skipping email notification")

        # 8. Build response
        message = f"Rapport {report_id} succesvol gegenereerd."
        if email_sent:
            message += f" E-mail verzonden naar {inspector_email or session.get('inspector_email')}."
        elif send_email and not is_email_configured():
            message += " E-mail niet verzonden (niet geconfigureerd)."
        elif send_email and not (inspector_email or session.get("inspector_email")):
            message += " E-mail niet verzonden (geen e-mailadres bekend)."

        return {
            "success": True,
            "session_id": session_id,
            "report_id": report_id,
            "paths": paths,
            "download_urls": download_urls,
            "summary": summary,
            "evidence_images_count": len(evidence_images) if evidence_images else 0,
            "email_sent": email_sent,
            "email_error": email_error,
            "message": message,
        }

    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Fout bij het genereren van het rapport.",
        }


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "reporting",
        "timestamp": datetime.now().isoformat(),
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


MAX_EVIDENCE_IMAGES = 5


@mcp.custom_route("/reports/{session_id}/images", methods=["POST"])
async def upload_evidence_image(request: Request) -> JSONResponse:
    """Upload an evidence image for an inspection report."""
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Session ID required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    image_data = body.get("image_data", "")
    caption = body.get("caption", "Bewijsfoto")
    mime_type = body.get("mime_type", "image/jpeg")
    description = body.get("description", "")

    if not image_data:
        return JSONResponse({"error": "image_data is required"}, status_code=400)

    # Decode base64 data URL
    try:
        if "," in image_data:
            _, b64_data = image_data.split(",", 1)
        else:
            b64_data = image_data
        image_bytes = base64.b64decode(b64_data)
    except Exception:
        return JSONResponse({"error": "Invalid base64 image data"}, status_code=400)

    # Save image
    result = storage.save_image(session_id, image_bytes, "", caption, mime_type, description=description)

    if result is None:
        return JSONResponse({
            "error": "Image limit reached",
            "message": f"Maximaal {MAX_EVIDENCE_IMAGES} foto's per sessie.",
            "current_count": storage.get_image_count(session_id),
        }, status_code=409)

    return JSONResponse({
        "success": True,
        "image": result,
        "current_count": storage.get_image_count(session_id),
        "max_images": MAX_EVIDENCE_IMAGES,
    }, status_code=201)


@mcp.custom_route("/reports/{session_id}/images/{image_index}/description", methods=["PATCH"])
async def update_image_description(request: Request) -> JSONResponse:
    """Update the AI-generated description for an evidence image."""
    session_id = request.path_params.get("session_id")
    image_index = int(request.path_params.get("image_index", "0"))

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    description = body.get("description", "")
    if not description:
        return JSONResponse({"error": "description is required"}, status_code=400)

    success = storage.update_image_description(session_id, image_index, description)
    if not success:
        return JSONResponse({"error": "Image not found"}, status_code=404)

    return JSONResponse({"success": True}, status_code=200)


@mcp.custom_route("/reports/{session_id}/images", methods=["GET"])
async def list_evidence_images(request: Request) -> JSONResponse:
    """List evidence images for a session."""
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Session ID required"}, status_code=400)

    images = storage.load_images(session_id)
    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "images": [
            {k: v for k, v in img.items() if k != "path"}
            for img in images
        ],
        "count": len(images),
        "max_images": MAX_EVIDENCE_IMAGES,
    })


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    info = {
        "name": "HAP Reporting Server",
        "version": "3.0.0",
        "description": "Stateless HAP inspection report renderer",
        "capabilities": {
            "tools": [
                "generate_report"
            ],
            "resources": ["server://info"],
            "features": [
                "Stateless report rendering (no LLM dependencies)",
                "Structured data to HAP report mapping",
                "Dual-format report generation (JSON + PDF)",
                "Evidence image attachments in PDF reports (max 5 per session)",
                "File-based session management",
            ],
            "workflow": [
                "1. Reporting agent extracts structured data from conversation",
                "2. generate_report - maps data to HAP schema, generates JSON + PDF",
            ],
        },
    }
    return json.dumps(info, indent=2)


if __name__ == "__main__":
    logger.info("Starting HAP Reporting MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp", stateless_http=True)
