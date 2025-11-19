# Document Ingestion Pipeline

Deze pipeline verwerkt regelgevende PDF's, deelt ze op in semantische stukken (chunks), genereert embeddings met behulp van het Nomic embedding model, en slaat ze op in Weaviate voor vector search.

## Architectuur

- **PDF Parsing**: Docling met agressieve OCR-instellingen voor structuurbehoudende conversie van PDF naar Markdown
- **OCR Fallback**: OpenAI GPT-4 Vision voor op afbeeldingen gebaseerde/gescande PDF's wanneer standaard OCR faalt
- **Semantische Chunking**: Splitsen op basis van artikelen/secties met behoud van metadata
- **Embeddings**: Nomic Embed v1.5 (768 dimensies) met taakspecifieke voorvoegsels
- **Samenvatting**: OpenAI GPT-4 voor documentsamenvattingen
- **Vector Database**: Weaviate met aangepast schema voor regelgevende inhoud

## Setup

### 1. Installeer Afhankelijkheden

```bash
cd mcp-servers/document-ingestion
pip install -r requirements.txt
```

**Opmerking voor macOS gebruikers**: `pdf2image` vereist poppler. Installeer het met:
```bash
brew install poppler
```

### 2. Stel Omgevingsvariabelen in

Maak een `.env` bestand in de root van het project (`/Users/lexlubbers/Code/AGORA/.env`) met **MCP_** voorvoegsel:

```bash
# MCP Server Configuratie (gebruikt MCP_ prefix, vergelijkbaar met APP_ voor server-openai)

# Vereist:
MCP_OPENAI_API_KEY=jouw_openai_api_key_hier

# Optioneel (standaardwaarden getoond):
MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
MCP_WEAVIATE_URL=http://localhost:8080
MCP_BATCH_SIZE=32
MCP_MAX_CHUNK_SIZE=1000
MCP_CHUNK_OVERLAP=100

# Optioneel - Forceer specifiek apparaat voor embedding model
# MCP_EMBEDDING_DEVICE=mps  # cuda, mps, of cpu
```

De configuratie gebruikt **pydantic-settings** met **MCP_** voorvoegsel, net als het `APP_` voorvoegsel voor server-openai.

Het ingest-script laadt automatisch het `.env` bestand vanuit de project root.

### 3. Start Weaviate

Zorg ervoor dat Weaviate draait:

```bash
cd mcp-servers
docker-compose up weaviate -d
```

Verifieer dat Weaviate gezond is:

```bash
curl http://localhost:8080/v1/meta
```

## Gebruik

### Draai Volledige Ingestion Pipeline

```bash
python ingest.py
```

Dit zal:
1. Alle PDF's parsen van `../input/SPEC Agent/`
2. Documentsamenvattingen genereren
3. Semantische chunks creëren
4. Chunks embedden met embedding model
5. Uploaden naar Weaviate

### Converteer Enkele PDF naar Markdown Alleen

Als je alleen een enkele PDF naar markdown wilt converteren zonder de volledige pipeline:

```bash
# Converteer een specifieke PDF
python pdf_to_markdown.py "../input/SPEC Agent/Nederlandse wetgeving - Warenwetregeling allergeneninformatie niet-voorverpakte levensmiddelen.pdf"

# Of specificeer een aangepaste uitvoermap
python pdf_to_markdown.py "/pad/naar/jouw/document.pdf" "./mijn_output/"

# Het markdown bestand wordt standaard opgeslagen in output/markdown/
```

**OpenAI Vision OCR Fallback**: Als standaard OCR minder dan 100 karakters produceert (meestal afbeeldingen), valt de parser automatisch terug op OpenAI GPT-4 Vision voor OCR. Dit is vooral handig voor:
- Gescande documenten
- PDF's gebaseerd op afbeeldingen
- PDF's van slechte kwaliteit waar standaard OCR faalt

De fallback converteert elke pagina naar een afbeelding en gebruikt GPT-4 Vision om tekst te extraheren, inclusief tabelstructuur.

Dit is handig voor:
- Testen van PDF parsing op een enkel document
- Snelle conversie zonder embedding/database stappen
- Inspecteren van documentstructuur vóór volledige ingestion

### Inspecteer Tussenbestanden

Markdown bestanden:
```bash
ls -la output/markdown/
cat output/markdown/Bestandsnaam.md
```

Chunk JSON bestanden:
```bash
ls -la output/chunks/
cat output/chunks/Bestandsnaam_chunks.json | jq '.[0]'
```

### Verifieer Ingestion

Controleer totaal aantal documenten:
```bash
curl -X POST http://localhost:8080/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{Aggregate{RegulationChunk{meta{count}}}}"}'
```

Vraag een specifiek chunk op:
```bash
curl -X POST http://localhost:8080/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{Get{RegulationChunk(limit: 1){content document_name regulation_type}}}"
  }'
```

## Schema

Het Weaviate schema bevat:

### Kern Inhoud
- `content` - De chunk tekst
- `chunk_id` - Unieke identifier

### Document Metadata
- `document_name` - Brondocument
- `document_summary` - 200-token AI samenvatting
- `source_type` - Dutch, EU, of SPEC
- `regulation_type` - food_safety, hygiene, allergens, etc.
- `regulation_number` - BWBR code of EU verordening nummer

### Citatie Metadata
- `article_number` - Artikel referentie
- `section_title` - Sectie kop
- `page_number` - Paginanummer
- `page_range` - Paginabereik string

### Extra Metadata
- `effective_date` - Datum van inwerkingtreding
- `nvwa_category` - NVWA compliance categorie
- `keywords` - Geëxtraheerde sleutelwoorden

### Navigatie
- `previous_chunk_id` - Vorige chunk voor context
- `next_chunk_id` - Volgende chunk voor context

## Chunking Strategie

1. **Primair**: Splitsen op artikelgrenzen (Artikel 1, Artikel 2, etc.)
2. **Secundair**: Splitsen op sectiekoppen (### headers)
3. **Fallback**: Vaste 1000-karakter chunks met 100-karakter overlap

## Embedding Model Embeddings

Gebruik makend van het open source embedding model v4 model van Hugging Face met taakspecifieke voorvoegsels:

- **Ingestion**: `task="retrieval.passage"` - Voor document chunks
- **Query**: `task="retrieval.query"` - Voor gebruikersvragen (gebruikt in MCP server)

Model: `nomic-ai/nomic-embed-text-v1.5` van Hugging Face (768 dimensies)

Het model wordt lokaal geladen met PyTorch en transformers, waarbij automatisch het beste apparaat wordt geselecteerd:
- CUDA (NVIDIA GPU)
- MPS (Apple Silicon)
- CPU (fallback)

De eerste keer draaien zal het model downloaden (~2GB). Latere runs gebruiken de gecachte versie.

## Probleemoplossing

### Weaviate Verbinding Mislukt
```bash
# Controleer of Weaviate draait
docker ps | grep weaviate

# Controleer Weaviate logs
docker logs weaviate

# Herstart Weaviate
docker-compose restart weaviate
```

### OpenAI Rate Limits
De pipeline verwerkt documenten sequentieel. Als je rate limits raakt, zal de samenvatter terugvallen op het gebruik van de eerste 200 woorden.

### Model Laden
De eerste keer dat je de ingestion draait, wordt het embedding model gedownload van Hugging Face (~2GB). Dit kan enkele minuten duren, afhankelijk van je verbinding.

### Out of Memory Fouten
Als je OOM fouten krijgt tijdens het embedden:
- Verminder batch size in `.env` of config (standaard is 32)
- Gebruik CPU in plaats daarvan: `export MCP_EMBEDDING_DEVICE=cpu`
- Sluit andere applicaties om geheugen vrij te maken

### PDF Parsing Fouten
Als een PDF niet geparsed kan worden met docling, controleer:
- PDF is niet beveiligd met wachtwoord
- PDF is niet corrupt
- PDF bevat tekst (niet alleen gescande afbeeldingen)

## Integratie met MCP Server

De geïnvesteerde data is automatisch beschikbaar voor de `regulation-analysis` MCP server op `http://localhost:5002`.

Zie `../regulation-analysis/README.md` voor zoek API documentatie.
