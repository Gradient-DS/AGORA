from __future__ import annotations
from typing import Protocol, Any
from common.hai_types import UserMessage, AssistantMessage


class Orchestrator(Protocol):
    """Protocol for orchestrator implementations."""
    
    async def process_message(
        self,
        message: UserMessage,
        session_id: str,
    ) -> AssistantMessage:
        """Process user message and return assistant response."""
        ...


class ToolClient(Protocol):
    """Protocol for tool execution clients."""
    
    async def discover_tools(self) -> list[dict[str, Any]]:
        """Discover available tools."""
        ...
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool with given parameters."""
        ...


class Moderator(Protocol):
    """Protocol for moderation implementations."""
    
    async def validate_input(self, content: str) -> tuple[bool, str | None]:
        """Validate user input. Returns (is_valid, error_message)."""
        ...
    
    async def validate_output(self, content: str) -> tuple[bool, str | None]:
        """Validate assistant output. Returns (is_valid, error_message)."""
        ...


class AuditLogger(Protocol):
    """Protocol for audit logging implementations."""
    
    async def log_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        """Log a message exchange."""
        ...
    
    async def log_tool_execution(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
        session_id: str,
    ) -> None:
        """Log tool execution."""
        ...
    
    async def log_approval_request(
        self,
        approval_id: str,
        tool_name: str,
        approved: bool,
        session_id: str,
    ) -> None:
        """Log approval decision."""
        ...

