from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    """User message from HAI."""
    type: Literal["user_message"] = "user_message"
    content: str = Field(description="User's message content")
    session_id: str = Field(description="Session identifier for conversation continuity")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class AssistantMessage(BaseModel):
    """Assistant response to HAI."""
    type: Literal["assistant_message"] = "assistant_message"
    content: str = Field(description="Assistant's response content")
    session_id: str | None = Field(default=None, description="Session identifier")
    agent_id: str | None = Field(default=None, description="Which agent generated this response")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ToolApprovalRequest(BaseModel):
    """Request human approval for tool execution."""
    type: Literal["tool_approval_request"] = "tool_approval_request"
    tool_name: str = Field(description="Name of the tool requiring approval")
    tool_description: str = Field(description="Description of what the tool does")
    parameters: dict[str, Any] = Field(description="Tool parameters")
    reasoning: str = Field(description="Why the agent wants to use this tool")
    risk_level: Literal["low", "medium", "high", "critical"] = Field(description="Risk assessment")
    session_id: str = Field(description="Session identifier")
    approval_id: str = Field(description="Unique approval request ID")


class ToolApprovalResponse(BaseModel):
    """User's approval/rejection decision."""
    type: Literal["tool_approval_response"] = "tool_approval_response"
    approval_id: str = Field(description="ID matching the request")
    approved: bool = Field(description="Whether to proceed with tool execution")
    feedback: str | None = Field(default=None, description="Optional user feedback")


class ErrorMessage(BaseModel):
    """Error message to HAI."""
    type: Literal["error"] = "error"
    error_code: str = Field(description="Error code for programmatic handling")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional error details")


class StatusMessage(BaseModel):
    """Status update message."""
    type: Literal["status"] = "status"
    status: Literal["thinking", "routing", "executing_tools", "completed"] = Field(
        description="Current processing status"
    )
    message: str | None = Field(default=None, description="Optional status message")
    session_id: str | None = Field(default=None, description="Session identifier")


HAIMessage = (
    UserMessage
    | AssistantMessage
    | ToolApprovalRequest
    | ToolApprovalResponse
    | ErrorMessage
    | StatusMessage
)

