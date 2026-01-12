from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Represents a tool call request."""

    tool_name: str = Field(description="Name of the tool to execute")
    parameters: dict[str, Any] | None = Field(
        default=None, description="Parameters to pass to the tool"
    )


class ToolResult(BaseModel):
    """Represents the result of a tool execution."""

    tool_name: str = Field(description="Name of the executed tool")
    success: bool = Field(description="Whether execution succeeded")
    result: dict[str, Any] | None = Field(default=None, description="Result data")
    error: str | None = Field(default=None, description="Error message if failed")


class MCPFunction(BaseModel):
    """MCP function definition."""

    name: str = Field(description="Tool name")
    description: str = Field(description="What the tool does")
    parameters: dict[str, Any] = Field(description="JSON Schema for parameters")


class MCPTool(BaseModel):
    """MCP tool definition in OpenAI format."""

    type: str = Field(
        default="function", description="Tool type (always 'function' for MCP)"
    )
    function: MCPFunction = Field(description="Function definition")


class AgentMetadata(BaseModel):
    """Metadata about an agent."""

    agent_id: str = Field(description="Unique agent identifier")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="What the agent specializes in")
    capabilities: list[str] = Field(description="List of capabilities")


class SessionInfo(BaseModel):
    """Session information."""

    session_id: str = Field(description="Session identifier")
    thread_id: str = Field(description="OpenAI thread ID")
    created_at: str = Field(description="Creation timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
