# Backend Spoken Text Storage Implementation Plan

## Overview

Store spoken text (TTS-optimized content) in the backend with messages and return it via the session history API, completely replacing the frontend localStorage approach.

## Current State Analysis

### Frontend (localStorage)
- `HAI/src/stores/useMessageStore.ts:17-47` stores spoken content in localStorage under key `agora-spoken-content`
- `replaceMessages()` (line 235) merges localStorage data back into messages on session restore
- Functions: `loadPersistedSpokenContent()`, `persistSpokenContent()`, `clearPersistedSpokenContent()`

### Backend (server-langgraph)
- `graph.py:465-509` - `merge_parallel_outputs()` creates final AIMessage but does NOT store `spoken_text` in `additional_kwargs`
- `orchestrator.py:841-939` - `get_conversation_history()` extracts `agent_id` from `additional_kwargs` but not `spoken_text`
- The spoken text IS generated (`final_spoken`) but not persisted with the message

### Key Discovery
The pattern for storing message metadata already exists - `agent_id` is stored in `AIMessage.additional_kwargs` at `graph.py:506`. We use the same pattern for `spoken_text`.

## Desired End State

1. Spoken text is stored in `AIMessage.additional_kwargs["spoken_text"]` when messages are created
2. History API returns `spoken_text` field for assistant messages
3. Frontend receives spoken text from API, no localStorage dependency
4. localStorage code completely removed from frontend

### Verification
- Load an existing session with spoken text → comparison view shows written/spoken
- Create new message → spoken text persists after page refresh
- No `agora-spoken-content` key in localStorage

## What We're NOT Doing

- Backwards compatibility with old sessions (user explicitly stated they don't care)
- server-openai parity (different architecture, separate ticket if needed)
- Message ID changes (keeping synthetic `history-{sessionId}-{index}` IDs)
- Compression of spoken text

## Implementation Approach

Store `spoken_text` alongside `agent_id` in `additional_kwargs`, following the established pattern. Update API contract and frontend to consume the new field.

---

## Phase 1: Backend - Store Spoken Text with Messages

### Overview
Modify the LangGraph graph to store `final_spoken` in the AIMessage's `additional_kwargs` when merging parallel outputs.

### Changes Required:

#### 1. Graph merge_parallel_outputs
**File**: `server-langgraph/src/agora_langgraph/core/graph.py`

**Changes**: Add `spoken_text` to the AIMessage's `additional_kwargs`

Current code (lines 505-509):
```python
return {
    "messages": [AIMessage(content=written_content)],
    "final_written": written_content,
    "final_spoken": spoken_content,
}
```

Change to:
```python
return {
    "messages": [
        AIMessage(
            content=written_content,
            additional_kwargs={"spoken_text": spoken_content} if spoken_content else {},
        )
    ],
    "final_written": written_content,
    "final_spoken": spoken_content,
}
```

### Success Criteria:

#### Automated Verification:
- [x] Python type checking passes: `cd server-langgraph && mypy src/` (pre-existing errors, none from this change)
- [x] Linting passes: `cd server-langgraph && ruff check src/` (pre-existing errors, none from this change)
- [x] Unit tests pass: `cd server-langgraph && pytest tests/` (all 12 tests pass)

#### Manual Verification:
- [ ] Send a message via WebSocket, then check graph state contains `spoken_text` in the AIMessage's `additional_kwargs`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Backend - Return Spoken Text in History API

### Overview
Modify `get_conversation_history()` to extract and return `spoken_text` from `additional_kwargs`.

### Changes Required:

#### 1. Orchestrator get_conversation_history
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

**Changes**: Extract `spoken_text` from `additional_kwargs` and include in response

In the `elif msg.type == "ai":` block (around line 874), after extracting `agent_id`:

```python
# Extract agent_id from additional_kwargs if present
agent_id = None
spoken_text = None
if hasattr(msg, "additional_kwargs"):
    agent_id = msg.additional_kwargs.get("agent_id")
    spoken_text = msg.additional_kwargs.get("spoken_text")
```

Then when building the history dict (around lines 886, 910, 916), include `spoken_text`:

```python
history.append(
    {
        "role": "assistant",
        "content": str(msg.content),
        "agent_id": agent_id or "",
        "spoken_text": spoken_text,  # ADD THIS (will be None for old messages)
    }
)
```

Apply to all three places where assistant messages are added:
- Line 886-891 (AI with tool calls and content)
- Line 910-914 (replacing previous AI message)
- Line 916-921 (new AI message)

### Success Criteria:

#### Automated Verification:
- [x] Python type checking passes: `cd server-langgraph && mypy src/` (pre-existing errors only)
- [x] Linting passes: `cd server-langgraph && ruff check src/` (pre-existing errors only)
- [x] Unit tests pass: `cd server-langgraph && pytest tests/` (all 12 tests pass)

#### Manual Verification:
- [ ] Call `GET /sessions/{id}/history` → assistant messages include `spoken_text` field
- [ ] Verify `spoken_text` is present for new messages, null/missing for old ones

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: API Contract Updates

### Overview
Update OpenAPI spec, JSON schema, and mock server to document and implement the new `spoken_text` field.

### Changes Required:

#### 1. OpenAPI Specification
**File**: `docs/hai-contract/openapi.yaml`

**Changes**: Add `spoken_text` to `HistoryMessage` schema (around line 819)

```yaml
HistoryMessage:
  type: object
  description: |
    A single message in the conversation history.
    The role field determines the message type and available fields.
  required: [role, content]
  properties:
    role:
      type: string
      enum: [user, assistant, tool_call, tool]
    content:
      type: string
    agent_id:
      type: string
    tool_call_id:
      type: string
    tool_name:
      type: string
    spoken_text:
      type: string
      description: |
        TTS-optimized version of the message content.
        Only present for assistant messages. May be null for historical
        messages created before this feature was implemented.
```

#### 2. JSON Schema
**File**: `docs/hai-contract/schemas/messages.json`

**Changes**: Add `spoken_text` to `HistoryMessage` properties (line 61-87)

```json
"HistoryMessage": {
  "type": "object",
  "description": "A message in conversation history (role determines available fields)",
  "required": ["role", "content"],
  "properties": {
    "role": {
      "type": "string",
      "enum": ["user", "assistant", "tool_call", "tool"]
    },
    "content": {
      "type": "string"
    },
    "agent_id": {
      "type": ["string", "null"]
    },
    "tool_call_id": {
      "type": ["string", "null"]
    },
    "tool_name": {
      "type": ["string", "null"]
    },
    "spoken_text": {
      "type": ["string", "null"],
      "description": "TTS-optimized version of the content (assistant messages only)"
    }
  }
}
```

#### 3. Mock Server
**File**: `docs/hai-contract/mock_server.py`

**Changes**: Add `spoken_text` to mock history responses in `get_mock_history()` (around line 156)

Update assistant messages to include `spoken_text`:

```python
{
    "role": "assistant",
    "content": "Inspectie gestart voor **Restaurant Bella Rosa**.\n\n**Bedrijfsgegevens:**\n- KVK: 92251854\n- Rechtsvorm: Besloten Vennootschap\n- Status: Actief\n\n**Inspectiehistorie:**\n⚠️ Er is 1 openstaande overtreding uit 15 mei 2022.",
    "agent_id": Agents.HISTORY,
    "spoken_text": "Inspectie gestart voor Restaurant Bella Rosa. Bedrijfsgegevens: Kamer van Koophandel nummer 92251854, Rechtsvorm Besloten Vennootschap, Status Actief. Inspectiehistorie: Let op, er is 1 openstaande overtreding uit 15 mei 2022.",
},
```

Apply similar updates to all assistant messages in the mock history.

### Success Criteria:

#### Automated Verification:
- [x] Mock server starts without errors: Python syntax valid
- [x] OpenAPI spec is valid YAML: File readable (1093 lines)
- [x] JSON schema is valid: `python3 -c "import json; json.load(open('...'))"` passes

#### Manual Verification:
- [ ] Mock server returns `spoken_text` in history responses

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 4.

---

## Phase 4: Frontend - Update API Types and Mapping

### Overview
Update the frontend to receive `spoken_text` from the API and map it to `spokenContent`.

### Changes Required:

#### 1. HistoryMessage Interface
**File**: `HAI/src/lib/api/sessions.ts`

**Changes**: Add `spoken_text` to the interface (line 27-33)

```typescript
interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool_call' | 'tool';
  content: string;
  tool_name?: string;
  tool_call_id?: string;
  agent_id?: string;
  spoken_text?: string;  // ADD THIS
}
```

#### 2. fetchSessionHistory Mapping
**File**: `HAI/src/lib/api/sessions.ts`

**Changes**: Map `spoken_text` to `spokenContent` when building ChatMessage (around line 126-136)

```typescript
if (msg.role === 'user' || msg.role === 'assistant') {
  // Regular text messages
  messages.push({
    id: `history-${sessionId}-${messageIndex}`,
    role: msg.role,
    content: msg.content,
    agentId: msg.agent_id,
    spokenContent: msg.spoken_text,  // ADD THIS
    timestamp: new Date(),
    isStreaming: false,
  });
  messageIndex++;
}
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript type checking passes: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Tests pass: `cd HAI && pnpm run test` (27 tests pass)

#### Manual Verification:
- [ ] Load a session → messages have `spokenContent` from API

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 5.

---

## Phase 5: Frontend - Remove localStorage

### Overview
Remove all localStorage-related code for spoken content from the message store.

### Changes Required:

#### 1. Remove localStorage Functions and Constant
**File**: `HAI/src/stores/useMessageStore.ts`

**Changes**: Delete lines 16-47 (the localStorage key and helper functions)

Remove:
```typescript
/** localStorage key for persisted spoken content */
const SPOKEN_CONTENT_STORAGE_KEY = 'agora-spoken-content';

/** Load persisted spoken content from localStorage */
function loadPersistedSpokenContent(): Record<string, string> {
  // ... entire function
}

/** Save spoken content to localStorage */
function persistSpokenContent(messageId: string, content: string): void {
  // ... entire function
}

/** Clear persisted spoken content from localStorage */
function clearPersistedSpokenContent(): void {
  // ... entire function
}
```

#### 2. Remove persistSpokenContent Calls
**File**: `HAI/src/stores/useMessageStore.ts`

**Changes**: Remove calls in `finalizeSpokenMessage` (lines 197-200 and 213-215)

Current code:
```typescript
if (existingMsg.spokenContent) {
  persistSpokenContent(messageId, existingMsg.spokenContent);
}
```

Remove these blocks entirely. The function body becomes:
```typescript
finalizeSpokenMessage: (messageId) => {
  set((state) => {
    const existingMsg = state.messages.find((msg) => msg.id === messageId);
    if (existingMsg) {
      return {
        messages: state.messages.map((msg) =>
          msg.id === messageId ? { ...msg, isSpokenStreaming: false } : msg
        ),
      };
    }
    // Update buffer
    const newBuffers = new Map(state.spokenBuffers);
    const existing = newBuffers.get(messageId);
    if (existing) {
      newBuffers.set(messageId, { ...existing, isStreaming: false });
    }
    return { spokenBuffers: newBuffers };
  });
},
```

#### 3. Remove clearPersistedSpokenContent Call
**File**: `HAI/src/stores/useMessageStore.ts`

**Changes**: Remove call in `clearMessages` (line 231)

Change from:
```typescript
clearMessages: () => {
  clearPersistedSpokenContent();
  set({ messages: [], processingStatus: null, isTyping: false, spokenBuffers: new Map() });
},
```

To:
```typescript
clearMessages: () => {
  set({ messages: [], processingStatus: null, isTyping: false, spokenBuffers: new Map() });
},
```

#### 4. Remove localStorage Merge in replaceMessages
**File**: `HAI/src/stores/useMessageStore.ts`

**Changes**: Simplify `replaceMessages` (lines 235-246)

Change from:
```typescript
replaceMessages: (messages: ChatMessage[]) => {
  // Merge persisted spoken content from localStorage
  const persistedSpoken = loadPersistedSpokenContent();
  const messagesWithSpoken = messages.map((msg) => {
    const spokenContent = persistedSpoken[msg.id];
    if (spokenContent) {
      return { ...msg, spokenContent };
    }
    return msg;
  });
  set({ messages: messagesWithSpoken, processingStatus: null, isTyping: false });
},
```

To:
```typescript
replaceMessages: (messages: ChatMessage[]) => {
  set({ messages, processingStatus: null, isTyping: false, spokenBuffers: new Map() });
},
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript type checking passes: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Tests pass: `cd HAI && pnpm run test` (27 tests pass)
- [x] Build succeeds: `cd HAI && pnpm run build`

#### Manual Verification:
- [ ] Open DevTools → Application → Local Storage → no `agora-spoken-content` key
- [ ] Create new conversation with spoken text → text comparison works
- [ ] Refresh page → spoken text persists (loaded from API)
- [ ] Clear messages → no localStorage errors

**Implementation Note**: This is the final phase. Run full E2E testing after completion.

---

## Testing Strategy

### Unit Tests:
- Add test in `server-langgraph/tests/unit/` to verify `merge_parallel_outputs` stores `spoken_text`
- Add test to verify `get_conversation_history` returns `spoken_text`

### Integration Tests:
- Update `server-langgraph/tests/integration/test_dual_channel_spoken.py` to verify `spoken_text` in history

### Manual Testing Steps:
1. Start backend: `cd server-langgraph && python -m agora_langgraph.api.server`
2. Start frontend: `cd HAI && pnpm run dev`
3. Create new session, send message with spoken text enabled
4. Verify comparison view shows both written and spoken
5. Refresh page
6. Verify spoken text persists after refresh
7. Check localStorage has no `agora-spoken-content` key

## References

- Research document: `thoughts/shared/research/2026-01-28-backend-spoken-text-storage.md`
- Current localStorage implementation: `HAI/src/stores/useMessageStore.ts:17-47`
- Agent ID storage pattern: `server-langgraph/src/agora_langgraph/core/agents.py:194-196`
- Graph merge function: `server-langgraph/src/agora_langgraph/core/graph.py:465-509`
- History retrieval: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:841-939`
