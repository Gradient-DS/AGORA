---
date: 2025-01-15T14:30:00+01:00
researcher: Claude
git_commit: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
branch: main
repository: AGORA
topic: "Session Names CRUD Operations - Database Storage and API Impact Analysis"
tags: [research, sessions, crud, api, database, server-openai, server-langgraph, bug-analysis, llm-titles]
status: complete
last_updated: 2025-01-15
last_updated_by: Claude
last_updated_note: "Added follow-up research for session context bug and LLM title generation"
---

# Research: Session Names CRUD Operations

**Date**: 2025-01-15T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
**Branch**: main
**Repository**: AGORA

## Research Question

Can we store session names in the database and expose CRUD operations in the API for session names? What is the impact on the mock server, documentation, and both backend implementations?

## Summary

**Yes, session names can be stored and exposed via CRUD operations.** The database schema already has a `title` field that is currently auto-generated from the first message. Adding rename capability requires:

1. **Database**: No schema changes needed - `title` column exists
2. **Backend Code**: Add `update_session_title()` method to `SessionMetadataManager`
3. **API**: Add `PUT /sessions/{session_id}` endpoint to both backends
4. **Mock Server**: Add corresponding PUT endpoint
5. **AG-UI Protocol**: Update AsyncAPI spec with new endpoint definition

The change is straightforward because the infrastructure already exists - we're just exposing existing data for modification.

## Detailed Findings

### Current Session Database Schema

Both `server-openai` and `server-langgraph` use identical schemas in their `SessionMetadataManager`:

```sql
CREATE TABLE IF NOT EXISTS session_metadata (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,              -- ← Already exists, auto-generated
    first_message_preview TEXT,
    message_count INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    last_activity TEXT DEFAULT (datetime('now'))
)
```

**Key Insight**: The `title` field already exists and stores session names. Currently, it's auto-generated from the first message (truncated to 100 characters at word boundary).

### Current API Endpoints

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/sessions` | ✅ Exists | List sessions for user |
| GET | `/sessions/{id}/metadata` | ✅ Exists | Get session metadata |
| GET | `/sessions/{id}/history` | ✅ Exists | Get conversation history |
| DELETE | `/sessions/{id}` | ✅ Exists | Delete session |
| PUT | `/sessions/{id}` | ❌ Missing | **Update session (rename)** |

### Auto-Generated Title Logic

Both backends generate titles identically:

**server-openai**: `src/agora_openai/adapters/session_metadata.py:298-326`
**server-langgraph**: `src/agora_langgraph/adapters/session_metadata.py:280-308`

```python
def _generate_title(self, first_message: str) -> str:
    if not first_message:
        return "New Conversation"
    message = " ".join(first_message.split())
    if len(message) <= 100:
        return message
    truncated = message[:100]
    last_space = truncated.rfind(" ")
    if last_space > 50:
        truncated = truncated[:last_space]
    return truncated + "..."
```

## Implementation Requirements

### 1. SessionMetadataManager Changes

Add method to both backends:

**File**: `src/agora_*/adapters/session_metadata.py`

```python
async def update_session_title(
    self, session_id: str, title: str
) -> dict[str, Any] | None:
    """Update the title of a session.

    Args:
        session_id: Session identifier
        title: New title (max 200 chars recommended)

    Returns:
        Updated session metadata or None if not found
    """
    if not self._connection:
        raise RuntimeError("Database connection not initialized")

    title = title.strip()[:200]  # Sanitize and limit length

    async with self._connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE session_metadata
            SET title = ?, last_activity = datetime('now')
            WHERE session_id = ?
            """,
            (title, session_id),
        )
        await self._connection.commit()

        if cursor.rowcount == 0:
            return None

    return await self.get_session(session_id)
```

### 2. API Endpoint Addition

**Files**:
- `server-openai/src/agora_openai/api/server.py`
- `server-langgraph/src/agora_langgraph/api/server.py`

```python
class UpdateSessionRequest(BaseModel):
    """Request body for updating a session."""
    title: str | None = Field(None, description="New session title", max_length=200)

@app.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
) -> dict[str, Any]:
    """Update session metadata (e.g., rename session)."""
    session_metadata = request.app.state.session_metadata

    if request.title is not None:
        updated = await session_metadata.update_session_title(
            session_id, request.title
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True, "session": updated}

    raise HTTPException(status_code=400, detail="No update fields provided")
```

### 3. Mock Server Update

**File**: `docs/hai-contract/mock_server.py`

Add after line 529 (after `delete_session`):

```python
class UpdateSessionRequest(BaseModel):
    """Request body for updating a session."""
    title: str | None = Field(None, description="New session title")

@app.put("/sessions/{session_id}")
async def update_session(session_id: str, request: UpdateSessionRequest):
    """Update session metadata (e.g., rename)."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.title is not None:
        MOCK_SESSIONS[session_id]["title"] = request.title[:200]
        MOCK_SESSIONS[session_id]["lastActivity"] = datetime.now().isoformat() + "Z"

    log_event("send", "HTTP", f"PUT /sessions/{session_id}")
    return {"success": True, "session": MOCK_SESSIONS[session_id]}
```

Also update the docstring at lines 28-30:

```python
#     REST API - Sessions:
#         GET  /sessions?user_id={user_id}
#         GET  /sessions/{session_id}/history?include_tools=true
#         GET  /sessions/{session_id}/metadata
#         PUT  /sessions/{session_id}                    # NEW
#         DELETE /sessions/{session_id}
```

### 4. AsyncAPI Specification Update

**File**: `docs/hai-contract/asyncapi.yaml`

Add under channels (around line 50):

```yaml
/sessions/{session_id}:
  put:
    operationId: updateSession
    summary: Update session metadata
    description: Update session properties such as title (rename)
    parameters:
      session_id:
        description: Session identifier
        schema:
          type: string
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/UpdateSessionRequest'
    responses:
      '200':
        description: Session updated successfully
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SessionResponse'
      '404':
        description: Session not found
```

Add to components/schemas:

```yaml
UpdateSessionRequest:
  type: object
  properties:
    title:
      type: string
      maxLength: 200
      description: New session title

SessionResponse:
  type: object
  required: [success, session]
  properties:
    success:
      type: boolean
    session:
      $ref: '#/components/schemas/SessionMetadata'
```

### 5. JSON Schema Update

**File**: `docs/hai-contract/schemas/messages.json`

Add after `SessionListResponse` (around line 60):

```json
"UpdateSessionRequest": {
  "type": "object",
  "properties": {
    "title": {
      "type": ["string", "null"],
      "maxLength": 200,
      "description": "New session title"
    }
  }
},
"SessionResponse": {
  "type": "object",
  "required": ["success", "session"],
  "properties": {
    "success": { "type": "boolean" },
    "session": { "$ref": "#/definitions/SessionMetadata" }
  }
}
```

## Code References

### Existing Session Infrastructure

| Component | File | Lines | Description |
|-----------|------|-------|-------------|
| Schema | `server-openai/.../session_metadata.py` | 59-71 | Table definition with `title` column |
| Schema | `server-langgraph/.../session_metadata.py` | 59-78 | Identical table definition |
| Title gen | `server-openai/.../session_metadata.py` | 298-326 | Auto-title from first message |
| Title gen | `server-langgraph/.../session_metadata.py` | 280-308 | Identical auto-title logic |
| List API | `server-openai/.../server.py` | 183-202 | GET /sessions endpoint |
| List API | `server-langgraph/.../server.py` | 181-200 | GET /sessions endpoint |
| Delete API | `server-openai/.../server.py` | 221-238 | DELETE /sessions endpoint |
| Delete API | `server-langgraph/.../server.py` | 219-236 | DELETE /sessions endpoint |
| Mock list | `docs/hai-contract/mock_server.py` | 481-497 | GET /sessions mock |
| Mock delete | `docs/hai-contract/mock_server.py` | 522-529 | DELETE /sessions mock |

### Session Metadata Fields

From `docs/hai-contract/schemas/messages.json:7-44`:

| Field | Type | Required | Editable |
|-------|------|----------|----------|
| `sessionId` | string | Yes | No (PK) |
| `userId` | string | Yes | No (ownership) |
| `title` | string | Yes | **Yes (proposed)** |
| `firstMessagePreview` | string | No | No (auto) |
| `messageCount` | integer | Yes | No (auto) |
| `createdAt` | date-time | Yes | No (auto) |
| `lastActivity` | date-time | Yes | Auto-updated |

## Architecture Insights

### Design Decision: Single Editable Field

Only `title` should be user-editable. Other fields are either:
- **Immutable identifiers**: `sessionId`, `userId`
- **Auto-maintained counters**: `messageCount`
- **System timestamps**: `createdAt`, `lastActivity`
- **Derived content**: `firstMessagePreview`

### Consistency Requirement

Per `CLAUDE.md`: "API changes must be implemented identically in both server-openai and server-langgraph". The implementation above maintains this requirement.

### Frontend Integration

The HAI frontend will need to:
1. Add rename UI (inline edit or modal)
2. Call `PUT /sessions/{id}` with `{ title: "new name" }`
3. Update local state on success

## Open Questions

1. **Title validation**: Should we enforce minimum length or disallow empty titles?
2. **Conflict handling**: What if user renames to same title as another session?
3. **Audit logging**: Should title changes be logged for compliance?
4. **Undo capability**: Should we preserve `original_title` for reverting?

## Recommended Implementation Order

1. Add `update_session_title()` to `SessionMetadataManager` in both backends
2. Add `PUT /sessions/{session_id}` endpoint to both backends
3. Add endpoint to mock server
4. Update AsyncAPI spec and JSON schemas
5. Update HAI frontend to use new endpoint

---

## Follow-up Research (2025-01-15)

### Issue 1: Session Context Not Loading When Selecting Old Sessions

#### Problem Description

When selecting an old session from the sidebar, a new session appears to be created without the context from the previous conversation continuing the chat.

#### Root Cause Analysis

The frontend and backend session handling is **correctly implemented**. The context loading mechanism works as follows:

**Frontend Flow:**
1. User clicks session in `ConversationSidebar.tsx:49` → `switchToSession(sessionId)`
2. `clearMessages()` and `clearToolCalls()` clear current UI state (lines 45-46)
3. `App.tsx:74-103` useEffect detects session change and loads history via HTTP
4. When user sends a new message, `session.id` is sent as `threadId` in WebSocket

**Backend Flow:**
1. `threadId` extracted from `RunAgentInput` at `orchestrator.py:136`
2. LangGraph config created: `{"configurable": {"thread_id": thread_id}}` at line 199
3. `AsyncSqliteSaver` checkpointer automatically loads existing state for that thread_id
4. Agent receives full message history via `state["messages"]` (agents.py:86)

**The Bug is NOT in the core session handling.** Possible causes:

#### Potential Bug Locations

1. **Server Restart Clears In-Memory Cache (server-openai only)**

   File: `server-openai/src/agora_openai/core/agent_runner.py:139-151`
   ```python
   self.sessions: dict[str, SQLiteSession] = {}  # In-memory cache

   def get_or_create_session(self, session_id: str) -> SQLiteSession:
       if session_id not in self.sessions:
           self.sessions[session_id] = SQLiteSession(...)  # Creates new object
   ```

   If the server restarts, the in-memory cache is empty. A new `SQLiteSession` object is created, but **it should still load existing data from SQLite**. If this isn't happening, the bug is in the OpenAI Agents SDK's `SQLiteSession` initialization.

2. **Frontend History Load Condition**

   File: `HAI/src/App.tsx:82-86`
   ```typescript
   if (messages.length > 0) {
     loadedHistoryForSession.current = session.id;
     return;  // Skips loading if messages exist
   }
   ```

   If `clearMessages()` doesn't complete before this check runs, history won't load.

3. **WebSocket Sends Only Current Message**

   File: `HAI/src/lib/websocket/client.ts:115`
   ```typescript
   messages: [{ role: 'user', content }],  // Only current message sent
   ```

   This is **by design** - the backend is supposed to load history from its persistence layer. But if the backend isn't doing this, the LLM only sees the current message.

4. **LangGraph Checkpointer Thread ID Mismatch**

   The `thread_id` used for saving checkpoints MUST match exactly when loading. Check if there's any transformation or prefix being added inconsistently.

#### Debugging Steps

1. **Check if history is loading in frontend:**
   ```typescript
   // In App.tsx:92, add logging:
   console.log('Loading history for session:', session.id);
   const { messages: historyMessages } = await fetchSessionHistory(session.id);
   console.log('Loaded messages:', historyMessages.length);
   ```

2. **Check if backend receives correct threadId:**
   ```python
   # In orchestrator.py:136, add logging:
   log.info(f"Processing message for thread_id: {thread_id}")
   ```

3. **Check if checkpointer has state:**
   ```python
   # In orchestrator.py, after line 199:
   state = await self.graph.aget_state(config)
   log.info(f"Existing state for {thread_id}: {len(state.values.get('messages', []))} messages")
   ```

4. **Verify SQLite has data:**
   ```bash
   sqlite3 sessions.db "SELECT session_id, message_count FROM session_metadata;"
   ```

#### Most Likely Cause

Based on the code analysis, the most likely cause is **the checkpointer state not being persisted or loaded correctly**. The LangGraph `AsyncSqliteSaver` should automatically handle this, but there may be:

- A race condition where the checkpoint isn't committed before the server processes the next request
- The checkpoint table structure doesn't match what the code expects
- Session metadata exists but conversation state doesn't (two separate storage systems)

**Recommendation:** Add debug logging to verify the checkpoint is being read on session resume.

---

### Issue 2: LLM-Based Title Generation

#### Current Implementation

Both backends use simple string truncation:

```python
# server-openai/src/agora_openai/adapters/session_metadata.py:298-326
# server-langgraph/src/agora_langgraph/adapters/session_metadata.py:280-308

def _generate_title(self, first_message: str) -> str:
    if not first_message:
        return "New Conversation"
    message = " ".join(first_message.split())
    if len(message) <= 100:
        return message
    truncated = message[:100]
    last_space = truncated.rfind(" ")
    if last_space > 50:
        truncated = truncated[:last_space]
    return truncated + "..."
```

#### Proposed LLM-Based Implementation

##### Configuration Access

Both backends have LLM configuration available:

**server-openai** (`config.py:19-46`):
```python
settings = get_settings()
api_key = settings.openai_api_key.get_secret_value()
model = settings.openai_model  # default: "gpt-4o"
```

**server-langgraph** (`config.py:18-56`):
```python
settings = get_settings()
api_key = settings.openai_api_key.get_secret_value()
model = settings.openai_model  # default: "gpt-4o"
base_url = settings.openai_base_url  # supports OpenAI-compatible APIs
```

##### Implementation for server-openai

**File**: `server-openai/src/agora_openai/adapters/session_metadata.py`

```python
import logging
from openai import AsyncOpenAI

log = logging.getLogger(__name__)

TITLE_GENERATION_PROMPT = """Generate a concise, descriptive title (3-8 words) for a conversation that starts with this message.
The title should capture the main topic or intent.
Do not use quotes or punctuation at the end.
Respond with only the title, nothing else.

User message: {message}"""

async def _generate_title_with_llm(
    self, first_message: str, api_key: str, model: str = "gpt-4o-mini"
) -> str:
    """Generate a title using an LLM.

    Args:
        first_message: The first user message
        api_key: OpenAI API key
        model: Model to use (default: gpt-4o-mini for speed/cost)

    Returns:
        Generated title or fallback to truncation
    """
    if not first_message:
        return "New Conversation"

    try:
        client = AsyncOpenAI(api_key=api_key)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": TITLE_GENERATION_PROMPT.format(
                        message=first_message[:500]  # Limit input length
                    ),
                }
            ],
            max_tokens=50,
            temperature=0.3,  # Low temperature for consistency
        )

        title = response.choices[0].message.content.strip()

        # Sanitize: remove quotes, limit length
        title = title.strip('"\'')[:100]

        if title:
            return title

    except Exception as e:
        log.warning(f"LLM title generation failed, falling back to truncation: {e}")

    # Fallback to original truncation method
    return self._generate_title(first_message)
```

##### Implementation for server-langgraph

**File**: `server-langgraph/src/agora_langgraph/adapters/session_metadata.py`

```python
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

log = logging.getLogger(__name__)

TITLE_GENERATION_PROMPT = """Generate a concise, descriptive title (3-8 words) for a conversation that starts with this message.
The title should capture the main topic or intent.
Do not use quotes or punctuation at the end.
Respond with only the title, nothing else.

User message: {message}"""

async def _generate_title_with_llm(
    self,
    first_message: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
) -> str:
    """Generate a title using an LLM.

    Args:
        first_message: The first user message
        api_key: OpenAI API key
        model: Model to use (default: gpt-4o-mini for speed/cost)
        base_url: API base URL (for OpenAI-compatible providers)

    Returns:
        Generated title or fallback to truncation
    """
    if not first_message:
        return "New Conversation"

    try:
        llm = ChatOpenAI(
            model=model,
            temperature=0.3,
            max_tokens=50,
            api_key=api_key,
            base_url=base_url,
        )

        prompt = TITLE_GENERATION_PROMPT.format(message=first_message[:500])
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        title = response.content.strip().strip('"\'')[:100]

        if title:
            return title

    except Exception as e:
        log.warning(f"LLM title generation failed, falling back to truncation: {e}")

    # Fallback to original truncation method
    return self._generate_title(first_message)
```

##### Integration with create_or_update_metadata

**Both backends** - modify `create_or_update_metadata()`:

```python
async def create_or_update_metadata(
    self,
    session_id: str,
    user_id: str,
    first_message: str | None = None,
    api_key: str | None = None,  # NEW: Optional API key for LLM
    model: str = "gpt-4o-mini",   # NEW: Model for title generation
) -> None:
    """Create or update session metadata."""
    # ... existing code ...

    # Generate title
    if first_message:
        if api_key:
            title = await self._generate_title_with_llm(
                first_message, api_key, model
            )
        else:
            title = self._generate_title(first_message)
    else:
        title = "New Conversation"

    # ... rest of existing code ...
```

##### Orchestrator Changes

Pass API key from settings to session metadata manager:

**server-openai** - `orchestrator.py:132-140`:
```python
from agora_openai.config import get_settings

settings = get_settings()
await self.session_metadata.create_or_update_metadata(
    session_id=thread_id,
    user_id=user_id,
    first_message=user_content,
    api_key=settings.openai_api_key.get_secret_value(),
    model="gpt-4o-mini",  # Fast/cheap model for titles
)
```

**server-langgraph** - `orchestrator.py:149-164`:
```python
from agora_langgraph.config import get_settings

settings = get_settings()
await self.session_metadata.create_or_update_metadata(
    session_id=thread_id,
    user_id=user_id,
    first_message=user_content,
    api_key=settings.openai_api_key.get_secret_value(),
    model="gpt-4o-mini",
)
```

#### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Model | `gpt-4o-mini` | Fast, cheap, sufficient for title generation |
| Temperature | 0.3 | Low for consistent, predictable titles |
| Max tokens | 50 | Titles should be short |
| Fallback | Truncation | Graceful degradation if LLM fails |
| Input limit | 500 chars | Prevent excessive token usage |

#### Cost Estimate

Using `gpt-4o-mini` at ~$0.15/1M input tokens:
- ~100 tokens per title generation
- 10,000 sessions = ~1M tokens = ~$0.15

#### Alternative: Background Title Generation

For better UX, generate titles asynchronously:

1. Create session with truncated title immediately
2. Fire background task to generate LLM title
3. Update title when LLM completes
4. Frontend polls or receives WebSocket update

This avoids blocking session creation on LLM latency.

---

## Updated Open Questions

1. **Title validation**: Should we enforce minimum length or disallow empty titles?
2. **Conflict handling**: What if user renames to same title as another session?
3. **Audit logging**: Should title changes be logged for compliance?
4. **Undo capability**: Should we preserve `original_title` for reverting?
5. **Session context bug**: Need to add debug logging to identify where context is lost
6. **LLM title timing**: Synchronous (blocks session creation) vs async (better UX)?
7. **Title regeneration**: Should users be able to regenerate title with LLM after initial creation?
