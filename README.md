# AGORA

Multi-agent compliance platform voor NVWA-inspecteurs. Orkestreert gespecialiseerde AI-agenten via het AG-UI Protocol voor inspectieworkflows, regelgevingsanalyse en rapportage.

Dit project wordt ontwikkeld in opdracht van de **Nederlandse Voedsel- en Warenautoriteit (NVWA)**.

## Contact

Voor vragen of meer informatie, neem contact op met:
- **Lex Lubbers**: [lex@gradient-ds.com](mailto:lex@gradient-ds.com)

## Functionaliteit

AGORA biedt inspecteurs:
- Real-time tekst- en spraakinterface voor inspecties
- Geautomatiseerde bedrijfsverificatie (KVK) en inspectiegeschiedenis
- Analyse van regelgeving met semantische zoekfunctionaliteit
- Generatie van HAP-inspectierapporten (JSON + PDF)
- Human-in-the-loop goedkeuringsworkflow voor risicovolle acties
- Volledige audit trail met OpenTelemetry observability

Na de pilot fase wordt dit uitgebreid tot een multi-agent systeem voor toepassing binnen de gehele NVWA.
## Architectuur

```
Inspecteur (Browser)
       ↓ WebSocket (AG-UI Protocol)
    HAI (React UI)
       ↓ 
  server-openai (FastAPI + OpenAI Agents SDK)
       ↓ MCP Protocol (HTTP)
  mcp-servers (FastMCP)
    ├── inspection-history (poort 5005)
    ├── regulation-analysis (poort 5002)
    └── reporting (poort 5003)
```

**Belangrijkste Componenten:**
- **HAI**: React frontend met tekst/spraak interface (poort 3000)
- **server-openai**: OpenAI Agents SDK orchestrator met autonome agent handoffs (poort 8000)
- **server-langgraph**: LangGraph orchestrator - open-source alternatief (poort 8000)
- **mcp-servers**: FastMCP tool servers voor domeinoperaties
- **docs/hai-contract**: AG-UI Protocol specificatie (AsyncAPI 3.0)
- **c4**: Architectuurdiagrammen (Structurizr)

## Snel aan de slag

### Vereisten

- Node.js 20+
- Python 3.11+
- Docker & Docker Compose
- pnpm 8+

### 1. Start MCP Servers

```bash
cd mcp-servers
export DOCKER_BUILDKIT=0  # macOS optimalisatie
docker-compose up --build
```

Servers starten op:
- http://localhost:5002 (Regelgevingsanalyse)
- http://localhost:5003 (Rapportage)
- http://localhost:5005 (Inspectiegeschiedenis)

### 2. Start Orchestrator Server

Je kunt kiezen tussen twee backends die dezelfde HAI Protocol API implementeren:

**Optie A: OpenAI Agents SDK (server-openai)**
```bash
cd server-openai
pip install -e .
export MCP_OPENAI_API_KEY="jouw_api_key"
export APP_MCP_SERVERS="regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5005"
python -m agora_openai.api.server
```

**Optie B: LangGraph (server-langgraph)** - Open-source alternatief
```bash
cd server-langgraph
pip install -e .
export MCP_OPENAI_API_KEY="jouw_api_key"
export APP_MCP_SERVERS="regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5005"
python -m agora_langgraph.api.server
```

Beide servers starten op http://localhost:8000 met identieke WebSocket API

### 3. Start HAI Frontend

```bash
cd HAI
pnpm install
cp .env.example .env.local  # Configureer VITE_WS_URL=ws://localhost:8000/ws
pnpm run dev
```

Frontend beschikbaar op http://localhost:3000

### 4. Bekijk Architectuurdiagrammen

```bash
cd c4
npm run up
```

Open http://localhost:8080 voor interactieve C4-diagrammen

## Projectstructuur

```
AGORA/
├── HAI/                      # React frontend (TypeScript + Vite)
│   ├── src/components/       # UI componenten (chat, voice, goedkeuring)
│   ├── src/stores/           # Zustand state management
│   └── src/lib/websocket/    # HAI protocol client
├── server-openai/            # OpenAI Agents SDK orchestrator
│   ├── src/agora_openai/
│   │   ├── core/             # Agent definities & runner
│   │   ├── adapters/         # MCP client, Realtime API
│   │   ├── pipelines/        # Orchestratie logica
│   │   └── api/              # FastAPI + WebSocket server
│   └── common/               # Gedeelde types & protocollen
├── server-langgraph/         # LangGraph orchestrator (open-source)
│   ├── src/agora_langgraph/
│   │   ├── core/             # StateGraph, agents, routing
│   │   ├── adapters/         # MCP client, checkpointer
│   │   ├── pipelines/        # Orchestratie met astream_events
│   │   └── api/              # FastAPI + WebSocket (zelfde API)
├── mcp-servers/              # FastMCP tool servers
│   ├── inspection-history/   # KVK + inspectiedata
│   ├── regulation-analysis/  # Semantische regelgeving zoeken
│   └── reporting/            # HAP rapportgeneratie
├── docs/hai-contract/        # AG-UI Protocol specificatie
│   ├── AG_UI_PROTOCOL.md     # Leesbare documentatie
│   ├── asyncapi.yaml         # Machine-leesbaar contract
│   └── schemas/              # JSON Schema definities
└── c4/                       # Architectuurdiagrammen (Structurizr DSL)
```

## Ontwikkelingsworkflow

1. **Protocolwijzigingen**: Update eerst `docs/hai-contract/asyncapi.yaml`
2. **MCP servers**: Elke server is een onafhankelijke FastMCP service
3. **Orchestrator**: Agenten gedefinieerd in `server-openai/src/agora_openai/core/agent_definitions.py`
4. **Frontend**: Componenten in `HAI/src/components/`, state in `HAI/src/stores/`
5. **Architectuur**: Bewerk `c4/workspace-openai.dsl`, bekijk op http://localhost:8080

## Testen

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

Full stack met Docker Compose (ontwikkeling):
```bash
# Start MCP servers
cd mcp-servers && docker-compose up -d

# Start OpenAI server (vereist .env configuratie)
cd server-openai && docker-compose up -d

# Start HAI (nginx)
cd HAI && docker build -t agora-hai . && docker run -p 80:80 agora-hai
```

## Documentatie

- **[AG-UI Protocol](./docs/hai-contract/AG_UI_PROTOCOL.md)**: Volledige WebSocket API specificatie
- **[HAI Contract README](./docs/hai-contract/README.md)**: AsyncAPI tooling gids
- **[MCP Servers](./mcp-servers/README.md)**: FastMCP implementatie & tools
- **[Server OpenAI](./server-openai/README.md)**: OpenAI Agents SDK orchestrator
- **[Server LangGraph](./server-langgraph/README.md)**: LangGraph orchestrator (open-source)
- **[HAI Frontend](./HAI/README.md)**: React app setup & features
- **[C4 Architectuur](./c4/README.md)**: Systeemdiagrammen & ontwerpbeslissingen
- **[Demo Scenario's](./DEMO_SCENARIOS.md)**: Voorbeeld gespreksflows

## Compliance & Standaarden

- **EU AI Act**: Human-in-the-loop, audit trails, transparantie
- **AVG/GDPR**: Dataminimalisatie, encryptie
- **BIO**: Overheidsbeveiligingsstandaarden (Baseline Informatiebeveiliging Overheid)
- **WCAG 2.1 AA**: Toegankelijkheidsconform

## Tech Stack

| Laag | Technologie |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Zustand + shadcn/ui |
| Orchestrator | OpenAI Agents SDK of LangGraph + FastAPI + WebSocket |
| Agenten | OpenAI GPT modellen met autonome handoffs |
| Tools | FastMCP (HTTP transport) |
| Protocol | AG-UI (WebSocket) + MCP (HTTP) |
| State | SQLite (sessies) + LocalStorage (UI) |
| Observability | OpenTelemetry + gestructureerde logging |

### Orchestrator Opties

| Feature | server-openai | server-langgraph |
|---------|---------------|------------------|
| Framework | OpenAI Agents SDK | LangGraph |
| State | SQLiteSession | AsyncSqliteSaver |
| Handoffs | SDK built-in | ToolNode + conditional edges |
| Streaming | Runner.run_streamed() | astream_events() |
| LLM Provider | OpenAI | Any OpenAI-compatible |

## Licentie

Dit project wordt voorbereid voor open source vrijgave. De definitieve licentie is nader te bepalen (Suggestie: MIT of EUPL).
Zie [CONTRIBUTING.md](CONTRIBUTING.md) voor richtlijnen over bijdragen.

