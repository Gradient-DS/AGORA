---
date: 2026-01-28T15:30:00+01:00
researcher: Claude
git_commit: ac88f9f2000b62db9ae8d5a3811180d15a74fee5
branch: feat/buffer
repository: AGORA
topic: "Store spoken text in backend instead of localStorage"
tags: [research, codebase, spoken-text, session-history, ag-ui-protocol]
status: complete
last_updated: 2026-01-28
last_updated_by: Claude
---

# Research: Store Spoken Text in Backend Instead of localStorage

**Date**: 2026-01-28T15:30:00+01:00
**Researcher**: Claude
**Git Commit**: ac88f9f2000b62db9ae8d5a3811180d15a74fee5
**Branch**: feat/buffer
**Repository**: AGORA

## Research Question

Can we store spoken text in the backend and return it with session history, instead of using localStorage? What changes would this entail?

## Summary

**Yes, this is feasible with moderate changes.** The backend already generates spoken text per-message and streams it via `agora:spoken_text_*` events. The key gap is that this text is not persisted with the message history. The solution involves:

1. **Backend**: Store `spoken_text` in `AIMessage.additional_kwargs` (same pattern used for `agent_id`)
2. **API**: Add `spoken_text` field to `HistoryMessage` response
3. **Frontend**: Map API `spoken_text` to `spokenContent` on session restore
4. **Docs**: Update OpenAPI spec, mock server, and JSON schemas

Importantly, **no agent functionality changes** - the spoken text generation remains identical.

## Detailed Findings

### Current Architecture

#### Frontend localStorage Storage (`HAI/src/stores/useMessageStore.ts:17-47`)

Spoken text is currently persisted to localStorage under key `agora-spoken-content`:

```typescript
// Format: { "msg-uuid-1": "spoken content...", "msg-uuid-2": "..." }
localStorage.setItem('agora-spoken-content', JSON.stringify(spokenContentMap));
```

On session restore, `replaceMessages()` merges localStorage data back into messages:

```typescript
// HAI/src/stores/useMessageStore.ts:235-246
replaceMessages: (messages: ChatMessage[]) => {
  const persistedSpoken = loadPersistedSpokenContent();
  const messagesWithSpoken = messages.map((msg) => {
    const spokenContent = persistedSpoken[msg.id];
    if (spokenContent) {
      return { ...msg, spokenContent };
    }
    return msg;
  });
  set({ messages: messagesWithSpoken, ... });
},
```

#### Backend Spoken Text Generation (`server-langgraph/src/agora_langgraph/core/graph.py:456-462`)

Spoken text is generated in parallel with written text via LangGraph's `Send` API:

```python
# Parallel generation dispatched at graph.py:364-387
Send("generate_written", GeneratorState(stream_type="written", ...)),
Send("generate_spoken", GeneratorState(stream_type="spoken", ...)),
```

The orchestrator streams `agora:spoken_text_*` events but **does not persist the final spoken text**.

#### Backend State Schema (`server-langgraph/src/agora_langgraph/core/state.py:27-48`)

The `AgentState` includes spoken-related fields, but these are accumulators for streaming, not per-message storage:

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    spoken: Annotated[list[str], operator.add]      # Streaming accumulator
    final_spoken: str                                # Merged final text (single string)
    # ... other fields
```

#### History Retrieval (`server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:841-939`)

Currently extracts `agent_id` from `additional_kwargs` but no `spoken_text`:

```python
# Line 871
agent_id = ai_msg.additional_kwargs.get("agent_id")
# Returns dict with: role, content, agent_id - NO spoken_text
```

### Proposed Solution

#### Approach: Store in `additional_kwargs`

LangChain's `AIMessage` has an extensible `additional_kwargs` dictionary. This is already used for `agent_id`:

```python
# server-langgraph/src/agora_langgraph/core/agents.py:194-196
if hasattr(response, "additional_kwargs"):
    response.additional_kwargs["agent_id"] = agent_id
```

We can use the same pattern for `spoken_text`.

### Required Changes

#### 1. Backend: Store Spoken Text with Message

**File**: `server-langgraph/src/agora_langgraph/core/graph.py`

After parallel generation completes, the spoken text needs to be attached to the AIMessage. This happens in the `merge_outputs` node (lines 465-505):

```python
# Current code creates AIMessage at line 506
final_message = AIMessage(
    content=final_written,
    additional_kwargs={"agent_id": agent_id},  # Already has agent_id
)

# Change to:
final_message = AIMessage(
    content=final_written,
    additional_kwargs={
        "agent_id": agent_id,
        "spoken_text": final_spoken,  # ADD THIS
    },
)
```

**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In `get_conversation_history()`, extract and return `spoken_text`:

```python
# Around line 871, after extracting agent_id:
agent_id = ai_msg.additional_kwargs.get("agent_id")
spoken_text = ai_msg.additional_kwargs.get("spoken_text")  # ADD THIS

# Around line 897, in the output dict:
output = {
    "role": "assistant",
    "content": ai_msg.content,
    "agent_id": agent_id,
    "spoken_text": spoken_text,  # ADD THIS (only if not None)
}
```

#### 2. Backend: server-openai Parity

**File**: `server-openai/src/agora_openai/core/agent_runner.py`

Similar changes needed to store spoken text with messages and return in history.

#### 3. API Contract: OpenAPI Spec

**File**: `docs/hai-contract/openapi.yaml`

Add `spoken_text` to `HistoryMessage` schema (around line 819):

```yaml
HistoryMessage:
  type: object
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
    spoken_text:                          # ADD THIS
      type: string
      description: |
        TTS-optimized version of the message content.
        Only present for assistant messages when spoken text was generated.
```

#### 4. API Contract: JSON Schema

**File**: `docs/hai-contract/schemas/messages.json`

Add to `HistoryMessage` properties (around line 61):

```json
"spoken_text": {
  "type": "string",
  "description": "TTS-optimized version of the content"
}
```

#### 5. Mock Server

**File**: `docs/hai-contract/mock_server.py`

Update `get_mock_history()` (around line 156) to include `spoken_text`:

```python
{
    "role": "assistant",
    "content": "Inspectie gestart voor **Restaurant Bella Rosa**...",
    "agent_id": Agents.HISTORY,
    "spoken_text": "Inspectie gestart voor Restaurant Bella Rosa...",  # ADD
},
```

#### 6. Frontend: API Types

**File**: `HAI/src/lib/api/sessions.ts`

Update `HistoryMessage` interface (line 27):

```typescript
export interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool_call' | 'tool';
  content: string;
  tool_name?: string;
  tool_call_id?: string;
  agent_id?: string;
  spoken_text?: string;  // ADD THIS
}
```

#### 7. Frontend: Map API Response

**File**: `HAI/src/lib/api/sessions.ts`

In `fetchSessionHistory()` (around line 94), map `spoken_text` to `spokenContent`:

```typescript
// Around line 119, when converting to ChatMessage:
const chatMessage: ChatMessage = {
  id: `msg-${index}`,
  role: msg.role === 'assistant' ? 'assistant' : 'user',
  content: msg.content,
  agentId: msg.agent_id,
  spokenContent: msg.spoken_text,  // ADD THIS
  // ...
};
```

#### 8. Frontend: Remove localStorage Dependency (Optional)

**File**: `HAI/src/stores/useMessageStore.ts`

Either:
- **Option A**: Remove localStorage entirely (breaking change for existing sessions)
- **Option B**: Keep localStorage as fallback for messages without `spoken_text`

Recommended: Option B for backwards compatibility:

```typescript
replaceMessages: (messages: ChatMessage[]) => {
  const persistedSpoken = loadPersistedSpokenContent();
  const messagesWithSpoken = messages.map((msg) => {
    // Prefer spoken_text from API, fallback to localStorage
    if (msg.spokenContent) {
      return msg;  // Already has spoken content from API
    }
    const localSpoken = persistedSpoken[msg.id];
    if (localSpoken) {
      return { ...msg, spokenContent: localSpoken };
    }
    return msg;
  });
  set({ messages: messagesWithSpoken, ... });
},
```

### Files to Modify

| File | Change |
|------|--------|
| `server-langgraph/src/agora_langgraph/core/graph.py` | Store `spoken_text` in `additional_kwargs` |
| `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py` | Return `spoken_text` in history |
| `server-openai/src/agora_openai/core/agent_runner.py` | Same changes for parity |
| `server-openai/src/agora_openai/pipelines/orchestrator.py` | Same changes for parity |
| `docs/hai-contract/openapi.yaml` | Add `spoken_text` to HistoryMessage |
| `docs/hai-contract/schemas/messages.json` | Add `spoken_text` field |
| `docs/hai-contract/mock_server.py` | Add `spoken_text` to mock responses |
| `HAI/src/lib/api/sessions.ts` | Update types and mapping |
| `HAI/src/stores/useMessageStore.ts` | Optional: simplify localStorage usage |

### Migration Considerations

1. **Backwards Compatibility**: Existing sessions won't have `spoken_text` stored. The frontend should fallback to localStorage for these.

2. **Database Migration**: No schema migration needed - `additional_kwargs` is already stored as JSON by LangGraph's checkpointer.

3. **API Versioning**: The change is additive (new optional field), so no breaking API changes.

4. **Testing**: Update integration tests in `tests/integration/test_dual_channel_spoken.py` to verify `spoken_text` is returned in history.

## Code References

- `HAI/src/stores/useMessageStore.ts:17-47` - Current localStorage implementation
- `HAI/src/stores/useMessageStore.ts:235-246` - `replaceMessages()` restoration
- `HAI/src/lib/api/sessions.ts:27` - `HistoryMessage` interface
- `server-langgraph/src/agora_langgraph/core/graph.py:456-505` - Spoken text generation
- `server-langgraph/src/agora_langgraph/core/state.py:27-48` - AgentState schema
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:841-939` - History retrieval
- `server-langgraph/src/agora_langgraph/core/agents.py:194-196` - `agent_id` storage pattern
- `docs/hai-contract/openapi.yaml:819` - HistoryMessage schema
- `docs/hai-contract/mock_server.py:156` - Mock history responses

## Architecture Insights

1. **Pattern Consistency**: The `additional_kwargs` pattern for storing message metadata is already established (`agent_id`). Using it for `spoken_text` maintains consistency.

2. **No Agent Changes**: The spoken text generation pipeline remains unchanged. Only the storage and retrieval of the final text changes.

3. **Parallel Compatibility**: Both `server-langgraph` and `server-openai` need identical changes to maintain API parity.

4. **Incremental Rollout**: The localStorage fallback allows gradual migration without losing existing spoken content.

## Open Questions

1. **localStorage Cleanup**: Should we add a migration to remove localStorage spoken content after successful API retrieval? This would prevent unbounded growth.

2. **Message ID Stability**: The current frontend generates synthetic IDs (`msg-${index}`) for history messages. If the backend starts returning real message IDs, localStorage keys may not match. Consider using a stable ID from the backend.

3. **Selective Storage**: Should spoken text always be stored, or only when the user has the comparison feature enabled? Storage-conscious approach vs. simplicity.

4. **Compression**: For long conversations, spoken text doubles storage. Consider if compression of `additional_kwargs` is needed.
