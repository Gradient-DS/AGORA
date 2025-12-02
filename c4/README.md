# AGORA C4 Architectuur Diagrammen

Deze directory bevat de C4-model architectuurdocumentatie voor AGORA v1.0, het multi-agent systeem voor NVWA-inspecteurs.

## 📋 Wat is C4?

Het [C4-model](https://c4model.com/) beschrijft softwarearchitectuur op vier niveaus:
1. **Systeemcontext (C1)** - Hoe past AGORA in het grotere systeem?
2. **Containers (C2)** - Welke applicaties en dataopslag vormen AGORA?
3. **Componenten (C3)** - Hoe zijn individuele containers intern gestructureerd?
4. **Code (C4)** - Gedetailleerde implementatie (optioneel)

## 🚀 Snel aan de slag

### Vereisten
- Docker geïnstalleerd
- Poort 8080 beschikbaar

### Starten

**Optie 1: Via npm scripts** (aanbevolen)
```bash
cd c4
npm run up
```

**Optie 2: Direct via Docker**
```bash
cd c4
docker compose up -d
```

### Bekijken
Open in je browser: **http://localhost:8080**

Structurizr Lite laadt automatisch het `workspace.dsl` bestand en toont alle beschikbare diagrammen in het linkerpaneel.

### Stoppen
```bash
cd c4
npm run down
```

## 📐 Beschikbare Diagrammen

### C1: Systeemcontext
Toont AGORA in relatie tot:
- **NVWA Inspecteur** - Gebruiker van het systeem
- **AGORA** - Multi-agent compliance platform
- **MCP Agent Ecosystem** - Uitbreidbare domain agents via MCP Protocol

### C2: Container Diagram
Toont alle AGORA containers:

| Container | Status | Beschrijving |
|-----------|--------|--------------|
| **HAI** | ✅ Geïmplementeerd | React + Vite + Zustand frontend |
| **Orchestrator** | ✅ Geïmplementeerd | OpenAI of OpenSource (LangGraph) backend |
| **MCP Agent Servers** | ✅ Geïmplementeerd | FastMCP domain agents |
| **User Profile** | 🚧 Niet geïmplementeerd | PostgreSQL voor RBAC |
| **Memory Service** | 🚧 Niet geïmplementeerd | Vector DB voor long-term memory |
| **Visibility Stack** | 🚧 Niet geïmplementeerd | Grafana + Prometheus + Jaeger |
| **Evaluation Service** | 🚧 Niet geïmplementeerd | Langfuse voor LLM tracing |
| **Auth Service** | 🚧 Niet geïmplementeerd | OAuth2/OIDC authenticatie |

### C3: HAI Componenten (Shared)
Uitsplitsing van de HAI frontend:
- **Chat Components** - ChatInterface, ChatMessageList, ChatInput, ToolCallCard
- **Approval Dialog** - Human-in-the-loop tool approval workflow
- **Debug Panel** - Tool call visualisatie
- **State Management** - Zustand stores (messages, sessions, connections, etc.)
- **WebSocket Client** - AG-UI Protocol communicatie
- **Voice Interface** - 🚧 Niet geïmplementeerd (Whisper + ElevenLabs)

### C3: Orchestrator [OpenAI] Componenten
Uitsplitsing van de OpenAI Agents SDK implementatie:

| Layer | Componenten |
|-------|-------------|
| **API Layer** | FastAPI Server, AG-UI Protocol Handler, REST Endpoints |
| **Pipelines Layer** | Orchestrator Pipeline, Moderator |
| **Core Layer** | Agent Definitions (agents.Agent), Agent Executor (agents.Runner), Handoff Logic (SDK built-in), Approval Logic, Session Persistence (SQLiteSession) |
| **Adapters Layer** | MCP Adapter (MCPServerStreamableHttp), Audit Logger (OpenTelemetry) |

### C3: Orchestrator [OpenSource] Componenten
Uitsplitsing van de LangGraph implementatie:

| Layer | Componenten |
|-------|-------------|
| **API Layer** | FastAPI Server, AG-UI Protocol Handler, REST Endpoints |
| **Pipelines Layer** | Orchestrator Pipeline, Moderator |
| **Core Layer** | Agent Definitions (async functions), Agent Executor (StateGraph), Tool Executor (ToolNode), Handoff Logic (transfer_to_* tools), Routing Logic, Approval Logic, Session Persistence (AsyncSqliteSaver) |
| **Adapters Layer** | MCP Adapter (langchain-mcp-adapters), Audit Logger (OpenTelemetry) |

### C3: MCP Agent Servers (Shared)
Beschikbare MCP servers:
- **Regulation Agent** (:5002) - search_regulations, analyze_document, lookup_articles
- **Reporting Agent** (:5003) - start/extract/verify/generate inspection reports
- **History Agent** (:5005) - company history, violations, repeat checks

## 🏷️ Tag Systeem

De architectuur gebruikt tags om implementatiestatus aan te geven:

| Tag | Kleur | Betekenis |
|-----|-------|-----------|
| `Shared` | Lichtblauw | Gedeeld tussen OpenAI en OpenSource backends |
| `OpenAI` | Groen | Specifiek voor OpenAI Agents SDK implementatie |
| `OpenSource` | Oranje | Specifiek voor LangGraph implementatie |
| `NotImplemented` | Rood (dashed) | Nog niet geïmplementeerd |

## 🔄 Workflow in Cursor

### Live Bewerken
1. Open `workspace.dsl` in Cursor
2. Maak wijzigingen
3. Sla op (Cmd+S / Ctrl+S)
4. Refresh je browser - Structurizr Lite herlaadt automatisch

### AI-Ondersteund Bewerken
Selecteer een blok in `workspace.dsl` en vraag Cursor:
- "Voeg een nieuwe MCP server toe voor planning"
- "Markeer de Auth Service als geïmplementeerd"
- "Voeg een deployment view toe voor productie"

### Diagrammen Exporteren
In Structurizr UI:
1. Selecteer een diagram
2. Klik **Share** → **Export diagrams**
3. Kies formaat: PNG, SVG, PlantUML

## 📝 Architectuur Highlights

### Twee Backend Implementaties
AGORA ondersteunt twee backend implementaties met dezelfde HAI frontend:

1. **OpenAI Agents SDK** - Native handoffs, SDK session persistence
2. **LangGraph** - StateGraph met explicit routing, provider-agnostisch

Beide implementaties delen:
- AG-UI Protocol voor frontend communicatie
- MCP Protocol voor agent communicatie
- Approval Logic voor human-in-the-loop
- Moderator voor input/output validatie

### Belangrijke Koppelingen

#### K.1: AG-UI Protocol
- **Van:** HAI → Orchestrator
- **Type:** WebSocket/JSON op :8001
- **Events:** RUN_STARTED/FINISHED, TEXT_MESSAGE_*, TOOL_CALL_*, STATE_SNAPSHOT, CUSTOM (approval)

#### K.2: MCP Protocol
- **Van:** Orchestrator → MCP Agent Servers
- **Type:** HTTP POST /mcp (Streamable HTTP)
- **Voordelen:** Auditeerbaar, observeerbaar, uitbreidbaar

### Technologie Stack (v1.0)

| Component | Technologie | Status |
|-----------|-------------|--------|
| Frontend | React + Vite + Zustand + TailwindCSS | ✅ |
| Backend (OpenAI) | FastAPI + OpenAI Agents SDK | ✅ |
| Backend (OpenSource) | FastAPI + LangGraph | ✅ |
| Agent Protocol | MCP (FastMCP) | ✅ |
| Session Persistence | SQLite | ✅ |
| Logging | OpenTelemetry | ⚠️ Basis |
| Observability | Grafana + Prometheus + Jaeger | 🚧 |
| Auth | OAuth2/OIDC | 🚧 |

## 🛡️ Compliance

AGORA v1.0 is ontworpen voor:
- **EU AI Act** - Traceerbaarheid, human-in-the-loop, risicobeoordeling
- **AVG/GDPR** - Encryptie, minimale verwerking
- **BIO** - Passende beveiligingsmaatregelen voor overheid
- **WCAG** - Toegankelijkheidsrichtlijnen

## 📚 Bronnen

- [C4 Model](https://c4model.com/)
- [Structurizr DSL](https://github.com/structurizr/dsl)
- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [FastMCP](https://github.com/jlowin/fastmcp)

## 🤝 Bijdragen

Bij het bijwerken van de architectuur:
1. Update eerst `workspace.dsl`
2. Controleer de diagrammen in Structurizr Lite
3. Gebruik correcte tags (`Shared`, `OpenAI`, `OpenSource`, `NotImplemented`)
4. Commit het `.dsl` bestand - diagrammen zijn reproduceerbaar

## 💡 Tips

- **Auto-layout** werkt goed voor nieuwe diagrammen
- **Tags** bepalen kleuren en styling automatisch
- **[NOT IMPLEMENTED]** in description + `NotImplemented` tag voor toekomstige features
- **Consistentie** - gebruik dezelfde terminologie als in technisch ontwerp
