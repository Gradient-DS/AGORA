"""AG-UI Protocol event types for AGORA.

This module re-exports the official AG-UI Protocol types from the ag-ui-protocol package
and adds AGORA-specific extensions for human-in-the-loop (HITL) approval flow.

Reference: https://github.com/ag-ui-protocol/ag-ui
"""

from __future__ import annotations

from typing import Any, Literal

# Re-export all official AG-UI types
from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    Event,
    EventType,
    Message,
    MessagesSnapshotEvent,
    RawEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    State,
    StateDeltaEvent,
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
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    # Official AG-UI types
    "EventType",
    "BaseEvent",
    "TextMessageStartEvent",
    "TextMessageContentEvent",
    "TextMessageEndEvent",
    "ToolCallStartEvent",
    "ToolCallArgsEvent",
    "ToolCallEndEvent",
    "ToolCallResultEvent",
    "StateSnapshotEvent",
    "StateDeltaEvent",
    "MessagesSnapshotEvent",
    "RawEvent",
    "CustomEvent",
    "RunStartedEvent",
    "RunFinishedEvent",
    "RunErrorEvent",
    "StepStartedEvent",
    "StepFinishedEvent",
    "Event",
    "Message",
    "State",
    # AGORA extensions
    "RunAgentInput",
    "ToolApprovalRequestPayload",
    "ToolApprovalResponsePayload",
    "ErrorPayload",
    "SpokenTextErrorPayload",
    "AGORA_TOOL_APPROVAL_REQUEST",
    "AGORA_TOOL_APPROVAL_RESPONSE",
    "AGORA_ERROR",
    "AGORA_SPOKEN_TEXT_ERROR",
]


class AgoraBaseModel(BaseModel):
    """Base model with camelCase alias generation for JSON serialization."""

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        populate_by_name=True,
    )


# AGORA-specific input type (simplified version of official RunAgentInput)
class RunAgentInput(AgoraBaseModel):
    """Input for starting an agent run (client → server).

    This is a simplified version of the official RunAgentInput that matches
    the AGORA frontend expectations.
    """

    thread_id: str = Field(description="Thread/session identifier")
    run_id: str | None = Field(
        default=None,
        description="Unique run identifier (auto-generated if not provided)",
    )
    user_id: str = Field(description="User ID that owns this session (UUID)")
    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="Input messages"
    )


# AGORA-specific custom event payloads for HITL approval


class ToolApprovalRequestPayload(AgoraBaseModel):
    """Payload for agora:tool_approval_request custom event."""

    tool_name: str = Field(description="Name of the tool requiring approval")
    tool_description: str = Field(description="Description of what the tool does")
    parameters: dict[str, Any] = Field(description="Tool parameters")
    reasoning: str = Field(description="Why the agent wants to use this tool")
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        description="Risk assessment"
    )
    approval_id: str = Field(description="Unique approval request ID")


class ToolApprovalResponsePayload(AgoraBaseModel):
    """Payload for agora:tool_approval_response custom event."""

    approval_id: str = Field(description="ID matching the request")
    approved: bool = Field(description="Whether to proceed with tool execution")
    feedback: str | None = Field(default=None, description="Optional user feedback")


class ErrorPayload(AgoraBaseModel):
    """Payload for agora:error custom event."""

    error_code: str = Field(description="Error code for programmatic handling")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )


class SpokenTextErrorPayload(AgoraBaseModel):
    """Payload for agora:spoken_text_error custom event."""

    message_id: str = Field(description="Message ID this error relates to")
    error_code: str = Field(description="Error code for programmatic handling")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )


# Custom event names used by AGORA
AGORA_TOOL_APPROVAL_REQUEST = "agora:tool_approval_request"
AGORA_TOOL_APPROVAL_RESPONSE = "agora:tool_approval_response"
AGORA_ERROR = "agora:error"
AGORA_SPOKEN_TEXT_ERROR = "agora:spoken_text_error"
