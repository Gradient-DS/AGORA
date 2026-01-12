---
date: 2026-01-12T14:30:00+01:00
researcher: Claude
git_commit: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
branch: main
repository: Gradient-DS/AGORA
topic: "Mock Server vs Backend Sync Analysis"
tags: [research, mock-server, ag-ui-protocol, websocket, rest-api, agora-openai, agora-langgraph]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Mock Server vs Backend Sync Analysis

**Date**: 2026-01-12T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
**Branch**: main
**Repository**: Gradient-DS/AGORA

## Research Question

Is the mock_server.py in sync with the actual agora_langgraph and agora_openai backends? Are they emitting the same events for WebSocket and REST API? Known discrepancy: spoken messages (agora:spoken...) in AG-UI protocol.

## Summary

The mock server is **mostly in sync** with both backends, with a few notable differences:

1. **WebSocket Events**: Both backends emit identical AG-UI Protocol events, but the **mock server emits additional `agora:spoken_text_*` events** that neither backend implements
2. **REST API**: Core endpoints match, but there are **parameter passing differences** (query params vs JSON body) and **additional endpoints** in backends
3. **Response Format**: Minor differences in response wrapping for some endpoints

## Detailed Findings

### WebSocket Events Comparison

#### Events Both Backends Emit (Matching Mock)

| Event Type | Mock | agora_openai | agora_langgraph |
|------------|------|--------------|-----------------|
| `RUN_STARTED` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `RUN_FINISHED` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `RUN_ERROR` | :x: (not emitted) | :white_check_mark: | :white_check_mark: |
| `STEP_STARTED` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `STEP_FINISHED` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TEXT_MESSAGE_START` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TEXT_MESSAGE_CONTENT` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TEXT_MESSAGE_END` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TOOL_CALL_START` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TOOL_CALL_ARGS` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TOOL_CALL_END` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `TOOL_CALL_RESULT` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `STATE_SNAPSHOT` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `agora:tool_approval_request` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `agora:error` | :x: (not emitted) | :white_check_mark: | :white_check_mark: |

#### Events Mock Emits But Backends Do Not

| Event | Mock Server | Backends | Impact |
|-------|-------------|----------|--------|
| `agora:spoken_text_start` | :white_check_mark: `mock_server.py:997-1006` | :x: Not implemented | TTS feature not in backends |
| `agora:spoken_text_content` | :white_check_mark: `mock_server.py:1023-1034` | :x: Not implemented | TTS feature not in backends |
| `agora:spoken_text_end` | :white_check_mark: `mock_server.py:1048-1058` | :x: Not implemented | TTS feature not in backends |

#### Events Backends Emit But Mock Does Not

| Event | agora_openai | agora_langgraph | Mock |
|-------|--------------|-----------------|------|
| `RUN_ERROR` | :white_check_mark: `ag_ui_handler.py:153-160` | :white_check_mark: `ag_ui_handler.py:159-166` | :x: Not emitted |
| `agora:error` | :white_check_mark: `ag_ui_handler.py:297-318` | :white_check_mark: `ag_ui_handler.py:303-324` | :x: Not emitted |

### REST API Comparison

#### Matching Endpoints

| Endpoint | Mock | agora_openai | agora_langgraph |
|----------|------|--------------|-----------------|
| `GET /health` | :white_check_mark: | :white_check_mark: `server.py:105-108` | :white_check_mark: `server.py:106-109` |
| `GET /sessions?user_id=` | :white_check_mark: | :white_check_mark: `server.py:174-193` | :white_check_mark: `server.py:175-194` |
| `GET /sessions/{id}/history` | :white_check_mark: | :white_check_mark: `server.py:141-171` | :white_check_mark: `server.py:142-172` |
| `GET /sessions/{id}/metadata` | :white_check_mark: | :white_check_mark: `server.py:196-209` | :white_check_mark: `server.py:197-210` |
| `DELETE /sessions/{id}` | :white_check_mark: | :white_check_mark: `server.py:212-229` | :white_check_mark: `server.py:213-230` |
| `POST /users` | :white_check_mark: | :white_check_mark: `server.py:245-263` | :white_check_mark: `server.py:246-264` |
| `GET /users` | :white_check_mark: | :white_check_mark: `server.py:266-280` | :white_check_mark: `server.py:267-281` |
| `GET /users/{id}` | :white_check_mark: | :white_check_mark: `server.py:337-350` | :white_check_mark: `server.py:338-351` |
| `DELETE /users/{id}` | :white_check_mark: | :white_check_mark: `server.py:376-393` | :white_check_mark: `server.py:377-394` |

#### Endpoints with Parameter Differences

| Endpoint | Mock Implementation | Backend Implementation | Difference |
|----------|---------------------|------------------------|------------|
| `GET /users/me` | No auth required | Requires `user_id` query param | Mock simulates auth with `CURRENT_USER_ID` constant |
| `PUT /users/me/preferences` | JSON body: `{"theme": "...", ...}` | Query params: `?theme=...&notifications_enabled=...` | Different parameter passing method |
| `PUT /users/{id}` | JSON body: `{"name": "...", "preferences": {...}}` | Query params: `?name=...&role=...` | Different parameter passing method |

#### Endpoints Only in Backends

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Root endpoint with service info and docs links |
| `GET /agents` | List active and inactive agents |

#### Endpoints Only in Mock

| Endpoint | Purpose |
|----------|---------|
| `GET /mock_documents/{filename}` | Serve static test files (report.json, report.pdf) |

### Response Format Differences

#### Health Check Response

**Mock:**
```json
{"status": "healthy", "service": "agora-mock", "protocol": "ag-ui"}
```

**agora_openai:**
```json
{"status": "healthy", "service": "agora-agents", "protocol": "ag-ui"}
```

**agora_langgraph:**
```json
{"status": "healthy", "service": "agora-langgraph", "protocol": "ag-ui"}
```

#### GET /users/me Response

**Mock:** Returns user with `success` wrapper omitted (direct user object)
**Backends:** Also return user directly without wrapper

This is actually consistent - both mock and backends return the user object directly for this endpoint.

## Code References

### Mock Server
- `docs/hai-contract/mock_server.py:977-1086` - `stream_response()` with spoken text events
- `docs/hai-contract/mock_server.py:758-786` - Tool approval request
- `docs/hai-contract/mock_server.py:1089-1516` - REST API `process_request()` handler

### agora_openai Backend
- `server-openai/src/agora_openai/api/server.py:105-393` - REST endpoints
- `server-openai/src/agora_openai/api/server.py:396-519` - WebSocket handler
- `server-openai/src/agora_openai/api/ag_ui_handler.py:130-318` - AG-UI event emissions
- `server-openai/src/agora_openai/pipelines/orchestrator.py:97-374` - Event triggering

### agora_langgraph Backend
- `server-langgraph/src/agora_langgraph/api/server.py:106-394` - REST endpoints
- `server-langgraph/src/agora_langgraph/api/server.py:397-520` - WebSocket handler
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:136-324` - AG-UI event emissions
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:118-270` - Event triggering

## Architecture Insights

### Event Emission Consistency

Both `agora_openai` and `agora_langgraph` have nearly identical AG-UI Protocol handler implementations. They:
- Use the same event types from `ag_ui.core`
- Have identical method signatures in `AGUIProtocolHandler`
- Use the same timestamp format (Unix milliseconds)
- Use camelCase JSON serialization via Pydantic aliases

### Spoken Text Feature Gap

The mock server includes a TTS-friendly text streaming feature (`agora:spoken_text_*` events) that:
- Runs in parallel with regular `TEXT_MESSAGE_*` events
- Strips markdown formatting
- Expands Dutch abbreviations (KVK, NVWA, etc.)
- Replaces emojis with text equivalents

This feature is **not implemented in either backend**. If TTS support is needed, this would require:
1. Adding `agora:spoken_text_*` event types to `ag_ui_types.py`
2. Implementing `to_spoken_text()` conversion logic
3. Emitting parallel spoken text events in the orchestrator

### REST API Design Patterns

**Backends use FastAPI query parameters** for update operations rather than JSON bodies:
```python
# Backend pattern
@app.put("/users/me/preferences")
async def update_preferences(
    user_id: str,
    theme: str | None = None,
    notifications_enabled: bool | None = None,
):
```

**Mock uses JSON bodies** (more RESTful):
```python
# Mock pattern (in process_request)
request_body = get_request_body()
user["preferences"]["theme"] = request_body.get("theme")
```

This is a design choice - the backend approach is simpler but less RESTful.

## Recommendations

### High Priority
1. **Add error events to mock server** - Mock should emit `RUN_ERROR` and `agora:error` events for testing error handling flows

### Medium Priority
2. **Align REST API parameter passing** - Consider whether backends should accept JSON bodies for PUT operations to match RESTful conventions and mock server
3. **Document spoken text feature status** - Clarify in protocol spec whether `agora:spoken_text_*` events are optional extensions or deprecated

### Low Priority
4. **Add `/agents` endpoint to mock** - For testing agent listing functionality
5. **Consistent service names** - Standardize the service name in health responses

## Open Questions

1. **Is the spoken text feature planned for backends?** If so, should it be added to both `agora_openai` and `agora_langgraph`?
2. **Should the REST API parameter style be standardized?** Query params (current) vs JSON bodies (more RESTful)?
3. **Should `RUN_ERROR` be added to mock server?** Currently mock doesn't simulate error scenarios.
