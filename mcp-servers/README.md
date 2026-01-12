# AGORA MCP Servers

Model Context Protocol (MCP) servers voor het compliance platform van AGORA, gebruikmakend van het **FastMCP** framework met HTTP transport voor OpenAI integratie.

## Overzicht

Drie gespecialiseerde MCP servers die tools bieden voor compliance operaties:

1. **Regelgevingsanalyse** (poort 5002) - Regelgeving opzoeken en documentanalyse
2. **Rapportage** (poort 5003) - Generatie van HAP-inspectierapporten
3. **Bedrijfsinformatie & Inspectiegeschiedenis** (poort 5005) - KVK opzoeken en historische inspectiedata

## Snel aan de slag

### 1. Bouwen en draaien met Docker Compose

```bash
cd mcp-servers

# Op macOS, gebruik legacy builder voor snellere builds
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

docker-compose up --build
```

Dit start de MCP servers:

- http://localhost:5002 - Regelgevingsanalyse
- http://localhost:5003 - Rapportage
- http://localhost:5005 - Bedrijfsinformatie & Inspectiegeschiedenis

### 2. Configureer OpenAI Orchestrator

Voeg toe aan je `.env` bestand:

```bash
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,inspection-history=http://localhost:5005
```

### 3. Test de Servers

Controleer gezondheidsstatus:

```bash
# Test health endpoint (HTTP)
curl http://localhost:5002/health

# Controleer container gezondheid
docker-compose ps

# Bekijk logs
docker-compose logs regulation-analysis
```

Elke server biedt:
- **HTTP MCP endpoints** voor tool uitvoering en toegang tot bronnen
- **`/health` HTTP endpoint** voor gezondheidscontroles en monitoring
- **`server://info` resource** voor server mogelijkheden

Test MCP endpoints:
```bash
# Lijst beschikbare tools
curl http://localhost:5002/mcp/tools

# Roep een tool aan
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "lookup_regulation_articles",
    "arguments": {"domain": "food_safety", "keywords": ["HACCP"]}
  }'
```

## Architectuur

Elke server draait onafhankelijk met gebruik van het **FastMCP** framework met **HTTP transport** voor OpenAI integratie:

- ✅ **HTTP Transport** - Compatibel met OpenAI Responses API en standaard HTTP clients
- ✅ **Automatische tool registratie** - Gebruik `@mcp.tool` decorator
- ✅ **Aangepaste HTTP routes** - Voeg endpoints toe zoals `/health` met `@mcp.custom_route`
- ✅ **Type-safe parameters** - Volledige Python type hints
- ✅ **Resource endpoints** - Stel data beschikbaar via `@mcp.resource()`
- ✅ **Ingebouwde server** - Enkele `mcp.run()` aanroep start alles

## Embedding Configuration

The regulation-analysis server supports two embedding providers:

### OpenAI Embeddings (Default)

Uses `text-embedding-3-small` with 768 dimensions. Requires `MCP_OPENAI_API_KEY`.

```bash
MCP_EMBEDDING_PROVIDER=openai
MCP_OPENAI_API_KEY=sk-...
```

### Local Embeddings

Uses `nomic-ai/nomic-embed-text-v1.5` via sentence-transformers. Requires additional dependencies (~800MB).

```bash
MCP_EMBEDDING_PROVIDER=local
MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5  # optional, this is default
MCP_EMBEDDING_DEVICE=cpu  # optional, auto-detected
```

### Docker Builds

For smaller images when using OpenAI embeddings:

```bash
# OpenAI embeddings (~300MB image)
docker build --build-arg EMBEDDING_PROVIDER=openai -t regulation-analysis .

# Local embeddings (~1.1GB image)
docker build --build-arg EMBEDDING_PROVIDER=local -t regulation-analysis .
```

### Re-ingesting Documents

When switching providers, documents should be re-ingested to ensure query/document embedding consistency:

```bash
cd mcp-servers/document-ingestion
MCP_EMBEDDING_PROVIDER=openai MCP_OPENAI_API_KEY=sk-... python ingest.py
```

## Ontwikkeling

### Lokaal draaien (zonder Docker)

```bash
cd mcp-servers/regulation-analysis
pip install -r requirements.txt
python server.py
```

Server start met http transport op de standaard poort.

### Projectstructuur

```
mcp-servers/
├── regulation-analysis/
│   ├── server.py
│   ├── requirements.txt
│   └── Dockerfile
├── reporting/
│   ├── server.py
│   ├── analyzers/
│   ├── generators/
│   ├── models/
│   ├── storage/
│   ├── verification/
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml
```

## Beschikbare Tools

### Regelgevingsanalyse

- `semantic_search_regulations(query, top_k)` - Zoek regelgeving met semantische gelijkenis
- `get_regulation_by_id(regulation_id)` - Haal specifieke regelgeving op via ID

### Rapportage

- `start_inspection_report(session_id, inspector_name, inspection_date)` - Start een nieuw inspectierapport
- `extract_inspection_data(session_id, conversation_history)` - Extraheer gestructureerde data uit gesprek
- `verify_inspection_data(session_id)` - Krijg verificatievragen voor ontbrekende data
- `submit_verification_answers(session_id, answers)` - Dien antwoorden in op verificatievragen
- `generate_final_report(session_id)` - Genereer definitieve JSON en PDF rapporten

### Bedrijfsinformatie & Inspectiegeschiedenis

**Bedrijfsverificatie:**
- `check_company_exists(kvk_number)` - Controleer of bedrijf bestaat in KVK register

**Inspectiegeschiedenis (inclusief volledige bedrijfsdetails):**
- `get_inspection_history(kvk_number, limit)` - Haal eerdere inspecties op voor een bedrijf
- `get_company_violations(kvk_number, limit, severity)` - Haal alle overtredingen op over inspecties heen
- `check_repeat_violation(kvk_number, violation_category)` - Controleer of overtreding een herhaling is
- `get_follow_up_status(kvk_number, inspection_id)` - Haal status van vervolgactie op
- `search_inspections_by_inspector(inspector_name, limit)` - Zoek inspecties op inspecteur

## Probleemoplossing

**Trage Docker builds op macOS (exporteren naar OCI formaat duurt minuten):**
```bash
# Gebruik legacy builder in plaats van BuildKit
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0
docker-compose up --build

# Of voeg toe aan je shell profiel (~/.zshrc of ~/.bash_profile):
echo 'export DOCKER_BUILDKIT=0' >> ~/.zshrc
echo 'export COMPOSE_DOCKER_CLI_BUILD=0' >> ~/.zshrc
```

**Poorten al in gebruik:**
```bash
# Controleer wat de poorten gebruikt
lsof -i :5002-5003

# Stop containers
docker-compose down
```

## Licentie

Zie de hoofd-README voor licentie-informatie.
