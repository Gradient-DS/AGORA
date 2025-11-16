# Demo Issues - Fix Summary

## Issues Identified

### Issue #1: Vector Search Not Working ❌
**Symptom:** `search_regulations` tool returning error: `"Weaviate search not available"`

**Root Cause:** The regulation-analysis Docker container couldn't import the `config` module and Weaviate dependencies because they weren't copied into the Docker image.

**Fixes Applied:**
1. **Updated `mcp-servers/docker-compose.yml`:**
   - Changed build context from `./regulation-analysis` to `.` (parent directory)
   - Updated dockerfile path to `./regulation-analysis/Dockerfile`
   - Fixed environment variables to use `MCP_` prefix: `MCP_WEAVIATE_URL`, `MCP_EMBEDDING_MODEL`, `MCP_EMBEDDING_DEVICE`

2. **Updated `mcp-servers/regulation-analysis/Dockerfile`:**
   - Updated COPY commands to reference files from parent context
   - Now copies: `config.py`, `database/`, and `embeddings/` from `document-ingestion/`

3. **Updated `mcp-servers/regulation-analysis/server.py`:**
   - Removed `sys.path.insert()` hack (no longer needed)
   - Improved error handling for missing dependencies

### Issue #2: Report Generation Failing ❌
**Symptom:** `extract_inspection_data` tool failing with validation error: `"Missing required conversation_history"`

**Root Cause:** The tool required `conversation_history` as a parameter, but the OpenAI agent had no way to provide it since conversations are stored in the OpenAI thread, not accessible to the agent.

**Fixes Applied:**
1. **Updated `server-openai/src/agora_openai/adapters/openai_assistants.py`:**
   - Added new method `get_thread_messages()` to retrieve conversation history from OpenAI threads

2. **Updated `server-openai/src/agora_openai/pipelines/orchestrator.py`:**
   - Enhanced `_execute_tool_with_notification()` to detect when `extract_inspection_data` is called
   - Automatically retrieves conversation history from the OpenAI thread and injects it into the tool parameters

3. **Updated `mcp-servers/reporting/server.py`:**
   - Made `conversation_history` parameter optional (with default `None`)
   - Added fallback to retrieve from session storage if not provided

## Commands to Apply Fixes

### 1. Rebuild the MCP services

```bash
cd /Users/lexlubbers/Code/AGORA/mcp-servers
docker-compose build regulation-analysis reporting
docker-compose up -d
```

### 2. Verify Weaviate connection

```bash
# Check health of regulation-analysis service
curl http://localhost:5002/health | python3 -m json.tool

# Should now show: "weaviate_connected": true
```

### 3. Restart the OpenAI server

```bash
cd /Users/lexlubbers/Code/AGORA/server-openai

# If running in Docker:
docker-compose restart agora-openai

# If running locally:
# Stop the current process and restart it
```

### 4. Verify the fixes

```bash
# Check Weaviate has data
curl 'http://localhost:8080/v1/objects?class=RegulationChunk&limit=1' | python3 -m json.tool

# Check regulation-analysis server
curl -X POST http://localhost:5002/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test",
    "method": "tools/call",
    "params": {
      "name": "search_regulations",
      "arguments": {
        "query": "rauwe vis temperatuur",
        "filters": {"regulation_type": "food_safety"},
        "limit": 3
      }
    }
  }'
```

## Testing the Demo

Try the demo scenario again:

1. **Start inspection:** "Ik wil een inspectie doen voor Restaurant Bella Rosa, KVK nummer 92251854"
2. **Wait for history** and recommendations
3. **Report observation:** "Ik zie een geopende ton met rauwe vis op kamertemperatuur naast een afvoerputje vol schoonmaakmiddelresten"
4. **Ask regulations:** "Welke regelgeving is van toepassing?"
   - Should now return actual regulation citations from Weaviate
5. **Generate report:** "Genereer rapport"
   - Should now successfully extract data from conversation history

## Technical Details

### Why the conversation_history fix works:

The orchestrator sits between the OpenAI Assistant and the MCP tools. It has access to:
- The `session_id` (which maps to a `thread_id`)
- The OpenAI client (which can retrieve thread messages)

When the agent calls `extract_inspection_data`, the orchestrator:
1. Detects it's this specific tool
2. Looks up the thread_id for the session
3. Retrieves all messages from that thread
4. Injects them into the parameters before passing to the MCP tool

This way:
- The agent doesn't need to know about conversation history
- The tool gets the data it needs
- No changes needed to the OpenAI Assistant definitions

### Why the Weaviate fix works:

Docker build contexts are relative to where the Dockerfile is invoked from. By changing the context to the parent directory (`mcp-servers/`), the Dockerfile can now access both:
- `regulation-analysis/` (its own files)
- `document-ingestion/` (shared dependencies)

The `MCP_` prefix for environment variables matches what the `config.py` expects (configured via Pydantic settings with `env_prefix="MCP_"`).

## Verification Checklist

- [ ] Weaviate is running and contains data
- [ ] regulation-analysis server shows `"weaviate_connected": true`
- [ ] reporting server is healthy
- [ ] OpenAI server has been restarted with updated code
- [ ] Demo scenario completes successfully:
  - [ ] Inspection history is retrieved
  - [ ] Vector search returns actual regulations
  - [ ] Report generation extracts data from conversation

