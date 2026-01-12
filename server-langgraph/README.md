# Server LangGraph

Open-source LangGraph-based orchestration backend for the AGORA multi-agent system. This is a drop-in replacement for `server-openai`, providing the same AG-UI Protocol interface while using LangGraph for agent orchestration.

## Overview

This server implements multi-agent orchestration using LangGraph's StateGraph, providing:

- **StateGraph-based routing** - Conditional edges for agent handoffs
- **Session persistence** - SQLite checkpointer for conversation history
- **Real-time streaming** - `astream_events` for AG-UI Protocol messages
- **MCP integration** - Same MCP tool servers as `server-openai`
- **OpenAI-compatible LLM** - Uses `langchain-openai` for LLM calls

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HAI Frontend                            │
└─────────────────────┬───────────────────────────────────────┘
                      │ WebSocket (AG-UI Protocol)
┌─────────────────────▼───────────────────────────────────────┐
│                  FastAPI Server                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │             AG-UI Protocol Handler                    │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Orchestrator                         │  │
│  │   (astream_events → AG-UI events)                    │  │
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
| `/ws` | WebSocket | AG-UI Protocol events |
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

Environment variables use the `LANGGRAPH_` prefix:

| Variable | Description | Default |
|----------|-------------|---------|
| `LANGGRAPH_OPENAI_API_KEY` | OpenAI-compatible API key | Required |
| `LANGGRAPH_OPENAI_BASE_URL` | Base URL for LLM API | `https://api.openai.com/v1` |
| `LANGGRAPH_OPENAI_MODEL` | Default model name | `gpt-4o` |
| `LANGGRAPH_MCP_SERVERS` | MCP servers (name=url,name2=url2) | Empty |
| `LANGGRAPH_GUARDRAILS_ENABLED` | Enable content moderation | `true` |
| `LANGGRAPH_LOG_LEVEL` | Logging level | `INFO` |
| `LANGGRAPH_HOST` | Server host | `0.0.0.0` |
| `LANGGRAPH_PORT` | Server port | `8000` |

## Alternative LLM Providers

Unlike `server-openai`, this server supports any OpenAI-compatible API endpoint. This enables:
- Cost reduction with open-source models
- Vendor independence
- Air-gapped deployments with self-hosted models

### Supported Providers

| Provider | Base URL | Notes |
|----------|----------|-------|
| OpenAI | `https://api.openai.com/v1` | Default |
| Together.ai | `https://api.together.ai/v1` | Best OSS model selection |
| Groq | `https://api.groq.com/openai/v1` | Fastest inference |
| OpenRouter | `https://openrouter.ai/api/v1` | Model aggregator |
| Fireworks | `https://api.fireworks.ai/inference/v1` | Fast, good pricing |
| vLLM | `http://localhost:8000/v1` | Self-hosted |
| Ollama | `http://localhost:11434/v1` | Local development |

### Recommended Models for Agentic Applications

| Model | Provider | Tool Calling | Cost/1M tokens |
|-------|----------|--------------|----------------|
| GPT-4o | OpenAI | Excellent | $5.00 |
| GPT-4o-mini | OpenAI | Good | $0.15 |
| DeepSeek-V3 | Together.ai | Excellent | $1.25 |
| Llama 3.3 70B | Together/Groq | Good | $0.80 |
| Qwen 2.5 72B | Together.ai | Good | $1.00 |

### Configuration Examples

**Together.ai with DeepSeek-V3:**
```bash
export LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
export LANGGRAPH_OPENAI_API_KEY=your_together_api_key
export LANGGRAPH_OPENAI_MODEL=deepseek-ai/DeepSeek-V3
```

**Groq with Llama 3.3 (fastest inference):**
```bash
export LANGGRAPH_OPENAI_BASE_URL=https://api.groq.com/openai/v1
export LANGGRAPH_OPENAI_API_KEY=your_groq_api_key
export LANGGRAPH_OPENAI_MODEL=llama-3.3-70b-versatile
```

**Self-hosted vLLM:**
```bash
export LANGGRAPH_OPENAI_BASE_URL=http://localhost:8000/v1
export LANGGRAPH_OPENAI_API_KEY=not-needed
export LANGGRAPH_OPENAI_MODEL=meta-llama/Llama-3.3-70B-Instruct
```

**Local Ollama:**
```bash
export LANGGRAPH_OPENAI_BASE_URL=http://localhost:11434/v1
export LANGGRAPH_OPENAI_API_KEY=not-needed
export LANGGRAPH_OPENAI_MODEL=llama3.3:70b
```

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
export LANGGRAPH_OPENAI_API_KEY=your-key
export LANGGRAPH_MCP_SERVERS="regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5005"
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
