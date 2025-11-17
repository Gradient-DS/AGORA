# AGORA Agent SDK Server

OpenAI Agents SDK implementation for AGORA's multi-agent compliance platform.

## Philosophy

**Maximize leverage of OpenAI's platform features. Only build what's unique to AGORA's domain.**

This implementation uses:
- ✅ **OpenAI Agents SDK** - Multi-agent orchestration with handoffs
- ✅ **Unified Voice & Text** - Same agents for both modalities via VoicePipeline
- ✅ **Autonomous Handoffs** - Agents transfer control to specialists (text & voice)
- ✅ **Session Management** - SQLite-based conversation persistence
- ✅ **Streaming Responses** - Real-time message chunks
- ✅ **Native MCP Integration** - Single SDK-native tool integration
- ✅ **Per-Agent TTS Settings** - Customized voice personalities

## What OpenAI Handles

- Agent orchestration and handoffs (text & voice)
- Conversation state (SQLiteSession)
- Tool execution loops
- Context management and token counting
- Parallel tool execution
- Streaming responses (text)
- Voice I/O (STT & TTS via VoicePipeline)

## What We Build

- HAI protocol implementation (WebSocket)
- Native MCP tool integration via Agents SDK
- Domain-specific agent definitions and handoff strategy
- Unified voice handler with VoicePipeline
- Per-agent TTS personality settings
- Audit logging and observability
- Moderation and validation

## Architecture

```
server-openai/
├── src/agora_openai/
│   ├── config.py                  # Pydantic settings
│   ├── logging_config.py          # Structured logging
│   ├── core/                      # Domain logic
│   │   ├── agent_definitions.py  # Agent configs with handoffs
│   │   └── agent_runner.py       # Agent SDK wrapper
│   ├── adapters/                  # External integrations
│   │   ├── mcp_client.py         # MCP protocol
│   │   ├── mcp_tools.py          # MCP → Agent SDK tools
│   │   ├── realtime_client.py    # OpenAI Realtime API
│   │   └── audit_logger.py       # OpenTelemetry
│   ├── pipelines/                 # Orchestration
│   │   ├── orchestrator.py       # Main coordinator
│   │   └── moderator.py          # Validation
│   └── api/                       # Entry points
│       ├── server.py              # FastAPI + WebSocket
│       ├── hai_protocol.py        # HAI messages
│       └── voice_handler.py       # Voice session handler
└── common/                        # Shared types
    ├── hai_types.py
    ├── protocols.py
    └── schemas.py
```

## Agent Flow

```
User Message → general-agent (triage)
                    ↓ handoff when needed
              ┌─────┴─────┐
              ↓           ↓
      history-agent   regulation-agent
              ↓           ↓
              └─────→ reporting-agent
                      ↓
                 general-agent
```

### Agent Roles

1. **general-agent** (Entry Point)
   - Handles greetings and general questions
   - Triages requests to specialist agents
   - Handoffs to: history, regulation, reporting

2. **history-agent**
   - Company verification (KVK lookup)
   - Inspection history
   - Violation patterns
   - Handoffs to: regulation, reporting, general

3. **regulation-agent**
   - Regulatory compliance analysis
   - Rule interpretation
   - Violation assessment
   - Handoffs to: reporting, general

4. **reporting-agent**
   - HAP report generation
   - Data extraction and verification
   - PDF/JSON report creation
   - Handoffs to: general

## Setup

1. Install dependencies:
```bash
cd server-openai
pip install -e .
```

2. Configure environment:
```bash
export APP_OPENAI_API_KEY="your_key"
export APP_MCP_SERVERS="history=http://localhost:8001,regulation=http://localhost:8002,reporting=http://localhost:8003"
export APP_GUARDRAILS_ENABLED=true
```

3. Run server:
```bash
python -m agora_openai.api.server
```

## Usage

### Text Chat via WebSocket

Connect to `/ws` endpoint using HAI protocol:

```python
import asyncio
import websockets
import json

async def chat():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        message = {
            "type": "user_message",
            "content": "Start inspectie bij KVK 12345678",
            "session_id": "test-session-123"
        }
        await websocket.send(json.dumps(message))
        
        async for response_text in websocket:
            response = json.loads(response_text)
            print(response)

asyncio.run(chat())
```

### Voice Mode

Connect to `/ws/voice` for voice interaction:

```python
message = {
    "type": "session.start",
    "session_id": "voice-123",
    "agent_id": "general-agent",
    "conversation_history": []
}
```

## Key Features

### 1. Autonomous Agent Handoffs
Agents automatically transfer control to specialists based on request analysis.

### 2. Session Persistence
SQLite-based conversation history with automatic context management.

### 3. Streaming Responses
Real-time message chunks via HAI protocol for responsive UI.

### 4. MCP Tool Integration
Dynamic tool discovery and execution from MCP servers via HTTP.

### 5. Voice Mode Support
Realtime API for voice with same agent definitions as text mode.

### 6. Tool Execution Notifications
Real-time tool status updates (started/completed/failed) to UI.

## Development

Run tests:
```bash
pytest
```

Type checking:
```bash
mypy src/
```

Linting:
```bash
ruff check src/
```

## Session Management

- **Location**: `sessions.db` in working directory
- **Persistence**: Automatic across server restarts
- **Scope**: One session per `session_id`
- **History**: Full conversation context maintained

## Performance

- Handoff detection: ~500ms
- Tool execution: ~1-2s (parallel)
- Response generation: ~500ms
- **Total: ~2-3 seconds per query**

With parallel tool calling: 3 tools @ 2s each = **2s total** (not 6s!)

## Compliance

- **EU AI Act**: Human oversight, transparency, audit logging
- **AVG/GDPR**: Privacy by design, data minimization
- **BIO**: Government security standards
- **OpenTelemetry**: Full observability and tracing

## Migration from Assistants API

See [MIGRATION_TO_AGENTS_SDK.md](MIGRATION_TO_AGENTS_SDK.md) for detailed migration guide.

**Key improvements:**
- Autonomous handoffs (vs centralized routing)
- Simpler session management (SQLiteSession vs Thread IDs)
- Code-based agent configs (version controllable)
- Unified text/voice agent definitions

## License

Proprietary - NVWA AGORA Platform
