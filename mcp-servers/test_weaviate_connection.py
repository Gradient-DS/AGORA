#!/usr/bin/env python3
"""
Test script to debug Weaviate connection issues in the regulation-analysis MCP server.
Run this from the mcp-servers directory.
"""
import sys
import json
import asyncio
from pathlib import Path

print("=" * 80)
print("WEAVIATE CONNECTION DEBUG TEST")
print("=" * 80)
print()

# Test 1: Direct Weaviate connection
print("Test 1: Testing direct Weaviate connection...")
print("-" * 80)
try:
    import httpx
    response = httpx.get("http://localhost:8080/v1/.well-known/ready", timeout=5)
    if response.status_code == 200:
        print("✓ Weaviate is reachable at http://localhost:8080")
        print(f"  Response: {response.text}")
    else:
        print(f"✗ Weaviate returned status code: {response.status_code}")
except Exception as e:
    print(f"✗ Cannot reach Weaviate: {e}")
print()

# Test 2: Check Weaviate schema
print("Test 2: Checking Weaviate schema...")
print("-" * 80)
try:
    response = httpx.get("http://localhost:8080/v1/schema", timeout=5)
    if response.status_code == 200:
        schema = response.json()
        classes = schema.get("classes", [])
        print(f"✓ Found {len(classes)} class(es) in Weaviate")
        for cls in classes:
            print(f"  - {cls['class']}")
    else:
        print(f"✗ Failed to get schema: {response.status_code}")
except Exception as e:
    print(f"✗ Error checking schema: {e}")
print()

# Test 3: Check if data exists
print("Test 3: Checking if data exists in RegulationChunk...")
print("-" * 80)
try:
    response = httpx.get(
        "http://localhost:8080/v1/objects",
        params={"class": "RegulationChunk", "limit": 1},
        timeout=5
    )
    if response.status_code == 200:
        data = response.json()
        total = data.get("totalResults", 0)
        if total > 0:
            print(f"✓ Found {total} objects in RegulationChunk")
            if data.get("objects"):
                obj = data["objects"][0]
                print(f"  Sample: {obj.get('properties', {}).get('document_name', 'N/A')}")
        else:
            print("✗ No data in RegulationChunk - you need to ingest documents first!")
            print("  Run: cd document-ingestion && python ingest.py")
    else:
        print(f"✗ Failed to query objects: {response.status_code}")
except Exception as e:
    print(f"✗ Error checking data: {e}")
print()

# Test 4: Load config from document-ingestion
print("Test 4: Testing config loading...")
print("-" * 80)
sys.path.insert(0, str(Path(__file__).parent / "document-ingestion"))
try:
    from config import get_settings
    settings = get_settings()
    print("✓ Config loaded successfully")
    print(f"  Weaviate URL: {settings.weaviate_url}")
    print(f"  Embedding model: {settings.embedding_model}")
    print(f"  Embedding device: {settings.embedding_device}")
except Exception as e:
    print(f"✗ Failed to load config: {e}")
    import traceback
    traceback.print_exc()
print()

# Test 5: Test WeaviateClient
print("Test 5: Testing WeaviateClient initialization...")
print("-" * 80)
try:
    from database.weaviate_client import WeaviateClient
    client = WeaviateClient("http://localhost:8080")
    if client.connect():
        print("✓ WeaviateClient connected successfully")
        stats = client.get_stats()
        print(f"  Stats: {stats}")
    else:
        print("✗ WeaviateClient failed to connect")
except Exception as e:
    print(f"✗ Failed to initialize WeaviateClient: {e}")
    import traceback
    traceback.print_exc()
print()

# Test 6: Test Embedder
print("Test 6: Testing Embedder initialization...")
print("-" * 80)
try:
    from embeddings.embedder import Embedder
    print("  Note: This will download the model if not cached (~550MB)")
    print("  Loading model... (this may take a moment)")
    embedder = Embedder(
        model_name="nomic-ai/nomic-embed-text-v1.5",
        device="cpu"  # Use CPU for testing
    )
    print("✓ Embedder loaded successfully")
    print(f"  Model: {embedder.model_name}")
    print(f"  Device: {embedder.device}")
    print(f"  Dimension: {embedder.dimension}")
    
    # Test embedding
    test_vector = embedder.embed_query("test query")
    print(f"✓ Test embedding successful (vector length: {len(test_vector)})")
except ImportError as e:
    print(f"✗ Failed to import Embedder: {e}")
    print("  This might be a class name mismatch issue")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"✗ Failed to initialize Embedder: {e}")
    import traceback
    traceback.print_exc()
print()

# Test 7: Test vector search
print("Test 7: Testing vector search functionality...")
print("-" * 80)
try:
    from database.weaviate_client import WeaviateClient
    from embeddings.embedder import Embedder
    
    client = WeaviateClient("http://localhost:8080")
    embedder = Embedder(model_name="nomic-ai/nomic-embed-text-v1.5", device="cpu")
    
    if client.connect():
        test_query = "rauwe vis op kamertemperatuur"
        print(f"  Searching for: '{test_query}'")
        
        query_vector = embedder.embed_query(test_query)
        results = client.search(
            query_vector=query_vector,
            filters={},
            limit=3,
            alpha=0.7
        )
        
        if results:
            print(f"✓ Found {len(results)} results")
            for i, result in enumerate(results[:2], 1):
                content_preview = result.get("content", "")[:100]
                score = result.get("score", 0)
                doc = result.get("document_name", "Unknown")
                print(f"  {i}. [{doc}] Score: {score:.3f}")
                print(f"     {content_preview}...")
        else:
            print("✗ No results found - check if data is ingested")
    else:
        print("✗ Could not connect to Weaviate")
except Exception as e:
    print(f"✗ Vector search failed: {e}")
    import traceback
    traceback.print_exc()
print()

# Test 8: Test MCP server endpoint
print("Test 8: Testing MCP server endpoint...")
print("-" * 80)
async def test_mcp_endpoint():
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test health endpoint
            response = await client.get("http://localhost:5002/health")
            if response.status_code == 200:
                health = response.json()
                print(f"✓ MCP server is healthy")
                print(f"  Weaviate connected: {health.get('weaviate_connected')}")
                
                if not health.get('weaviate_connected'):
                    print("  ⚠ Server reports Weaviate is NOT connected")
                    print("  This is the issue! Server needs to be restarted after fixing imports.")
            else:
                print(f"✗ Health check failed: {response.status_code}")
            
            # Test actual tool call
            print("\n  Testing search_regulations tool...")
            mcp_request = {
                "jsonrpc": "2.0",
                "id": "test-123",
                "method": "tools/call",
                "params": {
                    "name": "search_regulations",
                    "arguments": {
                        "query": "rauwe vis temperatuur",
                        "filters": {"regulation_type": "food_safety"},
                        "limit": 3
                    }
                }
            }
            
            response = await client.post(
                "http://localhost:5002/mcp",
                json=mcp_request,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
            )
            
            if response.status_code == 200:
                # Parse SSE response
                lines = response.text.strip().split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        result = data.get("result", {})
                        
                        if "error" in result:
                            print(f"✗ Tool returned error: {result['error']}")
                        elif "content" in result:
                            content = result["content"]
                            if isinstance(content, list) and len(content) > 0:
                                parsed = json.loads(content[0].get("text", "{}"))
                                if "error" in parsed:
                                    print(f"✗ Search error: {parsed['error']}")
                                elif "results" in parsed:
                                    print(f"✓ Search successful! Found {parsed.get('found', 0)} results")
                                    for i, res in enumerate(parsed["results"][:2], 1):
                                        print(f"    {i}. {res.get('citation', 'No citation')}")
                                else:
                                    print(f"  Result: {parsed}")
            else:
                print(f"✗ MCP request failed: {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                
    except Exception as e:
        print(f"✗ MCP endpoint test failed: {e}")
        import traceback
        traceback.print_exc()

try:
    asyncio.run(test_mcp_endpoint())
except Exception as e:
    print(f"✗ Failed to run async test: {e}")
print()

# Summary
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print()
print("If all tests pass except Test 8, the issue is:")
print("  → The MCP server container has an old/cached version of the code")
print("  → Solution: Rebuild the container")
print()
print("If Tests 1-3 pass but Test 4-7 fail:")
print("  → There's a Python dependency or import issue")
print("  → Check if the class names match (Embedder vs JinaEmbedder)")
print()
print("If Test 1-2 pass but Test 3 fails:")
print("  → No data in Weaviate")
print("  → Run: cd document-ingestion && python ingest.py")
print()
print("To rebuild the MCP server:")
print("  cd /Users/lexlubbers/Code/AGORA/mcp-servers")
print("  docker-compose build regulation-analysis")
print("  docker-compose up -d regulation-analysis")
print()

