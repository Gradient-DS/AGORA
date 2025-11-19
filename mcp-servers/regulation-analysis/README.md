# Regelgevingsanalyse MCP Server

MCP server die mogelijkheden biedt voor het opzoeken van regelgeving en documentanalyse met behulp van de Weaviate vector database met semantische embeddings.

## Overzicht

Deze server biedt semantische zoekfunctionaliteit over regelgevende documenten (Nederlandse en EU-wetgeving, SPEC 37) met behulp van:
- **Vector Search**: Semantische embeddings (Nomic v1.5) voor semantische gelijkenis
- **Hybride Search**: Gecombineerde vector + BM25 trefwoordovereenkomst
- **Metadata Filtering**: Filter op brontype, regelgevingstype, datumbereik
- **Citatie Ondersteuning**: Volledige citatiemetadata voor compliance-referenties

## Tools

### search_regulations
Zoek naar relevante regelgevingsartikelen met behulp van vector en hybride search.

**Input:**
```json
{
  "query": "natuurlijke taal vraag",
  "filters": {
    "source_type": "Dutch | EU | SPEC",
    "regulation_type": "food_safety | hygiene | allergens | etc"
  },
  "limit": 10
}
```

**Output:**
```json
{
  "query": "string",
  "filters": {},
  "found": 5,
  "results": [
    {
      "content": "tekst van de regelgeving",
      "citation": "Bron: ... | Artikel: ... | Pagina: ... | Regelgeving: ...",
      "score": 0.95,
      "regulation_type": "allergens",
      "source_type": "Dutch",
      "article": "Artikel 2",
      "section": "Sectietitel",
      "document_summary": "200-token AI samenvatting"
    }
  ]
}
```

### get_regulation_context
Haal omliggende chunks op voor extra context rond een specifiek regelgevingschunk.

**Input:**
```json
{
  "chunk_id": "uuid",
  "context_size": 2
}
```

### get_database_stats
Haal statistieken op over de regelgevingsdatabase.

## Bronnen

- `server://info` - Server mogelijkheden en status
- `server://citation_instructions` - Uitgebreide richtlijnen voor het correct citeren van regelgeving

### Citatie Instructies

De server biedt gedetailleerde citatierichtlijnen via de `server://citation_instructions` resource. Deze resource moet door AI-agenten worden gelezen om te zorgen voor een juiste citatie van alle regelgevende informatie.

**Belangrijkste citatie-eisen:**
- Elke regelgevende verklaring moet bron, artikel, pagina en regelgevingsnummer bevatten
- Prioriteer officiële bronnen: EU-verordeningen > Nederlandse wetgeving > SPEC richtlijnen

## Setup

### Omgevingsvariabelen

De server laadt omgevingsvariabelen van `/Users/lexlubbers/Code/AGORA/.env` met **MCP_** voorvoegsel:

```bash
# MCP Server Configuratie
MCP_OPENAI_API_KEY=jouw_sleutel                   # Vereist voor documentsamenvatting
MCP_WEAVIATE_URL=http://localhost:8080
MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
MCP_EMBEDDING_DEVICE=mps                          # Optioneel: cuda/mps/cpu (auto-detected)
```

### Draaien met Docker Compose

```bash
cd mcp-servers
docker-compose up regulation-analysis weaviate -d
```

### Lokaal Draaien

```bash
pip install -r requirements.txt
python server.py
```

## Data Ingestion

Voordat de server regelgeving kan doorzoeken, moet je de PDF-documenten 'ingesten':

```bash
cd ../document-ingestion
pip install -r requirements.txt
python ingest.py
```

Zie `../document-ingestion/README.md` voor details.

## Testen

### Health Check
```bash
curl http://localhost:5002/health
```

### Zoek Regelgeving
```bash
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_regulations",
    "arguments": {
      "query": "allergenen etikettering eisen voor onverpakte levensmiddelen",
      "filters": {"source_type": "Dutch"},
      "limit": 5
    }
  }'
```

## Architectuur

```
┌─────────────────────┐
│  MCP Server         │
│  (FastMCP)          │
├─────────────────────┤
│  - search_regulations│
│  - get_context      │
│  - get_stats        │
└──────────┬──────────┘
           │
           ├─► Embedder (search_query prefix)
           │
           └─► Weaviate Client
                    │
                    ▼
           ┌─────────────────────┐
           │  Weaviate DB        │
           │  RegulationChunk    │
           │  Collection         │
           └─────────────────────┘
```

## Zoekstrategie

De server gebruikt een hybride zoekbenadering:

1. **Query Embedding** (70% gewicht)
   - Gebruikersvraag wordt embedded met taakvoorvoegsel `search_query`
   - Vector similarity search vindt semantisch gerelateerde chunks

2. **BM25 Trefwoord** (30% gewicht)
   - Traditionele trefwoordovereenkomst voor exacte termen
   - Goed voor specifieke artikelnummers, regelgevingscodes

## Fallback Modus

Als Weaviate niet beschikbaar is, zal de server:
- Succesvol starten maar met beperkte functionaliteit
- Foutmeldingen retourneren voor zoektools
- Nog steeds health check en info endpoints bieden

Dit zorgt ervoor dat de orchestrator kan starten, zelfs als de database tijdelijk niet beschikbaar is.

## Integratie met OpenAI Orchestrator

Voeg toe aan je OpenAI orchestrator configuratie:

```python
mcp_servers = {
    "regulation-analysis": "http://localhost:5002"
}
```

## Probleemoplossing

### "Weaviate search not available"
- Controleer of Weaviate draait: `docker ps | grep weaviate`
- Verifieer verbinding: `curl http://localhost:8080/v1/meta`

### Geen zoekresultaten
- Verifieer of data is geïngest: `get_database_stats` tool
- Probeer bredere zoektermen

## Bronnen

- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [Weaviate Vector Database](https://weaviate.io)
- [Nomic Embeddings](https://huggingface.co/nomic-ai)
