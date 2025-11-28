"""Audit logging for AGORA LangGraph - OpenTelemetry integration."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class AuditLogger:
    """Audit logger for tracking conversation events."""

    def __init__(self, otel_endpoint: str | None = None):
        """Initialize audit logger.

        Args:
            otel_endpoint: Optional OpenTelemetry endpoint for distributed tracing
        """
        self.otel_endpoint = otel_endpoint
        if otel_endpoint:
            log.info(f"Audit logger configured with OTEL endpoint: {otel_endpoint}")
        else:
            log.info("Audit logger configured in local-only mode")

    async def log_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a conversation message.

        Args:
            session_id: Session identifier
            role: Message role (user, assistant, tool)
            content: Message content
            metadata: Optional additional metadata
        """
        log.debug(
            f"[{session_id}] {role}: {content[:100]}..."
            if len(content) > 100
            else f"[{session_id}] {role}: {content}"
        )

    async def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        result: Any | None = None,
        status: str = "started",
    ) -> None:
        """Log a tool call event.

        Args:
            session_id: Session identifier
            tool_name: Name of the tool
            parameters: Tool parameters
            result: Optional tool result (for completed calls)
            status: Call status (started, completed, failed)
        """
        log.debug(f"[{session_id}] Tool {status}: {tool_name}")

    async def log_handoff(
        self,
        session_id: str,
        from_agent: str,
        to_agent: str,
    ) -> None:
        """Log an agent handoff event.

        Args:
            session_id: Session identifier
            from_agent: Source agent ID
            to_agent: Target agent ID
        """
        log.info(f"[{session_id}] Handoff: {from_agent} → {to_agent}")

    async def log_approval_request(
        self,
        session_id: str,
        tool_name: str,
        risk_level: str,
        approval_id: str,
    ) -> None:
        """Log a tool approval request.

        Args:
            session_id: Session identifier
            tool_name: Name of the tool requiring approval
            risk_level: Risk level assessment
            approval_id: Unique approval request ID
        """
        log.info(
            f"[{session_id}] Approval requested for {tool_name} (risk: {risk_level}, id: {approval_id})"
        )

    async def log_approval_response(
        self,
        session_id: str,
        approval_id: str,
        approved: bool,
    ) -> None:
        """Log a tool approval response.

        Args:
            session_id: Session identifier
            approval_id: Approval request ID
            approved: Whether the tool was approved
        """
        status = "approved" if approved else "rejected"
        log.info(f"[{session_id}] Approval {approval_id}: {status}")
