# AGORA v1.0

**Multi-agent systeem voor NVWA inspecteurs**

AGORA is een toekomstbestendig platform dat NVWA inspecteurs ondersteunt in hun dagelijkse werk door middel van AI-agents en Large Language Models. Het systeem is ontworpen met focus op betrouwbaarheid, veiligheid, compliance en gebruiksvriendelijkheid.

## 🏗️ Architectuur

De complete architectuur is gedocumenteerd met het C4 model. Bekijk de interactieve diagrammen:

```bash
cd c4
npm run up
```

Open http://localhost:8080 voor live architectuur diagrammen.

**Zie [c4/README.md](c4/README.md) voor gedetailleerde architectuur documentatie.**

## 🎯 Kernprincipes

- **Modulair** - Microservices architectuur met gestandaardiseerde koppelingen
- **Betrouwbaar** - Herleidbare beslissingen en transparante reasoning
- **Observeerbaar** - Human-in-the-loop met complete traceability
- **Veilig** - Hybride cloud infrastructuur met Nederlandse hosting voor gevoelige data
- **Compliant** - EU AI Act, AVG, BIO, WCAG, IAMA

## 🧩 Componenten

- **HAI (Human Agent Interface)** - React frontend met tekst en audio support
- **Orchestrator** - Centrale engine met LangChain + LLM (GPT-5/Sonnet-4.5)
- **Stack Manager** - Intelligente agent selectie o.b.v. context
- **Agent Stack** - Modulaire MCP agents (100-1000+ beschikbaar)
- **Moderator** - Guardrails-AI voor AI governance
- **Visibility** - Grafana + Prometheus + OpenTelemetry

## 🚀 Quick Start

```bash
# Bekijk architectuur diagrammen
cd c4 && npm run up

# Stop diagrammen viewer
cd c4 && npm run down
```

## 📋 Technologie Stack (v1.0)

| Component | Technologie |
|-----------|-------------|
| Frontend | React |
| HAI | Tekst + Audio (Whisper, ElevenLabs) |
| LLM | Closed-source (GPT-5, Sonnet-4.5) |
| Orchestrator | LangChain |
| Agent Protocol | MCP (Model Context Protocol) |
| Monitoring | Grafana + Prometheus + OpenTelemetry |
| Moderator | Guardrails-AI |
| Infrastructure | Hybride (NL Private Cloud + EU Cloud) |

## 🔗 Belangrijke Koppelingen

- **K.1: HAI Protocol** - Custom JSON/WebSocket tussen HAI en Orchestrator
- **K.2: MCP Protocol** - Gestandaardiseerde communicatie met agents

## 🛡️ Compliance

AGORA voldoet vanaf v1.0 aan:

- ✅ **EU AI Act** - Transparantie, human-in-the-loop, risicobeoordeling
- ✅ **AVG/GDPR** - Privacy by design, encryptie, verwerkersovereenkomsten
- ✅ **BIO** - Beveiligingsnormen voor overheid
- ✅ **WCAG** - Digitale toegankelijkheid
- ✅ **IAMA** - Impact assessment algoritmes

## 📚 Documentatie

- [C4 Architectuur](c4/README.md) - Interactieve diagrammen en architectuur overzicht
- [Technisch Ontwerp](docs/) - Gedetailleerde technische specificaties (toekomstig)

## 🤝 Ontwikkeling

AGORA is ontworpen voor continue innovatie:
- **Modulair** - Elk component kan los ontwikkeld worden
- **Gestandaardiseerd** - MCP protocol voor alle agents
- **Uitbreidbaar** - Nieuwe agents direct te integreren
- **Open** - Migratie naar open-source LLMs in latere versies

## 📞 Contact

Voor vragen over AGORA, neem contact op met het NVWA innovatieteam.
