"""Microsoft Graph API mailer service for sending HAP reports.

Provides email sending functionality using Microsoft Graph API
for delivering generated inspection reports to inspectors.
"""

import base64
import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Configuration - supports both MCP_ prefix and direct names
TENANT_ID = os.getenv("MCP_GRAPH_TENANT_ID") or os.getenv("GRAPH_TENANT_ID")
CLIENT_ID = os.getenv("MCP_GRAPH_CLIENT_ID") or os.getenv("GRAPH_CLIENT_ID")
CLIENT_SECRET = os.getenv("MCP_GRAPH_CLIENT_SECRET") or os.getenv("GRAPH_CLIENT_SECRET")
SENDER_ADDRESS = os.getenv("MCP_GRAPH_MAIL_SENDER_ADDRESS") or os.getenv("GRAPH_MAIL_SENDER_ADDRESS")
SENDER_DISPLAY = os.getenv("MCP_GRAPH_MAIL_SENDER_DISPLAY") or os.getenv("GRAPH_MAIL_SENDER_DISPLAY", "AGORA")

TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token" if TENANT_ID else None
SCOPE = "https://graph.microsoft.com/.default"


def is_email_configured() -> bool:
    """Check if email sending is properly configured.

    Returns:
        True if all required Graph API credentials are set
    """
    configured = all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, SENDER_ADDRESS])
    if not configured:
        logger.debug("Email not configured - missing Graph API credentials")
    return configured


def _get_graph_token() -> str:
    """Get a bearer token for Microsoft Graph using client credentials.

    Returns:
        Access token string

    Raises:
        RuntimeError: If token acquisition fails
    """
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
        raise RuntimeError(
            "Missing required Graph API credentials: GRAPH_TENANT_ID, "
            "GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET"
        )

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": SCOPE,
        "grant_type": "client_credentials",
    }

    try:
        resp = requests.post(TOKEN_URL, data=data, timeout=10)
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.RequestException as e:
        logger.error(f"Failed to get Graph API token: {e}")
        raise RuntimeError(f"Failed to get Graph API token: {e}")


def _send_email_via_graph(
    to_email: str,
    subject: str,
    body_html: str,
    attachment_name: Optional[str] = None,
    attachment_content: Optional[bytes] = None,
) -> None:
    """Send an email using Microsoft Graph API.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        body_html: HTML email body content
        attachment_name: Optional filename for attachment
        attachment_content: Optional attachment content as bytes

    Raises:
        RuntimeError: If email sending fails
    """
    if not SENDER_ADDRESS:
        raise RuntimeError("Missing GRAPH_MAIL_SENDER_ADDRESS environment variable")

    access_token = _get_graph_token()

    payload: Dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html,
            },
            "from": {
                "emailAddress": {
                    "address": SENDER_ADDRESS,
                    "name": SENDER_DISPLAY,
                }
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email,
                    }
                }
            ],
        },
        "saveToSentItems": False,
    }

    # Add attachment if provided
    if attachment_name and attachment_content:
        payload["message"]["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_name,
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(attachment_content).decode("utf-8"),
            }
        ]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    graph_send_url = f"https://graph.microsoft.com/v1.0/users/{SENDER_ADDRESS}/sendMail"

    try:
        resp = requests.post(graph_send_url, json=payload, headers=headers, timeout=30)
        if resp.status_code not in (202, 200):
            raise RuntimeError(
                f"Graph sendMail failed ({resp.status_code}): {resp.text}"
            )
        logger.info(f"Email sent via Graph API to {to_email}")
    except requests.RequestException as e:
        logger.error(f"Failed to send email via Graph API to {to_email}: {e}")
        raise RuntimeError(f"Failed to send email via Graph API: {e}")


def send_report_email(
    to_email: str,
    report_id: str,
    company_name: str,
    inspector_name: str,
    pdf_content: bytes,
    download_url: Optional[str] = None,
) -> None:
    """Send a HAP inspection report email with PDF attachment.

    Args:
        to_email: Inspector's email address
        report_id: The HAP report identifier
        company_name: Name of the inspected company
        inspector_name: Name of the inspector
        pdf_content: PDF report content as bytes
        download_url: Optional URL to download the report

    Raises:
        RuntimeError: If email sending fails
    """
    subject = f"NVWA Inspectierapport {report_id} - {company_name}"

    download_section = ""
    if download_url:
        download_section = f"""
                            <p style="margin: 20px 0 0 0; color: #999999; font-size: 14px; line-height: 1.5;">
                                Je kunt het rapport ook downloaden via:<br>
                                <a href="{download_url}" style="color: #2c5282; word-break: break-all;">{download_url}</a>
                            </p>
"""

    body_html = f"""
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding: 40px 40px 20px 40px; text-align: center; background-color: #1a365d; border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">NVWA Inspectierapport</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 30px 40px;">
                            <p style="margin: 0 0 20px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Beste {inspector_name},
                            </p>
                            <p style="margin: 0 0 20px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Je inspectierapport is succesvol gegenereerd en als bijlage aan deze email toegevoegd.
                            </p>

                            <table role="presentation" style="width: 100%; border-collapse: collapse; margin: 20px 0; background-color: #f7fafc; border-radius: 4px;">
                                <tr>
                                    <td style="padding: 20px;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px; width: 140px;"><strong>Rapport ID:</strong></td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px;">{report_id}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px;"><strong>Bedrijf:</strong></td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px;">{company_name}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px;"><strong>Inspecteur:</strong></td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px;">{inspector_name}</td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 20px 0 0 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                Het PDF-rapport vind je als bijlage bij deze email.
                            </p>
                            {download_section}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 30px 40px; border-top: 1px solid #eeeeee; background-color: #f7fafc; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0; color: #999999; font-size: 14px; line-height: 1.5;">
                                Met vriendelijke groet,<br>
                                <strong style="color: #333333;">AGORA - NVWA Inspectie Assistent</strong>
                            </p>
                            <p style="margin: 15px 0 0 0; color: #999999; font-size: 12px; line-height: 1.5;">
                                Dit is een automatisch gegenereerd bericht. Voor vragen over het rapport,
                                neem contact op met je leidinggevende.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    attachment_name = f"rapport_{report_id}.pdf"

    _send_email_via_graph(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        attachment_name=attachment_name,
        attachment_content=pdf_content,
    )
