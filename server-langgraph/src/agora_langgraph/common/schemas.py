"""Common schemas for AGORA LangGraph."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Represents a tool call for approval logic."""

    tool_name: str = Field(description="Name of the tool")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Tool parameters"
    )
