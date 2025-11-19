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

- HAI protocol implementatie (WebSocket)
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
│       ├── hai_protocol.py        # HAI berichten
│       └── voice_handler.py       # Spraak sessiebeheerder
└── common/                        # Gedeelde types
    ├── hai_types.py
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

### Tekstchat via WebSocket

Verbind met `/ws` endpoint via HAI protocol:

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
Real-time berichtfragmenten via HAI protocol voor responsieve UI.

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
