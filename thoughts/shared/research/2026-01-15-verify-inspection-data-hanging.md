---
date: 2026-01-15T18:00:00+01:00
researcher: Claude
git_commit: 3a26a07069b256101c1f2f9cd715b33c499e9a43
branch: fix/parallel-stream-context
repository: AGORA
topic: "verify_inspection_data tool call hanging in langgraph flow"
tags: [research, mcp, langgraph, timeout, verification]
status: complete
last_updated: 2026-01-15
last_updated_by: Claude
---

# Research: verify_inspection_data Tool Call Hanging in LangGraph Flow

**Date**: 2026-01-15T18:00:00+01:00
**Researcher**: Claude
**Git Commit**: 3a26a07069b256101c1f2f9cd715b33c499e9a43
**Branch**: fix/parallel-stream-context
**Repository**: AGORA

## Research Question

Why does the `verify_inspection_data` tool call hang after being called in the LangGraph flow? The logs show it starts but takes an extremely long time to complete.

## Summary

**Three contributing factors cause the hanging behavior:**

1. **JSON Parse Error in MCP Server**: OpenAI returned a malformed response (57,331 chars) that couldn't be parsed as JSON. Error: `line 24574 column 1 (char 57331)` suggests OpenAI returned an error page or rate limit message instead of JSON.

2. **MCP Session Crash**: After the JSON error, the MCP server crashes with `anyio.ClosedResourceError` when trying to send a response on a closed stream. This leaves the client waiting.

3. **Missing Timeout in server-langgraph**: Unlike server-openai (which has 30s/120s timeouts), server-langgraph has NO timeout configuration for MCP calls, so it waits indefinitely when the MCP server hangs.

4. **Missing Timeout on OpenAI Call**: The `verifier.py` OpenAI call has no `timeout` parameter, unlike `conversation_extractor.py` which has `timeout=60.0`.

## Detailed Findings

### 1. JSON Parse Error in Verifier

**Location**: `mcp-servers/reporting/verification/verifier.py:58`

```python
result = json.loads(response.choices[0].message.content)
```

The error indicates OpenAI returned ~57KB of non-JSON content:
```
JSONDecodeError: Expecting value: line 24574 column 1 (char 57331)
```

This is likely:
- An OpenAI rate limit HTML page
- An error message from the API
- Model output wrapped in markdown code blocks instead of raw JSON

The verifier has fallback logic (lines 65-67), but the error still propagates to crash the session.

### 2. MCP Session Crash

**Location**: Stack trace shows `mcp.server.streamable_http_manager:Stateless session crashed`

After the JSON error, the MCP server crashes with:
```
anyio.ClosedResourceError
```

This happens because:
1. Error occurs during `generate_verification_questions()`
2. Exception propagates up through the MCP tool handler
3. The HTTP response stream is already closed by the time the error handler tries to send a response
4. FastMCP's streamable HTTP manager crashes the session

### 3. Missing Timeouts in server-langgraph

**server-openai** has explicit timeouts (`server-openai/src/agora_openai/adapters/mcp_tools.py:104-128`):
```python
mcp_server = MCPServerStreamableHttp(
    params={
        "url": mcp_url,
        "timeout": timedelta(seconds=30),       # HTTP connection timeout
        "sse_read_timeout": timedelta(seconds=120),  # SSE read timeout
    },
    client_session_timeout_seconds=120,
)
```

**server-langgraph** has NO timeouts (`server-langgraph/src/agora_langgraph/adapters/mcp_client.py:40-45`):
```python
config = {
    server_name: {
        "url": mcp_url,
        "transport": "streamable_http",
        # No timeout configuration!
    }
}
```

### 4. Missing Timeout on OpenAI API Call

**Has timeout** - `conversation_extractor.py:43`:
```python
response = await self.client.chat.completions.create(
    model=self.model,
    messages=[...],
    timeout=60.0,  # Explicit 60-second timeout
)
```

**Missing timeout** - `verifier.py:48-56`:
```python
response = await self.client.chat.completions.create(
    model=self.model,
    messages=[...],
    # NO timeout parameter!
)
```

Also missing in `response_parser.py:48-56`.

## Code References

| File | Line | Issue |
|------|------|-------|
| `mcp-servers/reporting/verification/verifier.py` | 58 | JSON parse without error recovery |
| `mcp-servers/reporting/verification/verifier.py` | 48-56 | OpenAI call missing timeout |
| `mcp-servers/reporting/verification/response_parser.py` | 48-56 | OpenAI call missing timeout |
| `server-langgraph/src/agora_langgraph/adapters/mcp_client.py` | 40-45 | MCP client missing timeout config |
| `server-openai/src/agora_openai/adapters/mcp_tools.py` | 104-128 | Reference implementation with timeouts |

## Recommended Fixes

### Fix 1: Add timeout to verifier.py OpenAI call

```python
# verifier.py:48-56
response = await self.client.chat.completions.create(
    model=self.model,
    messages=[...],
    response_format={"type": "json_object"},
    temperature=0.3,
    timeout=60.0,  # Add this
)
```

### Fix 2: Add timeout to response_parser.py OpenAI call

```python
# response_parser.py:48-56
response = await self.client.chat.completions.create(
    model=self.model,
    messages=[...],
    response_format={"type": "json_object"},
    temperature=0.1,
    timeout=60.0,  # Add this
)
```

### Fix 3: Add timeout to server-langgraph MCP client

The `langchain-mcp-adapters` library may support timeout configuration. Check the library docs for:
```python
config = {
    server_name: {
        "url": mcp_url,
        "transport": "streamable_http",
        "timeout": 30,  # Add if supported
        "read_timeout": 120,  # Add if supported
    }
}
```

If not supported, wrap tool execution in `asyncio.wait_for()`.

### Fix 4: Improve error handling in verifier fallback

The current fallback logic catches exceptions but the MCP session still crashes. Consider:
1. Logging and returning fallback questions without re-raising
2. Ensuring the MCP tool always returns a valid dict, even on error

## Architecture Insights

The timeout disparity between server-openai and server-langgraph reveals an integration gap. Server-openai uses the OpenAI Agents SDK which has built-in MCP support with timeout parameters. Server-langgraph uses langchain-mcp-adapters which may not expose the same timeout controls.

This is a common pattern when integrating different SDK ecosystems - timeout and error handling behaviors differ significantly.

## Fixes Applied

### 1. Added timeout to verifier.py OpenAI call
```python
timeout=60.0,
```

### 2. Added minimal data extraction for prompts
New `_create_minimal_data()` method that:
- Excludes full violation descriptions (just count and types)
- Truncates long observations to 200 chars
- Reduces prompt size significantly

### 3. Added prompt size logging
```python
logger.info(f"Verification prompt size: {prompt_size} chars ({prompt_size / 1000:.1f}KB)")
```

### 4. Added timeout to response_parser.py
Same 60-second timeout added.

## Open Questions

1. What caused OpenAI to return 57KB of non-JSON content? Rate limiting? Model hallucination?
2. Does `langchain-mcp-adapters` support timeout configuration?
3. Should the fallback question logic be more robust to prevent session crashes?
