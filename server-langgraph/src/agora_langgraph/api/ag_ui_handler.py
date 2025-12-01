"""AG-UI Protocol WebSocket handler for AGORA.

Handles bidirectional WebSocket communication using the official AG-UI Protocol types.
Note: For WebSocket transport, we use plain JSON (not SSE format).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import WebSocket

from ag_ui.core import (
    EventType,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    StateSnapshotEvent,
    CustomEvent,
)

from agora_langgraph.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalRequestPayload,
    ToolApprovalResponsePayload,
    ErrorPayload,
    AGORA_TOOL_APPROVAL_REQUEST,
    AGORA_TOOL_APPROVAL_RESPONSE,
    AGORA_ERROR,
)

log = logging.getLogger(__name__)


def _now_timestamp() -> int:
    """Return current timestamp as Unix milliseconds (AG-UI standard)."""
    return int(time.time() * 1000)


class AGUIProtocolHandler:
    """Handle AG-UI protocol WebSocket communication using official types.

    Uses plain JSON serialization for WebSocket transport (not SSE format).
    The official EventEncoder is designed for HTTP SSE streaming.
    """

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

            # Check if it's a custom event (approval response)
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

            # Handle RunAgentInput (supports both camelCase and snake_case)
            if "threadId" in message_dict or "thread_id" in message_dict:
                return RunAgentInput(**message_dict)

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
        """Send an AG-UI event over WebSocket as plain JSON.

        Note: We use model_dump_json() directly instead of EventEncoder
        because EventEncoder outputs SSE format (data: {...}) which is
        for HTTP streaming, not WebSocket.
        """
        if not self.is_connected:
            log.debug("Cannot send event, WebSocket is not connected")
            return

        try:
            # Use Pydantic's JSON serialization with camelCase aliases
            event_json = event.model_dump_json(by_alias=True, exclude_none=True)
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

    async def send_run_started(
        self, thread_id: str, run_id: str, input_data: RunAgentInput | None = None
    ) -> None:
        """Emit RUN_STARTED event."""
        event = RunStartedEvent(
            thread_id=thread_id,
            run_id=run_id,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_run_finished(
        self, thread_id: str, run_id: str, result: Any | None = None
    ) -> None:
        """Emit RUN_FINISHED event."""
        event = RunFinishedEvent(
            thread_id=thread_id,
            run_id=run_id,
            result=result,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_run_error(self, message: str, code: str | None = None) -> None:
        """Emit RUN_ERROR event (official AG-UI error event)."""
        event = RunErrorEvent(
            message=message,
            code=code,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_step_started(self, step_name: str) -> None:
        """Emit STEP_STARTED event."""
        event = StepStartedEvent(
            step_name=step_name,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_step_finished(self, step_name: str) -> None:
        """Emit STEP_FINISHED event."""
        event = StepFinishedEvent(
            step_name=step_name,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    # Text message events

    async def send_text_message_start(
        self, message_id: str, role: str = "assistant"
    ) -> None:
        """Emit TEXT_MESSAGE_START event."""
        event = TextMessageStartEvent(
            message_id=message_id,
            role=role,  # type: ignore
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_text_message_content(self, message_id: str, delta: str) -> None:
        """Emit TEXT_MESSAGE_CONTENT event."""
        if not delta:
            return  # AG-UI requires non-empty delta
        event = TextMessageContentEvent(
            message_id=message_id,
            delta=delta,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_text_message_end(self, message_id: str) -> None:
        """Emit TEXT_MESSAGE_END event."""
        event = TextMessageEndEvent(
            message_id=message_id,
            timestamp=_now_timestamp(),
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
            tool_call_id=tool_call_id,
            tool_call_name=tool_call_name,
            parent_message_id=parent_message_id,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_tool_call_args(self, tool_call_id: str, args_json: str) -> None:
        """Emit TOOL_CALL_ARGS event."""
        event = ToolCallArgsEvent(
            tool_call_id=tool_call_id,
            delta=args_json,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_tool_call_end(self, tool_call_id: str) -> None:
        """Emit TOOL_CALL_END event (signals end of tool call streaming)."""
        event = ToolCallEndEvent(
            tool_call_id=tool_call_id,
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_tool_call_result(
        self,
        message_id: str,
        tool_call_id: str,
        content: str,
    ) -> None:
        """Emit TOOL_CALL_RESULT event with the tool execution result."""
        event = ToolCallResultEvent(
            message_id=message_id,
            tool_call_id=tool_call_id,
            content=content,
            role="tool",
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    # State events

    async def send_state_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Emit STATE_SNAPSHOT event for full state synchronization."""
        event = StateSnapshotEvent(
            snapshot=snapshot,
            timestamp=_now_timestamp(),
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
            tool_name=tool_name,
            tool_description=tool_description,
            parameters=parameters,
            reasoning=reasoning,
            risk_level=risk_level,  # type: ignore
            approval_id=approval_id,
        )
        event = CustomEvent(
            name=AGORA_TOOL_APPROVAL_REQUEST,
            value=payload.model_dump(by_alias=True),
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_error(
        self,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit agora:error custom event for AGORA-specific errors.

        For general run errors, prefer send_run_error() which uses the official
        RUN_ERROR event type.
        """
        payload = ErrorPayload(
            error_code=error_code,
            message=message,
            details=details,
        )
        event = CustomEvent(
            name=AGORA_ERROR,
            value=payload.model_dump(by_alias=True),
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)
