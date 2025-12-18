# Chat History Implementation Plan

## Overview

Add user-based conversation history to AGORA, allowing inspectors to view and resume past conversations. The implementation supports both `server-openai` and `server-langgraph` backends with copied (not shared) implementations.

### Requirements Summary

- **User-specific**: History tied to inspector persona (Koen, Fatima, Jan)
- **UI**: Collapsible sidebar showing past conversations
- **Titles**: Auto-generated from first message (not editable)
- **No search**: Simple chronological list

---

## Phase 1: Backend - Session Metadata Storage

### 1.1 Database Schema (Both Backends)

Create a new `session_metadata` table alongside existing session storage:

```sql
CREATE TABLE IF NOT EXISTS session_metadata (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,              -- Inspector persona ID
    title TEXT NOT NULL,
    first_message_preview TEXT,
    message_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_session_metadata_user_activity
    ON session_metadata (user_id, last_activity DESC);
```

### 1.2 New Files to Create

#### server-openai

**`server-openai/src/agora_openai/adapters/session_metadata.py`**

```python
class SessionMetadataManager:
    """Manages session metadata for conversation history listing."""

    def __init__(self, db_path: str = "sessions.db"):
        self.db_path = db_path
        self._ensure_tables()

    async def list_sessions(self, user_id: str, limit: int = 50, offset: int = 0) -> list[dict]
    async def get_session(self, session_id: str) -> dict | None
    async def delete_session(self, session_id: str) -> bool
    async def create_or_update_metadata(self, session_id: str, user_id: str, first_message: str | None = None) -> None
    async def increment_message_count(self, session_id: str) -> None
```

#### server-langgraph

**`server-langgraph/src/agora_langgraph/adapters/session_metadata.py`**

Same interface as server-openai, using async sqlite (aiosqlite).

### 1.3 Files to Modify

#### server-openai/src/agora_openai/api/server.py

Add three new endpoints:

```python
@app.get("/sessions")
async def list_sessions(user_id: str, limit: int = 50, offset: int = 0):
    """List all sessions for a user, ordered by last activity."""

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session metadata by ID."""

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its data."""
```

#### server-langgraph/src/agora_langgraph/api/server.py

Mirror the same three endpoints.

#### server-openai/src/agora_openai/pipelines/orchestrator.py

Hook metadata updates into `process_message()`:
- On first message: Create metadata entry with title from message
- On every message: Update `last_activity` and increment `message_count`

#### server-langgraph/src/agora_langgraph/pipelines/orchestrator.py

Same hooks as server-openai.

### 1.4 API Response Formats

**`GET /sessions?user_id={user_id}`**
```json
{
  "success": true,
  "sessions": [
    {
      "sessionId": "abc-123",
      "userId": "koen",
      "title": "Inspectie bij Restaurant Bella Rosa",
      "firstMessagePreview": "Start inspectie bij Restaurant...",
      "messageCount": 12,
      "createdAt": "2025-12-01T10:30:00Z",
      "lastActivity": "2025-12-01T11:45:00Z"
    }
  ],
  "totalCount": 42
}
```

**`GET /sessions/{session_id}`**
```json
{
  "success": true,
  "session": { /* same as above */ }
}
```

**`DELETE /sessions/{session_id}`**
```json
{
  "success": true,
  "message": "Session deleted"
}
```

---

## Phase 2: Frontend - State Management

### 2.1 New Files to Create

**`HAI/src/stores/useHistoryStore.ts`**

```typescript
interface HistoryStore {
  sessions: SessionMetadata[];
  isLoading: boolean;
  error: string | null;
  isSidebarOpen: boolean;

  fetchSessions: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  addOrUpdateSession: (session: SessionMetadata) => void;
}
```

**`HAI/src/lib/api/sessions.ts`**

```typescript
export async function fetchSessions(userId: string): Promise<SessionMetadata[]>
export async function deleteSession(sessionId: string): Promise<void>
export async function getSessionHistory(sessionId: string): Promise<ChatMessage[]>
```

### 2.2 Files to Modify

**`HAI/src/stores/useSessionStore.ts`**

- Change from `sessionStorage` to `localStorage` for persistence
- Add `switchToSession(sessionId: string)` method
- Add `startNewSession()` method
- Store `userId` (inspector persona ID) with session

**`HAI/src/stores/useMessageStore.ts`**

- Add `loadFromHistory(messages: ChatMessage[])` method
- Add `replaceMessages(messages: ChatMessage[])` method

**`HAI/src/types/index.ts`**

Add new types:
```typescript
export interface SessionMetadata {
  sessionId: string;
  userId: string;
  title: string;
  firstMessagePreview: string;
  messageCount: number;
  createdAt: Date;
  lastActivity: Date;
}
```

---

## Phase 3: Frontend - UI Components

### 3.1 New Files to Create

**`HAI/src/components/history/ConversationSidebar.tsx`**

- Collapsible sidebar (slides in from left)
- "New Conversation" button at top
- List of `SessionListItem` components
- Shows loading state while fetching

**`HAI/src/components/history/SessionListItem.tsx`**

- Displays title (truncated), message count, relative time
- Click to switch to that conversation
- Delete button (with confirmation)
- Highlight for currently active session

**`HAI/src/components/history/index.ts`**

Export all history components.

### 3.2 Files to Modify

**`HAI/src/components/layout/Header.tsx`**

- Add hamburger menu button to toggle sidebar
- Show current conversation title (truncated)

**`HAI/src/components/layout/MainLayout.tsx`**

- Integrate `ConversationSidebar` component
- Handle sidebar open/close state
- Adjust main content area when sidebar is open

**`HAI/src/App.tsx`**

- Initialize history store on app load
- Fetch sessions when user is selected
- Wire up session switching logic

**`HAI/src/hooks/useWebSocket.ts`**

- Handle session switching (disconnect/reconnect with new threadId)
- Update history store when messages are sent/received

---

## Phase 4: Session Switching Flow

### 4.1 User Clicks Existing Session

1. Close sidebar
2. Save current session state (already persisted on backend)
3. Update `useSessionStore` with new `sessionId`
4. Call `GET /sessions/{sessionId}/history?include_tools=true` to fetch messages AND tool calls
5. Replace messages in `useMessageStore`
6. **Populate `useToolCallStore` with historical tool calls** (NEW)
7. WebSocket continues with same connection (threadId changes on next message)

### 4.1.1 Tool Call History Loading (Implementation Gap Identified)

**Problem**: When loading history, only text messages are displayed. Tool calls that were made during the original conversation are not shown in:
- Chat window (no tool call pills/badges)
- "Onder de Motorkap" debug panel (empty tool call list)

**Root Cause**:
1. Frontend calls `/sessions/{id}/history` without `?include_tools=true`
2. Backend `get_conversation_history()` has `include_tool_calls=False` by default
3. Frontend `fetchSessionHistory()` only maps `role: 'user' | 'assistant' | 'tool'` but doesn't extract tool call metadata
4. `useToolCallStore` is not populated when loading history (only via live WebSocket events)

**Required Changes**:

#### Backend Changes
- Enhance history response to include structured tool call data with:
  - `toolCallId`, `toolName`, `parameters`, `result`, `status`
  - Keep tool calls associated with their parent message

#### Frontend Changes
- **`HAI/src/lib/api/sessions.ts`**:
  - Pass `?include_tools=true` query param
  - Parse tool call data from response
  - Return both messages AND tool calls

- **`HAI/src/stores/useToolCallStore.ts`**:
  - Add `replaceToolCalls(toolCalls: ToolCallInfo[])` method
  - Add `loadFromHistory(toolCalls: ToolCallInfo[])` method

- **`HAI/src/components/history/ConversationSidebar.tsx`**:
  - After loading messages, also populate tool call store
  - Clear tool calls when switching sessions

### 4.2 User Clicks "New Conversation"

1. Close sidebar
2. Generate new session ID
3. Clear `useMessageStore`
4. Update `useSessionStore` with new session
5. Next message creates new thread on backend

### 4.3 User Sends Message (Metadata Update)

1. Message sent via WebSocket with current `threadId`
2. Backend creates/updates `session_metadata` entry
3. On `RUN_FINISHED`, frontend could refresh session list (optional)

---

## Phase 5: Documentation & Mock Server Updates

### 5.1 Update AG-UI Protocol Documentation

**`docs/hai-contract/AG_UI_PROTOCOL.md`**
- Add section documenting Session History REST endpoints
- Include request/response format examples

**`docs/hai-contract/openapi.yaml`**
- Add `GET /sessions` endpoint schema (list sessions for user)
- Add `DELETE /sessions/{session_id}` endpoint schema
- Add `SessionMetadata` schema definition

**`docs/hai-contract/schemas/messages.json`**
- Add `SessionMetadata` JSON Schema definition

### 5.2 Update Mock Server

**`docs/hai-contract/mock_server.py`**
- Add HTTP handlers for session REST endpoints
- Add mock session data (3-5 demo sessions for testing)
- Wire up list, get, and delete operations with in-memory storage

---

## Phase 6: Document Changes

**`CHANGES.md`** - Add summary under History section:
```markdown
## History

- Added session metadata storage for conversation history tracking
- New REST endpoints: `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}`
- Frontend sidebar for browsing and resuming past conversations
- Session switching with message history loading
- Updated AG-UI Protocol documentation and mock server
```

---

## Implementation Order

### Step 1: Backend Session Metadata (server-openai)
1. Create `session_metadata.py` with `SessionMetadataManager`
2. Add `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` endpoints
3. Hook metadata updates into `orchestrator.process_message()`
4. Test with curl/Postman

### Step 2: Backend Session Metadata (server-langgraph)
1. Copy and adapt `session_metadata.py` for async sqlite
2. Add same endpoints to server
3. Hook metadata updates into orchestrator
4. Test with curl/Postman

### Step 3: Frontend API Layer
1. Create `HAI/src/lib/api/sessions.ts`
2. Add `SessionMetadata` type to `types/index.ts`
3. Create `useHistoryStore.ts`

### Step 4: Frontend Store Updates
1. Update `useSessionStore.ts` for localStorage and switching
2. Update `useMessageStore.ts` with history loading

### Step 5: Frontend UI Components
1. Create `ConversationSidebar.tsx`
2. Create `SessionListItem.tsx`
3. Update `Header.tsx` with sidebar toggle
4. Update `MainLayout.tsx` with sidebar integration

### Step 6: Integration & Polish
1. Wire up App.tsx
2. Handle WebSocket reconnection on session switch
3. Add loading states and error handling
4. Test full flow end-to-end

### Step 7: Documentation Updates
1. Update `docs/hai-contract/openapi.yaml` with session endpoints
2. Add `SessionMetadata` schema to `docs/hai-contract/schemas/messages.json`
3. Update `docs/hai-contract/AG_UI_PROTOCOL.md` with history section

### Step 8: Mock Server Updates
1. Add session HTTP handlers to `docs/hai-contract/mock_server.py`
2. Add mock session data for demo/testing
3. Test session endpoints with curl

### Step 9: Document Changes
1. Update `CHANGES.md` with History section summary

---

## Critical Files Summary

### Backend - server-openai
| File | Action |
|------|--------|
| `src/agora_openai/adapters/session_metadata.py` | **CREATE** |
| `src/agora_openai/api/server.py` | Modify - add 3 endpoints |
| `src/agora_openai/pipelines/orchestrator.py` | Modify - hook metadata updates |

### Backend - server-langgraph
| File | Action |
|------|--------|
| `src/agora_langgraph/adapters/session_metadata.py` | **CREATE** |
| `src/agora_langgraph/api/server.py` | Modify - add 3 endpoints |
| `src/agora_langgraph/pipelines/orchestrator.py` | Modify - hook metadata updates |

### Frontend - HAI
| File | Action |
|------|--------|
| `src/stores/useHistoryStore.ts` | **CREATE** |
| `src/lib/api/sessions.ts` | **CREATE** |
| `src/components/history/ConversationSidebar.tsx` | **CREATE** |
| `src/components/history/SessionListItem.tsx` | **CREATE** |
| `src/components/history/index.ts` | **CREATE** |
| `src/types/index.ts` | Modify - add SessionMetadata |
| `src/stores/useSessionStore.ts` | Modify - localStorage + switching |
| `src/stores/useMessageStore.ts` | Modify - history loading |
| `src/components/layout/Header.tsx` | Modify - sidebar toggle |
| `src/components/layout/MainLayout.tsx` | Modify - sidebar integration |
| `src/App.tsx` | Modify - wire up history |
| `src/hooks/useWebSocket.ts` | Modify - session switch handling |

### Documentation
| File | Action |
|------|--------|
| `docs/hai-contract/AG_UI_PROTOCOL.md` | Modify - add history endpoints section |
| `docs/hai-contract/openapi.yaml` | Modify - add session endpoint schemas |
| `docs/hai-contract/schemas/messages.json` | Modify - add SessionMetadata schema |
| `docs/hai-contract/mock_server.py` | Modify - add session HTTP handlers |
| `CHANGES.md` | Modify - add History section summary |

---

## Testing Checklist

### server-langgraph
- [x] Create new conversation - appears in sidebar
- [x] Switch between conversations - messages load correctly
- [x] Switch between conversations - tool calls load correctly (pills in chat)
- [x] Switch between conversations - tool calls appear in "Onder de Motorkap" debug panel
- [x] Tool calls grouped under correct agent (for NEW conversations only)
- [x] Tool call results truncated in debug panel (200 char limit)
- [x] Refresh page - current session and history persists
- [ ] Delete conversation - removed from sidebar and backend
- [ ] Switch inspector persona - shows different conversation history
- [ ] Send message in resumed conversation - continues correctly

### server-openai
- [x] Create new conversation - appears in sidebar
- [x] Switch between conversations - messages load correctly
- [x] Switch between conversations - tool calls load correctly (pills in chat)
- [x] Switch between conversations - tool calls appear in "Onder de Motorkap" debug panel
- [x] Tool calls grouped under correct agent
- [x] Tool call results truncated in debug panel (200 char limit)
- [x] Refresh page - current session and history persists
- [x] **Backend restart - sessions and tool calls persist** (bug fixed 2025-12-17)
- [ ] Delete conversation - removed from sidebar and backend
- [ ] Switch inspector persona - shows different conversation history
- [ ] Send message in resumed conversation - continues correctly

---

## Implementation Status (2025-12-17)

### server-langgraph: COMPLETED

All tool call history features have been implemented for `server-langgraph`.

#### Changes Made

**Backend Changes:**

1. **`server-langgraph/src/agora_langgraph/core/agents.py`**
   - Added `agent_id` to `AIMessage.additional_kwargs` when agents generate responses
   - This allows tracking which agent made which tool call

2. **`server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`**
   - Modified `get_conversation_history()` to include:
     - `tool_call_id` field for correlating tool calls with results
     - `agent_id` field extracted from `additional_kwargs`
   - Both `tool_call` and `tool` role messages now include these fields

**Frontend Changes:**

3. **`HAI/src/lib/api/sessions.ts`**
   - Added `?include_tools=true` query parameter
   - Updated `HistoryMessage` interface with `tool_call_id` and `agent_id` fields
   - Changed return type to `FetchHistoryResult { messages, toolCalls }`
   - Two-pass parsing: first collects tool results, then builds messages and tool calls
   - Passes `agentId` to both `ChatMessage` and `ToolCallInfo` objects

4. **`HAI/src/stores/useToolCallStore.ts`**
   - Added `replaceToolCalls(toolCalls: ToolCallInfo[])` method

5. **`HAI/src/components/history/ConversationSidebar.tsx`**
   - Added `clearToolCalls()` and `replaceToolCalls()` hooks
   - Updated `handleSelectSession()` to clear and populate tool call store

6. **`HAI/src/components/chat/ToolCallCard.tsx`**
   - Added truncation for long tool call results (200 char limit + `line-clamp-3`)

7. **`HAI/src/App.tsx`**
   - Added `useEffect` to load session history on page refresh
   - Uses `useRef` to track which session history has been loaded (prevents duplicate loads)
   - Centralized history loading for both page refresh AND sidebar session switching

8. **`HAI/src/components/history/ConversationSidebar.tsx`** (simplified)
   - Removed direct history fetching - now handled centrally by App.tsx
   - `handleSelectSession` just clears state and switches session

#### API Response Format (History Endpoint)

```json
GET /sessions/{session_id}/history?include_tools=true

{
  "success": true,
  "threadId": "session-123",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "agent_id": "general-agent"},
    {"role": "tool_call", "tool_call_id": "tc-1", "tool_name": "search", "content": "{...}", "agent_id": "regulation-agent"},
    {"role": "tool", "tool_call_id": "tc-1", "tool_name": "search", "content": "result..."}
  ],
  "messageCount": 4
}
```

#### Important Notes

- **Agent association only works for NEW conversations** started after the backend changes
- Existing historical conversations won't have `agent_id` metadata (tool calls will appear under "Tool Aanroepen" / unassigned)
- Tool call results are truncated to 200 characters in the debug panel UI
- **Page refresh**: Session history is automatically loaded from backend when page refreshes
- **Centralized loading**: All history loading (refresh + sidebar switch) is handled in `App.tsx`

---

### server-openai: COMPLETED (2025-12-17)

All tool call history features have been implemented for `server-openai` to match `server-langgraph`.

#### Implementation Approach

Since the OpenAI Agents SDK doesn't support custom metadata on session items like LangGraph does, we implemented a separate `tool_call_agents` table to store agent_id mappings at execution time.

#### Changes Made

**Backend Changes:**

1. **`server-openai/src/agora_openai/adapters/session_metadata.py`**
   - Added `tool_call_agents` table to store tool_call_id → agent_id mapping
   - Added `record_tool_call_agent()` method to persist agent_id when tool calls start
   - Added `update_tool_call_result()` method to store tool call results
   - Added `get_tool_calls_for_session()` method to retrieve full tool call data for history

2. **`server-openai/src/agora_openai/pipelines/orchestrator.py`**
   - Added call to `record_tool_call_agent()` in tool_callback when `status == "started"`
   - Added call to `update_tool_call_result()` in tool_callback when `status == "completed"`
   - Added `get_conversation_history()` wrapper method that:
     - Fetches full tool call data from session_metadata
     - Passes `stored_tool_calls` to agent_runner.get_conversation_history()

3. **`server-openai/src/agora_openai/core/agent_runner.py`**
   - **Bug Fix (2025-12-17)**: Changed `get_conversation_history()` to load session from SQLite if not in memory
     - Previously returned `[]` if session wasn't cached, breaking history after backend restart
     - Now calls `get_or_create_session()` to load from database first
   - **Bug Fix (2025-12-17)**: Added handling for OpenAI SDK's `function_call` and `function_call_output` item types
     - OpenAI SDK stores tool calls with `type="function_call"` (not `role="tool"`)
     - Added first-pass to build `call_id` → `tool_call_id` mapping for ID correlation
     - `function_call` items have `id` (fc_...) and `call_id` (call_...) fields
     - `function_call_output` items only have `call_id` field - must be mapped back
   - Rewrote `get_conversation_history()` to accept `stored_tool_calls` parameter
   - Added `role: "tool_call"` entries for tool calls
   - Added `agent_id` field to assistant and tool_call messages
   - Added `_extract_content()` helper method

4. **`server-openai/src/agora_openai/api/server.py`**
   - Updated `/sessions/{session_id}/history` endpoint to call orchestrator wrapper
   - Response format now matches langgraph exactly: `threadId`, `history`, `messageCount`

#### Bug Fixes Applied (2025-12-17)

**Issue 1: Empty history after backend restart**
- **Root Cause**: `get_conversation_history()` returned `[]` if `session_id not in self.sessions`
- **Fix**: Call `get_or_create_session(session_id)` to load session from SQLite database
- **Location**: `agent_runner.py:443-444`

**Issue 2: Tool calls not appearing in history**
- **Root Cause**: Code only checked `role == "tool"` but OpenAI SDK uses `type="function_call"` and `type="function_call_output"`
- **Fix**: Added handling for `function_call` and `function_call_output` item types
- **Additional Fix**: Built `call_id` → `tool_call_id` mapping because:
  - `function_call` has both `id: "fc_..."` and `call_id: "call_..."`
  - `function_call_output` only has `call_id: "call_..."`
  - Mapping ensures tool results link to correct tool calls
- **Location**: `agent_runner.py:459-537`

#### API Response Format (Matches langgraph)

```json
GET /sessions/{session_id}/history?include_tools=true

{
  "success": true,
  "threadId": "session-123",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "agent_id": "general-agent"},
    {"role": "tool_call", "tool_call_id": "fc_...", "tool_name": "search", "content": "{...}", "agent_id": "regulation-agent"},
    {"role": "tool", "tool_call_id": "fc_...", "tool_name": "search", "content": "result..."}
  ],
  "messageCount": 4
}
```

#### Important Notes

- **Agent tracking uses separate table**: Unlike langgraph which stores agent_id in message metadata, server-openai stores it in `tool_call_agents` table
- **Agent ID recorded at execution time**: Same pattern as langgraph - agent_id is persisted when tool calls happen, not inferred later
- **Backward compatible**: Old sessions without agent tracking will default to `"general-agent"`
- **No frontend changes needed**: Both backends produce identical API responses
- **Session loading**: Sessions are now automatically loaded from SQLite on history request (survives backend restart)
- **OpenAI SDK item format**: Tool calls use `type` field, not `role` field - different from expected format
