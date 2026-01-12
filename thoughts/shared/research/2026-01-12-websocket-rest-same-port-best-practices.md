---
date: 2026-01-12T12:00:00+01:00
researcher: Claude
git_commit: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
branch: main
repository: AGORA
topic: "WebSocket and REST API on Same Port - Best Practices"
tags: [research, websocket, rest-api, fastapi, mock-server, ag-ui-protocol]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: WebSocket and REST API on Same Port - Best Practices

**Date**: 2026-01-12T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
**Branch**: main
**Repository**: AGORA

## Research Question

Is exposing WebSocket and REST API on the same port best practice? Why are PUT requests getting stuck on the mock_server.py while GET requests work?

## Summary

**The PUT request issue in mock_server.py is caused by a documented limitation of the `websockets` library** - its `process_request` callback cannot reliably access POST/PUT request bodies. The FastAPI-based servers (server-langgraph and server-openai) do not have this issue because FastAPI/Starlette natively supports full HTTP functionality alongside WebSocket.

**Recommendation**: Rewrite the mock_server.py using FastAPI or aiohttp to properly support all HTTP methods. Exposing WebSocket and REST on the same port IS best practice when using the right framework.

## Detailed Findings

### Root Cause: websockets Library Limitation

The mock_server.py uses the `websockets` library with `process_request` callback (lines 1089-1515) to handle HTTP requests that aren't WebSocket upgrades. This approach has a critical limitation documented by the library maintainer:

> "Providing an HTTP server is out of scope for websockets. It only aims at providing a WebSocket server. There's limited support for returning HTTP responses with the process_request hook."

From [GitHub Issue #926](https://github.com/aaugustin/websockets/issues/926):
> "After looking at the process_request function, it looks like it can't receive the body of a POST request."

The `get_request_body()` helper at lines 1283-1290 attempts to access `request.body`, but this attribute is not reliably populated by the websockets library for non-GET requests:

```python
def get_request_body() -> dict:
    """Parse JSON request body if present."""
    try:
        if hasattr(request, "body") and request.body:
            return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, AttributeError):
        pass
    return {}
```

### Why FastAPI Servers Work Correctly

The server-langgraph and server-openai implementations use FastAPI, which is built on Starlette (ASGI framework). FastAPI natively differentiates between HTTP and WebSocket connections via the ASGI `scope["type"]`:

- HTTP requests have `scope["type"] == "http"` - full request body access
- WebSocket requests have `scope["type"] == "websocket"` - upgrade to bidirectional

FastAPI handles PUT request bodies properly with Pydantic validation:

```python
# server-langgraph/src/agora_langgraph/api/server.py:354-374
@app.put("/users/{user_id}")
async def update_user(
    user_id: str,
    name: str | None = Query(None, description="User's display name"),
    role: str | None = Query(None, description="User's role"),
):
```

### Comparison: Protocol Handling

| Feature | websockets library | FastAPI/Starlette |
|---------|-------------------|-------------------|
| HTTP GET | Works (limited) | Full support |
| HTTP POST/PUT body | **Not accessible** | Full parsing + validation |
| WebSocket | Full support | Full support |
| Routing | Manual `process_request` | Declarative decorators |
| Request validation | None | Pydantic integration |
| CORS middleware | Manual headers | Built-in middleware |

### Best Practice: Single Port Deployment

**Yes, serving WebSocket and REST on the same port is best practice** - when using the right framework:

1. **Simplified deployment** - Single port for load balancers, proxies
2. **Unified CORS handling** - One configuration point
3. **Shared authentication** - Same middleware chain
4. **Easier client configuration** - Single base URL

The key is using a framework that natively supports both protocols (FastAPI, Starlette, aiohttp), not bolting HTTP onto a WebSocket-only library.

## Code References

- `docs/hai-contract/mock_server.py:1089-1515` - HTTP handling via `process_request` callback
- `docs/hai-contract/mock_server.py:1283-1290` - Broken `get_request_body()` helper
- `server-langgraph/src/agora_langgraph/api/server.py:397-520` - FastAPI WebSocket endpoint
- `server-langgraph/src/agora_langgraph/api/server.py:97-103` - CORS middleware
- `server-openai/src/agora_openai/api/server.py:396-519` - FastAPI WebSocket endpoint

## Recommended Solutions

### Option 1: Rewrite mock_server.py with FastAPI (Recommended)

```python
from fastapi import FastAPI, WebSocket, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class UpdateUserRequest(BaseModel):
    name: str | None = None
    preferences: dict | None = None

@app.put("/users/{user_id}")
async def update_user(user_id: str, request: UpdateUserRequest):
    # Full request body access works
    ...

@app.put("/users/me/preferences")
async def update_preferences(user_id: str = Query(...), request: UpdateUserRequest):
    # Works correctly with FastAPI
    ...

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # WebSocket handling unchanged
    ...
```

### Option 2: Use aiohttp (Alternative)

```python
from aiohttp import web

async def update_user(request):
    user_id = request.match_info['user_id']
    data = await request.json()  # Full body access
    return web.json_response({"success": True})

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    # WebSocket handling
    return ws

app = web.Application()
app.add_routes([
    web.put('/users/{user_id}', update_user),
    web.get('/ws', websocket_handler)
])
```

### Option 3: Quick Workaround (Not Recommended)

If immediate migration isn't feasible, PUT endpoints could be converted to use query parameters like the current FastAPI servers do:

```python
# Instead of PUT body, use query params
# PUT /users/me/preferences?theme=dark&language=nl-NL
```

This is how the FastAPI servers currently handle PUT (see `server.py:302-335`), but it's not RESTful and limits payload complexity.

## Architecture Insights

Both production servers (server-langgraph and server-openai) correctly use FastAPI for combined WebSocket + REST. The mock_server.py was likely built as a quick prototype using the simpler websockets library, without anticipating the need for full REST functionality.

The AG-UI Protocol itself is WebSocket-based for real-time streaming, but session/user management naturally uses REST. This is a common pattern and FastAPI handles it well.

## Open Questions

1. Should mock_server.py be rewritten to match the production servers' FastAPI stack for consistency?
2. Are there specific PUT endpoints that are critical for testing and need immediate fixes?
3. Would it be acceptable to use aiohttp instead of FastAPI for the mock server (smaller dependency)?

## Sources

- [FastAPI WebSockets Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [websockets FAQ - Server](https://websockets.readthedocs.io/en/stable/faq/server.html)
- [GitHub Issue #926 - POST Request Handling](https://github.com/aaugustin/websockets/issues/926)
- [Starlette Routing Documentation](https://www.starlette.io/routing/)
