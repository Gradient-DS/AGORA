"""AG-UI Protocol WebSocket handler for AGORA (OpenAI Agents SDK backend).

Handles bidirectional WebSocket communication using the official AG-UI Protocol types.
Maps OpenAI Agents SDK stream events to AG-UI Protocol events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from ag_ui.core import (
    CustomEvent,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from fastapi import WebSocket

from agora_openai.common.ag_ui_types import (
    AGORA_ERROR,
    AGORA_TOOL_APPROVAL_REQUEST,
    AGORA_TOOL_APPROVAL_RESPONSE,
    ErrorPayload,
    RunAgentInput,
    ToolApprovalRequestPayload,
    ToolApprovalResponsePayload,
)

log = logging.getLogger(__name__)


def _now_timestamp() -> int:
    """Return current timestamp as Unix milliseconds (AG-UI standard)."""
    return int(time.time() * 1000)


class AGUIProtocolHandler:
    """Handle AG-UI protocol WebSocket communication using official types.

    Uses plain JSON serialization for WebSocket transport (not SSE format).
    Maps OpenAI Agents SDK events to AG-UI Protocol events.
    """

    def __init__(self, websocket: WebSocket):
        """Initialize handler with WebSocket connection."""
        self.websocket = websocket
        self.is_connected = True
        self._send_lock = asyncio.Lock()  # Serialize concurrent WebSocket sends

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

        Uses a lock to serialize concurrent sends from multiple tasks
        (e.g., parallel written and spoken streams).
        """
        if not self.is_connected:
            return

        async with self._send_lock:
            if not self.is_connected:
                return

            try:
                event_json = event.model_dump_json(by_alias=True, exclude_none=True)
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

    # Spoken text events (for TTS)

    async def send_spoken_text_start(
        self, message_id: str, role: str = "assistant"
    ) -> None:
        """Emit agora:spoken_text_start custom event for TTS stream."""
        event = CustomEvent(
            name="agora:spoken_text_start",
            value={"messageId": message_id, "role": role},
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_spoken_text_content(self, message_id: str, delta: str) -> None:
        """Emit agora:spoken_text_content custom event for TTS stream."""
        if not delta:
            return  # Skip empty deltas
        event = CustomEvent(
            name="agora:spoken_text_content",
            value={"messageId": message_id, "delta": delta},
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_spoken_text_end(self, message_id: str) -> None:
        """Emit agora:spoken_text_end custom event for TTS stream."""
        event = CustomEvent(
            name="agora:spoken_text_end",
            value={"messageId": message_id},
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_spoken_text_error(
        self,
        message_id: str,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit agora:spoken_text_error custom event when TTS generation fails."""
        from agora_openai.common.ag_ui_types import (
            AGORA_SPOKEN_TEXT_ERROR,
            SpokenTextErrorPayload,
        )

        payload = SpokenTextErrorPayload(
            message_id=message_id,
            error_code=error_code,
            message=message,
            details=details,
        )
        event = CustomEvent(
            name=AGORA_SPOKEN_TEXT_ERROR,
            value=payload.model_dump(by_alias=True),
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
