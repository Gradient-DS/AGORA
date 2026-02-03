---
date: "2026-02-03T15:30:00+01:00"
researcher: Claude
git_commit: 7e07592a065e7652f6f84fcf8122bc38342e0809
branch: feat/benchmark
repository: AGORA
topic: "Vergelijking Technisch Ontwerp rapport (H5) met huidige codebase"
tags: [research, codebase, rapport, technisch-ontwerp, vergelijking, server-openai, server-langgraph, HAI, mcp-servers, api-gateway]
status: complete
last_updated: "2026-02-03"
last_updated_by: Claude
last_updated_note: "Correctie: TrueLime is het bedrijf dat de productie-HAI bouwt (LiveKit/WebRTC), embeddings blijven nomic-embed-text-v1.5"
---

# Research: Vergelijking Technisch Ontwerp rapport (H5) met huidige codebase

**Date**: 2026-02-03T15:30:00+01:00
**Researcher**: Claude
**Git Commit**: 7e07592a065e7652f6f84fcf8122bc38342e0809
**Branch**: feat/benchmark
**Repository**: AGORA

## Research Question

Vergelijk het rapport-hoofdstuk "5. Technisch ontwerp" met de huidige staat van de codebase. Identificeer discrepanties in technologieen, packages, ontbrekende componenten, stubs, en features die niet in het rapport beschreven zijn.

## Summary

Het rapport geeft een grotendeels correct beeld van de architectuur, maar bevat enkele inaccuraatheden in specifieke technische details (logging) en mist significante componenten die wel geimplementeerd zijn (API gateway, dual-channel streaming, listen mode, benchmark systeem, user/session management, email service). Daarnaast zijn enkele in het rapport genoemde componenten niet of slechts als stub geimplementeerd (OpenTelemetry, Grafana, Jaeger, Langfuse, KVK API, structlog).

**Context over HAI en voice**: TrueLime (Limescape) is het bedrijf dat de productie-HAI bouwt. Hun implementatie gebruikt LiveKit (WebRTC) als transport-laag met een voice-first interface (Next.js, React 19, LiveKit Agents Framework). De AGORA-repository bevat een aparte ontwikkel-HAI (React + Vite + Zustand) met ElevenLabs voice-integratie voor prototyping. Het rapport verwijst correct naar "Truelime (voice)" als de HAI-leverancier.

## Detailed Findings

### 1. Tabel 5.3 - Correcties en nuanceringen

#### LLM keuze open-source prototype

**Rapport**: "LLaMA 3.1 (OpenAI-compatible)"

**Werkelijkheid**: De default in `server-langgraph/src/agora_langgraph/config.py:38` is `gpt-4o`, identiek aan het closed-source prototype. LangGraph *ondersteunt* alternatieve providers via `LANGGRAPH_OPENAI_BASE_URL` en `LANGGRAPH_OPENAI_MODEL`, maar LLaMA 3.1 was slechts een van de testmodellen in het benchmark-systeem. Het benchmark testte 7 modellen: gpt-4o, gpt-4o-mini, gpt-5.2, qwen-2.5-72b, gpt-oss-120b, mistral-large, ministral-14b.

**Suggestie**: Nuanceren dat de default gpt-4o is, maar dat het prototype vendor-flexibel is en getest is met meerdere modellen waaronder LLaMA 3.1.

#### Embeddings

**Rapport**: "nomic-embed-text-v1.5 (lokaal)" voor beide prototypes

**Werkelijkheid**: Er zijn twee embedding-providers geimplementeerd in `mcp-servers/document-ingestion/embeddings/embedder.py`:
- `OpenAIEmbedder`: gebruikt `text-embedding-3-small` met 768 dimensies (`embedder.py:19-67`)
- `LocalEmbedder`: gebruikt `nomic-ai/nomic-embed-text-v1.5` via sentence-transformers (`embedder.py:70-148`)

De code-default provider is `openai` (`config.py:29`), maar de docker-compose configureert `MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5`. De rapportvermelding van nomic-embed-text-v1.5 is correct als beschrijving van het gekozen embeddingmodel.

**Status**: OK. Eventueel noemenswaardig dat er ook een OpenAI embedding-optie beschikbaar is als alternatief.

#### Agent-handoffs en MCP toolkoppeling (closed-source)

**Rapport**: "SDK-intern" voor handoffs, "MCP (native client)" voor toolkoppeling

**Werkelijkheid**: Er is een belangrijke workaround: MCP tools worden via `FunctionTool` wrappers geregistreerd i.p.v. de SDK's native `mcp_servers=` parameter, gedocumenteerd als workaround voor OpenAI Agents SDK issue #617 (`agent_runner.py:84`). De `MCPServerStreamableHttp` class wordt wel gebruikt voor connectie, maar tools worden individueel gewrapped.

**Suggestie**: Nuanceren dat dit een workaround betreft.

#### HAI / Voice provider

**Rapport**: "Truelime (voice)" voor beide prototypes

**Werkelijkheid**: Correct. TrueLime (Limescape) is het bedrijf dat de productie-HAI ontwikkelt. Hun deployment op `agora-hai.limescape.ai` gebruikt:
- **LiveKit** als WebRTC transport-laag voor real-time voice interactie
- **LiveKit Agents Framework** voor de STT -> LLM -> TTS pipeline
- **Next.js** (React 19) met shadcn/ui en Radix UI
- Vier functionele modi: Inspection, Dictaphone, Interview, Interpreter

De AGORA-repository bevat daarnaast een eigen ontwikkel-HAI (React 18 + Vite + Zustand) met ElevenLabs-integratie (`HAI/src/lib/elevenlabs/`) voor prototyping en benchmark-doeleinden. Deze twee HAI-implementaties zijn onafhankelijk van elkaar.

**Status**: OK.

#### Logging

**Rapport**: "structlog (JSON)" voor beide prototypes

**Werkelijkheid**:
- **server-openai**: structlog is geconfigureerd in `logging_config.py` (processors, JSONRenderer, timestamper), maar de meeste modules gebruiken `logging.getLogger(__name__)` (stdlib) i.p.v. `structlog.get_logger()`.
- **server-langgraph**: structlog staat als dependency in `pyproject.toml:24` maar wordt **nergens geimporteerd of gebruikt**. Logging is volledig via stdlib `logging.basicConfig()` in `logging_config.py:7-25`.

**Suggestie**: Correctie nodig. De implementatie gebruikt voornamelijk Python stdlib logging, niet structlog.

#### Observability / OpenTelemetry

**Rapport**: "OpenTelemetry (voorbereid)"

**Werkelijkheid**: Dependencies zijn gedeclareerd (`opentelemetry-api`, `-sdk`, `-instrumentation-fastapi`). De `AuditLogger` accepteert een `otel_endpoint` parameter maar de implementatie is een stub: `if self.enabled: pass` blokken in alle log-methoden. Er zijn geen traces, spans, of exports geimplementeerd.

**Suggestie**: Nuanceren dat het bij dependency-declaraties is gebleven.

#### Guardrails (closed-source)

**Rapport**: "SDK + approvals"

**Werkelijkheid**: Geen SDK-specifieke guardrails. Beide prototypes hebben een vrijwel identieke implementatie: `ModerationPipeline` (regex-based) + `approval_logic.py` (risk-based tool approval) + HITL via `asyncio.Future`. Het verschil is minimaal.

---

### 2. Significante componenten die ontbreken in het rapport

#### a) API Gateway (`api-gateway/`)

Een volledige reverse proxy (FastAPI) die niet in het rapport beschreven wordt:
- Path-based routing naar openai/langgraph/mock backends
- Optionele API key authenticatie met constant-time vergelijking (`secrets.compare_digest`)
- **Voice proxy**: server-side proxy voor ElevenLabs (ontwikkel-HAI), houdt API keys server-side
- Dependencies: `fastapi>=0.115.0`, `httpx>=0.27.0`, `websockets>=12.0`
- Files: `api-gateway/src/api_gateway/main.py`, `proxy.py`, `auth.py`, `config.py`

#### b) Dual-channel streaming (geschreven + gesproken tekst)

Beide prototypes implementeren parallel streaming van written en spoken text:
- **server-openai** (`orchestrator.py:214-368`): spawnt een aparte `AsyncOpenAI` chat completion call met spoken prompts + `asyncio.Queue` voor interleaving
- **server-langgraph** (`graph.py:323-509`): gebruikt LangGraph `Send` API voor parallelle `generate_written` en `generate_spoken` graph nodes, samengevoegd in `merge_parallel_outputs()`
- Spoken mode keuze per user preference: `"summarize"` (aparte LLM call) of `"dictate"` (dupliceert written)
- AG-UI custom events: `agora:spoken_text_start`, `agora:spoken_text_content`, `agora:spoken_text_end`

#### c) Voice-integratie in ontwikkel-HAI (ElevenLabs)

De AGORA-repository bevat een eigen HAI-implementatie met ElevenLabs voice (los van de TrueLime productie-HAI):
- **STT**: WebSocket naar ElevenLabs realtime API, model `scribe_v2_realtime`, VAD-gebaseerd, Nederlandse taal
- **TTS**: Streaming audio via API gateway proxy, model `eleven_multilingual_v2`
- Audio capture: `AudioContext` + `ScriptProcessorNode` met volume monitoring
- Complete hooks: `useVoiceMode`, `useTTS` met event-driven architectuur
- UI: `VoiceInterface`, `VoiceButton`, `AudioVisualizer` (canvas-based), `TTSToggle`

Dit is een aparte implementatie naast de TrueLime productie-HAI en hoeft niet per se in het rapport vermeld te worden, maar toont aan dat de orchestrator voice-ready is.

#### d) Listen mode (alleen server-langgraph)

Een alternatieve interactiemodus die alleen in het open-source prototype bestaat:
- Wake word detectie ("AGORA") via `detect_wake_word()` (`graph.py:50-56`)
- Berichten worden gebufferd in graph state (`message_buffer` met `accumulate_messages` reducer)
- Wake word triggert verwerking van alle gebufferde berichten
- Nodes: `buffer_message_node`, `process_buffer_node`, `wake_word_handler_node` (`graph.py:59-174`)
- Relevant voor vendor-vergelijking: demonstreert LangGraph's flexibiliteit voor complexe interactiepatronen

#### e) User management systeem

Volledige CRUD via REST API:
- `UserManager` class: `server-openai/src/agora_openai/adapters/user_manager.py`, `server-langgraph/src/agora_langgraph/adapters/user_manager.py`
- SQLite `users` tabel met id, email, name, role, preferences (JSON), timestamps
- Preferences: `spoken_text_type`, `interaction_mode`, `theme`, `email_reports`
- `update_user_settings` als agent-tool: het LLM kan user preferences wijzigen via conversatie
- HAI: `useUserStore`, `useAdminStore`, admin panel met user CRUD UI

#### f) Session management

- `SessionMetadataManager` met SQLite (`session_metadata` tabel)
- LLM-gegenereerde sessietitels via `gpt-4o-mini` (temperature 0.3, max 50 tokens)
- Tool call tracking per sessie (`tool_call_agents` tabel in server-openai)
- HAI: `useHistoryStore`, `useSessionStore`, conversation sidebar met hernoemen/verwijderen
- IndexedDB offline buffer voor berichten bij disconnect

#### g) Email service (Microsoft Graph API)

De reporting MCP server kan rapporten per email versturen:
- OAuth2 client credentials flow met Microsoft Graph API (`reporting/services/email_service.py`)
- HTML email template met NVWA-branding
- PDF als base64-encoded bijlage
- Configuratie via `MCP_GRAPH_TENANT_ID`, `MCP_GRAPH_CLIENT_ID`, `MCP_GRAPH_CLIENT_SECRET`

#### h) Benchmark systeem (`benchmark/`)

Volledig LLM benchmark framework:
- 7 modellen getest tegen server-langgraph (`benchmark.py:85-138`)
- 2 scenario's: `inspection_start`, `regulation_query` (`benchmark.py:142-174`)
- Pairwise vergelijking met Claude (`claude-sonnet-4-5`) als LLM-as-a-judge
- 4 evaluatiedimensies: tool_usage, agent_routing, answer_quality, language_quality
- Distractor tool scaling test: 0, 2, 5, 10, 20, 50 neptools
- Speed metrics: TTFT, response time, total time
- Visualisatie: 10 matplotlib plottypen met Nederlandse labels (`plot_results.py`)
- Resultaten in `benchmark/results/` met pairwise JSON en plot afbeeldingen

#### i) Document ingestion pipeline (`mcp-servers/document-ingestion/`)

Offline CLI pipeline voor het vullen van Weaviate:
- PDF parsing via `docling` library met OCR (`parsers/pdf_parser.py`)
- GPT-4o Vision fallback voor slecht-OCR'bare pagina's
- OpenAI `gpt-4o-mini` summarisatie
- Semantic chunking op artikel-grenzen met overlap (2000 chars, 200 overlap)
- Bidirectionele chunk-linking (`previous_chunk_id`/`next_chunk_id`)
- Nederlandse regelgeving keyword extractie via regex

#### j) Clarificatie-tool (alleen server-langgraph)

- `request_clarification()` tool gebruikt `langgraph.types.interrupt()` (`tools.py:78-107`)
- Pauzeert de graph execution, stuurt vragen naar de gebruiker
- Hervat met `Command(resume=user_content)` bij volgend bericht
- Niet beschikbaar in server-openai (SDK ondersteunt dit patroon niet native)

---

### 3. Componenten die stubs of niet-volledig geimplementeerd zijn

| Component | Rapport vermelding | Werkelijke staat |
|-----------|-------------------|------------------|
| **OpenTelemetry** | "voorbereid" | Dependencies aanwezig. `AuditLogger` heeft `otel_endpoint` maar export is `pass` stub. Geen traces, spans. |
| **Grafana + Prometheus** | "voorzien in doelarchitectuur" | Niet geimplementeerd. Alleen in C4 als `NotImplemented`. |
| **Jaeger (tracing)** | "voorzien" | Niet geimplementeerd. |
| **Langfuse (LLM observability)** | "voorzien" | Niet geimplementeerd. C4 markering: `evalService (NotImplemented)`. |
| **KVK API verificatie** | Geimpliceerd als werkend | Code in `inspection-history/server.py:170-236` retourneert altijd `{"exists": True}` via early return op regel 193. De werkelijke `httpx` call naar `opendata.kvk.nl/api/v1/hvds` is onbereikbaar. |
| **analyze_document tool** | Niet specifiek genoemd | Placeholder in `regulation-analysis/server.py:188-204`: retourneert hardcoded "This is a placeholder for document analysis". |
| **4 inspection-history tools** | Niet specifiek genoemd | `get_company_violations`, `check_repeat_violation`, `get_follow_up_status`, `search_inspections_by_inspector` zijn geimplementeerd maar uitgeschakeld (`# @mcp.tool()`, annotatie: "Temporarily disabled for demo"). |
| **Moderation pipeline** | "Moderation pipeline voor input en output" | Basale regex-based validatie. server-openai: prompt injection patronen. server-langgraph: SQL injection + XSS patronen. Geen LLM-based content moderatie. |

---

### 4. C4 diagrammen: NotImplemented componenten

De `c4/workspace.dsl` (regels 273-296) markeert deze als NotImplemented (rode stippellijn):

| Component | Beschrijving | Huidige staat |
|-----------|-------------|---------------|
| `userProfile` | PostgreSQL user database | SQLite in-process DB |
| `memory` | Vector DB voor agent-geheugen | Niet geimplementeerd |
| `visibility` | Grafana/Prometheus/Jaeger | Niet geimplementeerd |
| `evalService` | Langfuse evaluatie | Niet geimplementeerd (benchmark systeem is alternatief) |
| `authService` | Auth0/Keycloak | Simpele API key auth via gateway |

**Let op**: `Voice Interface` in HAI is in C4 gemarkeerd als NotImplemented. De productie-HAI van TrueLime heeft voice wel geimplementeerd (via LiveKit), en de ontwikkel-HAI in de repo heeft een ElevenLabs-integratie. De C4-markering is dus verouderd.

---

### 5. Functionele verschillen tussen prototypes (aanvulling op sectie 5.10)

Het rapport noemt dat "niet alle beoogde functionaliteiten in het closed-source prototype gerealiseerd konden worden." De specifieke verschillen:

| Feature | server-openai | server-langgraph |
|---------|---------------|------------------|
| Listen mode (wake word) | Niet aanwezig | Volledig (`graph.py:59-174`) |
| Clarificatie-tool (interrupt) | Niet aanwezig | Via `interrupt()` (`tools.py:78-107`) |
| Distractor tools benchmark | Niet aanwezig | Via `LANGGRAPH_DISTRACTOR_TOOLS` (`tools.py:213-315`) |
| Configureerbaar spoken model | Hardcoded OpenAI | Aparte `LANGGRAPH_SPOKEN_*` settings (`config.py:40-48`) |
| Graph state inspection | Beperkt (SDK internal) | Volledige state via checkpointer |
| Alternative LLM providers | Alleen OpenAI | Elke OpenAI-compatible provider |
| Parallel generation | Via `asyncio.Queue` | Via LangGraph `Send` API (graph-native) |
| Moderation patronen | Prompt injection focus | SQL injection + XSS focus |

---

### 6. Volledige dependency-overzichten

#### server-openai (`pyproject.toml`)

| Package | Versie | Doel |
|---------|--------|------|
| `fastapi` | `>=0.109.0` | HTTP/WebSocket framework |
| `uvicorn[standard]` | `>=0.27.0` | ASGI server |
| `websockets` | `>=12.0` | WebSocket transport |
| `openai` | `>=1.50.0` | OpenAI Python client |
| `openai-agents` | `>=0.1.0` | OpenAI Agents SDK |
| `ag-ui-protocol` | `>=0.1.0` | AG-UI event types |
| `pydantic` | `>=2.5.0` | Data models |
| `pydantic-settings` | `>=2.1.0` | Environment config |
| `httpx` | `>=0.26.0` | Async HTTP client |
| `structlog` | `>=24.1.0` | Structured logging (geconfigureerd maar beperkt gebruikt) |
| `opentelemetry-api` | `>=1.22.0` | OTel API (stub) |
| `opentelemetry-sdk` | `>=1.22.0` | OTel SDK (stub) |
| `opentelemetry-instrumentation-fastapi` | `>=0.43b0` | FastAPI instrumentatie (stub) |
| `python-dotenv` | `>=1.0.0` | .env loading |
| `numpy` | `>=1.24.0` | Numerieke operaties |
| `aiosqlite` | `>=0.19.0` | Async SQLite |

#### server-langgraph (`pyproject.toml`)

| Package | Versie | Doel |
|---------|--------|------|
| `langgraph` | `>=0.2.0` | StateGraph, ToolNode, Send, interrupt |
| `langchain-openai` | `>=0.2.0` | ChatOpenAI LLM wrapper |
| `langchain-core` | `>=0.3.0` | BaseTool, message types |
| `langchain-mcp-adapters` | `>=0.1.0` | MCP integratie |
| `langgraph-checkpoint-sqlite` | `>=2.0.0` | AsyncSqliteSaver |
| `aiosqlite` | `>=0.19.0,<0.22.0` | Async SQLite (gepiend) |
| `fastapi` | `>=0.109.0` | HTTP/WebSocket framework |
| `uvicorn[standard]` | `>=0.27.0` | ASGI server |
| `websockets` | `>=12.0` | WebSocket transport |
| `httpx` | `>=0.27.0` | Async HTTP client |
| `pydantic` | `>=2.5.0` | Data models |
| `pydantic-settings` | `>=2.1.0` | Environment config |
| `structlog` | `>=24.1.0` | Declared maar **niet gebruikt** |
| `opentelemetry-api` | `>=1.22.0` | Declared (stub) |
| `opentelemetry-sdk` | `>=1.22.0` | Declared (stub) |
| `opentelemetry-instrumentation-fastapi` | `>=0.43b0` | Declared (stub) |
| `python-dotenv` | `>=1.0.0` | .env loading |
| `ag-ui-protocol` | `>=0.1.0` | AG-UI event types |

#### HAI frontend (`package.json`)

| Package | Versie | Doel |
|---------|--------|------|
| `react` | `^18.3.1` | UI framework |
| `react-dom` | `^18.3.1` | DOM renderer |
| `zustand` | `^4.5.0` | State management (13 stores) |
| `zod` | `^3.22.4` | Runtime schema validatie |
| `@ag-ui/core` | `^0.0.41` | AG-UI Protocol types |
| `react-markdown` | `^9.0.1` | Markdown rendering |
| `remark-gfm` | `^4.0.0` | GitHub Flavored Markdown |
| `rehype-raw` | `^7.0.0` | Raw HTML in markdown |
| `lucide-react` | `^0.344.0` | Iconen |
| `clsx` | `^2.1.0` | CSS class utility |
| `tailwind-merge` | `^2.2.1` | Tailwind deduplicatie |
| `class-variance-authority` | `^0.7.0` | Component variants (shadcn/ui) |
| 7x `@radix-ui/*` | diverse | UI primitives (dialog, dropdown, toast, tooltip, avatar, scroll-area, separator, alert-dialog) |

Dev: `typescript ^5.4.2`, `vite ^5.1.4`, `vitest ^1.3.1`, `tailwindcss ^3.4.1`, `eslint ^8.57.0`, `@axe-core/react ^4.8.4`

#### MCP servers dependencies

| Server | Key packages |
|--------|-------------|
| regulation-analysis | `fastmcp`, `weaviate-client>=4.0.0`, `openai>=1.0.0`, optioneel: `sentence-transformers>=2.2.0`, `torch>=2.0.0` |
| reporting | `fastmcp>=0.2.0`, `openai>=1.10.0`, `reportlab>=4.0.0`, `requests>=2.31.0` |
| inspection-history | `fastmcp>=0.2.0`, `httpx>=0.27.0` (lichtste server) |
| document-ingestion | `docling`, `sentence-transformers`, `weaviate-client`, `openai` |

#### Infrastructuur

| Component | Versie/Details |
|-----------|---------------|
| Weaviate | `cr.weaviate.io/semitechnologies/weaviate:1.27.0` |
| Python | `>=3.11` (alle backends) |
| Node.js | via Vite (HAI build) |
| Docker | 9 containers + 1 tool-profile container |
| Caddy | Reverse proxy in productie (SSL) |

---

### 7. Productie-infrastructuur (niet in rapport)

- `docker-compose.yml`: 9 services op `agora-network` bridge
- `docker-compose.production.yml`: + Caddy reverse proxy voor SSL/TLS
- API Gateway als centraal toegangspunt (port 8080)
- Named volumes: `weaviate_data`, `reporting_storage`, `langgraph_sessions`, `caddy_data`, `caddy_config`
- Geen CI/CD configuratie aanwezig (geen `.github/workflows/`)

## Code References

- `server-openai/pyproject.toml:11-28` - Dependencies closed-source
- `server-langgraph/pyproject.toml:11-30` - Dependencies open-source
- `server-langgraph/src/agora_langgraph/config.py:38` - Default model `gpt-4o`
- `server-openai/src/agora_openai/core/agent_runner.py:84` - FunctionTool workaround
- `mcp-servers/document-ingestion/embeddings/embedder.py:70-148` - LocalEmbedder (nomic-embed-text-v1.5)
- `mcp-servers/document-ingestion/embeddings/embedder.py:151-175` - Embedder factory (openai/local)
- `server-langgraph/src/agora_langgraph/core/graph.py:59-174` - Listen mode nodes
- `server-langgraph/src/agora_langgraph/core/tools.py:78-107` - Clarificatie interrupt
- `mcp-servers/inspection-history/server.py:193` - KVK API early return (unreachable)
- `server-openai/src/agora_openai/logging_config.py:8-36` - structlog configuratie
- `server-langgraph/src/agora_langgraph/logging_config.py:7-25` - stdlib logging only
- `benchmark/benchmark.py:85-138` - Benchmark model definities
- `c4/workspace.dsl:273-296` - NotImplemented componenten
- `api-gateway/src/api_gateway/main.py` - API gateway endpoints

## Architecture Insights

1. **API Gateway als ontbrekende laag**: Het rapport beschrijft een directe HAI-naar-orchestrator verbinding, maar er zit een API gateway tussen die routing, auth, en voice proxying afhandelt.
2. **Twee HAI-implementaties**: TrueLime bouwt de productie-HAI met LiveKit/WebRTC (voice-first, Next.js). De AGORA-repo bevat een ontwikkel-HAI met ElevenLabs (text-first, React+Vite). Beide communiceren via hetzelfde AG-UI protocol met de orchestrator.
3. **Dual-channel streaming is architecturaal significant**: Het parallel genereren van geschreven en gesproken tekst is een kernfeature die de AG-UI protocol uitbreidt met custom events. Dit maakt de voice-integratie mogelijk ongeacht welke HAI-implementatie wordt gebruikt.
4. **Listen mode toont LangGraph flexibiliteit**: De wake word + buffer + batch-processing flow is alleen mogelijk door LangGraph's graph-gebaseerde state management, en demonstreert concreet de vendor-afhankelijkheidsthese.
5. **Observability gap**: Ondanks dependencies en config-parameters is er geen werkende observability pipeline. Dit is de grootste gap tussen rapport-claim en implementatie.
6. **Moderation is basaal**: Regex-based patroonherkenning, geen LLM-gebaseerde content moderatie of OpenAI Moderation API integratie.

## Open Questions

1. Moet het benchmark systeem (H6 resultatenanalyse) ook beschreven worden in H5?
2. Zijn de uitgeschakelde inspection-history tools bewust weggelaten uit het rapport, of moeten ze als "geimplementeerd maar uitgeschakeld" beschreven worden?
3. Is er een plan om de structlog configuratie werkend te maken, of moet het rapport aangepast worden naar de werkelijke situatie (stdlib logging)?
4. Moet de API gateway als aparte architectuurlaag in het rapport beschreven worden, of valt deze onder de bestaande "HAI-backend protocol" beschrijving?

## Resolved Questions

1. **TrueLime verwijzing** (opgelost): TrueLime/Limescape is het bedrijf dat de productie-HAI bouwt met LiveKit/WebRTC voice-first interface. De AGORA-repo bevat een aparte ontwikkel-HAI met ElevenLabs. "Truelime (voice)" in het rapport is correct.
2. **Embeddings** (opgelost): nomic-embed-text-v1.5 is het gekozen embeddingmodel. De codebase biedt ook een OpenAI embedding-optie, maar nomic is de primaire keuze.
