# Regulation Analysis MCP Server

MCP server providing regulation lookup and document analysis capabilities using Weaviate vector database with semantic embeddings.

## Overview

This server provides semantic search over regulatory documents (Dutch and EU legislation, SPEC 37) using:
- **Vector Search**: Semantic embeddings (Nomic v1.5) for semantic similarity
- **Hybrid Search**: Combined vector + BM25 keyword matching
- **Metadata Filtering**: Filter by source type, regulation type, date range
- **Citation Support**: Full citation metadata for compliance references

## Tools

### search_regulations
Search for relevant regulation articles using vector and hybrid search.

**Input:**
```json
{
  "query": "natural language query",
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
      "content": "regulation text",
      "citation": "Source: ... | Article: ... | Page: ... | Regulation: ...",
      "score": 0.95,
      "regulation_type": "allergens",
      "source_type": "Dutch",
      "article": "Artikel 2",
      "section": "Section title",
      "document_summary": "200-token AI summary"
    }
  ]
}
```

### get_regulation_context
Get surrounding chunks for additional context around a specific regulation chunk.

**Input:**
```json
{
  "chunk_id": "uuid",
  "context_size": 2
}
```

**Output:**
```json
{
  "chunk_id": "uuid",
  "context_size": 5,
  "chunks": [
    {
      "content": "text",
      "chunk_id": "uuid",
      "previous_chunk_id": "uuid",
      "next_chunk_id": "uuid",
      "article_number": "Artikel 1",
      "section_title": "Section"
    }
  ]
}
```

### lookup_regulation_articles (Legacy)
Search for relevant regulation articles by domain and keywords.

**Input:**
```json
{
  "domain": "food_safety",
  "keywords": ["allergen", "labeling"]
}
```

Uses `search_regulations` internally.

### get_database_stats
Get statistics about the regulation database.

**Output:**
```json
{
  "status": "connected",
  "weaviate_url": "http://weaviate:8080",
  "collection": "RegulationChunk",
  "statistics": {
    "total_chunks": 1234
  }
}
```

## Resources

- `server://info` - Server capabilities and status
- `server://citation_instructions` - Comprehensive guidelines for citing regulations properly

### Citation Instructions

The server provides detailed citation guidelines through the `server://citation_instructions` resource. This resource should be read by AI agents to ensure proper citation of all regulatory information.

**Key citation requirements:**
- Every regulatory statement must include source, article, page, and regulation number
- Use inline citations for short facts: `[Source: ... | Article: ... | Page: ...]`
- Use block citations for longer excerpts with full metadata
- Never make up citations - only use sources from search results
- Prioritize official sources: EU regulations > Dutch law > SPEC guidelines

The citation instructions include:
- Standard citation formats
- Examples for different use cases
- Special handling for tables, cross-references, and conflicts
- Integration guidelines for compliance, risk analysis, and enforcement responses

## Setup

### Environment Variables

The server loads environment variables from `/Users/lexlubbers/Code/AGORA/.env` with **MCP_** prefix:

```bash
# MCP Server Configuration
MCP_OPENAI_API_KEY=your_key                      # Required for document summarization
MCP_WEAVIATE_URL=http://localhost:8080
MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
MCP_EMBEDDING_DEVICE=mps                         # Optional: cuda/mps/cpu (auto-detected)
```

Uses **pydantic-settings** with **MCP_** prefix, matching the pattern used by server-openai (which uses **APP_** prefix).

The embedding model is loaded from Hugging Face and runs locally (no API key needed).

When running in Docker, these are set via `docker-compose.yml`.

### Running with Docker Compose

```bash
cd /Users/lexlubbers/Code/AGORA/mcp-servers
docker-compose up regulation-analysis weaviate -d
```

The server will:
1. Wait for Weaviate to be healthy
2. Connect to Weaviate on startup
3. Serve on http://localhost:5002

### Running Locally

```bash
pip install -r requirements.txt

# Make sure .env file exists at project root with required variables
python server.py
```

## Data Ingestion

Before the server can search regulations, you must ingest the PDF documents:

```bash
cd ../document-ingestion
pip install -r requirements.txt

# Ensure .env file exists at project root with MCP_OPENAI_API_KEY
python ingest.py
```

See `../document-ingestion/README.md` for details.

## Testing

### Health Check
```bash
curl http://localhost:5002/health
```

### Search Regulations
```bash
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_regulations",
    "arguments": {
      "query": "allergen labeling requirements for unpacked foods",
      "filters": {"source_type": "Dutch"},
      "limit": 5
    }
  }'
```

### Get Database Stats
```bash
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_database_stats",
    "arguments": {}
  }'
```

### Get Context
```bash
curl -X POST http://localhost:5002/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_regulation_context",
    "arguments": {
      "chunk_id": "your-chunk-uuid",
      "context_size": 2
    }
  }'
```

## Architecture

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

## Search Strategy

The server uses a hybrid search approach:

1. **Query Embedding** (70% weight)
   - User query is embedded with task prefix `search_query`
   - Vector similarity search finds semantically related chunks

2. **BM25 Keyword** (30% weight)
   - Traditional keyword matching for exact terms
   - Good for specific article numbers, regulation codes

Alpha parameter: 0.7 (70% vector, 30% keyword)

## Fallback Mode

If Weaviate is not available, the server will:
- Start successfully but with limited functionality
- Return error messages for search tools
- Still provide health check and info endpoints

This allows the orchestrator to start even if the database is temporarily unavailable.

## Integration with OpenAI Orchestrator

Add to your OpenAI orchestrator configuration:

```python
mcp_servers = {
    "regulation-analysis": "http://localhost:5002"
}
```

The orchestrator can then call tools like:
- `search_regulations` for finding relevant regulations
- `get_regulation_context` for expanding context
- `get_database_stats` for debugging

## Troubleshooting

### "Weaviate search not available"
- Check Weaviate is running: `docker ps | grep weaviate`
- Verify connection: `curl http://localhost:8080/v1/meta`
- Check logs: `docker logs mcp-regulation-analysis`

### No search results
- Verify data is ingested: `get_database_stats` tool
- Check Weaviate has data: `curl http://localhost:8080/v1/objects`
- Try broader query terms

### Slow searches
- Reduce limit parameter
- Use more specific filters
- Check Weaviate performance: `docker stats weaviate`

## References

- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [Weaviate Vector Database](https://weaviate.io)
- [Nomic Embeddings](https://huggingface.co/nomic-ai)
