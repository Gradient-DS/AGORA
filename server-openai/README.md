# AGORA Agent SDK Server

OpenAI Agents SDK implementatie voor het AGORA multi-agent compliance platform.

## Filosofie

**Maximaliseer het gebruik van OpenAI's platformfuncties. Bouw alleen wat uniek is voor het domein van AGORA.**

Deze implementatie maakt gebruik van:
- ✅ **OpenAI Agents SDK** - Multi-agent orchestratie met handoffs
- ✅ **Verenigde Spraak & Tekst** - Zelfde agenten voor beide modaliteiten via VoicePipeline
- ✅ **Autonome Handoffs** - Agenten dragen controle over aan specialisten (tekst & spraak)
- ✅ **Sessiebeheer** - Op SQLite gebaseerde gespreksopslag
- ✅ **Streaming Responses** - Real-time berichtfragmenten
- ✅ **Native MCP Integratie** - Enkele SDK-native tool integratie
- ✅ **Per-Agent TTS Instellingen** - Aangepaste stem persoonlijkheden

## Wat OpenAI afhandelt

- Agent orchestratie en handoffs (tekst & spraak)
- Gespreksstatus (SQLiteSession)
- Tool uitvoeringsloops
- Contextbeheer en token telling
- Parallelle tool uitvoering
- Streaming responses (tekst)
- Spraak I/O (STT & TTS via VoicePipeline)

## Wat wij bouwen

- AG-UI Protocol implementatie (WebSocket)
- Native MCP tool integratie via Agents SDK
- Domeinspecifieke agent definities en handoff strategie
- Verenigde spraakafhandelaar met VoicePipeline
- Per-agent TTS persoonlijkheidsinstellingen
- Audit logging en observability
- Moderatie en validatie

## Architectuur

```
server-openai/
├── src/agora_openai/
│   ├── config.py                  # Pydantic instellingen
│   ├── logging_config.py          # Gestructureerde logging
│   ├── core/                      # Domein logica
│   │   ├── agent_definitions.py  # Agent configs met handoffs
│   │   └── agent_runner.py       # Agent SDK wrapper
│   ├── adapters/                  # Externe integraties
│   │   ├── mcp_client.py         # MCP protocol
│   │   ├── mcp_tools.py          # MCP → Agent SDK tools
│   │   ├── realtime_client.py    # OpenAI Realtime API
│   │   └── audit_logger.py       # OpenTelemetry
│   ├── pipelines/                 # Orchestratie
│   │   ├── orchestrator.py       # Hoofdcoördinator
│   │   └── moderator.py          # Validatie
│   └── api/                       # Entry points
│       ├── server.py              # FastAPI + WebSocket
│       ├── ag_ui_handler.py       # AG-UI Protocol events
│       └── voice_handler.py       # Spraak sessiebeheerder
└── common/                        # Gedeelde types
    ├── ag_ui_types.py
    ├── protocols.py
    └── schemas.py
```

## Agent Flow

```
Gebruikersbericht → general-agent (triage)
                    ↓ handoff indien nodig
              ┌─────┴─────┐
              ↓           ↓
      history-agent   regulation-agent
              ↓           ↓
              └─────→ reporting-agent
                      ↓
                 general-agent
```

### Agent Rollen

1. **general-agent** (Toegangspunt)
   - Behandelt begroetingen en algemene vragen
   - Triages verzoeken naar gespecialiseerde agenten
   - Handoffs naar: history, regulation, reporting

2. **history-agent**
   - Bedrijfsverificatie (KVK opzoeken)
   - Inspectiegeschiedenis
   - Overtredingspatronen
   - Handoffs naar: regulation, reporting, general

3. **regulation-agent**
   - Analyse van naleving regelgeving
   - Interpretatie van regels
   - Beoordeling van overtredingen
   - Handoffs naar: reporting, general

4. **reporting-agent**
   - Generatie van HAP-rapporten
   - Data-extractie en verificatie
   - PDF/JSON rapport creatie
   - Handoffs naar: general

## Installatie

1. Installeer afhankelijkheden:
```bash
cd server-openai
pip install -e .
```

2. Configureer omgeving:
```bash
export APP_OPENAI_API_KEY="jouw_sleutel"
export APP_MCP_SERVERS="history=http://localhost:8001,regulation=http://localhost:8002,reporting=http://localhost:8003"
export APP_GUARDRAILS_ENABLED=true
```

3. Start server:
```bash
python -m agora_openai.api.server
```

## Gebruik

### Tekstchat via WebSocket (AG-UI Protocol)

Verbind met `/ws` endpoint via AG-UI Protocol:

```python
import asyncio
import websockets
import json

async def chat():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        # AG-UI RunAgentInput format
        message = {
            "threadId": "test-session-123",
            "messages": [
                {"role": "user", "content": "Start inspectie bij KVK 12345678"}
            ]
        }
        await websocket.send(json.dumps(message))
        
        # Receive AG-UI events
        async for response_text in websocket:
            event = json.loads(response_text)
            event_type = event.get("type")
            
            if event_type == "TEXT_MESSAGE_CONTENT":
                print(event.get("delta", ""), end="", flush=True)
            elif event_type == "RUN_FINISHED":
                print("\n[Run completed]")
                break

asyncio.run(chat())
```

#### AG-UI Event Types

| Event | Purpose |
|-------|---------|
| `RUN_STARTED` | Agent run began |
| `TEXT_MESSAGE_START` | New message begins |
| `TEXT_MESSAGE_CONTENT` | Streaming text chunk |
| `TEXT_MESSAGE_END` | Message complete |
| `TOOL_CALL_START` | Tool execution began |
| `TOOL_CALL_ARGS` | Tool arguments |
| `TOOL_CALL_END` | Tool finished |
| `STATE_SNAPSHOT` | Current agent state |
| `RUN_FINISHED` | Run complete |
| `RUN_ERROR` | Error occurred |
| `CUSTOM` | HITL approval events |

### Spraakmodus (TODO)

Verbind met `/ws/voice` voor spraakinteractie:

```python
message = {
    "type": "session.start",
    "session_id": "voice-123",
    "agent_id": "general-agent",
    "conversation_history": []
}
```

## Belangrijkste Kenmerken

### 1. Autonome Agent Handoffs
Agenten dragen automatisch de controle over aan specialisten op basis van verzoekanalyse.

### 2. Sessiepersistentie
Op SQLite gebaseerde gespreksgeschiedenis met automatisch contextbeheer.

### 3. Streaming Responses
Real-time berichtfragmenten via AG-UI Protocol voor responsieve UI.

### 4. MCP Tool Integratie
Dynamische tool-ontdekking en uitvoering van MCP servers via HTTP.

### 5. Meldingen van Tool-uitvoering
Real-time status updates (gestart/voltooid/mislukt) naar UI.

## Ontwikkeling

Tests uitvoeren:
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

## Sessiebeheer

- **Locatie**: `sessions.db` in werkmap
- **Persistentie**: Automatisch over server herstarts heen
- **Bereik**: Eén sessie per `session_id`
- **Geschiedenis**: Volledige gesprekscontext behouden

## Prestaties

- Handoff detectie: ~500ms
- Tool uitvoering: ~1-2s (parallel)
- Responsgeneratie: ~500ms
- **Totaal: ~2-3 seconden per vraag**

## Compliance

- **EU AI Act**: Menselijk toezicht, transparantie, audit logging
- **AVG/GDPR**: Privacy by design, dataminimalisatie
- **BIO**: Overheidsbeveiligingsstandaarden
- **OpenTelemetry**: Volledige observability en tracing

## Migratie van Assistants API

Zie [MIGRATION_TO_AGENTS_SDK.md](MIGRATION_TO_AGENTS_SDK.md) voor gedetailleerde migratiegids.

## Licentie

Zie de hoofd-README voor licentie-informatie.
