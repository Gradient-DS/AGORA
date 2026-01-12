---
date: 2026-01-12T00:00:00+01:00
researcher: Claude
git_commit: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
branch: feat/mock_server_update
repository: AGORA
topic: "Comparison of mock_server.py FastAPI vs feat/async-io-server implementations"
tags: [research, mock-server, fastapi, rest-api, websocket]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Mock Server FastAPI vs async-io-server Branch Comparison

**Date**: 2026-01-12
**Researcher**: Claude
**Git Commit**: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
**Branch**: feat/mock_server_update
**Repository**: AGORA

## Research Question

Does the current FastAPI mock_server.py implementation meet the requirements of the downstream developer who created the feat/async-io-server branch?

## Summary

**Yes, the current FastAPI implementation meets and exceeds the requirements.** The current version provides all REST endpoints that were added in feat/async-io-server, plus additional features like:
- Single port operation (8000) instead of separate ports
- OpenAPI documentation at `/docs`
- Additional `/agents` endpoint
- Additional `GET /users/me/preferences` endpoint

The only minor differences are in the user preferences schema and some response format variations.

## Detailed Findings

### Architecture Comparison

| Aspect | feat/async-io-server | Current (FastAPI) |
|--------|---------------------|-------------------|
| **Framework** | Raw `websockets` + `asyncio.start_server` | FastAPI + uvicorn |
| **WebSocket Port** | 8000 | 8000 |
| **REST API Port** | 8001 (separate) | 8000 (same) |
| **OpenAPI Docs** | None | `/docs` |
| **Validation** | Manual | Pydantic models |
| **CORS** | Manual headers | CORSMiddleware |

### Endpoint Comparison

| Endpoint | async-io-server | FastAPI |
|----------|----------------|---------|
| `GET /` | Yes | Yes |
| `GET /health` | Yes | Yes |
| `GET /agents` | **No** | **Yes** |
| `GET /sessions?user_id` | Yes | Yes |
| `GET /sessions/{id}/history` | Yes | Yes |
| `GET /sessions/{id}/metadata` | Yes | Yes |
| `DELETE /sessions/{id}` | Yes | Yes |
| `GET /users/me` | Yes | Yes |
| `GET /users/me/preferences` | **No** | **Yes** (with `?user_id`) |
| `PUT /users/me/preferences` | Yes (no user_id param) | Yes (with `?user_id` param) |
| `POST /users` | Yes | Yes |
| `GET /users` | Yes | Yes |
| `GET /users/{id}` | Yes | Yes |
| `PUT /users/{id}` | Yes | Yes |
| `DELETE /users/{id}` | Yes | Yes |
| `GET /mock_documents/{filename}` | Yes | Yes |

### Preferences Schema Difference

**feat/async-io-server preferences:**
```json
{
  "theme": "light",
  "notifications_enabled": true,
  "default_agent_id": "general-agent",
  "language": "nl-NL",
  "spoken_text_type": "summarize"
}
```

**Current FastAPI preferences:**
```json
{
  "spoken_response_mode": "summarize"
}
```

The FastAPI version has a simpler preferences model focused on `spoken_response_mode`. The async-io-server branch had richer preferences including theme, notifications, default agent, and language.

### Port Configuration

- **feat/async-io-server**: Two ports - WebSocket on 8000, REST on 8001
- **Current FastAPI**: Single port 8000 for both WebSocket and REST

This is actually an **improvement** - single port is simpler for frontend configuration.

## Code References

- Current implementation: `docs/hai-contract/mock_server.py`
- async-io-server branch: `origin/feat/async-io-server:docs/hai-contract/mock_server.py`

### Key sections in current implementation:
- Session endpoints: lines 465-513
- User endpoints: lines 521-647
- Mock documents: lines 655-667
- Agents endpoint: lines 445-457

## Assessment

### Requirements Met
1. **Session CRUD** - All session endpoints (list, history, metadata, delete) are implemented
2. **User CRUD** - All user endpoints (list, get, create, update, delete) are implemented
3. **Preferences** - Preferences can be read and updated via `/users/me/preferences`
4. **Mock Documents** - Report PDF/JSON download works
5. **WebSocket** - AG-UI protocol unchanged

### Improvements in FastAPI Version
1. **Single port** - Simpler configuration
2. **OpenAPI docs** - Automatic API documentation
3. **Validation** - Pydantic models for request/response validation
4. **Agents endpoint** - List available agents
5. **Preferences GET** - Dedicated endpoint to fetch preferences

### Minor Differences
1. **Preferences schema** - Different field names and structure
2. **Port** - Frontend may need to update from 8001 to 8000 for REST calls
3. **user_id in preferences** - Query param vs no param (FastAPI is more explicit)

## Recommendation

The downstream developer can safely merge/use the current FastAPI implementation. They should:

1. Update any frontend code that calls REST endpoints on port 8001 to use port 8000
2. Update preferences field names if they were using `spoken_text_type` (now `spoken_response_mode`)
3. Consider if they need the richer preferences schema (theme, notifications, etc.)

## Open Questions

1. Does the frontend rely on the richer preferences schema (theme, notifications_enabled, etc.)?
2. Should we add those preference fields to the FastAPI version for full compatibility?
