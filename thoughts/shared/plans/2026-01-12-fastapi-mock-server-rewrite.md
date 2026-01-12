# FastAPI Mock Server Rewrite Implementation Plan

## Overview

Rewrite the mock_server.py from using the `websockets` library to FastAPI to properly support full REST functionality (PUT/POST request bodies) while maintaining all existing features and behavior.

## Current State Analysis

The current mock server at `docs/hai-contract/mock_server.py` (1604 lines) uses the `websockets` library with a `process_request` callback for HTTP handling. This has a **documented limitation**: the `websockets` library cannot reliably access POST/PUT request bodies, causing those endpoints to fail silently.

### Current Components:
- **Mock data structures**: Sessions (4 demo sessions), Users (3 demo personas), Demo scenario data
- **WebSocket handling**: AG-UI Protocol events for real-time communication
- **REST endpoints**: 14 endpoints for sessions and users

### Key Discoveries:
- `mock_server.py:1283-1290` - The `get_request_body()` helper attempts to access `request.body` but this is not populated by websockets library for non-GET requests
- `server-langgraph/src/agora_langgraph/api/server.py:96-103` - Production servers use FastAPI CORS middleware
- `server-openai/src/agora_openai/api/server.py:237-243` - Pydantic models for request bodies with `Field(...)` for required fields

## Desired End State

A FastAPI-based mock server that:
1. Properly handles all HTTP methods (GET, POST, PUT, DELETE) with full request body support
2. Maintains identical API contract as current server (same endpoints, same responses)
3. Serves WebSocket connections at `/ws` for AG-UI Protocol
4. Keeps all mock data structures and demo functionality
5. Follows patterns consistent with production servers

### Verification:
- All existing curl commands from the mock server output work unchanged
- PUT `/users/me/preferences` accepts JSON body and updates preferences
- WebSocket communication works identically to before
- Frontend (HAI) works without modification

## What We're NOT Doing

- NOT changing the API contract (endpoints, response formats)
- NOT adding new features or endpoints
- NOT modifying the AG-UI Protocol event handling logic
- NOT changing the demo scenario behavior
- NOT adding database persistence (keeping in-memory storage)

## Implementation Approach

The rewrite is a structural change from callback-based HTTP handling to FastAPI decorators. We'll preserve all business logic functions unchanged and only refactor the HTTP/WebSocket layer.

**Strategy**:
1. Add FastAPI imports and setup
2. Convert `process_request` callback logic into FastAPI route handlers
3. Convert WebSocket handler to FastAPI WebSocket endpoint
4. Remove websockets library dependency
5. Test thoroughly

---

## Phase 1: FastAPI App Setup and Imports

### Overview
Set up the FastAPI application with CORS middleware, matching the production server patterns.

### Changes Required:

#### 1. Update imports
**File**: `docs/hai-contract/mock_server.py`
**Lines**: 43-55

Replace:
```python
import websockets
from websockets.http11 import Response
```

With:
```python
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
```

#### 2. Add Pydantic request models (after line 356)
**File**: `docs/hai-contract/mock_server.py`
**Add after**: `CURRENT_USER_ID = ...`

```python
# ---------------------------------------------------------------------------
# REQUEST MODELS (for FastAPI)
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    """Request body for creating a user."""
    email: str = Field(..., description="User's email address")
    name: str = Field(..., description="User's display name")


class UpdateUserRequest(BaseModel):
    """Request body for updating a user."""
    name: str | None = Field(None, description="User's display name")
    preferences: dict | None = Field(None, description="User preferences")


class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""
    theme: str | None = Field(None, description="Theme preference")
    notifications_enabled: bool | None = Field(None, description="Enable notifications")
    default_agent_id: str | None = Field(None, description="Default agent ID")
    language: str | None = Field(None, description="Language preference")
```

#### 3. Add FastAPI app setup (after request models)
**File**: `docs/hai-contract/mock_server.py`

```python
# ---------------------------------------------------------------------------
# FASTAPI APPLICATION
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    print()
    print("=" * 64)
    print("  AG-UI Protocol Mock Server v2.4.0 - Demo Mode (FastAPI)")
    print("=" * 64)
    print()
    print("  WebSocket: ws://localhost:8000/ws")
    print("  REST API:  http://localhost:8000")
    print("  API Docs:  http://localhost:8000/docs")
    print()
    yield
    print("\nServer shutting down...")


app = FastAPI(
    title="AGORA Mock Server (AG-UI Protocol)",
    description="Mock server for testing AG-UI Protocol WebSocket and REST API",
    version="2.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Success Criteria:

#### Automated Verification:
- [ ] Server starts without import errors: `cd docs/hai-contract && python mock_server.py`
- [ ] No Python syntax errors: `python -m py_compile docs/hai-contract/mock_server.py`

#### Manual Verification:
- [ ] N/A for this phase (app setup only)

**Implementation Note**: After completing this phase, proceed to Phase 2.

---

## Phase 2: REST Endpoint Migration

### Overview
Convert all REST endpoints from the `process_request` callback to FastAPI route decorators.

### Changes Required:

#### 1. Health and root endpoints
**File**: `docs/hai-contract/mock_server.py`
**Add after**: FastAPI app setup

```python
# ---------------------------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "agora-mock", "protocol": "ag-ui"}


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "AGORA Mock Server",
        "version": "2.4.0",
        "protocol": "AG-UI Protocol v2.4.0",
        "endpoints": {
            "websocket": "/ws",
            "sessions": "/sessions?user_id={user_id}",
            "history": "/sessions/{id}/history?include_tools=true",
            "users": "/users",
            "currentUser": "/users/me",
        },
    }
```

#### 2. Session endpoints
**File**: `docs/hai-contract/mock_server.py`

```python
# ---------------------------------------------------------------------------
# SESSION ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/sessions")
async def list_sessions(
    user_id: str = Query(..., description="User/inspector persona ID"),
):
    """List all sessions for a user, ordered by last activity."""
    user_sessions = [
        session for session in MOCK_SESSIONS.values()
        if session["userId"] == user_id
    ]
    user_sessions.sort(key=lambda s: s["lastActivity"], reverse=True)

    log_event("send", "HTTP", f"GET /sessions?user_id={user_id} -> {len(user_sessions)} sessions")

    return {
        "success": True,
        "sessions": user_sessions,
        "totalCount": len(user_sessions),
    }


@app.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    include_tools: bool = Query(False, description="Include tool call messages"),
):
    """Get conversation history for a session."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    history = get_mock_history(session_id, include_tools)

    log_event("send", "HTTP", f"GET /sessions/{session_id}/history -> {len(history)} messages")

    return {
        "success": True,
        "threadId": session_id,
        "history": history,
        "messageCount": len(history),
    }


@app.get("/sessions/{session_id}/metadata")
async def get_session_metadata(session_id: str):
    """Get session metadata by ID."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    log_event("send", "HTTP", f"GET /sessions/{session_id}/metadata")

    return {
        "success": True,
        "session": MOCK_SESSIONS[session_id],
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    del MOCK_SESSIONS[session_id]

    log_event("send", "HTTP", f"DELETE /sessions/{session_id}")

    return {
        "success": True,
        "message": "Session deleted",
    }
```

#### 3. User endpoints
**File**: `docs/hai-contract/mock_server.py`

```python
# ---------------------------------------------------------------------------
# USER ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/users/me")
async def get_current_user():
    """Get current user profile."""
    if CURRENT_USER_ID not in MOCK_USERS:
        raise HTTPException(status_code=401, detail="User not found")

    user = MOCK_USERS[CURRENT_USER_ID]
    log_event("send", "HTTP", f"GET /users/me -> {user['name']}")

    return user


@app.put("/users/me/preferences")
async def update_current_user_preferences(request: UpdatePreferencesRequest):
    """Update current user's preferences."""
    if CURRENT_USER_ID not in MOCK_USERS:
        raise HTTPException(status_code=401, detail="User not found")

    user = MOCK_USERS[CURRENT_USER_ID]

    if "preferences" not in user:
        user["preferences"] = {}

    # Update only provided fields
    if request.theme is not None:
        user["preferences"]["theme"] = request.theme
    if request.notifications_enabled is not None:
        user["preferences"]["notifications_enabled"] = request.notifications_enabled
    if request.default_agent_id is not None:
        user["preferences"]["default_agent_id"] = request.default_agent_id
    if request.language is not None:
        user["preferences"]["language"] = request.language

    log_event("send", "HTTP", "PUT /users/me/preferences")

    return {
        "success": True,
        "preferences": user["preferences"],
    }


@app.post("/users", status_code=201)
async def create_user(request: CreateUserRequest):
    """Create a new user."""
    # Check email uniqueness
    for existing_user in MOCK_USERS.values():
        if existing_user["email"] == request.email:
            raise HTTPException(status_code=409, detail="Email already exists")

    # Create new user
    new_user_id = str(uuid.uuid4())
    now = datetime.now()
    new_user = {
        "id": new_user_id,
        "email": request.email,
        "name": request.name,
        "preferences": {
            "theme": "system",
            "notifications_enabled": True,
            "default_agent_id": "general-agent",
            "language": "nl-NL",
        },
        "createdAt": now.isoformat() + "Z",
        "lastActivity": now.isoformat() + "Z",
    }
    MOCK_USERS[new_user_id] = new_user

    log_event("send", "HTTP", f"POST /users -> created {new_user['email']}")

    return {
        "success": True,
        "user": new_user,
    }


@app.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=100, description="Max users to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List all users, ordered by creation date."""
    all_users = list(MOCK_USERS.values())
    all_users.sort(key=lambda u: u["createdAt"], reverse=True)

    paginated_users = all_users[offset:offset + limit]

    log_event("send", "HTTP", f"GET /users -> {len(paginated_users)} of {len(all_users)} users")

    return {
        "success": True,
        "users": paginated_users,
        "totalCount": len(all_users),
    }


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user profile by ID."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")

    log_event("send", "HTTP", f"GET /users/{user_id}")

    return {
        "success": True,
        "user": MOCK_USERS[user_id],
    }


@app.put("/users/{user_id}")
async def update_user(user_id: str, request: UpdateUserRequest):
    """Update user profile."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")

    user = MOCK_USERS[user_id]

    if request.name is not None:
        user["name"] = request.name

    if request.preferences is not None:
        if "preferences" not in user:
            user["preferences"] = {}
        for key in ["theme", "notifications_enabled", "default_agent_id", "language"]:
            if key in request.preferences:
                user["preferences"][key] = request.preferences[key]

    log_event("send", "HTTP", f"PUT /users/{user_id}")

    return {
        "success": True,
        "user": user,
    }


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """Delete a user and associated sessions."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")

    # Find legacy userId mapping
    legacy_user_id = None
    for legacy_id, uuid_id in USER_ID_MAP.items():
        if uuid_id == user_id:
            legacy_user_id = legacy_id
            break

    # Delete associated sessions
    sessions_to_delete = [
        session_id for session_id, session in MOCK_SESSIONS.items()
        if session["userId"] == legacy_user_id or session["userId"] == user_id
    ]

    for session_id in sessions_to_delete:
        del MOCK_SESSIONS[session_id]

    del MOCK_USERS[user_id]

    log_event("send", "HTTP", f"DELETE /users/{user_id} -> {len(sessions_to_delete)} sessions deleted")

    return {
        "success": True,
        "message": "User and associated sessions deleted",
        "deletedSessionsCount": len(sessions_to_delete),
    }
```

#### 4. Mock documents endpoint
**File**: `docs/hai-contract/mock_server.py`

```python
# ---------------------------------------------------------------------------
# MOCK DOCUMENTS (for report download testing)
# ---------------------------------------------------------------------------

@app.get("/mock_documents/{filename}")
async def get_mock_document(filename: str):
    """Serve mock document files (report.json, report.pdf)."""
    allowed_files = {"report.json", "report.pdf"}

    if filename not in allowed_files:
        raise HTTPException(status_code=404, detail="File not found")

    mock_docs_dir = Path(__file__).parent / "mock_documents"
    file_path = mock_docs_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = "application/json" if filename.endswith(".json") else "application/pdf"

    log_event("send", "HTTP", f"GET /mock_documents/{filename}")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )
```

### Success Criteria:

#### Automated Verification:
- [ ] All REST endpoints respond correctly:
  ```bash
  curl http://localhost:8000/health
  curl http://localhost:8000/
  curl http://localhost:8000/sessions?user_id=koen
  curl http://localhost:8000/sessions/session-koen-bella-rosa/history
  curl http://localhost:8000/sessions/session-koen-bella-rosa/metadata
  curl http://localhost:8000/users/me
  curl http://localhost:8000/users
  curl -X PUT http://localhost:8000/users/me/preferences -H "Content-Type: application/json" -d '{"theme": "dark"}'
  curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d '{"email": "test@test.nl", "name": "Test"}'
  ```

#### Manual Verification:
- [ ] PUT `/users/me/preferences` with JSON body correctly updates preferences
- [ ] POST `/users` with JSON body creates new user

**Implementation Note**: After completing this phase, proceed to Phase 3.

---

## Phase 3: WebSocket Endpoint Migration

### Overview
Convert the WebSocket handling from `websockets.serve()` to FastAPI WebSocket decorator while preserving all AG-UI Protocol event handling.

### Changes Required:

#### 1. WebSocket endpoint
**File**: `docs/hai-contract/mock_server.py`
**Add after**: REST endpoints

```python
# ---------------------------------------------------------------------------
# WEBSOCKET ENDPOINT
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for AG-UI protocol communication."""
    await websocket.accept()

    print(f"\n{'='*60}")
    print("Client connected")
    print(f"{'='*60}")

    state = ConversationState()

    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
                data = json.loads(raw_message)
                event_type = data.get("type", "RunAgentInput")
                log_event("recv", event_type)

                if data.get("type") == "CUSTOM":
                    name = data.get("name", "")
                    if name == "agora:tool_approval_response":
                        await handle_approval_response_ws(websocket, data, state)
                        continue
                    print(f"  Unknown custom event: {name}")
                    continue

                if "threadId" in data or "thread_id" in data:
                    await handle_run_input_ws(websocket, data, state)

            except WebSocketDisconnect:
                print("\nClient disconnected")
                print(f"{'='*60}\n")
                break
            except json.JSONDecodeError as e:
                print(f"  Invalid JSON: {e}")
                continue

    except Exception as e:
        print(f"WebSocket error: {e}")
```

#### 2. Adapt WebSocket helper functions
**File**: `docs/hai-contract/mock_server.py`

The existing helper functions (`send_event`, `send_step`, `send_tool_call`, `stream_response`, etc.) use the old `websocket.send()` interface. We need to create wrapper versions that use FastAPI's `websocket.send_text()`:

```python
async def send_event_ws(websocket: WebSocket, event: dict, detail: str = "") -> None:
    """Send an event over WebSocket (FastAPI version)."""
    log_event("send", event.get("type", "unknown"), detail)
    await websocket.send_text(json.dumps(event))
```

Then update all the handler functions to use the new wrapper. The cleanest approach is to:
1. Rename all existing `websocket` parameter functions to accept a generic send function
2. Create thin wrappers for both old and new interfaces

**Alternative (simpler)**: Since we're completely replacing the websockets library, we can simply:
1. Change `await websocket.send(json.dumps(event))` to `await websocket.send_text(json.dumps(event))` in `send_event`
2. Update type hints from `websockets.WebSocketServerProtocol` to `WebSocket`

Update `send_event` (line 396-399):
```python
async def send_event(websocket: WebSocket, event: dict, detail: str = "") -> None:
    """Send an event over WebSocket and log it."""
    log_event("send", event.get("type", "unknown"), detail)
    await websocket.send_text(json.dumps(event))
```

Update `handle_connection` to `handle_run_input_ws` and `handle_approval_response_ws`:
```python
async def handle_run_input_ws(websocket: WebSocket, data: dict, state: ConversationState) -> None:
    """Handle a RunAgentInput (FastAPI WebSocket version)."""
    # Same logic as handle_run_input, using websocket.send_text
    await handle_run_input(websocket, data, state)


async def handle_approval_response_ws(websocket: WebSocket, data: dict, state: ConversationState) -> None:
    """Handle approval response (FastAPI WebSocket version)."""
    await handle_approval_response(websocket, data, state)
```

#### 3. Update main function
**File**: `docs/hai-contract/mock_server.py`
**Replace**: Lines 1518-1603

```python
def main():
    """Start the mock server."""
    print()
    print("REST API Endpoints:")
    print()
    print("  Sessions:")
    print("    GET  /sessions?user_id={user_id}       - List sessions")
    print("    GET  /sessions/{id}/history            - Get conversation history")
    print("    GET  /sessions/{id}/metadata           - Get session metadata")
    print("    DELETE /sessions/{id}                  - Delete session")
    print()
    print("  Users:")
    print("    GET  /users/me                         - Get current user")
    print("    PUT  /users/me/preferences             - Update preferences")
    print("    POST /users                            - Create new user")
    print("    GET  /users                            - List all users")
    print("    GET  /users/{id}                       - Get user by ID")
    print("    PUT  /users/{id}                       - Update user")
    print("    DELETE /users/{id}                     - Delete user")
    print()
    print("Mock Data (for testing):")
    print("  Sessions:")
    print("    - koen: 2 sessions (Bella Rosa, Hotel Sunset)")
    print("    - fatima: 1 session (Bakkerij)")
    print("    - jan: 1 session (Supermarkt)")
    print("  Users:")
    print("    - Koen van den Berg (koen.vandenberg@nvwa.nl)")
    print("    - Fatima El-Amrani (fatima.el-amrani@nvwa.nl)")
    print("    - Jan de Vries (jan.devries@nvwa.nl)")
    print()
    print("Test the REST API:")
    print("  curl http://localhost:8000/sessions?user_id=koen")
    print("  curl http://localhost:8000/users/me")
    print("  curl http://localhost:8000/users")
    print()
    print("-" * 64)
    print()
    print(f"Demo Scenario: Inspecteur Koen - Restaurant Bella Rosa")
    print()
    print("Agents:")
    print(f"  - {Agents.GENERAL}")
    print(f"  - {Agents.HISTORY}")
    print(f"  - {Agents.REGULATION}")
    print(f"  - {Agents.REPORTING}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
```

### Success Criteria:

#### Automated Verification:
- [ ] Server starts without errors: `python docs/hai-contract/mock_server.py`
- [ ] WebSocket connection test using websocat or similar tool

#### Manual Verification:
- [ ] HAI frontend connects and displays agents correctly
- [ ] Demo scenario 1 works: "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854"
- [ ] Agent handoffs display correctly in UI
- [ ] Tool approval flow works for report generation

**Implementation Note**: After completing this phase, verify all automated criteria pass before manual testing.

---

## Phase 4: Cleanup and Final Testing

### Overview
Remove old websockets code, clean up the file, and perform comprehensive testing.

### Changes Required:

#### 1. Remove old imports
**File**: `docs/hai-contract/mock_server.py`

Remove:
```python
import websockets
from websockets.http11 import Response
```

#### 2. Remove process_request function
**File**: `docs/hai-contract/mock_server.py`

Delete the entire `process_request` function (lines 1089-1515 in current file).

#### 3. Remove old handle_connection function
The old `handle_connection` function is replaced by `websocket_endpoint`.

#### 4. Update dependencies
Create or update `docs/hai-contract/requirements.txt`:
```
fastapi>=0.115.0
uvicorn>=0.32.0
```

Remove websockets from any requirements if listed.

### Success Criteria:

#### Automated Verification:
- [x] Python syntax check passes: `python -m py_compile docs/hai-contract/mock_server.py`
- [x] Server starts: `cd docs/hai-contract && python mock_server.py`
- [x] Health check: `curl http://localhost:8000/health` returns `{"status": "healthy"}`
- [x] Session list: `curl http://localhost:8000/sessions?user_id=koen` returns 2 sessions
- [x] User list: `curl http://localhost:8000/users` returns 3 users
- [x] PUT preferences works: `curl -X PUT http://localhost:8000/users/me/preferences -H "Content-Type: application/json" -d '{"theme":"dark"}' | jq .preferences.theme` returns "dark"
- [x] POST user works: `curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d '{"email":"new@test.nl","name":"New User"}' | jq .success` returns true

#### Manual Verification:
- [ ] HAI frontend at localhost:3000 connects to mock server
- [ ] Chat interface loads and displays agent selector
- [ ] Demo scenario completes end-to-end:
  1. "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854" -> Shows company info and violation
  2. "Ik zie een geopende ton met rauwe vis op kamertemperatuur" -> Shows regulation analysis
  3. "Genereer rapport" -> Shows approval dialog, approval works
- [ ] Session history loads in sidebar
- [ ] User preferences persist (theme change reflects in UI)

---

## Testing Strategy

### Unit Tests:
No unit tests needed for mock server (it is the test fixture itself).

### Integration Tests:
Run all existing curl commands from current mock server documentation.

### Manual Testing Steps:
1. Start mock server: `cd docs/hai-contract && python mock_server.py`
2. Start HAI frontend: `cd HAI && pnpm run dev`
3. Open http://localhost:3000
4. Complete full demo scenario as Koen
5. Test PUT preferences via curl to verify body parsing works

## Performance Considerations

FastAPI with uvicorn is significantly faster than the websockets library for HTTP handling. No performance concerns expected.

## Migration Notes

This is a drop-in replacement. The API contract is unchanged, so:
- HAI frontend requires no changes
- Any integration tests should continue to work
- curl examples in documentation remain valid

## References

- Research document: `thoughts/shared/research/2026-01-12-websocket-rest-same-port-best-practices.md`
- Production server pattern: `server-langgraph/src/agora_langgraph/api/server.py`
- Production server pattern: `server-openai/src/agora_openai/api/server.py`
- Current mock server: `docs/hai-contract/mock_server.py`
