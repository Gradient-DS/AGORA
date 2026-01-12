---
date: 2026-01-12T12:00:00+01:00
researcher: Claude
git_commit: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
branch: feat/mock_server_update
repository: AGORA
topic: "Mock Server and API Contract Sync Analysis"
tags: [research, api-contract, mock-server, ag-ui-protocol, openapi, asyncapi]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Mock Server and API Contract Sync Analysis

**Date**: 2026-01-12T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
**Branch**: feat/mock_server_update
**Repository**: AGORA

## Research Question

Are `docs/hai-contract/mock_server.py`, `docs/hai-contract/openapi.yaml`, and `docs/hai-contract/asyncapi.yaml` in sync with the actual server-openai and server-langgraph backend implementations?

## Summary

The analysis reveals **several sync issues** between the contracts and implementations. Both backends (server-openai and server-langgraph) are **consistent with each other** but have diverged from the documented contracts in specific ways. The most significant issues are:

1. **REST API response schema differences** - especially `/agents` and `/` endpoints
2. **Missing spoken text events** - `agora:spoken_text_*` events not implemented in either backend
3. **Missing `RUN_ERROR` event in asyncapi.yaml** - implemented but not documented

## Detailed Findings

### REST API Sync Status (openapi.yaml)

#### Endpoints Implementation Status

| Endpoint | Contract | server-openai | server-langgraph | mock_server |
|----------|----------|---------------|------------------|-------------|
| GET /health | Yes | Yes | Yes | Yes |
| GET / | Yes | Yes | Yes | Yes |
| GET /agents | Yes | Yes | Yes | Yes |
| GET /sessions | Yes | Yes | Yes | Yes |
| GET /sessions/{id}/history | Yes | Yes | Yes | Yes |
| GET /sessions/{id}/metadata | Yes | Yes | Yes | Yes |
| DELETE /sessions/{id} | Yes | Yes | Yes | Yes |
| GET /users/me | Yes | Yes | Yes | Yes |
| GET /users/me/preferences | Yes | Yes | Yes | Yes |
| PUT /users/me/preferences | Yes | Yes | Yes | Yes |
| POST /users | Yes | Yes | Yes | Yes |
| GET /users | Yes | Yes | Yes | Yes |
| GET /users/{id} | Yes | Yes | Yes | Yes |
| PUT /users/{id} | Yes | Yes | Yes | Yes |
| DELETE /users/{id} | Yes | Yes | Yes | Yes |
| GET /mock_documents/{filename} | Yes | No* | No* | Yes |

*Intentionally mock-only, correctly documented

#### Response Schema Differences

| Endpoint | Contract Schema | Actual Implementation | Issue |
|----------|----------------|----------------------|-------|
| `GET /agents` | `{success, agents: [{id, name, description}]}` | `{active_agents: [{id, name, model, description}], inactive_agents}` | Different structure, extra `model` field |
| `GET /` | Nested `endpoints` object | Flat with `docs`, `websocket` keys | Different structure |
| `GET /health` | `service: "agora-mock"` | `service: "agora-agents"` / `"agora-langgraph"` | Service name differs |
| `GET /users/me` | No query param (authenticated) | Requires `user_id` query param | Auth model differs |
| `PUT /users/{id}` | JSON body `UpdateUserRequest` | Query parameters `name`, `role` | Request format differs |
| `POST /users` | `{email, name}` | `{email, name, role}` | Extra `role` field |

### WebSocket/AG-UI Event Sync Status (asyncapi.yaml)

#### Event Implementation Status

| Event Type | asyncapi.yaml | server-openai | server-langgraph | mock_server |
|------------|---------------|---------------|------------------|-------------|
| RUN_STARTED | Yes | Yes | Yes | Yes |
| RUN_FINISHED | Yes | Yes | Yes | Yes |
| RUN_ERROR | **No** | Yes | Yes | No |
| STEP_STARTED | Yes | Yes | Yes | Yes |
| STEP_FINISHED | Yes | Yes | Yes | Yes |
| TEXT_MESSAGE_START | Yes | Yes | Yes | Yes |
| TEXT_MESSAGE_CONTENT | Yes | Yes | Yes | Yes |
| TEXT_MESSAGE_END | Yes | Yes | Yes | Yes |
| TOOL_CALL_START | Yes | Yes | Yes | Yes |
| TOOL_CALL_ARGS | Yes | Yes | Yes | Yes |
| TOOL_CALL_END | Yes | Yes | Yes | Yes |
| TOOL_CALL_RESULT | Yes | Yes | Yes | Yes |
| STATE_SNAPSHOT | Yes | Yes | Yes | Yes |
| agora:tool_approval_request | Yes | Yes | Yes | Yes |
| agora:tool_approval_response | Yes | Yes | Yes | Yes |
| agora:error | Yes | Yes | Yes | No |
| agora:spoken_text_start | Yes | **No** | **No** | Yes |
| agora:spoken_text_content | Yes | **No** | **No** | Yes |
| agora:spoken_text_end | Yes | **No** | **No** | Yes |

#### Key WebSocket Issues

1. **Missing `RUN_ERROR` in asyncapi.yaml** - Both backends implement this official AG-UI event, but it's not documented in the asyncapi.yaml contract

2. **Missing `agora:spoken_text_*` events in backends** - The mock_server.py implements these TTS-optimized events (lines 1319-1381), but neither backend implements them:
   - `agora:spoken_text_start`
   - `agora:spoken_text_content`
   - `agora:spoken_text_end`

3. **Missing `toolDescription` field usage** - asyncapi.yaml specifies an optional `toolDescription` field in TOOL_CALL_START for TTS announcements (lines 545-551), but the backends don't populate this field

### RunAgentInput Schema Sync

| Field | asyncapi.yaml | Implementations | Status |
|-------|---------------|-----------------|--------|
| threadId | Required | Required | Synced |
| runId | Optional | Optional | Synced |
| userId | Required (AGORA ext) | Required | Synced |
| messages | Required | Required | Synced |
| context | Optional | Optional | Synced |

## Code References

### server-openai
- REST endpoints: `server-openai/src/agora_openai/api/server.py:105-410`
- WebSocket: `server-openai/src/agora_openai/api/server.py:413-536`
- AG-UI handler: `server-openai/src/agora_openai/api/ag_ui_handler.py`
- Orchestrator events: `server-openai/src/agora_openai/pipelines/orchestrator.py:152-370`

### server-langgraph
- REST endpoints: `server-langgraph/src/agora_langgraph/api/server.py:106-411`
- WebSocket: `server-langgraph/src/agora_langgraph/api/server.py:414-538`
- AG-UI handler: `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py`
- Orchestrator events: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:176-453`

### Contracts
- `docs/hai-contract/openapi.yaml` - REST API contract
- `docs/hai-contract/asyncapi.yaml` - WebSocket event contract
- `docs/hai-contract/mock_server.py` - Mock implementation

## Recommendations (No Code Changes)

These are observations for future consideration:

### High Priority (Contract/Implementation Mismatch)
1. **Document `RUN_ERROR` in asyncapi.yaml** - This official AG-UI event is implemented but not documented
2. **Align `/agents` endpoint response** - Either update contract or implementations
3. **Decide on spoken text events** - Either implement in backends or remove from contract/mock

### Medium Priority (Schema Alignment)
4. **`GET /` endpoint structure** - Align contract and implementations
5. **`PUT /users/{id}` request format** - Contract says JSON body, impl uses query params
6. **`GET /users/me` auth model** - Document that `user_id` query param is required

### Low Priority (Consistency Improvements)
7. **Document `role` field in user schemas** - Implementations use it but contract doesn't show it
8. **Document `model` field in agent response** - Implementations include it but contract doesn't

## Architecture Insights

1. **Both backends are consistent** - server-openai and server-langgraph have identical API behavior and identical deviations from the contract

2. **Mock server is more complete for demo features** - It implements spoken text events that backends don't

3. **Contract serves as aspirational spec** - Some features documented (spoken text) appear to be planned but not yet implemented

4. **Backend implementations evolved** - The `active_agents`/`inactive_agents` structure and `role` field suggest features added after initial contract

## Open Questions

1. Are the `agora:spoken_text_*` events planned for implementation in backends, or should they be removed from the contract?

2. Should the `/agents` endpoint response be changed to match contract, or should the contract be updated to match implementation?

3. Is the `toolDescription` field in TOOL_CALL_START intended to be used? Neither backend populates it currently.
