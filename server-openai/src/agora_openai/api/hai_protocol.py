from __future__ import annotations
import json
import logging
from typing import Any
from fastapi import WebSocket
from common.hai_types import (
    UserMessage,
    AssistantMessage,
    ErrorMessage,
    StatusMessage,
    HAIMessage,
)

log = logging.getLogger(__name__)


class HAIProtocolHandler:
    """Handle HAI protocol WebSocket communication."""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
    
    async def receive_message(self) -> UserMessage | None:
        """Receive and parse HAI message from WebSocket."""
        try:
            data = await self.websocket.receive_text()
            message_dict = json.loads(data)
            
            if message_dict.get("type") == "user_message":
                return UserMessage(**message_dict)
            
            log.warning("Received unexpected message type: %s", message_dict.get("type"))
            return None
            
        except json.JSONDecodeError as e:
            log.error("Invalid JSON received: %s", e)
            await self.send_error("invalid_json", "Invalid JSON format")
            return None
        except Exception as e:
            log.error("Error receiving message: %s", e)
            await self.send_error("receive_error", str(e))
            return None
    
    async def send_message(self, message: HAIMessage) -> None:
        """Send HAI message to WebSocket."""
        try:
            message_json = message.model_dump_json()
            await self.websocket.send_text(message_json)
        except Exception as e:
            log.error("Error sending message: %s", e)
    
    async def send_assistant_message(self, content: str, session_id: str, agent_id: str | None = None) -> None:
        """Send assistant message."""
        message = AssistantMessage(
            content=content,
            session_id=session_id,
            agent_id=agent_id,
        )
        await self.send_message(message)
    
    async def send_status(self, status: str, message: str | None = None, session_id: str | None = None) -> None:
        """Send status update."""
        status_message = StatusMessage(
            status=status,  # type: ignore
            message=message,
            session_id=session_id,
        )
        await self.send_message(status_message)
    
    async def send_error(self, error_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        """Send error message."""
        error_message = ErrorMessage(
            error_code=error_code,
            message=message,
            details=details or {},
        )
        await self.send_message(error_message)

