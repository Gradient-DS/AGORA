# Listen Mode (Ambient Agents) Implementation Plan

## Overview

Implement a "listen mode" for AGORA where the system can passively collect inspector messages without responding, then process the accumulated context when switching back to "feedback mode". This enables ambient agent behavior during inspections where the inspector talks without expecting immediate AI feedback.

## Current State Analysis

### What's Already Implemented

| Component | Status | Location |
|-----------|--------|----------|
| **Database storage** | Done | `user_manager.py:62-74` - `interaction_mode` stored in `users.preferences` JSON |
| **REST API** | Done | `server.py:349-456` - GET/PUT `/users/me/preferences` |
| **Agent tool** | Done | `tools.py:110-175` - `update_user_settings` tool |
| **Frontend UI (admin)** | Done | `UserForm.tsx:243-280` - Feedback/Listen toggle |
| **Frontend badge** | Done | `Header.tsx:128-142` - Shows current mode |

### What's Missing (This Plan)

| Component | Status | Impact |
|-----------|--------|--------|
| **Orchestrator fetch** | Not done | Mode not passed to graph |
| **State fields** | Not done | `interaction_mode`, `message_buffer`, `buffer_context` missing |
| **Routing logic** | Not done | `route_from_start` ignores mode |
| **Buffer nodes** | Not done | No `buffer_message`, `process_buffer` nodes |
| **Wake word detection** | Not done | No way to switch modes via voice |
| **Offline buffering** | Not done | No client-side IndexedDB buffer |

### Key Discoveries

- **Preference pattern exists**: `spoken_text_type` is fetched at `orchestrator.py:403-413` - use same pattern
- **Reducer pattern exists**: `Annotated[list[str], operator.add]` at `state.py:24-25` - can adapt for buffer
- **Conditional routing exists**: `route_from_start` at `graph.py:39-60` - extend with mode check
- **Custom event pattern exists**: `ag_ui_handler.py:345-391` - use for listen mode acknowledgments

## Desired End State

1. **Listen mode active**: Inspector messages are stored in `message_buffer` without LLM processing. A minimal acknowledgment is sent to confirm receipt.

2. **Wake word detected**: Inspector says "AGORA" (anywhere in message) → mode switches to feedback, preference is persisted, buffer is processed, and normal conversation resumes with remaining message content.

3. **Mode switch to listen**: General agent uses `update_user_settings` tool when user requests listen mode (no wake phrase for this direction).

4. **Offline resilience**: Client buffers messages during disconnection, replays on reconnect with `isOfflineBatch: true` context.

5. **Report generation**: Reporting agent receives `buffer_context` with accumulated listen-mode messages for comprehensive reports.

### Verification Criteria

- [ ] In listen mode, messages return minimal acknowledgment (no LLM call)
- [ ] Buffer persists across invocations via checkpointer
- [ ] Switching to feedback mode processes buffer and adds to `buffer_context`
- [ ] Wake phrase "AGORA" triggers mode switch and persists preference
- [ ] Frontend shows animated listen mode indicator with buffered message count
- [ ] Offline messages are buffered in IndexedDB and replayed on reconnect

## What We're NOT Doing

- **Real-time transcription**: This is for text messages, not audio processing
- **Buffer size limits**: Not implementing caps initially (can add later if needed)
- **Buffer TTL/expiration**: Not auto-expiring buffers
- **Separate storage**: Buffer lives in LangGraph state, not separate database
- **Partial processing**: No incremental summarization during listen mode

## Implementation Approach

Use LangGraph's existing patterns:
1. **Custom reducer** for message buffer accumulation
2. **Conditional routing** to bypass agents in listen mode
3. **Checkpointer persistence** to maintain buffer across invocations
4. **Direct text events** for minimal acknowledgments (no LLM)

---

## Phase 1: Backend Core - State Extension

### Overview

Extend `AgentState` with listen mode fields and add custom reducer for buffer accumulation.

### Changes Required

#### 1. State Definition
**File**: `server-langgraph/src/agora_langgraph/core/state.py`

Add custom reducer and new fields:

```python
"""LangGraph state definition for multi-agent orchestration."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


def accumulate_messages(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Custom reducer for message buffer accumulation.

    Accumulates message dicts. The buffer is cleared by returning an empty
    list from the process_buffer node (via Overwrite).
    """
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


class AgentState(TypedDict):
    """State shared across all agent nodes."""

    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    current_agent: str
    pending_approval: dict[str, Any] | None
    metadata: dict[str, Any]
    # Parallel output accumulators
    written: Annotated[list[str], operator.add]
    spoken: Annotated[list[str], operator.add]
    # Final merged outputs
    final_written: str
    final_spoken: str
    # Listen mode fields
    interaction_mode: str  # "feedback" | "listen"
    message_buffer: Annotated[list[dict[str, Any]], accumulate_messages]
    buffer_context: str  # Processed summary from buffered messages
```

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Lint passes: `cd server-langgraph && ruff check src/`
- [ ] Existing tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Confirm state.py imports correctly in Python REPL

---

## Phase 2: Backend Core - Graph Routing

### Overview

Modify graph routing to check `interaction_mode` and add buffer/process nodes.

### Changes Required

#### 1. Buffer and Process Nodes
**File**: `server-langgraph/src/agora_langgraph/core/graph.py`

Add new nodes and routing logic. Insert after imports and before `VALID_AGENTS`:

```python
import time
from langgraph.types import Overwrite

# Wake word to switch from listen mode to feedback mode
# Just "AGORA" (case-insensitive) anywhere in the message
WAKE_WORD = "agora"


def detect_wake_word(content: str) -> bool:
    """Detect if message contains the AGORA wake word.

    Returns True if wake word found, False otherwise.
    Only used to switch FROM listen mode TO feedback mode.
    """
    return WAKE_WORD in content.lower()


def buffer_message_node(state: AgentState) -> dict[str, Any]:
    """Store incoming message in buffer without agent processing.

    In listen mode, messages are stored for later batch processing.
    Returns minimal acknowledgment without LLM call.
    """
    from langchain_core.messages import HumanMessage

    messages = state.get("messages", [])

    # Get latest human message to buffer
    latest_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_human = msg
            break

    if latest_human:
        buffer_count = len(state.get("message_buffer", [])) + 1
        return {
            "message_buffer": [{
                "content": latest_human.content,
                "timestamp": time.time(),
            }],
            # Minimal acknowledgment - no full response generation
            "final_written": f"[Luistermodus actief - bericht {buffer_count} opgeslagen]",
            "final_spoken": "",
        }

    return {}


def process_buffer_node(state: AgentState) -> dict[str, Any]:
    """Process all buffered messages and prepare context for agent.

    Called when transitioning from listen to feedback mode.
    Summarizes accumulated context and clears buffer.
    """
    buffer = state.get("message_buffer", [])

    if not buffer:
        return {}

    # Build context summary from buffered messages
    buffer_lines = []
    for i, msg in enumerate(buffer, 1):
        ts = msg.get("timestamp", 0)
        content = msg.get("content", "")
        buffer_lines.append(f"{i}. {content}")

    buffer_content = "\n".join(buffer_lines)

    context_summary = (
        f"--- Context verzameld tijdens luistermodus ({len(buffer)} berichten) ---\n"
        f"{buffer_content}\n"
        f"--- Einde luistermodus context ---"
    )

    log.info(f"process_buffer_node: Processed {len(buffer)} buffered messages")

    return {
        "buffer_context": context_summary,
        # Clear buffer using Overwrite to bypass reducer
        "message_buffer": Overwrite([]),
    }


def wake_word_handler_node(state: AgentState) -> dict[str, Any]:
    """Handle wake word detection - switch from listen to feedback mode.

    When "AGORA" is detected in a message while in listen mode:
    1. Switches interaction_mode to "feedback"
    2. Processes any buffered messages into buffer_context
    3. Strips the wake word and passes remaining content for processing

    Note: The preference is also persisted via user_manager in the orchestrator
    after this node runs (see Phase 3).
    """
    import re
    from langchain_core.messages import HumanMessage

    messages = state.get("messages", [])
    buffer = state.get("message_buffer", [])

    if not messages:
        return {}

    latest = messages[-1]
    if not isinstance(latest, HumanMessage):
        return {}

    # Remove "AGORA" from message (case-insensitive) and get remaining content
    remaining_content = re.sub(r'\bagora\b', '', latest.content, flags=re.IGNORECASE).strip()

    result: dict[str, Any] = {
        "interaction_mode": "feedback",
    }

    # Process buffer if we have buffered messages
    if buffer:
        buffer_lines = [f"{i+1}. {m['content']}" for i, m in enumerate(buffer)]
        result["buffer_context"] = (
            f"Context uit luistermodus ({len(buffer)} berichten):\n"
            + "\n".join(buffer_lines)
        )
        result["message_buffer"] = Overwrite([])

    result["final_written"] = f"[Feedback modus geactiveerd - {len(buffer)} berichten verwerkt]"
    result["final_spoken"] = "Feedback modus geactiveerd"

    # If there's content after removing the wake word, update message for processing
    if remaining_content:
        result["messages"] = [HumanMessage(content=remaining_content)]

    log.info(f"wake_word_handler: Switching to feedback mode, {len(buffer)} messages buffered")
    return result
```

#### 2. Update Route Function
**File**: `server-langgraph/src/agora_langgraph/core/graph.py`

Replace `route_from_start` function:

```python
def route_from_start(state: AgentState) -> str:
    """Route from START based on interaction mode and wake word.

    Priority:
    1. If in listen mode AND wake word detected → wake_word_handler
    2. If in listen mode (no wake word) → buffer_message
    3. If buffer exists and in feedback mode → process_buffer first
    4. Otherwise → route to persisted agent
    """
    from langchain_core.messages import HumanMessage

    messages = state.get("messages", [])
    mode = state.get("interaction_mode", "feedback")
    buffer = state.get("message_buffer", [])

    # In listen mode, check for wake word to switch back to feedback
    if mode == "listen":
        if messages:
            latest = messages[-1]
            if isinstance(latest, HumanMessage) and detect_wake_word(latest.content):
                log.info("route_from_start: Wake word 'AGORA' detected, routing to wake_word_handler")
                return "wake_word_handler"

        # No wake word - buffer the message
        log.info("route_from_start: Listen mode active, routing to buffer_message")
        return "buffer_message"

    # Feedback mode with buffer - process buffer first
    if mode == "feedback" and buffer:
        log.info(f"route_from_start: Processing {len(buffer)} buffered messages")
        return "process_buffer"

    # Normal routing to persisted agent
    current = state.get("current_agent", "general-agent")
    if current not in VALID_AGENTS:
        log.info(f"route_from_start: Unknown agent '{current}', defaulting to general-agent")
        return "general-agent"

    log.info(f"route_from_start: Routing to persisted agent '{current}'")
    return current
```

#### 3. Update Graph Construction
**File**: `server-langgraph/src/agora_langgraph/core/graph.py`

In `build_agent_graph()`, add new nodes and edges. After agent nodes are added:

```python
def build_agent_graph(
    mcp_tools_by_server: dict[str, list[Any]] | None = None,
) -> StateGraph[AgentState]:
    """Build the multi-agent StateGraph."""

    # ... existing setup code ...

    graph = StateGraph(AgentState)

    # Listen mode nodes (add BEFORE agent nodes)
    graph.add_node("buffer_message", buffer_message_node)
    graph.add_node("process_buffer", process_buffer_node)
    graph.add_node("wake_word_handler", wake_word_handler_node)

    # Agent nodes (existing)
    graph.add_node("general-agent", general_agent)
    graph.add_node("regulation-agent", regulation_agent)
    graph.add_node("reporting-agent", reporting_agent)
    graph.add_node("history-agent", history_agent)

    # ... tool node and generator nodes ...

    # Entry point - now includes listen mode routing
    graph.add_conditional_edges(
        START,
        route_from_start,
        {
            "buffer_message": "buffer_message",
            "process_buffer": "process_buffer",
            "wake_word_handler": "wake_word_handler",
            "general-agent": "general-agent",
            "regulation-agent": "regulation-agent",
            "reporting-agent": "reporting-agent",
            "history-agent": "history-agent",
        },
    )

    # Buffer goes directly to END (no response generation)
    graph.add_edge("buffer_message", END)

    # Process buffer then continues to general-agent
    graph.add_edge("process_buffer", "general-agent")

    # Wake word handler always switches to feedback mode
    # Route to general-agent if there's remaining content, otherwise END
    def route_after_wake(state: AgentState) -> str:
        messages = state.get("messages", [])
        if messages:
            latest = messages[-1]
            # Check if there's content after stripping AGORA
            if hasattr(latest, 'content') and latest.content.strip():
                return "general-agent"
        return END  # No remaining content - just acknowledge mode switch

    graph.add_conditional_edges(
        "wake_word_handler",
        route_after_wake,
        {
            "general-agent": "general-agent",
            END: END,
        },
    )

    # ... rest of existing edges ...
```

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Lint passes: `cd server-langgraph && ruff check src/`
- [ ] Unit tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Graph builds without errors in Python REPL
- [ ] Routing logic reaches buffer_message when mode is "listen"

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 3: Backend Core - Orchestrator Integration

### Overview

Fetch `interaction_mode` from user preferences and pass it to graph state.

### Changes Required

#### 1. Fetch Interaction Mode
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In `process_message()`, around line 196-211 where metadata is populated, add:

```python
# Include user_id and user context in metadata so agents can access it
metadata = agent_input.context.copy() if agent_input.context else {}
metadata["user_id"] = user_id

# Fetch user email, preferences, AND interaction_mode
interaction_mode = "feedback"  # default
if self.user_manager:
    try:
        user = await self.user_manager.get_user(user_id)
        if user:
            metadata["user_email"] = user.get("email")
            metadata["user_name"] = user.get("name")
            prefs = user.get("preferences", {})
            if prefs:
                metadata["email_reports"] = prefs.get("email_reports", True)
                # NEW: Get interaction_mode
                interaction_mode = prefs.get("interaction_mode", "feedback")
    except Exception as e:
        log.warning(f"Failed to fetch user info for metadata: {e}")
```

#### 2. Include in Graph Input
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Around line 238 where `graph_input` is constructed:

```python
graph_input = {
    "messages": [HumanMessage(content=user_content)],
    "session_id": thread_id,
    "current_agent": "general-agent",
    "pending_approval": None,
    "metadata": metadata,
    # NEW: Include listen mode fields
    "interaction_mode": interaction_mode,
    "message_buffer": [],  # Will accumulate via reducer
    "buffer_context": "",
}
```

#### 3. Handle Listen Mode Response
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In `_stream_response()`, add logic after the streaming loop to:
1. Send listen mode acknowledgments (no LLM streaming)
2. Persist preference if wake word changed the mode

After `final_state = await self.graph.aget_state(config)`:

```python
# Check if this was a listen mode or wake word response (no streaming needed)
final_written = ""
final_spoken = ""
final_interaction_mode = None
if final_state and final_state.values:
    final_written = final_state.values.get("final_written", "")
    final_spoken = final_state.values.get("final_spoken", "")
    final_interaction_mode = final_state.values.get("interaction_mode")

# If we have final_written but didn't stream (listen mode), send it now
if final_written and not message_started:
    await protocol_handler.send_text_message_start(message_id, "assistant")
    await protocol_handler.send_text_message_content(message_id, final_written)
    await protocol_handler.send_text_message_end(message_id)
    message_started = True
    full_response.append(final_written)

    # Also send spoken if present
    if final_spoken:
        await protocol_handler.send_spoken_text_start(message_id, "assistant")
        await protocol_handler.send_spoken_text_content(message_id, final_spoken)
        await protocol_handler.send_spoken_text_end(message_id)

# Persist interaction_mode if it changed (wake word triggered switch)
if final_interaction_mode and final_interaction_mode != interaction_mode:
    if self.user_manager:
        try:
            await self.user_manager.update_preferences(
                user_id, {"interaction_mode": final_interaction_mode}
            )
            log.info(f"Persisted interaction_mode change to '{final_interaction_mode}' for user {user_id}")
        except Exception as e:
            log.warning(f"Failed to persist interaction_mode change: {e}")
```

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Lint passes: `cd server-langgraph && ruff check src/`
- [ ] Tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Set user preference to "listen" mode via API or UI
- [ ] Send a message via WebSocket
- [ ] Verify response is `[Luistermodus actief - bericht 1 opgeslagen]`
- [ ] Verify NO LLM call was made (check logs)
- [ ] Send second message, verify `bericht 2` in response
- [ ] Switch to "feedback" mode
- [ ] Send message, verify buffer context is included in agent prompt

**Implementation Note**: This is the core functionality. Extensive manual testing required.

---

## Phase 4: Agent Context Injection

### Overview

Inject `buffer_context` into agent system prompts when available.

### Changes Required

#### 1. Modify Agent Runner
**File**: `server-langgraph/src/agora_langgraph/core/agents.py`

In `_run_agent_node()`, around where the system prompt is constructed:

```python
async def _run_agent_node(state: AgentState, agent_id: str) -> dict[str, Any]:
    """Execute an agent node with tool support."""

    agent_config = get_agent_by_id(agent_id)
    if not agent_config:
        raise ValueError(f"Unknown agent: {agent_id}")

    # Get base system prompt
    system_prompt = agent_config.get("instructions", "")

    # NEW: Prepend buffer context if present
    buffer_context = state.get("buffer_context", "")
    if buffer_context:
        system_prompt = f"{buffer_context}\n\n{system_prompt}"
        log.info(f"Injected buffer context ({len(buffer_context)} chars) into {agent_id}")

    # ... rest of agent logic ...
```

### Success Criteria

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Accumulate 3+ messages in listen mode
- [ ] Switch to feedback mode with "AGORA wat denk je hiervan?"
- [ ] Verify agent response references the buffered context
- [ ] Verify preference is persisted (check via API or admin UI)

---

## Phase 5: Frontend - Listen Mode Indicator Enhancement

### Overview

Enhance the listen mode badge to show animation and buffered message count.

### Changes Required

#### 1. Add Listen Mode Store
**File**: `HAI/src/stores/useListenModeStore.ts` (new file)

```typescript
import { create } from 'zustand';

interface ListenModeStore {
  bufferedCount: number;
  setBufferedCount: (count: number) => void;
  incrementBufferedCount: () => void;
  resetBufferedCount: () => void;
}

export const useListenModeStore = create<ListenModeStore>((set) => ({
  bufferedCount: 0,
  setBufferedCount: (count) => set({ bufferedCount: count }),
  incrementBufferedCount: () => set((s) => ({ bufferedCount: s.bufferedCount + 1 })),
  resetBufferedCount: () => set({ bufferedCount: 0 }),
}));
```

#### 2. Update Header Component
**File**: `HAI/src/components/layout/Header.tsx`

Enhance the listen mode badge:

```tsx
import { useListenModeStore } from '@/stores/useListenModeStore';

// In Header component:
const bufferedCount = useListenModeStore((state) => state.bufferedCount);

// Replace existing interaction_mode badge with:
{preferences?.interaction_mode && (
  <Badge
    variant={preferences.interaction_mode === 'listen' ? 'default' : 'outline'}
    className={`text-xs ${preferences.interaction_mode === 'listen' ? 'animate-pulse bg-amber-500' : ''}`}
  >
    {preferences.interaction_mode === 'feedback' ? (
      <>
        <MessageSquare className="h-3 w-3 mr-1" />
        Feedback
      </>
    ) : (
      <>
        <Headphones className="h-3 w-3 mr-1" />
        Luisteren {bufferedCount > 0 && `(${bufferedCount})`}
      </>
    )}
  </Badge>
)}
```

#### 3. Update Message Handler
**File**: `HAI/src/hooks/useWebSocket.ts` (or wherever events are processed)

Parse listen mode acknowledgments to update count:

```typescript
// When receiving TEXT_MESSAGE_CONTENT
if (content.startsWith('[Luistermodus actief')) {
  const match = content.match(/bericht (\d+)/);
  if (match) {
    useListenModeStore.getState().setBufferedCount(parseInt(match[1], 10));
  }
}

// When receiving mode change acknowledgment
if (content.includes('Feedback modus geactiveerd')) {
  useListenModeStore.getState().resetBufferedCount();
}
```

### Success Criteria

#### Automated Verification:
- [ ] TypeScript compiles: `cd HAI && pnpm run type-check`
- [ ] Lint passes: `cd HAI && pnpm run lint`
- [ ] Tests pass: `cd HAI && pnpm run test`

#### Manual Verification:
- [ ] Listen mode badge pulses with amber color
- [ ] Count increases with each buffered message
- [ ] Count resets when switching to feedback mode

---

## Phase 6: Frontend - Offline Buffering

### Overview

Add client-side IndexedDB buffering for messages during connectivity loss.

### Changes Required

#### 1. Create Offline Buffer Module
**File**: `HAI/src/lib/websocket/offlineBuffer.ts` (new file)

```typescript
interface BufferedMessage {
  id: string;
  content: string;
  timestamp: number;
  threadId: string;
  userId: string;
}

const DB_NAME = 'agora-offline-buffer';
const STORE_NAME = 'messages';

class OfflineMessageBuffer {
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        }
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onerror = () => reject(request.error);
    });
  }

  async addMessage(message: BufferedMessage): Promise<void> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const request = store.add(message);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getAndClearMessages(): Promise<BufferedMessage[]> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const getRequest = store.getAll();

      getRequest.onsuccess = () => {
        const messages = getRequest.result;
        store.clear();
        resolve(messages.sort((a, b) => a.timestamp - b.timestamp));
      };

      getRequest.onerror = () => reject(getRequest.error);
    });
  }

  async getCount(): Promise<number> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const request = store.count();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
}

export const offlineBuffer = new OfflineMessageBuffer();
```

#### 2. Integrate with WebSocket Client
**File**: `HAI/src/lib/websocket/client.ts`

Add offline buffering logic:

```typescript
import { offlineBuffer } from './offlineBuffer';
import { generateUUID } from '@/lib/utils';

// In sendRunInput method:
sendRunInput(threadId: string, userId: string, content: string, context?: Record<string, unknown>): string {
  const runId = generateUUID();
  const input: RunAgentInput = {
    threadId,
    runId,
    userId,
    messages: [{ role: 'user', content }],
    context,
  };

  if (this.ws?.readyState === WebSocket.OPEN) {
    this.ws.send(JSON.stringify(input));
  } else {
    // Buffer for later
    offlineBuffer.addMessage({
      id: runId,
      content,
      timestamp: Date.now(),
      threadId,
      userId,
    }).then(() => {
      console.log('Message buffered offline');
    });
  }

  return runId;
}

// In onopen handler, add replay logic:
this.ws.onopen = async () => {
  this.isConnecting = false;
  this.updateStatus('connected');
  this.reconnectAttempts = 0;

  // Replay offline buffer
  const buffered = await offlineBuffer.getAndClearMessages();
  if (buffered.length > 0) {
    const batchContent = buffered
      .map(m => `[${new Date(m.timestamp).toLocaleTimeString()}] ${m.content}`)
      .join('\n');

    const batchInput: RunAgentInput = {
      threadId: buffered[0].threadId,
      runId: generateUUID(),
      userId: buffered[0].userId,
      messages: [{ role: 'user', content: batchContent }],
      context: { isOfflineBatch: true, messageCount: buffered.length },
    };

    this.ws!.send(JSON.stringify(batchInput));
    console.log(`Replayed ${buffered.length} offline messages`);
  }

  this.flushMessageQueue();
};
```

### Success Criteria

#### Automated Verification:
- [ ] TypeScript compiles: `cd HAI && pnpm run type-check`
- [ ] Tests pass: `cd HAI && pnpm run test`

#### Manual Verification:
- [ ] Disconnect from network
- [ ] Send 3 messages (should be buffered)
- [ ] Reconnect
- [ ] Verify batch message sent with `[isOfflineBatch]` context
- [ ] Backend receives and processes batch

---

## Testing Strategy

### Unit Tests

**Backend (`server-langgraph/tests/`):**
- `test_state.py`: Test `accumulate_messages` reducer
- `test_graph.py`: Test `detect_wake_word`, `route_from_start` with different modes
- `test_buffer_nodes.py`: Test `buffer_message_node`, `process_buffer_node`, `wake_word_handler_node`

**Frontend (`HAI/src/__tests__/`):**
- `offlineBuffer.test.ts`: Test IndexedDB operations
- `useListenModeStore.test.ts`: Test store operations

### Integration Tests

- Full flow: listen mode → buffer 3 messages → wake word → verify context in response
- Offline flow: disconnect → buffer → reconnect → verify batch processing

### Manual Testing Steps

1. **Basic Listen Mode**:
   - Set preference to "listen" via admin UI
   - Send message via chat
   - Verify minimal acknowledgment (no LLM call in logs)

2. **Wake Word Activation**:
   - While in listen mode, type "AGORA wat vind je hiervan?"
   - Verify mode switches to feedback
   - Verify preference is persisted (check admin UI)
   - Verify buffer context mentioned in response
   - Verify "wat vind je hiervan?" is processed (not the word AGORA)

3. **Offline Buffering**:
   - Open browser dev tools, go offline
   - Send 3 messages
   - Go online
   - Verify batch sent and processed

## Performance Considerations

- **Buffer size**: No hard limit, but checkpointer storage may grow
- **Context length**: Large buffers may exceed LLM context window - consider truncation
- **Offline storage**: IndexedDB has ~50MB limit, sufficient for text messages

## Migration Notes

- No database migration needed (uses existing preferences JSON field)
- No breaking changes to existing API
- Frontend changes are additive

## References

- Research document: `thoughts/shared/research/2026-01-15-listen-mode-message-buffering.md`
- LangGraph Ambient Agents: https://www.blog.langchain.com/introducing-ambient-agents/
- LangMem Delayed Processing: https://langchain-ai.github.io/langmem/guides/delayed_processing/
- Existing preference pattern: `orchestrator.py:403-413` (`spoken_text_type`)
