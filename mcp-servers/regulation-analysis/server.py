import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

try:
    from config import get_settings
    from database.weaviate_client import WeaviateClient
    from embeddings.embedder import Embedder
    WEAVIATE_AVAILABLE = True
except ImportError as e:
    WEAVIATE_AVAILABLE = False
    logging.warning(f"Weaviate dependencies not available - search functionality will be limited: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Regulation Analysis Server", stateless_http=True)

weaviate_client = None
embedder = None

if WEAVIATE_AVAILABLE:
    try:
        settings = get_settings()
        logger.info("Loaded configuration with MCP_ prefix")
        
        weaviate_client = WeaviateClient(settings.weaviate_url)
        embedder = Embedder(
            model_name=settings.embedding_model,
            device=settings.embedding_device
        )
        
        if weaviate_client.connect():
            logger.info("Successfully connected to Weaviate")
        else:
            logger.warning("Failed to connect to Weaviate - will use fallback mode")
            weaviate_client = None
    except Exception as e:
        logger.error(f"Error loading configuration or connecting to Weaviate: {e}")
        weaviate_client = None


@mcp.tool
async def search_regulations(query: str, filters: Optional[Dict[str, str]] = None, limit: int = 10) -> dict:
    """Search for relevant regulation articles using vector and hybrid search.
    
    Args:
        query: Natural language query describing what you're looking for
        filters: Optional filters (source_type: Dutch/EU/SPEC, regulation_type: microbiological_criteria/allergens/food_information)
        limit: Maximum number of results to return (default 10)
    """
    if not weaviate_client or not embedder:
        return {
            "error": "Weaviate search not available",
            "message": "Vector database is not connected. Please check configuration."
        }
    
    try:
        logger.info(f"Searching for: {query}")
        
        query_vector = embedder.embed_query(query)
        
        results = weaviate_client.search(
            query_vector=query_vector,
            filters=filters or {},
            limit=limit,
            alpha=0.7
        )
        
        formatted_results = []
        for result in results:
            citation = _format_citation(result)
            
            formatted_results.append({
                "content": result.get("content", ""),
                "citation": citation,
                "score": result.get("score"),
                "regulation_type": result.get("regulation_type", ""),
                "source_type": result.get("source_type", ""),
                "article": result.get("article_number", ""),
                "section": result.get("section_title", ""),
                "document_summary": result.get("document_summary", "")
            })
        
        return {
            "query": query,
            "filters": filters or {},
            "found": len(formatted_results),
            "results": formatted_results
        }
    
    except Exception as e:
        logger.error(f"Error searching regulations: {e}")
        return {
            "error": str(e),
            "query": query
        }


@mcp.tool
async def get_regulation_context(chunk_id: str, context_size: int = 2) -> dict:
    """Get surrounding chunks for additional context around a specific regulation chunk.
    
    Args:
        chunk_id: The ID of the chunk to get context for
        context_size: Number of chunks before and after to retrieve (default 2)
    """
    if not weaviate_client:
        return {
            "error": "Weaviate search not available"
        }
    
    try:
        logger.info(f"Getting context for chunk: {chunk_id}")
        
        current_chunk = weaviate_client.get_chunk_by_id(chunk_id)
        
        if not current_chunk:
            return {
                "error": f"Chunk not found: {chunk_id}"
            }
        
        context_chunks = [current_chunk]
        
        prev_id = current_chunk.get("previous_chunk_id")
        for _ in range(context_size):
            if not prev_id:
                break
            prev_chunk = weaviate_client.get_chunk_by_id(prev_id)
            if prev_chunk:
                context_chunks.insert(0, prev_chunk)
                prev_id = prev_chunk.get("previous_chunk_id")
        
        next_id = current_chunk.get("next_chunk_id")
        for _ in range(context_size):
            if not next_id:
                break
            next_chunk = weaviate_client.get_chunk_by_id(next_id)
            if next_chunk:
                context_chunks.append(next_chunk)
                next_id = next_chunk.get("next_chunk_id")
        
        return {
            "chunk_id": chunk_id,
            "context_size": len(context_chunks),
            "chunks": context_chunks
        }
    
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        return {
            "error": str(e),
            "chunk_id": chunk_id
        }


@mcp.tool
async def lookup_regulation_articles(domain: str, keywords: list[str]) -> dict:
    """Search for relevant regulation articles by domain and keywords (legacy interface).
    
    Args:
        domain: Regulation domain (microbiological_criteria, allergens, food_information, etc)
        keywords: Keywords to search for in regulations
    """
    if not weaviate_client or not embedder:
        return {
            "error": "Weaviate search not available",
            "message": "Vector database is not connected. Please use search_regulations instead."
        }
    
    query = " ".join(keywords)
    filters = {"regulation_type": domain} if domain else None
    
    return await search_regulations(query=query, filters=filters, limit=10)


@mcp.tool
async def analyze_document(document_uri: str, analysis_type: str) -> dict:
    """Analyze a document for summary, risks, or non-compliance issues.
    
    Args:
        document_uri: URI or path to the document to analyze
        analysis_type: Type of analysis ('summary', 'risks', 'noncompliance')
    """
    return {
        "document_uri": document_uri,
        "analysis_type": analysis_type,
        "result": f"Analysis of type '{analysis_type}' for document: {document_uri}",
        "findings": [
            "This is a placeholder for document analysis",
            "In production, this would analyze the actual document"
        ]
    }


@mcp.tool
async def get_database_stats() -> dict:
    """Get statistics about the regulation database.
    
    Returns information about total documents, chunks, and collection status.
    """
    if not weaviate_client:
        return {
            "error": "Weaviate not available"
        }
    
    try:
        stats = weaviate_client.get_stats()
        return {
            "status": "connected",
            "weaviate_url": weaviate_client.url,
            "collection": weaviate_client.collection_name,
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {
            "error": str(e)
        }


def _format_citation(result: Dict[str, Any]) -> str:
    parts = []
    
    doc_name = result.get("document_name", "Unknown")
    parts.append(f"Source: {doc_name}")
    
    article = result.get("article_number")
    section = result.get("section_title")
    if article:
        if section:
            parts.append(f"Article: {article} - {section}")
        else:
            parts.append(f"Article: {article}")
    elif section:
        parts.append(f"Section: {section}")
    
    page = result.get("page_number")
    if page and page > 0:
        parts.append(f"Page: {page}")
    
    reg_num = result.get("regulation_number")
    if reg_num:
        parts.append(f"Regulation: {reg_num}")
    
    return " | ".join(parts)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker and load balancers."""
    return JSONResponse({
        "status": "healthy",
        "server": "regulation-analysis",
        "timestamp": datetime.now().isoformat(),
        "weaviate_connected": weaviate_client is not None
    }, status_code=200)


@mcp.resource("server://info")
def server_info() -> str:
    """Get server information and capabilities."""
    tools = [
        "search_regulations",
        "get_regulation_context",
        "lookup_regulation_articles",
        "analyze_document",
        "get_database_stats"
    ]
    
    info = {
        "name": "Regulation Analysis Server",
        "version": "2.0.0",
        "description": "Provides regulation lookups via Weaviate vector database with semantic embeddings",
        "capabilities": {
            "tools": tools,
            "resources": ["server://info", "server://citation_instructions"],
            "vector_search": weaviate_client is not None,
            "hybrid_search": weaviate_client is not None,
        },
        "weaviate_connected": weaviate_client is not None
    }
    return json.dumps(info, indent=2)


@mcp.resource("server://citation_instructions")
def citation_instructions() -> str:
    """Get instructions for properly citing regulations and sources."""
    instructions = """
# Regulation Citation Instructions

When providing information from regulations, ALWAYS cite your sources properly. This is critical for compliance and legal accuracy.

## Citation Format

Every piece of regulatory information MUST include:

1. **Source Document**: The name of the regulation or law
2. **Article Number**: The specific article or section (if available)
3. **Page Number**: The page where the information appears
4. **Regulation Number**: Official regulation identifier (e.g., "EU 852/2004", "BWBR1234")

## How to Cite in Responses

### Format 1: Inline Citation
Use this for short quotes or specific facts:

"Allergen information must be clearly displayed [Source: Warenwetregeling allergeneninformatie | Article: Artikel 2 | Regulation: BWBR1234]"

### Format 2: Block Citation
Use this for longer excerpts or multiple related points:

According to the hygiene regulations:

> [Regulation text or summary here]

**Citation:**
- Source: Verordening (EG) nr. 852/2004
- Article: Artikel 4, lid 3
- Section: Hygiënevoorschriften
- Regulation: EU 852/2004
- Page: 12

### Format 3: Multiple Sources
When information comes from multiple regulations:

**Sources:**
1. Verordening (EG) nr. 178/2002 - Article 14 (Food Safety Requirements)
2. Nederlandse Warenwet - Artikel 2.1 (Allergen Labeling)
3. SPEC 37 - Section 3.2 (Inspection Guidelines)

## Citation Rules

1. **NEVER make up citations** - Only cite sources provided by the search results
2. **Include all available metadata** - Document name, article, page, regulation number
3. **Be specific** - Reference the exact article or section, not just the document
4. **Aggregate when appropriate** - If multiple chunks from the same document, cite once
5. **Prioritize official sources** - EU regulations > Dutch law > SPEC guidelines
6. **Show relevance scores** - When debugging or explaining search quality

## Examples from Search Results

When you receive search results like:
```json
{
  "content": "Exploitanten van levensmiddelenbedrijven...",
  "citation": "Source: EU 852/2004 | Article: Artikel 4 | Page: 12 | Regulation: EU 852/2004",
  "score": 0.95,
  "source_type": "EU",
  "regulation_type": "hygiene"
}
```

Convert to natural language:

"Food business operators must implement HACCP principles (EU Regulation 852/2004, Article 4, p. 12)."

## Special Cases

### Tables and Lists
If citing tabular data (like HAP lists):
- Reference the table number if available
- Include the specific row or entry
- Note the document version/date

### Cross-references
When regulations reference other regulations:
- Cite both the primary and referenced document
- Make the relationship clear
- Use "as referenced in" or "citing"

### Conflicting Information
If sources conflict:
- Cite all sources
- Note the conflict explicitly
- Prioritize more recent or more specific regulations
- Defer to EU law over national law when applicable

## Quality Indicators

Include these when helpful:
- **Relevance Score**: How well the source matches the query (0.0-1.0)
- **Source Type**: EU, Dutch, or SPEC
- **Regulation Type**: hygiene, allergens, food_safety, etc.
- **Document Summary**: Brief AI-generated summary of the regulation

## Common Mistakes to Avoid

❌ "According to food safety regulations..." (too vague)
✅ "According to EU Regulation 852/2004, Article 5..."

❌ Making statements without citations
✅ Every regulatory statement has a source

❌ Citing only the document name
✅ Include article, page, and regulation number

❌ Paraphrasing without attribution
✅ Always cite, even when paraphrasing

## Integration with Responses

### For Compliance Questions
ALWAYS provide:
1. Direct answer with citation
2. Full citation block
3. Link to get more context (chunk_id)

### For Risk Analysis
ALWAYS provide:
1. Each risk with supporting regulation
2. Citation for each regulatory requirement
3. Multiple sources if risk spans multiple regulations

### For Enforcement Actions
ALWAYS provide:
1. Legal basis with citation
2. Article numbers for violations
3. Penalty references (if available)

Remember: Proper citation is not just good practice - it's legally required for compliance advice.
"""
    return instructions.strip()


if __name__ == "__main__":
    logger.info("Starting Regulation Analysis MCP server on http://0.0.0.0:8000")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000, path="/mcp")
