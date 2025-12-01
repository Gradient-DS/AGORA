"""AG-UI Protocol WebSocket handler for AGORA.

Handles bidirectional WebSocket communication using the AG-UI Protocol,
replacing the previous HAI Protocol implementation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from agora_langgraph.common.ag_ui_types import (
    EventType,
    RunStartedEvent,
    RunFinishedEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    CustomEvent,
    ToolApprovalRequestPayload,
    ToolApprovalResponsePayload,
    ErrorPayload,
    RunAgentInput,
    AGORA_TOOL_APPROVAL_REQUEST,
    AGORA_TOOL_APPROVAL_RESPONSE,
    AGORA_ERROR,
)

log = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class AGUIProtocolHandler:
    """Handle AG-UI protocol WebSocket communication."""

    def __init__(self, websocket: WebSocket):
        """Initialize handler with WebSocket connection."""
        self.websocket = websocket
        self.is_connected = True

    async def receive_message(
        self,
    ) -> RunAgentInput | ToolApprovalResponsePayload | None:
        """Receive and parse AG-UI message from WebSocket.

        Returns:
            Parsed input or approval response, or None on error
        """
        if not self.is_connected:
            return None

        try:
            data = await self.websocket.receive_text()
            message_dict = json.loads(data)

            # Check if it's a run input or a custom event (approval response)
            if (
                "type" in message_dict
                and message_dict.get("type") == EventType.CUSTOM.value
            ):
                name = message_dict.get("name", "")
                if name == AGORA_TOOL_APPROVAL_RESPONSE:
                    value = message_dict.get("value", {})
                    return ToolApprovalResponsePayload(**value)
                log.warning("Received unknown custom event: %s", name)
                return None

            # Otherwise treat as RunAgentInput
            if "threadId" in message_dict:
                return RunAgentInput(**message_dict)

            # Legacy support: convert old HAI format to AG-UI
            if message_dict.get("type") == "user_message":
                return RunAgentInput(
                    threadId=message_dict.get("session_id", ""),
                    runId=message_dict.get("metadata", {}).get("run_id", ""),
                    messages=[
                        {"role": "user", "content": message_dict.get("content", "")}
                    ],
                    context=message_dict.get("metadata"),
                )

            log.warning("Received unexpected message format: %s", message_dict.keys())
            return None

        except json.JSONDecodeError as e:
            log.error("Invalid JSON received: %s", e)
            await self.send_error("invalid_json", "Invalid JSON format")
            return None
        except Exception as e:
            log.error("Error receiving message: %s", e)
            self.is_connected = False
            return None

    async def _send_event(self, event: Any) -> None:
        """Send an AG-UI event over WebSocket."""
        if not self.is_connected:
            log.debug("Cannot send event, WebSocket is not connected")
            return

        try:
            event_json = event.model_dump_json(by_alias=True)
            log.debug("Sending event: %s", event.type)
            await self.websocket.send_text(event_json)
        except RuntimeError as e:
            if "websocket.send" in str(e) or "websocket.close" in str(e):
                log.warning("WebSocket already closed, cannot send event: %s", e)
                self.is_connected = False
            else:
                log.error("RuntimeError sending event: %s", e, exc_info=True)
                self.is_connected = False
        except Exception as e:
            log.error("Exception sending event: %s", e, exc_info=True)
            self.is_connected = False

    # Lifecycle events

    async def send_run_started(self, thread_id: str, run_id: str) -> None:
        """Emit RUN_STARTED event."""
        event = RunStartedEvent(
            threadId=thread_id,
            runId=run_id,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_run_finished(self, thread_id: str, run_id: str) -> None:
        """Emit RUN_FINISHED event."""
        event = RunFinishedEvent(
            threadId=thread_id,
            runId=run_id,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_step_started(
        self, step_name: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Emit STEP_STARTED event."""
        event = StepStartedEvent(
            stepName=step_name,
            metadata=metadata,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_step_finished(self, step_name: str) -> None:
        """Emit STEP_FINISHED event."""
        event = StepFinishedEvent(
            stepName=step_name,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    # Text message events

    async def send_text_message_start(
        self, message_id: str, role: str = "assistant"
    ) -> None:
        """Emit TEXT_MESSAGE_START event."""
        event = TextMessageStartEvent(
            messageId=message_id,
            role=role,  # type: ignore
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_text_message_content(self, message_id: str, delta: str) -> None:
        """Emit TEXT_MESSAGE_CONTENT event."""
        event = TextMessageContentEvent(
            messageId=message_id,
            delta=delta,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_text_message_end(self, message_id: str) -> None:
        """Emit TEXT_MESSAGE_END event."""
        event = TextMessageEndEvent(
            messageId=message_id,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    # Tool call events

    async def send_tool_call_start(
        self,
        tool_call_id: str,
        tool_call_name: str,
        parent_message_id: str | None = None,
    ) -> None:
        """Emit TOOL_CALL_START event."""
        event = ToolCallStartEvent(
            toolCallId=tool_call_id,
            toolCallName=tool_call_name,
            parentMessageId=parent_message_id,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_tool_call_args(self, tool_call_id: str, args_json: str) -> None:
        """Emit TOOL_CALL_ARGS event."""
        event = ToolCallArgsEvent(
            toolCallId=tool_call_id,
            delta=args_json,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_tool_call_end(
        self,
        tool_call_id: str,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        """Emit TOOL_CALL_END event."""
        event = ToolCallEndEvent(
            toolCallId=tool_call_id,
            result=result,
            error=error,
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    # Custom events for HITL approval

    async def send_tool_approval_request(
        self,
        tool_name: str,
        tool_description: str,
        parameters: dict[str, Any],
        reasoning: str,
        risk_level: str,
        approval_id: str,
    ) -> None:
        """Emit agora:tool_approval_request custom event."""
        payload = ToolApprovalRequestPayload(
            toolName=tool_name,
            toolDescription=tool_description,
            parameters=parameters,
            reasoning=reasoning,
            riskLevel=risk_level,  # type: ignore
            approvalId=approval_id,
        )
        event = CustomEvent(
            name=AGORA_TOOL_APPROVAL_REQUEST,
            value=payload.model_dump(),
            timestamp=_now_iso(),
        )
        await self._send_event(event)

    async def send_error(
        self,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit agora:error custom event."""
        payload = ErrorPayload(
            errorCode=error_code,
            message=message,
            details=details,
        )
        event = CustomEvent(
            name=AGORA_ERROR,
            value=payload.model_dump(),
            timestamp=_now_iso(),
        )
        await self._send_event(event)
