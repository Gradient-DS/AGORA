"""HAI Protocol WebSocket handler - matching server-openai interface."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

from agora_langgraph.common.hai_types import (
    UserMessage,
    AssistantMessage,
    AssistantMessageChunk,
    ErrorMessage,
    StatusMessage,
    ToolCallMessage,
    ToolApprovalRequest,
    ToolApprovalResponse,
    HAIMessage,
)

log = logging.getLogger(__name__)


class HAIProtocolHandler:
    """Handle HAI protocol WebSocket communication."""

    def __init__(self, websocket: WebSocket):
        """Initialize handler with WebSocket connection.

        Args:
            websocket: FastAPI WebSocket connection
        """
        self.websocket = websocket
        self.is_connected = True

    async def receive_message(self) -> UserMessage | ToolApprovalResponse | None:
        """Receive and parse HAI message from WebSocket.

        Returns:
            Parsed message or None on error
        """
        if not self.is_connected:
            return None

        try:
            data = await self.websocket.receive_text()
            message_dict = json.loads(data)
            message_type = message_dict.get("type")

            if message_type == "user_message":
                return UserMessage(**message_dict)
            elif message_type == "tool_approval_response":
                return ToolApprovalResponse(**message_dict)

            log.warning("Received unexpected message type: %s", message_type)
            return None

        except json.JSONDecodeError as e:
            log.error("Invalid JSON received: %s", e)
            await self.send_error("invalid_json", "Invalid JSON format")
            return None
        except Exception as e:
            log.error("Error receiving message: %s", e)
            self.is_connected = False
            return None

    async def send_message(self, message: HAIMessage) -> None:
        """Send HAI message to WebSocket.

        Args:
            message: HAI message to send
        """
        if not self.is_connected:
            log.debug("Cannot send message, WebSocket is not connected")
            return

        try:
            log.debug("Attempting to send message type: %s", message.type)
            message_json = message.model_dump_json()
            log.debug(
                "Serialized message: %s",
                message_json[:200] if len(message_json) > 200 else message_json,
            )
            await self.websocket.send_text(message_json)
            log.debug("Message sent successfully")
        except RuntimeError as e:
            if "websocket.send" in str(e) or "websocket.close" in str(e):
                log.warning("WebSocket already closed, cannot send message: %s", e)
                self.is_connected = False
            else:
                log.error("RuntimeError sending message: %s", e, exc_info=True)
                self.is_connected = False
        except Exception as e:
            log.error(
                "Exception sending message: %s (type: %s)",
                e,
                type(e).__name__,
                exc_info=True,
            )
            self.is_connected = False

    async def send_assistant_message(
        self, content: str, session_id: str, agent_id: str | None = None
    ) -> None:
        """Send complete assistant message.

        Args:
            content: Message content
            session_id: Session identifier
            agent_id: Optional agent identifier
        """
        message = AssistantMessage(
            content=content,
            session_id=session_id,
            agent_id=agent_id,
        )
        await self.send_message(message)

    async def send_assistant_message_chunk(
        self,
        content: str,
        session_id: str,
        agent_id: str | None,
        message_id: str,
        is_final: bool = False,
    ) -> None:
        """Send streaming assistant message chunk.

        Args:
            content: Chunk content
            session_id: Session identifier
            agent_id: Agent identifier
            message_id: Message identifier for grouping chunks
            is_final: Whether this is the final chunk
        """
        message = AssistantMessageChunk(
            content=content,
            session_id=session_id,
            agent_id=agent_id,
            message_id=message_id,
            is_final=is_final,
        )
        await self.send_message(message)

    async def send_status(
        self, status: str, message: str | None = None, session_id: str | None = None
    ) -> None:
        """Send status update.

        Args:
            status: Status type (thinking, routing, executing_tools, completed)
            message: Optional status message
            session_id: Optional session identifier
        """
        status_message = StatusMessage(
            status=status,  # type: ignore
            message=message,
            session_id=session_id,
        )
        await self.send_message(status_message)

    async def send_error(
        self, error_code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        """Send error message.

        Args:
            error_code: Error code
            message: Error message
            details: Optional additional details
        """
        error_message = ErrorMessage(
            error_code=error_code,
            message=message,
            details=details or {},
        )
        await self.send_message(error_message)

    async def send_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        session_id: str,
        status: str,
        result: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Send tool call notification.

        Args:
            tool_call_id: Tool call identifier
            tool_name: Name of the tool
            parameters: Tool parameters
            session_id: Session identifier
            status: Execution status (started, completed, failed)
            result: Optional result summary
            agent_id: Optional agent identifier
        """
        tool_call_message = ToolCallMessage(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            parameters=parameters,
            session_id=session_id,
            status=status,  # type: ignore
            result=result,
            agent_id=agent_id,
        )
        await self.send_message(tool_call_message)

    async def send_tool_approval_request(
        self,
        tool_name: str,
        tool_description: str,
        parameters: dict[str, Any],
        reasoning: str,
        risk_level: str,
        session_id: str,
        approval_id: str,
    ) -> None:
        """Send tool approval request.

        Args:
            tool_name: Name of the tool
            tool_description: Tool description
            parameters: Tool parameters
            reasoning: Reason for approval request
            risk_level: Risk level (low, medium, high, critical)
            session_id: Session identifier
            approval_id: Unique approval request ID
        """
        request = ToolApprovalRequest(
            tool_name=tool_name,
            tool_description=tool_description,
            parameters=parameters,
            reasoning=reasoning,
            risk_level=risk_level,  # type: ignore
            session_id=session_id,
            approval_id=approval_id,
        )
        await self.send_message(request)
