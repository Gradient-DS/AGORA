"""Services for the HAP Reporting Server."""

from .email_service import (
    is_email_configured,
    send_report_email,
)

__all__ = [
    "is_email_configured",
    "send_report_email",
]
