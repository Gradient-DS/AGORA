# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AGORA is a multi-agent compliance platform for NVWA (Dutch Food & Consumer Authority) inspectors. It orchestrates specialized AI agents via the AG-UI Protocol for inspection workflows, regulatory analysis, and report generation.

## Architecture

```
Inspector (Browser)
    ↓ WebSocket (AG-UI Protocol)
HAI (React Frontend, port 3000)
    ↓
Orchestrator (server-openai OR server-langgraph, port 8000)
    ↓ HTTP MCP Protocol
MCP Servers (FastMCP)
    ├── regulation-analysis (port 5002)
    ├── reporting (port 5003)
    └── inspection-history (port 5005)
```

### Two Orchestrator Implementations

The project provides **two functionally equivalent backends** with identical AG-UI Protocol APIs:

| | server-openai | server-langgraph |
|--|---------------|------------------|
| **Purpose** | Proprietary implementation | Open-source alternative |
| **Framework** | OpenAI Agents SDK | LangGraph + LangChain |
| **State** | `agents.SQLiteSession` | `AsyncSqliteSaver` |
| **Handoffs** | SDK built-in | ToolNode + conditional edges |
| **LLM Provider** | OpenAI only | Any OpenAI-compatible |

Both implement the same multi-agent handoff pattern and expose identical WebSocket APIs. Choose based on your requirements for vendor lock-in vs. native OpenAI integration.

**Multi-Agent Handoff Pattern**: Agents explicitly hand off to specialists based on conversation flow. Entry point is `general-agent`, which transfers to `regulation-agent`, `history-agent`, or `reporting-agent` as needed.

## Common Development Commands

### HAI Frontend
```bash
cd HAI
pnpm install              # Install dependencies
pnpm run dev              # Dev server (port 3000)
pnpm run build            # Production build
pnpm run test             # Run Vitest
pnpm run test:watch       # Watch mode
pnpm run lint             # ESLint check
pnpm run type-check       # TypeScript check
```

### Python Backends (server-openai / server-langgraph)
```bash
cd server-openai  # or server-langgraph
pip install -e ".[dev]"   # Install with dev deps
python -m agora_openai.api.server   # Run server (or agora_langgraph)
pytest                    # Run tests
mypy src/                 # Type check
ruff check src/           # Lint
black src/                # Format
```

### MCP Servers
```bash
cd mcp-servers
docker-compose up --build                    # Start all MCP servers
curl http://localhost:5002/health            # Health check
curl http://localhost:5002/mcp/tools | jq    # List tools
```

### Quick Demo (Mock Server - No Backend)
```bash
# Terminal 1
cd docs/hai-contract && python mock_server.py

# Terminal 2
cd HAI && pnpm run dev
# Configure .env.local with VITE_WS_URL=ws://localhost:8000/ws
```

### Architecture Diagrams
```bash
cd c4 && npm run up    # Structurizr on port 8080
```

## Key Architectural Patterns

### AG-UI Protocol
WebSocket-based event protocol for frontend-backend communication:
- **Lifecycle**: `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, `STEP_STARTED`, `STEP_FINISHED`
- **Text**: `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END`
- **Tools**: `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`
- **Custom**: `CUSTOM` events with `agora:*` names for HITL approval

Packages: `ag-ui-protocol>=0.1.0` (Python), `@ag-ui/core` (TypeScript)

### MCP Integration
Model Context Protocol for tool exposure:
- Orchestrator calls `/mcp/tools/call` on MCP servers
- Each agent gets scoped tools via `AGENT_MCP_MAPPING` in `core/agent_runner.py`
- FastMCP framework with HTTP transport

### Human-in-the-Loop
High-risk operations require approval via `approval_logic.py`:
- Patterns: `delete`, `submit_final`, `publish`
- Custom events: `agora:tool_approval_request`, `agora:tool_approval_response`

## Project Structure

```
HAI/                          # React frontend (TypeScript + Vite)
├── src/components/           # UI (chat/, approval/, layout/)
├── src/stores/               # Zustand state management
├── src/lib/websocket/        # AG-UI protocol client
└── src/types/                # TypeScript types & Zod schemas

server-openai/                # OpenAI Agents SDK orchestrator
├── src/agora_openai/
│   ├── core/                 # agent_definitions.py, agent_runner.py, approval_logic.py
│   ├── adapters/             # mcp_tools.py, audit_logger.py
│   ├── pipelines/            # orchestrator.py, moderator.py
│   └── api/                  # server.py, ag_ui_handler.py

server-langgraph/             # LangGraph orchestrator (open-source alternative)
├── src/agora_langgraph/
│   ├── core/                 # state.py, agents.py, graph.py
│   ├── adapters/             # mcp_client.py
│   └── api/                  # Same API as server-openai

mcp-servers/                  # FastMCP tool servers
├── regulation-analysis/      # Semantic search, compliance
├── reporting/                # HAP report generation
└── inspection-history/       # KVK verification, violations

docs/hai-contract/            # AG-UI Protocol specification
├── AG_UI_PROTOCOL.md         # Human-readable spec
├── asyncapi.yaml             # AsyncAPI 3.0 contract
├── schemas/                  # JSON Schema definitions
└── mock_server.py            # Testing mock

c4/                           # Structurizr architecture diagrams
```

## Code Conventions

### Python (Backends & MCP)
- Python 3.11+, src-layout (`src/package_name/`)
- Layered architecture: Core → Adapters → Pipelines → API
- Pydantic Settings with env prefix (`APP_`, `MCP_`)
- Protocol-based interfaces (not ABC)
- Full type hints, Google-style docstrings

### TypeScript/React (HAI)
- TypeScript strict mode
- Functional components, one per file
- Zustand for state (one store per domain)
- Zod schemas for runtime validation
- shadcn/ui + Tailwind CSS
- WCAG 2.1 AA accessibility

### Naming
- Event types: `SCREAMING_CASE`
- Custom events: `agora:event_name`
- IDs: `threadId`, `messageId`, `toolCallId`, `approvalId` (camelCase)

## Development Guidelines

1. **Protocol-First**: Update `docs/hai-contract/asyncapi.yaml` before implementing protocol changes
2. **Scoped Capabilities**: Agents only get MCP tools relevant to their domain
3. **Stream Everything**: Always stream responses (text chunks, tool status)
4. **Both Orchestrators**: API changes must be implemented identically in both server-openai and server-langgraph

## Environment Variables

Copy `.env.example` to `.env` and configure:
```bash
APP_OPENAI_API_KEY=your_key
MCP_OPENAI_API_KEY=your_key
APP_MCP_SERVERS=regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5005
```

For HAI, copy `HAI/.env.example` to `HAI/.env.local`:
```bash
VITE_WS_URL=ws://localhost:8000/ws
VITE_OPENAI_API_KEY=your_key
VITE_APP_NAME=AGORA HAI
```
