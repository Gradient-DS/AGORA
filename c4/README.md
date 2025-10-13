# AGORA C4 Architectuur Diagrammen

Deze directory bevat de C4 model architectuur documentatie voor AGORA v1.0, het multi-agent systeem voor NVWA inspecteurs.

## 📋 Wat is C4?

Het [C4 model](https://c4model.com/) beschrijft software architectuur op vier niveaus:
1. **System Context** - Hoe past AGORA in het grotere systeem?
2. **Containers** - Welke applicaties en data stores vormen AGORA?
3. **Components** - Hoe zijn individuele containers intern gestructureerd?
4. **Code** - Gedetailleerde implementatie (optioneel)

## 🚀 Quick Start

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

### 1. System Context
Toont AGORA in relatie tot:
- **Inspecteurs** (gebruikers)
- **NVWA Systemen** (legacy applicaties)
- **Regelgeving & Kennis** (externe kennisbronnen)
- **Externe APIs** (weer, OV, locatie)

### 2. Container Diagram
Toont alle AGORA componenten:
- **HAI** - React frontend met audio support
- **Orchestrator** - LangChain + LLM (GPT-5/Sonnet-4.5)
- **Stack Manager** - Agent selectie en activatie
- **Agent Stack** - Actieve MCP agents
- **Unused Agent Stack** - Beschikbare agents (100-1000+)
- **Moderator** - Guardrails-AI voor governance
- **User Profile** - PostgreSQL database
- **Visibility** - Grafana + Prometheus + OpenTelemetry

### 3. Orchestrator Components
Breakdown van de Orchestrator:
- **Reasoning LLM** - Closed-source LLM
- **Task Router** - LangChain router
- **MCP Client** - Model Context Protocol client
- **Moderation Adapter** - Koppeling naar moderator
- **Audit Logger** - OpenTelemetry logging

### 4. Stack Manager Components
Breakdown van de Stack Manager:
- **Context Collector** - Verzamelt gebruiker, situatie, gebeurtenissen
- **Policy Engine** - Bepaalt beschikbare agents
- **Catalog Adapter** - Beheert agent stack

### 5. Deployment Diagram (Hybride)
Toont de hybride infrastructuur setup:
- **Nederlandse Private Cloud** - Gevoelige componenten (Intermax/Nebul/UbiOps)
- **Europese Cloud** - Minder gevoelige componenten (Azure/AWS)
- **Inspector Device** - Web browser op laptop/tablet

## 🔄 Workflow in Cursor

### Live Editing
1. Open `workspace.dsl` in Cursor
2. Maak wijzigingen
3. Sla op (Cmd+S / Ctrl+S)
4. Refresh je browser - Structurizr Lite herlaadt automatisch

### AI-Assisted Editing
Selecteer een blok in `workspace.dsl` en vraag Cursor:
- "Voeg een deployment view toe voor development environment"
- "Splits de HAI container uit in componenten"
- "Voeg een nieuwe agent toe aan de agent stack"
- "Maak een dynamic diagram voor een inspectie workflow"

### Diagrammen Exporteren
In Structurizr UI:
1. Selecteer een diagram
2. Klik **Share** → **Export diagrams**
3. Kies formaat: PNG, SVG, PlantUML

## 📝 Architectuur Highlights

### Kernprincipes
- **Modulariteit** - Elk component kan los ontwikkeld en opgeschaald worden
- **Standaardisering** - MCP protocol voor alle agent koppelingen
- **Observeerbaarheid** - OpenTelemetry voor complete traceability
- **Veiligheid** - Hybride cloud met gevoelige data in Nederland

### Belangrijke Koppelingen

#### K.1: HAI Protocol
- **Van:** HAI → Orchestrator
- **Type:** Custom JSON over WebSocket
- **Doel:** Real-time communicatie tussen UI en orchestrator

#### K.2: MCP Protocol
- **Van:** Orchestrator → Agent Stack
- **Type:** Model Context Protocol
- **Doel:** Gestandaardiseerde agent communicatie
- **Voordelen:** Auditeerbaar, observeerbaar, OAuth support

### Technologie Stack (v1.0)

| Component | Technologie | Rationale |
|-----------|-------------|-----------|
| Frontend | React | Uitbreidbaar met React Native, sterk ecosysteem |
| HAI | Tekst + Audio | Whisper, ElevenLabs (Video in v2.0) |
| LLM | Closed-source | GPT-5, Sonnet-4.5, Gemini-2.5-pro (hybrid later) |
| Orchestrator | LangChain | Agent chaining met OAuth support |
| Agent Protocol | MCP | Auditeerbaar & observeerbaar |
| Logging | Grafana + Prometheus + OTel | Volledige observability stack |
| Moderator | Guardrails-AI | Output moderatie (NeMo optioneel) |
| Infrastructuur | Hybride | NL private cloud + EU hyperscalers |

## 🛡️ Compliance

AGORA v1.0 voldoet aan:
- **EU AI Act** - Traceerbaarheid, human-in-the-loop, risicobeoordeling
- **AVG/GDPR** - Encryptie, minimale verwerking, verwerkersovereenkomsten
- **BIO** - Passende beveiligingsmaatregelen voor overheid
- **WCAG** - Toegankelijkheidsrichtlijnen, schermlezer support
- **IAMA** - Impact assessment van algoritmes

## 🎯 Randvoorwaarden

De architectuur is ontworpen met deze kernvereisten:
1. **Betrouwbaar** - Herleidbare beslissingen en bronnen
2. **Observeerbaar** - Human-in-the-loop met zichtbare acties
3. **Auditeerbaar** - Volledig herleidbare resultaten
4. **Beschikbaar** - Robuust en schaalbaar
5. **Uitbreidbaar** - Nieuwe agents direct integreerbaar
6. **Veilig** - Authenticatie, encryptie, cybersecurity
7. **Compliant** - BIO, AVG, WCAG, IAMA, EU AI Act
8. **Gebruiksvriendelijk** - Impact op NVWA medewerkers
9. **Innovatie stimulerend** - Platform voor verdere ontwikkeling

## 📚 Bronnen

- [C4 Model](https://c4model.com/)
- [Structurizr DSL](https://github.com/structurizr/dsl)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [LangChain](https://www.langchain.com/)
- [OpenTelemetry](https://opentelemetry.io/)

## 🔧 Advanced Usage

### Meerdere Workspaces
Voor complexe scenario's kun je meerdere `.dsl` bestanden maken:
```
c4/
  workspace.dsl          # Hoofd architectuur
  workspace-dev.dsl      # Development setup
  workspace-security.dsl # Security view
```

### Custom Styling
Pas kleuren en vormen aan in de `styles` sectie van `workspace.dsl`.

### Dynamic Diagrams
Voeg sequence-achtige diagrammen toe voor workflows:
```dsl
dynamic agora "InspectionFlow" {
  inspector -> hai "Start inspectie"
  hai -> orchestrator "Verwerk verzoek"
  orchestrator -> stackManager "Selecteer agents"
  // etc.
}
```

## 🤝 Bijdragen

Bij het bijwerken van de architectuur:
1. Update eerst `workspace.dsl`
2. Controleer de diagrammen in Structurizr Lite
3. Exporteer relevante diagrammen naar `docs/` (indien nodig)
4. Commit het `.dsl` bestand - diagrammen zijn reproduceerbaar

## 💡 Tips

- **Auto-layout** werkt goed voor nieuwe diagrammen, pas later handmatig aan indien nodig
- **Deployment diagrammen** zijn krachtig voor infrastructuur discussies
- **Component breakdown** alleen waar het waarde toevoegt (niet alles)
- **Consistency** - gebruik dezelfde terminologie als in technisch ontwerp

