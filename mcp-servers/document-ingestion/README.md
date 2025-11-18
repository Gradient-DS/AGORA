# Document Ingestion Pipeline

This pipeline parses regulatory PDFs, chunks them semantically, embeds them using Nomic embedding model, and stores them in Weaviate for vector search.

## Architecture

- **PDF Parsing**: Docling with aggressive OCR settings for structure-preserving PDF to Markdown conversion
- **OCR Fallback**: OpenAI GPT-4 Vision for image-based/scanned PDFs when standard OCR fails
- **Semantic Chunking**: Article/section-based splitting with metadata preservation
- **Embeddings**: Nomic Embed v1.5 (768 dimensions) with task-specific prefixes
- **Summarization**: OpenAI GPT-4 for document summaries
- **Vector Database**: Weaviate with custom schema for regulatory content

## Setup

### 1. Install Dependencies

```bash
cd /Users/lexlubbers/Code/AGORA/mcp-servers/document-ingestion
pip install -r requirements.txt
```

**Note for macOS users**: `pdf2image` requires poppler. Install it with:
```bash
brew install poppler
```

### 2. Set Environment Variables

Create a `.env` file at the project root (`/Users/lexlubbers/Code/AGORA/.env`) with **MCP_** prefix:

```bash
# MCP Server Configuration (uses MCP_ prefix, similar to APP_ for server-openai)

# Required:
MCP_OPENAI_API_KEY=your_openai_api_key_here

# Optional (defaults shown):
MCP_EMBEDDING_MODEL=embedding modelai/embedding model-embeddings-v4
MCP_WEAVIATE_URL=http://localhost:8080
MCP_BATCH_SIZE=32
MCP_MAX_CHUNK_SIZE=1000
MCP_CHUNK_OVERLAP=100

# Optional - Force specific device for embedding model model
# MCP_EMBEDDING_DEVICE=mps  # cuda, mps, or cpu
```

The configuration uses **pydantic-settings** with **MCP_** prefix, just like the `APP_` prefix for server-openai.

The ingestion script automatically loads the `.env` file from the project root.

### 3. Start Weaviate

Make sure Weaviate is running:

```bash
cd /Users/lexlubbers/Code/AGORA/mcp-servers
docker-compose up weaviate -d
```

Verify Weaviate is healthy:

```bash
curl http://localhost:8080/v1/meta
```

## Usage

### Run Full Ingestion Pipeline

```bash
python ingest.py
```

This will:
1. Parse all PDFs from `../input/SPEC Agent/`
2. Generate document summaries
3. Create semantic chunks
4. Embed chunks with embedding model
5. Upload to Weaviate

### Convert Single PDF to Markdown Only

If you just want to convert a single PDF to markdown without the full pipeline:

```bash
# Convert a specific PDF
python pdf_to_markdown.py "../input/SPEC Agent/Nederlandse wetgeving - Warenwetregeling allergeneninformatie niet-voorverpakte levensmiddelen.pdf"

# Or specify custom output directory
python pdf_to_markdown.py "/path/to/your/document.pdf" "./my_output/"

# The markdown file will be saved to output/markdown/ by default
```

**OpenAI Vision OCR Fallback**: If standard OCR produces less than 100 characters (mostly images), the parser automatically falls back to OpenAI GPT-4 Vision for OCR. This is particularly useful for:
- Scanned documents
- Image-based PDFs
- Poor quality PDFs where standard OCR fails

The fallback will convert each page to an image and use GPT-4 Vision to extract text, including table structure.

This is useful for:
- Testing PDF parsing on a single document
- Quick conversion without embedding/database steps
- Inspecting document structure before full ingestion

### Inspect Intermediate Files

Markdown files:
```bash
ls -la output/markdown/
cat output/markdown/Nederlandse\ wetgeving\ -\ Warenwetregeling\ allergeneninformatie\ niet-voorverpakte\ levensmiddelen.md
```

Chunk JSON files:
```bash
ls -la output/chunks/
cat output/chunks/Nederlandse\ wetgeving\ -\ Warenwetregeling\ allergeneninformatie\ niet-voorverpakte\ levensmiddelen_chunks.json | jq '.[0]'
```

### Verify Ingestion

Check total document count:
```bash
curl -X POST http://localhost:8080/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{Aggregate{RegulationChunk{meta{count}}}}"}'
```

Query a specific chunk:
```bash
curl -X POST http://localhost:8080/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{Get{RegulationChunk(limit: 1){content document_name regulation_type}}}"
  }'
```

## Schema

The Weaviate schema includes:

### Core Content
- `content` - The chunk text
- `chunk_id` - Unique identifier

### Document Metadata
- `document_name` - Source document
- `document_summary` - 200-token AI summary
- `source_type` - Dutch, EU, or SPEC
- `regulation_type` - food_safety, hygiene, allergens, etc.
- `regulation_number` - BWBR code or EU regulation number

### Citation Metadata
- `article_number` - Article reference
- `section_title` - Section heading
- `page_number` - Page number
- `page_range` - Page range string

### Additional Metadata
- `effective_date` - When regulation became effective
- `nvwa_category` - NVWA compliance category
- `keywords` - Extracted keywords

### Navigation
- `previous_chunk_id` - Previous chunk for context
- `next_chunk_id` - Next chunk for context

## Chunking Strategy

1. **Primary**: Split on article boundaries (Artikel 1, Artikel 2, etc.)
2. **Secondary**: Split on section headings (### headers)
3. **Fallback**: Fixed 1000-character chunks with 100-character overlap

## embedding model Embeddings

Using the open source embedding model v4 model from Hugging Face with task-specific prefixes:

- **Ingestion**: `task="retrieval.passage"` - For document chunks
- **Query**: `task="retrieval.query"` - For user queries (used in MCP server)

Model: `embedding modelai/embedding model-embeddings-v4` from Hugging Face (1024 dimensions)

The model is loaded locally using PyTorch and transformers, automatically selecting the best device:
- CUDA (NVIDIA GPU)
- MPS (Apple Silicon)
- CPU (fallback)

First run will download the model (~2GB). Subsequent runs use the cached version.

## Troubleshooting

### Weaviate Connection Failed
```bash
# Check if Weaviate is running
docker ps | grep weaviate

# Check Weaviate logs
docker logs weaviate

# Restart Weaviate
docker-compose restart weaviate
```

### OpenAI Rate Limits
The pipeline processes documents sequentially. If you hit rate limits, the summarizer will fall back to using the first 200 words.

### Model Loading
The first time you run the ingestion, it will download the embedding model model from Hugging Face (~2GB). This can take a few minutes depending on your connection.

### Out of Memory Errors
If you get OOM errors while embedding:
- Reduce batch size in `embedding model_embedder.py` (default is 32)
- Use CPU instead: `export embedding model_DEVICE=cpu`
- Close other applications to free memory

### PDF Parsing Errors
If a PDF fails to parse with docling, check:
- PDF is not password protected
- PDF is not corrupted
- PDF has text (not just scanned images)

## Integration with MCP Server

The ingested data is automatically available to the `regulation-analysis` MCP server at `http://localhost:5002`.

See `../regulation-analysis/README.md` for search API documentation.

