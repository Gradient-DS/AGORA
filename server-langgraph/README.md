# Server LangGraph

Open-source LangGraph-based orchestration backend for the AGORA multi-agent system. This is a drop-in replacement for `server-openai`, providing the same HAI Protocol interface while using LangGraph for agent orchestration.

## Overview

This server implements multi-agent orchestration using LangGraph's StateGraph, providing:

- **StateGraph-based routing** - Conditional edges for agent handoffs
- **Session persistence** - SQLite checkpointer for conversation history
- **Real-time streaming** - `astream_events` for HAI Protocol messages
- **MCP integration** - Same MCP tool servers as `server-openai`
- **OpenAI-compatible LLM** - Uses `langchain-openai` for LLM calls

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HAI Frontend                            │
└─────────────────────┬───────────────────────────────────────┘
                      │ WebSocket (HAI Protocol)
┌─────────────────────▼───────────────────────────────────────┐
│                  FastAPI Server                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              HAI Protocol Handler                     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Orchestrator                         │  │
│  │   (astream_events → HAI messages)                    │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              LangGraph StateGraph                     │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │  │
│  │  │ General │──│ History │  │Regulation│  │Reporting│ │  │
│  │  │  Agent  │  │  Agent  │  │  Agent  │  │  Agent  │ │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘ │  │
│  │       │            │            │            │       │  │
│  │       └────────────┴─────┬──────┴────────────┘       │  │
│  │                          │                           │  │
│  │                    ┌─────▼─────┐                     │  │
│  │                    │ Tool Node │                     │  │
│  │                    └───────────┘                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP (MCP Protocol)
┌─────────────────────▼───────────────────────────────────────┐
│                   MCP Tool Servers                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐    │
│  │ Regulation │  │  History   │  │     Reporting      │    │
│  │  Analysis  │  │   Server   │  │      Server        │    │
│  └────────────┘  └────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Agents

| Agent | Purpose | MCP Server |
|-------|---------|------------|
| `general-agent` | Entry point, triage, general questions | None |
| `regulation-agent` | Regulatory compliance analysis | `regulation` |
| `reporting-agent` | HAP inspection report generation | `reporting` |
| `history-agent` | Company and inspection history | `history` |

## API Compatibility

This server provides identical endpoints to `server-openai`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ws` | WebSocket | HAI Protocol messages |
| `/health` | GET | Health check |
| `/` | GET | Service info |
| `/agents` | GET | List agents |
| `/sessions/{id}/history` | GET | Conversation history |

## Installation

```bash
cd server-langgraph
pip install -e .
```

## Configuration

Environment variables (same as `server-openai`):

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_OPENAI_API_KEY` | OpenAI API key | Required |
| `APP_MCP_SERVERS` | MCP servers (name=url,name2=url2) | Empty |
| `APP_GUARDRAILS_ENABLED` | Enable content moderation | `true` |
| `APP_LOG_LEVEL` | Logging level | `INFO` |
| `APP_HOST` | Server host | `0.0.0.0` |
| `APP_PORT` | Server port | `8000` |

## Running

### Development

```bash
# Run directly
python -m agora_langgraph.api.server

# Or use the entry point
agora-langgraph
```

### Docker

```bash
docker-compose up --build
```

### With MCP Servers

```bash
export MCP_OPENAI_API_KEY=your-key
export APP_MCP_SERVERS="regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5004"
python -m agora_langgraph.api.server
```

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## Comparison with server-openai

| Feature | server-openai | server-langgraph |
|---------|---------------|------------------|
| Framework | OpenAI Agents SDK | LangGraph |
| State Management | SQLiteSession | SqliteSaver checkpointer |
| Handoffs | Built-in handoff tools | Conditional edges |
| Streaming | Runner.run_streamed() | astream_events() |
| Tool Execution | Automatic via SDK | ToolNode |
| LLM Provider | OpenAI only | Any OpenAI-compatible |

## License

See project root LICENSE file.
