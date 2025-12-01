"""AG-UI Protocol event types for AGORA.

This module defines the AG-UI Protocol events used for communication between
the HAI frontend and the LangGraph orchestrator backend.

Reference: https://github.com/ag-ui-protocol/ag-ui
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """AG-UI Protocol event types."""

    # Lifecycle events
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"

    # Text message events
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"

    # Tool call events
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"

    # State events
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"

    # Extension events
    CUSTOM = "CUSTOM"
    RAW = "RAW"


class BaseEvent(BaseModel):
    """Base class for all AG-UI events."""

    type: EventType = Field(description="Event type discriminator")
    timestamp: str | None = Field(default=None, description="ISO 8601 timestamp")


# Lifecycle Events


class RunStartedEvent(BaseEvent):
    """Emitted when an agent run begins."""

    type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED
    threadId: str = Field(description="Thread/session identifier")
    runId: str = Field(description="Unique run identifier")


class RunFinishedEvent(BaseEvent):
    """Emitted when an agent run completes."""

    type: Literal[EventType.RUN_FINISHED] = EventType.RUN_FINISHED
    threadId: str = Field(description="Thread/session identifier")
    runId: str = Field(description="Unique run identifier")


class StepStartedEvent(BaseEvent):
    """Emitted when a processing step begins."""

    type: Literal[EventType.STEP_STARTED] = EventType.STEP_STARTED
    stepName: str = Field(description="Name of the step (e.g., 'thinking', 'routing')")
    metadata: dict[str, Any] | None = Field(default=None, description="Step metadata")


class StepFinishedEvent(BaseEvent):
    """Emitted when a processing step completes."""

    type: Literal[EventType.STEP_FINISHED] = EventType.STEP_FINISHED
    stepName: str = Field(description="Name of the step")


# Text Message Events


class TextMessageStartEvent(BaseEvent):
    """Emitted when a text message begins."""

    type: Literal[EventType.TEXT_MESSAGE_START] = EventType.TEXT_MESSAGE_START
    messageId: str = Field(description="Unique message identifier")
    role: Literal["user", "assistant"] = Field(description="Message role")


class TextMessageContentEvent(BaseEvent):
    """Emitted for each content chunk of a streaming message."""

    type: Literal[EventType.TEXT_MESSAGE_CONTENT] = EventType.TEXT_MESSAGE_CONTENT
    messageId: str = Field(description="Message identifier matching start event")
    delta: str = Field(description="Content chunk")


class TextMessageEndEvent(BaseEvent):
    """Emitted when a text message is complete."""

    type: Literal[EventType.TEXT_MESSAGE_END] = EventType.TEXT_MESSAGE_END
    messageId: str = Field(description="Message identifier matching start event")


# Tool Call Events


class ToolCallStartEvent(BaseEvent):
    """Emitted when a tool call begins."""

    type: Literal[EventType.TOOL_CALL_START] = EventType.TOOL_CALL_START
    toolCallId: str = Field(description="Unique tool call identifier")
    toolCallName: str = Field(description="Name of the tool being called")
    parentMessageId: str | None = Field(
        default=None, description="ID of the message that triggered this tool call"
    )


class ToolCallArgsEvent(BaseEvent):
    """Emitted to stream tool call arguments."""

    type: Literal[EventType.TOOL_CALL_ARGS] = EventType.TOOL_CALL_ARGS
    toolCallId: str = Field(description="Tool call identifier")
    delta: str = Field(description="JSON string of arguments (can be streamed)")


class ToolCallEndEvent(BaseEvent):
    """Emitted when a tool call completes."""

    type: Literal[EventType.TOOL_CALL_END] = EventType.TOOL_CALL_END
    toolCallId: str = Field(description="Tool call identifier")
    result: str | None = Field(default=None, description="Tool execution result")
    error: str | None = Field(default=None, description="Error message if failed")


# State Events


class StateSnapshotEvent(BaseEvent):
    """Full state snapshot for synchronization."""

    type: Literal[EventType.STATE_SNAPSHOT] = EventType.STATE_SNAPSHOT
    snapshot: dict[str, Any] = Field(description="Full state snapshot")


class StateDeltaEvent(BaseEvent):
    """Incremental state update using JSON Patch format."""

    type: Literal[EventType.STATE_DELTA] = EventType.STATE_DELTA
    delta: list[dict[str, Any]] = Field(description="JSON Patch operations")


class MessagesSnapshotEvent(BaseEvent):
    """Snapshot of conversation messages."""

    type: Literal[EventType.MESSAGES_SNAPSHOT] = EventType.MESSAGES_SNAPSHOT
    messages: list[dict[str, Any]] = Field(description="List of messages")


# Custom Events (for HITL approval and errors)


class CustomEvent(BaseEvent):
    """Custom event for protocol extensions."""

    type: Literal[EventType.CUSTOM] = EventType.CUSTOM
    name: str = Field(
        description="Custom event name (e.g., 'agora:tool_approval_request')"
    )
    value: dict[str, Any] = Field(description="Event payload")


class RawEvent(BaseEvent):
    """Raw untyped event for edge cases."""

    type: Literal[EventType.RAW] = EventType.RAW
    data: Any = Field(description="Raw event data")


# AGORA-specific custom event payloads


class ToolApprovalRequestPayload(BaseModel):
    """Payload for agora:tool_approval_request custom event."""

    toolName: str = Field(description="Name of the tool requiring approval")
    toolDescription: str = Field(description="Description of what the tool does")
    parameters: dict[str, Any] = Field(description="Tool parameters")
    reasoning: str = Field(description="Why the agent wants to use this tool")
    riskLevel: Literal["low", "medium", "high", "critical"] = Field(
        description="Risk assessment"
    )
    approvalId: str = Field(description="Unique approval request ID")


class ToolApprovalResponsePayload(BaseModel):
    """Payload for agora:tool_approval_response custom event."""

    approvalId: str = Field(description="ID matching the request")
    approved: bool = Field(description="Whether to proceed with tool execution")
    feedback: str | None = Field(default=None, description="Optional user feedback")


class ErrorPayload(BaseModel):
    """Payload for agora:error custom event."""

    errorCode: str = Field(description="Error code for programmatic handling")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )


# Input types (client → server)


class RunAgentInput(BaseModel):
    """Input for starting an agent run (client → server)."""

    threadId: str = Field(description="Thread/session identifier")
    runId: str = Field(description="Unique run identifier")
    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="Input messages"
    )
    context: dict[str, Any] | None = Field(
        default=None, description="Additional context"
    )


class Message(BaseModel):
    """A conversation message."""

    role: Literal["user", "assistant", "system", "tool"] = Field(
        description="Message role"
    )
    content: str = Field(description="Message content")
    id: str | None = Field(default=None, description="Message ID")
    toolCallId: str | None = Field(
        default=None, description="Tool call ID for tool messages"
    )


# Union type for all events
AGUIEvent = (
    RunStartedEvent
    | RunFinishedEvent
    | StepStartedEvent
    | StepFinishedEvent
    | TextMessageStartEvent
    | TextMessageContentEvent
    | TextMessageEndEvent
    | ToolCallStartEvent
    | ToolCallArgsEvent
    | ToolCallEndEvent
    | StateSnapshotEvent
    | StateDeltaEvent
    | MessagesSnapshotEvent
    | CustomEvent
    | RawEvent
)


# Custom event names used by AGORA
AGORA_TOOL_APPROVAL_REQUEST = "agora:tool_approval_request"
AGORA_TOOL_APPROVAL_RESPONSE = "agora:tool_approval_response"
AGORA_ERROR = "agora:error"
