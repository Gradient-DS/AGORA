# AGORA

Multi-agent compliance platform for NVWA inspectors. Orchestrates specialized AI agents via the HAI (Human Agent Interface) protocol for inspection workflows, regulatory analysis, and reporting.

## Function

AGORA provides inspectors with:
- Real-time text and voice interface for inspections
- Automated company verification (KVK) and inspection history lookup
- Regulatory compliance analysis with semantic search
- HAP inspection report generation (JSON + PDF)
- Human-in-the-loop approval workflow for high-risk actions
- Full audit trail with OpenTelemetry observability

## Architecture

```
Inspector (Browser)
       ↓ WebSocket (HAI Protocol)
    HAI (React UI)
       ↓ 
  server-openai (FastAPI + OpenAI Agents SDK)
       ↓ MCP Protocol (HTTP)
  mcp-servers (FastMCP)
    ├── inspection-history (port 5005)
    ├── regulation-analysis (port 5002)
    └── reporting (port 5003)
```

**Key Components:**
- **HAI**: React frontend with text/voice interface (port 3000)
- **server-openai**: OpenAI Agents SDK orchestrator with autonomous agent handoffs (port 8000)
- **server-opensource**: LangGraph orchestrator ⚠️ **TODO - Not implemented**
- **mcp-servers**: FastMCP tool servers for domain operations
- **docs/hai-contract**: WebSocket protocol specification (AsyncAPI 3.0)
- **c4**: Architecture diagrams (Structurizr)

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker & Docker Compose
- pnpm 8+

### 1. Start MCP Servers

```bash
cd mcp-servers
export DOCKER_BUILDKIT=0  # macOS optimization
docker-compose up --build
```

Servers start on:
- http://localhost:5002 (Regulation Analysis)
- http://localhost:5003 (Reporting)
- http://localhost:5005 (Inspection History)

### 2. Start OpenAI Server

```bash
cd server-openai
pip install -e .

# Configure environment
export APP_OPENAI_API_KEY="your_key"
export APP_MCP_SERVERS="regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,inspection-history=http://localhost:5005"

# Run server
python -m agora_openai.api.server
```

Server starts on http://localhost:8000

### 3. Start HAI Frontend

```bash
cd HAI
pnpm install
cp .env.example .env.local  # Configure VITE_WS_URL=ws://localhost:8000/ws
pnpm run dev
```

Frontend available at http://localhost:3000

### 4. View Architecture Diagrams

```bash
cd c4
npm run up
```

Open http://localhost:8080 for interactive C4 diagrams

## Project Structure

```
AGORA/
├── HAI/                      # React frontend (TypeScript + Vite)
│   ├── src/components/       # UI components (chat, voice, approval)
│   ├── src/stores/           # Zustand state management
│   └── src/lib/websocket/    # HAI protocol client
├── server-openai/            # OpenAI Agents SDK orchestrator
│   ├── src/agora_openai/
│   │   ├── core/             # Agent definitions & runner
│   │   ├── adapters/         # MCP client, Realtime API
│   │   ├── pipelines/        # Orchestration logic
│   │   └── api/              # FastAPI + WebSocket server
│   └── common/               # Shared types & protocols
├── server-opensource/        # ⚠️ TODO: LangGraph orchestrator
├── mcp-servers/              # FastMCP tool servers
│   ├── inspection-history/   # KVK + inspection data
│   ├── regulation-analysis/  # Semantic regulation search
│   └── reporting/            # HAP report generation
├── docs/hai-contract/        # HAI Protocol specification
│   ├── HAI_PROTOCOL.md       # Human-readable docs
│   ├── asyncapi.yaml         # Machine-readable contract
│   └── schemas/              # JSON Schema definitions
└── c4/                       # Architecture diagrams (Structurizr DSL)
```

## Development Workflow

1. **Protocol changes**: Update `docs/hai-contract/asyncapi.yaml` first
2. **MCP servers**: Each server is independent FastMCP service
3. **Orchestrator**: Agents defined in `server-openai/src/agora_openai/core/agent_definitions.py`
4. **Frontend**: Components in `HAI/src/components/`, state in `HAI/src/stores/`
5. **Architecture**: Edit `c4/workspace-openai.dsl`, view at http://localhost:8080

## Testing

**MCP Servers:**
```bash
curl http://localhost:5002/health
curl http://localhost:5002/mcp/tools
```

**OpenAI Server:**
```bash
cd server-openai
pytest
```

**HAI Frontend:**
```bash
cd HAI
pnpm run test
```

## Docker Deployment

Full stack with Docker Compose (development):
```bash
# Start MCP servers
cd mcp-servers && docker-compose up -d

# Start OpenAI server (requires .env configuration)
cd server-openai && docker-compose up -d

# Start HAI (nginx)
cd HAI && docker build -t agora-hai . && docker run -p 80:80 agora-hai
```

## Documentation

- **[HAI Protocol](./docs/hai-contract/HAI_PROTOCOL.md)**: Complete WebSocket API specification
- **[HAI Contract README](./docs/hai-contract/README.md)**: AsyncAPI tooling guide
- **[MCP Servers](./mcp-servers/README.md)**: FastMCP implementation & tools
- **[Server OpenAI](./server-openai/README.md)**: Agent definitions & architecture
- **[HAI Frontend](./HAI/README.md)**: React app setup & features
- **[C4 Architecture](./c4/README.md)**: System diagrams & design decisions
- **[Demo Scenarios](./DEMO_SCENARIOS.md)**: Example conversation flows

## Compliance

- **EU AI Act**: Human-in-the-loop, audit trails, transparency
- **AVG/GDPR**: Data minimization, encryption
- **BIO**: Dutch government security standards
- **WCAG 2.1 AA**: Accessibility compliant

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Zustand + shadcn/ui |
| Orchestrator | OpenAI Agents SDK + FastAPI + WebSocket |
| Agents | OpenAI GPT models with autonomous handoffs |
| Tools | FastMCP (HTTP transport) |
| Protocol | HAI (WebSocket) + MCP (HTTP) |
| State | SQLite (sessions) + LocalStorage (UI) |
| Observability | OpenTelemetry + structured logging |

## License

Proprietary - NVWA AGORA Platform

