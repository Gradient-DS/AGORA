# Session Name CRUD Operations and LLM Title Generation

## Overview

Implement session renaming capability via a new `PUT /sessions/{session_id}` endpoint and enhance title generation with LLM-based summarization. Changes apply to mock_server.py, server-openai, and server-langgraph.

## Current State Analysis

### Existing Infrastructure

Both backends store session titles in the `title` column of `session_metadata` table, auto-generated from the first message via simple truncation (100 chars at word boundary). The infrastructure exists but titles are not user-editable.

**Key Files:**
- `server-openai/src/agora_openai/adapters/session_metadata.py:298-326` - `_generate_title()` truncation method
- `server-langgraph/src/agora_langgraph/adapters/session_metadata.py:280-308` - identical implementation
- `docs/hai-contract/mock_server.py:110-153` - `MOCK_SESSIONS` initialization

### Missing Components

1. No `update_session_title()` method in SessionMetadataManager
2. No `PUT /sessions/{session_id}` endpoint
3. No LLM-based title generation

## Desired End State

1. Users can rename sessions via `PUT /sessions/{session_id}` with `{"title": "new name"}`
2. New sessions get LLM-generated titles that summarize the conversation intent
3. All three components (mock, server-openai, server-langgraph) support the same API

### Verification

- `curl -X PUT localhost:8000/sessions/{id} -d '{"title":"test"}'` returns updated session
- New session titles are concise summaries (3-8 words) rather than truncated first messages
- Mock server supports the same endpoint for frontend development

## What We're NOT Doing

- Debugging session context loading (explicitly out of scope per user request)
- Background/async title generation (synchronous is acceptable for MVP)
- Title regeneration endpoint (users can manually rename if LLM title is poor)
- Audit logging for title changes
- AsyncAPI/OpenAPI specification updates (documentation-only, not functional)

## Implementation Approach

We'll implement in 4 phases, each independently testable:

1. **SessionMetadataManager update method** - Add `update_session_title()` to both backends
2. **PUT API endpoint** - Add endpoint to both backends
3. **Mock server endpoint** - Add endpoint for frontend testing
4. **LLM title generation** - Replace truncation with LLM summarization

---

## Phase 1: Add update_session_title() to SessionMetadataManager

### Overview

Add a method to update session titles in both backends. This provides the data layer for the API endpoint.

### Changes Required

#### 1. server-openai SessionMetadataManager

**File**: `server-openai/src/agora_openai/adapters/session_metadata.py`

**Location**: After `increment_message_count()` method (after line 296)

```python
async def update_session_title(
    self, session_id: str, title: str
) -> dict[str, Any] | None:
    """Update the title of a session.

    Args:
        session_id: Session identifier
        title: New title (will be sanitized and truncated to 200 chars)

    Returns:
        Updated session metadata dict, or None if session not found
    """
    if not self._connection:
        raise RuntimeError("Database connection not initialized")

    title = title.strip()[:200]
    now = datetime.now(UTC).isoformat()

    async with self._connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE session_metadata
            SET title = ?, last_activity = ?
            WHERE session_id = ?
            """,
            (title, now, session_id),
        )
        await self._connection.commit()

        if cursor.rowcount == 0:
            return None

    return await self.get_session(session_id)
```

#### 2. server-langgraph SessionMetadataManager

**File**: `server-langgraph/src/agora_langgraph/adapters/session_metadata.py`

**Location**: After `increment_message_count()` method (after line 278)

Add identical method as above.

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-openai && mypy src/`
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-openai && ruff check src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`

#### Manual Verification:
- [ ] Method can be called from Python REPL to update a session title

---

## Phase 2: Add PUT /sessions/{session_id} Endpoint

### Overview

Add the REST API endpoint to both backends for session updates (currently just title renaming).

### Changes Required

#### 1. server-openai API Server

**File**: `server-openai/src/agora_openai/api/server.py`

**Location**: After DELETE /sessions/{session_id} (after line 238), before USER MANAGEMENT comment block

```python
class UpdateSessionRequest(BaseModel):
    """Request body for updating session metadata."""

    title: str | None = Field(None, description="New session title", max_length=200)


@app.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
) -> dict[str, Any]:
    """Update session metadata (e.g., rename session)."""
    session_metadata = app.state.session_metadata

    if request.title is not None:
        updated = await session_metadata.update_session_title(
            session_id, request.title
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True, "session": updated}

    raise HTTPException(status_code=400, detail="No update fields provided")
```

#### 2. server-langgraph API Server

**File**: `server-langgraph/src/agora_langgraph/api/server.py`

**Location**: After DELETE /sessions/{session_id} (after line 236), before USER MANAGEMENT comment block

Add identical endpoint as above.

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-openai && mypy src/`
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-openai && ruff check src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Server starts without errors: `cd server-openai && python -m agora_openai.api.server`
- [ ] Server starts without errors: `cd server-langgraph && python -m agora_langgraph.api.server`

#### Manual Verification:
- [ ] `curl -X PUT localhost:8000/sessions/{valid_id} -H "Content-Type: application/json" -d '{"title":"New Title"}'` returns success
- [ ] PUT with non-existent session_id returns 404
- [ ] PUT with empty body returns 400

---

## Phase 3: Add PUT Endpoint to Mock Server

### Overview

Add the PUT endpoint to the mock server so frontend development can proceed independently.

### Changes Required

#### 1. Request Model

**File**: `docs/hai-contract/mock_server.py`

**Location**: After UpdatePreferencesRequest (around line 392)

```python
class UpdateSessionRequest(BaseModel):
    """Request body for updating session metadata."""

    title: str | None = Field(None, description="New session title")
```

#### 2. PUT Endpoint

**File**: `docs/hai-contract/mock_server.py`

**Location**: After DELETE /sessions/{session_id} (after line 529)

```python
@app.put("/sessions/{session_id}")
async def update_session(session_id: str, request: UpdateSessionRequest):
    """Update session metadata (e.g., rename)."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.title is not None:
        MOCK_SESSIONS[session_id]["title"] = request.title.strip()[:200]
        MOCK_SESSIONS[session_id]["lastActivity"] = datetime.now().isoformat() + "Z"

    log_event("send", "HTTP", f"PUT /sessions/{session_id}")
    return {"success": True, "session": MOCK_SESSIONS[session_id]}
```

### Success Criteria

#### Automated Verification:
- [ ] Mock server starts without errors: `cd docs/hai-contract && python mock_server.py`

#### Manual Verification:
- [ ] `curl -X PUT localhost:8000/sessions/session-koen-bella-rosa -H "Content-Type: application/json" -d '{"title":"Renamed Session"}'` returns updated session
- [ ] Session title is updated in subsequent GET requests

---

## Phase 4: LLM-Based Title Generation

### Overview

Replace simple truncation with LLM-generated titles that summarize the user's intent. Use `gpt-4o-mini` for speed and cost efficiency.

### Changes Required

#### 1. server-openai Title Generation

**File**: `server-openai/src/agora_openai/adapters/session_metadata.py`

**Add import at top of file:**
```python
from openai import AsyncOpenAI
```

**Add constant after imports (around line 12):**
```python
TITLE_GENERATION_PROMPT = """Generate a concise, descriptive title (3-8 words) for a conversation that starts with this message.
The title should capture the main topic or intent.
Do not use quotes or punctuation at the end.
Respond with only the title, nothing else.

User message: {message}"""
```

**Add new method after `_generate_title()` (after line 326):**

```python
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
                        message=first_message[:500]
                    ),
                }
            ],
            max_tokens=50,
            temperature=0.3,
        )

        title = response.choices[0].message.content
        if title:
            title = title.strip().strip("\"'")[:100]
            if title:
                return title

    except Exception as e:
        log.warning(f"LLM title generation failed, falling back to truncation: {e}")

    return self._generate_title(first_message)
```

**Update `create_or_update_metadata()` signature and implementation:**

**File**: `server-openai/src/agora_openai/adapters/session_metadata.py`

**Around lines 215-275**, update the method:

```python
async def create_or_update_metadata(
    self,
    session_id: str,
    user_id: str,
    first_message: str | None = None,
    api_key: str | None = None,
) -> None:
    """Create session metadata entry or update if exists.

    On first message for a session:
    - Creates metadata entry with auto-generated title (LLM if api_key provided)
    - Sets first_message_preview from message content

    On subsequent calls:
    - Updates last_activity timestamp

    Args:
        session_id: Session identifier
        user_id: User identifier (inspector persona ID)
        first_message: First user message (for title generation)
        api_key: OpenAI API key (enables LLM title generation)
    """
```

**Replace the title generation logic inside the method** (around line 259-262):

```python
# Generate title
if first_message:
    if api_key:
        title = await self._generate_title_with_llm(first_message, api_key)
    else:
        title = self._generate_title(first_message)
else:
    title = "New Conversation"
```

**Update orchestrator to pass API key:**

**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`

**Around lines 132-140**, update the call:

```python
if self.session_metadata:
    try:
        from agora_openai.config import get_settings
        settings = get_settings()
        await self.session_metadata.create_or_update_metadata(
            session_id=thread_id,
            user_id=user_id,
            first_message=user_content,
            api_key=settings.openai_api_key.get_secret_value(),
        )
    except Exception as e:
        log.warning(f"Failed to update session metadata: {e}")
```

#### 2. server-langgraph Title Generation

**File**: `server-langgraph/src/agora_langgraph/adapters/session_metadata.py`

**Add import at top of file:**
```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
```

**Add constant after imports (around line 12):**
```python
TITLE_GENERATION_PROMPT = """Generate a concise, descriptive title (3-8 words) for a conversation that starts with this message.
The title should capture the main topic or intent.
Do not use quotes or punctuation at the end.
Respond with only the title, nothing else.

User message: {message}"""
```

**Add new method after `_generate_title()` (after line 308):**

```python
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

        title = response.content
        if title:
            title = title.strip().strip("\"'")[:100]
            if title:
                return title

    except Exception as e:
        log.warning(f"LLM title generation failed, falling back to truncation: {e}")

    return self._generate_title(first_message)
```

**Update `create_or_update_metadata()` signature and implementation:**

**File**: `server-langgraph/src/agora_langgraph/adapters/session_metadata.py`

**Around lines 196-257**, update the method signature:

```python
async def create_or_update_metadata(
    self,
    session_id: str,
    user_id: str,
    first_message: str | None = None,
    api_key: str | None = None,
    base_url: str = "https://api.openai.com/v1",
) -> None:
```

**Replace the title generation logic** (around line 240-243):

```python
# Generate title
if first_message:
    if api_key:
        title = await self._generate_title_with_llm(
            first_message, api_key, base_url=base_url
        )
    else:
        title = self._generate_title(first_message)
else:
    title = "New Conversation"
```

**Update orchestrator to pass API key:**

**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

**Around lines 150-164**, update the call:

```python
if self.session_metadata:
    try:
        from agora_langgraph.config import get_settings
        settings = get_settings()
        log.info(f"Creating/updating session metadata: session_id={thread_id}, user_id={user_id}")
        await self.session_metadata.create_or_update_metadata(
            session_id=thread_id,
            user_id=user_id,
            first_message=user_content,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
        )
        log.info(f"Session metadata created/updated successfully for {thread_id}")
    except Exception as e:
        log.warning(f"Failed to update session metadata: {e}")
```

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-openai && mypy src/`
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-openai && ruff check src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Tests pass: `cd server-openai && pytest`
- [ ] Tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Start a new conversation and verify the title is a concise summary (not truncated first message)
- [ ] If OpenAI API is unavailable, title falls back to truncation
- [ ] LLM titles are 3-8 words summarizing the user intent

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation that LLM-generated titles are appropriate before considering the feature complete.

---

## Testing Strategy

### Unit Tests

For each backend, add tests to existing test files or create new ones:

```python
# Test update_session_title
async def test_update_session_title_success():
    manager = SessionMetadataManager(":memory:")
    await manager.initialize()
    # Create a session first
    await manager.create_or_update_metadata("test-id", "user-1", "Hello world")
    # Update title
    result = await manager.update_session_title("test-id", "New Title")
    assert result is not None
    assert result["title"] == "New Title"

async def test_update_session_title_not_found():
    manager = SessionMetadataManager(":memory:")
    await manager.initialize()
    result = await manager.update_session_title("nonexistent", "Title")
    assert result is None

# Test LLM title generation (mocked)
async def test_generate_title_with_llm_fallback():
    # Test that fallback works when LLM fails
    ...
```

### Integration Tests

Test the full flow from API to database:

```python
async def test_put_session_endpoint():
    # Create session via message
    # PUT new title
    # Verify GET returns updated title
    ...
```

### Manual Testing Steps

1. Start the server with a fresh database
2. Send a message to create a new session
3. Verify the session title is LLM-generated (check logs for "LLM title generation")
4. Use `curl -X PUT` to rename the session
5. Verify the title change persists via `GET /sessions`

---

## Performance Considerations

- **LLM latency**: Title generation adds ~200-500ms to first message. Acceptable for MVP since it's a one-time cost per session.
- **Cost**: Using `gpt-4o-mini` at ~$0.15/1M tokens. ~100 tokens per title = ~$0.015 per 1000 sessions.
- **Fallback**: If LLM times out or errors, truncation is used immediately without blocking.

---

## References

- Original research: `thoughts/shared/research/2025-01-15-session-name-crud-operations.md`
- SessionMetadataManager (openai): `server-openai/src/agora_openai/adapters/session_metadata.py:14-439`
- SessionMetadataManager (langgraph): `server-langgraph/src/agora_langgraph/adapters/session_metadata.py:14-309`
- API server (openai): `server-openai/src/agora_openai/api/server.py:183-238`
- API server (langgraph): `server-langgraph/src/agora_langgraph/api/server.py:181-236`
- Mock server: `docs/hai-contract/mock_server.py:476-529`
