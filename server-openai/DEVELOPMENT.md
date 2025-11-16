# Development Guide

## Setup

### Prerequisites

- Python 3.11 or higher
- OpenAI API key
- Running MCP servers (optional for testing)

### Installation

1. Clone the repository:
```bash
cd server-openai
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e ".[dev]"
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your OpenAI API key
```

## Running Locally

### Start the server:
```bash
python -m agora_openai.api.server
```

Or with uvicorn:
```bash
uvicorn agora_openai.api.server:app --reload
```

Server will be available at `http://localhost:8000`

### Test WebSocket connection:

```python
import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        # Send message
        message = {
            "type": "user_message",
            "content": "What are FDA food safety regulations?",
            "session_id": "test-123"
        }
        await websocket.send(json.dumps(message))
        
        # Receive responses
        async for response in websocket:
            print(json.loads(response))
            break

asyncio.run(test_connection())
```

## Testing

### Run all tests:
```bash
pytest
```

### Run with coverage:
```bash
pytest --cov=agora_openai --cov-report=html
```

### Run specific test file:
```bash
pytest tests/test_orchestrator.py
```

### Run specific test:
```bash
pytest tests/test_orchestrator.py::test_process_message_success
```

## Code Quality

### Type checking with mypy:
```bash
mypy src/
```

### Linting with ruff:
```bash
ruff check src/
```

### Format with ruff:
```bash
ruff format src/
```

## Docker Development

### Build image:
```bash
docker build -t agora-openai .
```

### Run container:
```bash
docker run -p 8000:8000 --env-file .env agora-openai
```

### With docker-compose:
```bash
docker-compose up
```

## Project Structure

```
server-openai/
├── src/agora_openai/
│   ├── __init__.py
│   ├── config.py              # Settings management
│   ├── logging_config.py      # Logging setup
│   │
│   ├── core/                  # Domain logic
│   │   ├── agent_definitions.py
│   │   ├── routing_logic.py
│   │   └── approval_logic.py
│   │
│   ├── adapters/              # External integrations
│   │   ├── openai_assistants.py
│   │   ├── mcp_client.py
│   │   └── audit_logger.py
│   │
│   ├── pipelines/             # Orchestration
│   │   ├── orchestrator.py
│   │   └── moderator.py
│   │
│   └── api/                   # Entry point
│       ├── server.py
│       └── hai_protocol.py
│
├── common/                    # Shared types
│   ├── hai_types.py
│   ├── protocols.py
│   └── schemas.py
│
├── tests/
│   ├── conftest.py
│   ├── test_orchestrator.py
│   ├── test_moderator.py
│   ├── test_routing.py
│   └── test_approval_logic.py
│
├── pyproject.toml
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Adding New Features

### Adding a New Agent

1. Add configuration to `core/agent_definitions.py`:
```python
{
    "id": "new-agent",
    "name": "New Agent",
    "instructions": "...",
    "model": "gpt-4o",
    "tools": ["file_search", "code_interpreter"],
    "temperature": 0.3,
}
```

2. Update routing logic in `core/routing_logic.py`:
```python
selected_agent: Literal[
    "regulation-agent",
    "reporting-agent",
    "new-agent",  # Add here
]
```

3. Update routing prompt to describe when to use the new agent

### Adding New Approval Rules

Edit `core/approval_logic.py`:

```python
HIGH_RISK_TOOL_PATTERNS = [
    "delete",
    "remove",
    "my_new_risky_operation",  # Add pattern
]
```

### Adding New Moderation Rules

Edit `pipelines/moderator.py`:

```python
BLOCKED_PATTERNS = [
    r"ignore previous instructions",
    r"my_new_blocked_pattern",  # Add pattern
]
```

## Configuration

### Environment Variables

All configuration via environment variables with `APP_` prefix:

- `APP_OPENAI_API_KEY` - OpenAI API key (required)
- `APP_OPENAI_MODEL` - Default model (default: gpt-4o)
- `APP_MCP_SERVERS` - Comma-separated servers (name=url,name2=url2)
- `APP_GUARDRAILS_ENABLED` - Enable moderation (default: true)
- `APP_OTEL_ENDPOINT` - OpenTelemetry endpoint
- `APP_HOST` - Server host (default: 0.0.0.0)
- `APP_PORT` - Server port (default: 8000)
- `APP_LOG_LEVEL` - Logging level (default: INFO)

### Settings Class

Settings managed by Pydantic in `config.py`:

```python
from agora_openai.config import get_settings

settings = get_settings()
print(settings.openai_model)
```

## Logging

### Structured Logging

Uses structlog for structured JSON logging:

```python
import logging
log = logging.getLogger(__name__)

log.info("Processing message", extra={
    "session_id": session_id,
    "agent_id": agent_id,
})
```

### Log Levels

- `DEBUG` - Detailed debugging information
- `INFO` - General informational messages
- `WARNING` - Warning messages
- `ERROR` - Error messages

Set via `APP_LOG_LEVEL` environment variable.

## Debugging

### Enable Debug Logging

```bash
export APP_LOG_LEVEL=DEBUG
python -m agora_openai.api.server
```

### OpenAI API Debugging

OpenAI SDK logs automatically with Python logging:

```python
import logging
logging.getLogger("openai").setLevel(logging.DEBUG)
```

### Thread Inspection

Threads are stored in `orchestrator.threads` dict:

```python
# In orchestrator
print(f"Thread ID for session: {self.threads.get(session_id)}")
```

## Common Issues

### "No OpenAI API key"

Set `APP_OPENAI_API_KEY` in `.env` file or environment.

### "MCP server not responding"

Check that MCP servers are running and URLs are correct in `APP_MCP_SERVERS`.

### "Import errors"

Make sure you installed in development mode:
```bash
pip install -e .
```

### "Tests failing"

Tests use mocks by default, so they don't require OpenAI API key or MCP servers.

## Best Practices

### 1. Keep Logic in Core

Business logic belongs in `core/` - pure functions, no I/O.

### 2. Thin Adapters

Adapters in `adapters/` should be thin wrappers around external APIs.

### 3. Minimal Pipelines

Pipelines in `pipelines/` coordinate but don't implement logic.

### 4. Type Everything

Use type hints everywhere:
```python
async def process_message(
    self,
    message: UserMessage,
    session_id: str,
) -> AssistantMessage:
```

### 5. Test Business Logic

Focus tests on `core/` modules - these are pure and easy to test.

### 6. Mock External APIs

Mock OpenAI and MCP in tests - they're expensive and rate-limited.

### 7. Structured Logging

Always use structured logging with context:
```python
log.info("Event occurred", extra={"key": "value"})
```

## Performance Tips

### 1. Parallel Tools

OpenAI handles parallel tool execution automatically - no configuration needed.

### 2. Streaming (Future)

Consider streaming responses for better UX (not yet implemented).

### 3. Thread Caching

Threads are cached in memory - consider Redis for multi-instance deployments.

### 4. Rate Limiting

Consider implementing rate limiting per session for production.

## Contributing

### Code Style

- Follow PEP 8
- Use type hints
- Document functions
- Keep functions small and focused

### Commit Messages

- Use conventional commits format
- Be descriptive

### Pull Requests

- Include tests for new features
- Update documentation
- Run linting and type checking
- Ensure tests pass

## Resources

- [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview)
- [MCP Protocol Spec](https://modelcontextprotocol.io)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

