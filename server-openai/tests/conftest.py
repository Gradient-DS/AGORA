import pytest
from typing import Any, AsyncGenerator
from agora_openai.adapters.openai_assistants import OpenAIAssistantsClient
from agora_openai.adapters.mcp_client import MCPToolClient
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.pipelines.orchestrator import Orchestrator


class MockOpenAIAssistantsClient:
    """Mock OpenAI Assistants API."""
    
    def __init__(self):
        self.threads: dict[str, list[str]] = {}
        self.assistants: dict[str, str] = {}
    
    async def initialize_assistant(
        self,
        agent_id: str,
        name: str,
        instructions: str,
        model: str,
        tools: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> str:
        assistant_id = f"asst_mock_{agent_id}"
        self.assistants[agent_id] = assistant_id
        return assistant_id
    
    async def create_thread(self, metadata: dict[str, Any] | None = None) -> str:
        thread_id = f"thread_mock_{len(self.threads)}"
        self.threads[thread_id] = []
        return thread_id
    
    async def send_message(self, thread_id: str, content: str) -> None:
        if thread_id in self.threads:
            self.threads[thread_id].append(content)
    
    async def run_assistant_with_tools(
        self,
        thread_id: str,
        assistant_id: str,
        tool_executor: Any,
    ) -> str:
        return "Mock response from assistant"
    
    async def route_with_structured_output(
        self,
        message: str,
        context: dict[str, Any],
        response_model: type,
    ) -> Any:
        from agora_openai.core.routing_logic import AgentSelection
        return AgentSelection(
            selected_agent="regulation-agent",
            reasoning="Mock routing",
            confidence=0.95,
        )


class MockMCPToolClient:
    """Mock MCP tool client."""
    
    def __init__(self):
        self.tool_definitions = []
    
    async def discover_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "mock_tool",
                    "description": "A mock tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        return {"status": "success", "result": "mock result"}


@pytest.fixture
def mock_openai_client() -> MockOpenAIAssistantsClient:
    """Provide mock OpenAI client."""
    return MockOpenAIAssistantsClient()


@pytest.fixture
def mock_mcp_client() -> MockMCPToolClient:
    """Provide mock MCP client."""
    return MockMCPToolClient()


@pytest.fixture
def audit_logger() -> AuditLogger:
    """Provide audit logger."""
    return AuditLogger(otel_endpoint=None)


@pytest.fixture
def moderator() -> ModerationPipeline:
    """Provide moderator."""
    return ModerationPipeline(enabled=True)


@pytest.fixture
async def orchestrator(
    mock_openai_client: MockOpenAIAssistantsClient,
    mock_mcp_client: MockMCPToolClient,
    moderator: ModerationPipeline,
    audit_logger: AuditLogger,
) -> AsyncGenerator[Orchestrator, None]:
    """Provide orchestrator with mocked dependencies."""
    orch = Orchestrator(
        openai_client=mock_openai_client,
        mcp_client=mock_mcp_client,
        moderator=moderator,
        audit_logger=audit_logger,
    )
    yield orch

