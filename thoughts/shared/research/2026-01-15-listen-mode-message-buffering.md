---
date: 2026-01-15T17:30:00+01:00
researcher: Claude
git_commit: 3a26a07069b256101c1f2f9cd715b33c499e9a43
branch: fix/parallel-stream-context
repository: AGORA
topic: "Listen Mode Architecture for Background Information Collection"
tags: [research, langgraph, listen-mode, message-buffering, conditional-routing, agora]
status: complete
last_updated: 2026-01-15
last_updated_by: Claude
last_updated_note: "Added offline buffering and wake word trigger sections"
---

# Research: Listen Mode Architecture for Background Information Collection

**Date**: 2026-01-15T17:30:00+01:00
**Researcher**: Claude
**Git Commit**: 3a26a07069b256101c1f2f9cd715b33c499e9a43
**Branch**: fix/parallel-stream-context
**Repository**: AGORA

## Research Question

How to implement a "listen mode" in AGORA's server-langgraph where:
1. **Feedback mode (default)**: System responds normally to user input
2. **Listen mode**: System buffers user messages without responding, collecting information passively
3. **Mode transition**: When switching from listen to feedback, process the buffer to gather relevant context (regulations, company history, etc.)
4. **Report generation**: Should work based on all collected info from listen mode

## Summary

LangGraph provides several patterns that can be combined to implement this "background listening assistant" functionality:

1. **Custom reducers with `Annotated[list, accumulate_or_clear]`** for message buffering
2. **Conditional edges via `add_conditional_edges`** for mode-based routing
3. **The `Overwrite` type** for clearing accumulated state when flushing the buffer
4. **Parallel Send API** (already in use) for dual-channel output

The recommended approach is to add a **routing node before `general-agent`** that checks the `interaction_mode` preference and either:
- Routes to a `buffer_message` node (listen mode) that accumulates and exits without response
- Routes to a `process_buffer` node (on mode transition) that summarizes accumulated context
- Routes to `general-agent` (feedback mode) for normal processing

## Detailed Findings

### Current Architecture Analysis

The existing graph flow (`server-langgraph/src/agora_langgraph/core/graph.py`):

```
START → general-agent → route_from_agent → {
  tools → route_after_tools → {agent nodes}
  generate_written, generate_spoken (parallel via Send) → merge → END
}
```

The state (`server-langgraph/src/agora_langgraph/core/state.py`) already uses:
- `Annotated[list[BaseMessage], add_messages]` for message accumulation
- `Annotated[list[str], operator.add]` for written/spoken output accumulation

### Key LangGraph Patterns for Listen Mode

#### Pattern 1: Custom Reducer for Message Buffer

```python
def accumulate_or_clear(left: list | None, right: list | None) -> list:
    """Accumulate messages, or clear if empty list is passed."""
    if left is None:
        left = []
    if right is None:
        right = []
    # Convention: empty list with special marker = clear signal
    if len(right) == 0:
        return []
    return left + right

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # ... existing fields ...
    # NEW: Listen mode fields
    interaction_mode: str  # "feedback" | "listen"
    message_buffer: Annotated[list[dict], accumulate_or_clear]
    buffer_context: str  # Processed summary from buffer
```

#### Pattern 2: Conditional Entry Routing

```python
from typing import Literal

def route_entry(state: AgentState) -> Literal[
    "buffer_message", "process_buffer", "general-agent"
]:
    """Route at entry based on interaction mode and buffer state."""
    mode = state.get("interaction_mode", "feedback")
    buffer = state.get("message_buffer", [])

    # In listen mode - buffer without processing
    if mode == "listen":
        return "buffer_message"

    # Mode is feedback AND we have buffered messages - process them first
    if mode == "feedback" and buffer:
        return "process_buffer"

    # Normal feedback mode - go to agent
    return "general-agent"
```

#### Pattern 3: Buffer Node (Passive Accumulation)

```python
def buffer_message_node(state: AgentState) -> dict:
    """Store incoming message in buffer without agent processing.

    In listen mode, messages are stored for later batch processing.
    Returns minimal response to acknowledge receipt.
    """
    messages = state.get("messages", [])

    # Get latest human message to buffer
    latest_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_human = msg
            break

    if latest_human:
        return {
            "message_buffer": [{
                "content": latest_human.content,
                "timestamp": time.time(),
            }],
            # Minimal acknowledgment - no full response generation
            "final_written": "[Luistermodus actief - bericht opgeslagen]",
            "final_spoken": "",
        }

    return {}
```

#### Pattern 4: Process Buffer Node (On Mode Transition)

```python
from langgraph.types import Overwrite

async def process_buffer_node(state: AgentState) -> dict:
    """Process all buffered messages and prepare context for agent.

    Called when transitioning from listen to feedback mode.
    Summarizes accumulated context and clears buffer.
    """
    buffer = state.get("message_buffer", [])

    if not buffer:
        return {}

    # Build context summary from buffered messages
    buffer_content = "\n".join([
        f"[{msg['timestamp']}] {msg['content']}"
        for msg in buffer
    ])

    # Create context message for the agent
    context_summary = (
        f"--- Context verzameld tijdens luistermodus ({len(buffer)} berichten) ---\n"
        f"{buffer_content}\n"
        f"--- Einde luistermodus context ---"
    )

    return {
        # Add context to state for agent to use
        "buffer_context": context_summary,
        # Clear buffer using Overwrite to bypass reducer
        "message_buffer": Overwrite([]),
    }
```

### Recommended Architecture

```
                            ┌─────────────────┐
                            │  route_entry    │
                            │ (conditional)   │
                            └────────┬────────┘
                   ┌─────────────────┼─────────────────┐
                   ▼                 ▼                 ▼
         ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │ buffer_message  │ │ process_buffer  │ │  general-agent  │
         │ (listen mode)   │ │ (mode change)   │ │  (normal flow)  │
         └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
                  │                   │                   │
                  ▼                   ▼                   │
               [END]          ┌──────────────┐           │
          (no response)       │general-agent │◄──────────┘
                              │(with context)│
                              └──────┬───────┘
                                     │
                              [existing flow]
                                     │
                                     ▼
                         generate_written, generate_spoken
                                     │
                                     ▼
                                  merge → END
```

### Implementation Plan

#### Step 1: Extend State (`state.py`)

```python
def accumulate_or_clear(left: list | None, right: list | None) -> list:
    """Custom reducer: accumulates, or clears if given empty list via Overwrite."""
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


class AgentState(TypedDict):
    """State shared across all agent nodes."""
    # Existing fields
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    current_agent: str
    pending_approval: dict[str, Any] | None
    metadata: dict[str, Any]
    written: Annotated[list[str], operator.add]
    spoken: Annotated[list[str], operator.add]
    final_written: str
    final_spoken: str

    # NEW: Listen mode fields
    interaction_mode: str  # "feedback" | "listen" - from user preferences
    message_buffer: Annotated[list[dict], accumulate_or_clear]
    buffer_context: str  # Processed summary from buffered messages
```

#### Step 2: Add Routing Logic (`graph.py`)

```python
def route_entry(state: AgentState) -> Literal[
    "buffer_message", "process_buffer", "general-agent"
]:
    """Route at graph entry based on interaction mode."""
    mode = state.get("interaction_mode", "feedback")
    buffer = state.get("message_buffer", [])

    if mode == "listen":
        return "buffer_message"

    if mode == "feedback" and buffer:
        return "process_buffer"

    return "general-agent"


def buffer_message_node(state: AgentState) -> dict:
    """Store message without processing."""
    messages = state.get("messages", [])
    latest = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)),
        None
    )

    if latest:
        return {
            "message_buffer": [{
                "content": latest.content,
                "timestamp": time.time(),
            }],
            "final_written": "[Luistermodus: bericht opgeslagen]",
            "final_spoken": "",
        }
    return {}


async def process_buffer_node(state: AgentState) -> dict:
    """Process buffered messages on mode transition."""
    buffer = state.get("message_buffer", [])
    if not buffer:
        return {}

    content = "\n".join(f"- {m['content']}" for m in buffer)
    context = f"Context uit luistermodus ({len(buffer)} berichten):\n{content}"

    return {
        "buffer_context": context,
        "message_buffer": Overwrite([]),
    }
```

#### Step 3: Update Graph Construction

```python
def build_agent_graph(...) -> StateGraph[AgentState]:
    graph = StateGraph(AgentState)

    # NEW: Entry routing and buffer nodes
    graph.add_node("buffer_message", buffer_message_node)
    graph.add_node("process_buffer", process_buffer_node)

    # Existing agent nodes
    graph.add_node("general-agent", general_agent)
    # ... other agents ...

    # NEW: Entry routing
    graph.add_conditional_edges(
        START,
        route_entry,
        {
            "buffer_message": "buffer_message",
            "process_buffer": "process_buffer",
            "general-agent": "general-agent",
        }
    )

    # Buffer goes directly to END (no response generation)
    graph.add_edge("buffer_message", END)

    # Process buffer then continues to agent
    graph.add_edge("process_buffer", "general-agent")

    # ... rest of existing edges ...
```

#### Step 4: Pass Mode from Orchestrator (`orchestrator.py`)

```python
async def process_message(self, agent_input, protocol_handler):
    # ... existing code ...

    # Fetch interaction_mode from user preferences
    interaction_mode = "feedback"  # default
    if self.user_manager:
        try:
            user = await self.user_manager.get_user(user_id)
            if user:
                prefs = user.get("preferences", {})
                interaction_mode = prefs.get("interaction_mode", "feedback")
        except Exception as e:
            log.warning(f"Failed to fetch interaction_mode: {e}")

    input_state = {
        "messages": [HumanMessage(content=user_content)],
        "session_id": thread_id,
        "current_agent": "general-agent",
        "pending_approval": None,
        "metadata": metadata,
        # NEW: Pass interaction mode
        "interaction_mode": interaction_mode,
        "message_buffer": [],  # Will accumulate via reducer
        "buffer_context": "",
    }
```

#### Step 5: Inject Buffer Context into Agent Prompt

Modify `general_agent` in `agents.py` to include `buffer_context`:

```python
async def general_agent(state: AgentState) -> dict[str, Any]:
    buffer_context = state.get("buffer_context", "")

    # Prepend buffer context to system prompt if present
    system_prompt = get_agent_config("general-agent")["instructions"]
    if buffer_context:
        system_prompt = f"{buffer_context}\n\n{system_prompt}"

    # ... rest of agent logic ...
```

### Frontend Integration

The listen mode can be triggered in two ways:

1. **Via User Settings UI** (already implemented in UserForm.tsx)
2. **Via Chat Command** (general agent can call `update_user_settings`)

When in listen mode, the frontend could show:
- A visual indicator (badge/icon) that listen mode is active
- A minimal acknowledgment message instead of full response

### Reporting Integration

For the reporting flow, the `buffer_context` should be passed through when:
1. User switches from listen to feedback mode
2. User requests a report generation

The reporting agent can access `buffer_context` from state to include in reports:

```python
async def reporting_agent(state: AgentState) -> dict[str, Any]:
    buffer_context = state.get("buffer_context", "")

    if buffer_context:
        # Include buffered context in report generation
        context_message = HumanMessage(
            content=f"Aanvullende context uit luistermodus:\n{buffer_context}"
        )
        messages = list(state["messages"]) + [context_message]
    else:
        messages = state["messages"]

    # ... continue with report generation ...
```

### Wake Word / Trigger Phrase Detection in Listen Mode

**Question**: Can the user trigger a mode swap while in listen mode using a trigger word like "AGORA initiate"?

**Answer**: Yes! This is a "wake word" pattern similar to voice assistants ("Hey Siri", "OK Google").

#### Implementation Approach

The `buffer_message_node` (or a pre-routing function) should scan for trigger phrases before buffering:

```python
# Configurable trigger phrases
WAKE_PHRASES = {
    "agora start": "feedback",      # Switch to feedback mode
    "agora initiate": "feedback",
    "agora feedback": "feedback",
    "agora luister": "listen",      # Switch to listen mode (if in feedback)
    "agora listen": "listen",
}

def detect_wake_phrase(content: str) -> str | None:
    """Detect wake phrase and return target mode, or None if not found."""
    content_lower = content.lower().strip()
    for phrase, target_mode in WAKE_PHRASES.items():
        if content_lower.startswith(phrase):
            return target_mode
    return None


def route_entry(state: AgentState) -> Literal[
    "buffer_message", "process_buffer", "general-agent", "wake_word_handler"
]:
    """Route at entry, checking for wake phrases first."""
    messages = state.get("messages", [])
    mode = state.get("interaction_mode", "feedback")
    buffer = state.get("message_buffer", [])

    # Check latest message for wake phrase
    if messages:
        latest = messages[-1]
        if isinstance(latest, HumanMessage):
            wake_target = detect_wake_phrase(latest.content)
            if wake_target:
                return "wake_word_handler"

    # Normal routing logic
    if mode == "listen":
        return "buffer_message"
    if mode == "feedback" and buffer:
        return "process_buffer"
    return "general-agent"


async def wake_word_handler_node(state: AgentState) -> dict:
    """Handle wake word detection - update mode and route appropriately."""
    messages = state.get("messages", [])
    buffer = state.get("message_buffer", [])

    latest = messages[-1] if messages else None
    if not latest:
        return {}

    wake_target = detect_wake_phrase(latest.content)
    if not wake_target:
        return {}

    # Extract any message content after the wake phrase
    content_lower = latest.content.lower()
    remaining_content = ""
    for phrase in WAKE_PHRASES:
        if content_lower.startswith(phrase):
            remaining_content = latest.content[len(phrase):].strip()
            break

    result = {
        "interaction_mode": wake_target,
    }

    if wake_target == "feedback":
        # Switching TO feedback - acknowledge and process buffer
        if buffer:
            content = "\n".join(f"- {m['content']}" for m in buffer)
            result["buffer_context"] = f"Context uit luistermodus ({len(buffer)} berichten):\n{content}"
            result["message_buffer"] = Overwrite([])

        # If there's content after the wake phrase, include it
        if remaining_content:
            result["messages"] = [HumanMessage(content=remaining_content)]

        result["final_written"] = f"[Feedback modus geactiveerd - {len(buffer)} berichten verwerkt]"
        result["final_spoken"] = "Feedback modus geactiveerd"

    else:  # Switching TO listen
        result["final_written"] = "[Luistermodus geactiveerd]"
        result["final_spoken"] = "Luistermodus geactiveerd"

    return result
```

#### Graph Update for Wake Word Handler

```python
# Add wake word handler node
graph.add_node("wake_word_handler", wake_word_handler_node)

# Update entry routing
graph.add_conditional_edges(
    START,
    route_entry,
    {
        "buffer_message": "buffer_message",
        "process_buffer": "process_buffer",
        "general-agent": "general-agent",
        "wake_word_handler": "wake_word_handler",
    }
)

# Wake word handler routes based on new mode
def route_after_wake(state: AgentState) -> str:
    mode = state.get("interaction_mode", "feedback")
    if mode == "feedback":
        return "general-agent"  # Continue to agent with buffer context
    return END  # Listen mode - just end


graph.add_conditional_edges(
    "wake_word_handler",
    route_after_wake,
    {
        "general-agent": "general-agent",
        END: END,
    }
)
```

#### Wake Phrase Design Considerations

| Phrase | Pro | Con |
|--------|-----|-----|
| `"AGORA start"` | Clear, brand-aligned | Common word "start" |
| `"AGORA initiate"` | Distinctive | Harder to pronounce |
| `"AGORA feedback"` | Self-documenting | Longer |
| `"Hey AGORA"` | Familiar pattern | Very common |

**Recommendation**: Support multiple phrases to accommodate different user preferences and speech recognition accuracy.

---

### Offline / Connectivity Drop Handling

**Question**: Can the same buffering logic handle connectivity drops - dictating during outage and committing when connectivity returns?

**Answer**: This requires **client-side buffering** in addition to server-side. The patterns are complementary but architecturally different.

#### Architecture Layers

```
┌────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (HAI)                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Offline Buffer (IndexedDB/localStorage)                         │  │
│  │  - Stores messages when WebSocket disconnected                   │  │
│  │  - Queues for replay on reconnection                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                    WebSocket │ (when connected)                         │
└────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       BACKEND (server-langgraph)                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Listen Mode Buffer (LangGraph state)                            │  │
│  │  - Stores messages when in listen mode                           │  │
│  │  - Processes on mode change to feedback                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

#### Client-Side Offline Buffering (Frontend)

This is a **separate feature** from listen mode, implemented in the HAI frontend:

```typescript
// HAI/src/lib/websocket/offlineBuffer.ts

interface BufferedMessage {
  id: string;
  content: string;
  timestamp: number;
  threadId: string;
}

class OfflineMessageBuffer {
  private dbName = 'agora-offline-buffer';
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);
      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        db.createObjectStore('messages', { keyPath: 'id' });
      };
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };
      request.onerror = () => reject(request.error);
    });
  }

  async addMessage(message: BufferedMessage): Promise<void> {
    if (!this.db) return;
    const tx = this.db.transaction('messages', 'readwrite');
    tx.objectStore('messages').add(message);
  }

  async getAndClearMessages(): Promise<BufferedMessage[]> {
    if (!this.db) return [];
    return new Promise((resolve) => {
      const tx = this.db!.transaction('messages', 'readwrite');
      const store = tx.objectStore('messages');
      const request = store.getAll();
      request.onsuccess = () => {
        const messages = request.result;
        store.clear(); // Clear after retrieval
        resolve(messages.sort((a, b) => a.timestamp - b.timestamp));
      };
    });
  }
}

// Usage in WebSocket manager
class WebSocketManager {
  private offlineBuffer = new OfflineMessageBuffer();
  private isConnected = false;

  async sendMessage(content: string, threadId: string): Promise<void> {
    if (this.isConnected) {
      // Normal send via WebSocket
      this.ws.send(JSON.stringify({ content, threadId }));
    } else {
      // Buffer for later
      await this.offlineBuffer.addMessage({
        id: crypto.randomUUID(),
        content,
        timestamp: Date.now(),
        threadId,
      });
      // Show user feedback
      this.showOfflineIndicator(`Message saved offline (${await this.getBufferCount()} pending)`);
    }
  }

  async onReconnect(): Promise<void> {
    this.isConnected = true;
    const bufferedMessages = await this.offlineBuffer.getAndClearMessages();

    if (bufferedMessages.length > 0) {
      // Option A: Send as batch with context
      const batchContent = bufferedMessages
        .map(m => `[${new Date(m.timestamp).toLocaleTimeString()}] ${m.content}`)
        .join('\n');

      this.ws.send(JSON.stringify({
        content: `[Offline berichten - ${bufferedMessages.length} items]\n${batchContent}`,
        threadId: bufferedMessages[0].threadId,
        isOfflineBatch: true,
      }));

      // Option B: Send sequentially (preserves individual messages)
      // for (const msg of bufferedMessages) {
      //   await this.sendMessage(msg.content, msg.threadId);
      //   await new Promise(r => setTimeout(r, 100)); // Throttle
      // }
    }
  }
}
```

#### WebSocket Flow During Connectivity Drop

```
Timeline:
─────────────────────────────────────────────────────────────────────────
User dictates    │ Connection │   User continues    │ Reconnect │ Batch
"Checking temp"  │   DROPS    │   dictating offline │  RESTORES │ sent
                 │            │                     │           │
                 ▼            ▼                     ▼           ▼
┌─────────┐    ┌─────────┐  ┌─────────────────┐  ┌─────────┐  ┌────────┐
│ Send OK │    │ Buffer  │  │ Buffer locally  │  │ Replay  │  │ Server │
│ via WS  │    │ locally │  │ (IndexedDB)     │  │ buffer  │  │ process│
└─────────┘    └─────────┘  └─────────────────┘  └─────────┘  └────────┘
```

#### Backend Handling of Offline Batch

The backend can recognize offline batches and process them appropriately:

```python
async def process_message(self, agent_input, protocol_handler):
    user_content = extract_user_content(agent_input)

    # Detect if this is an offline batch
    is_offline_batch = agent_input.context.get("isOfflineBatch", False)

    if is_offline_batch:
        log.info(f"Processing offline batch with {user_content.count(chr(10))} messages")
        # Could optionally set interaction_mode to process batch differently
        # Or add metadata for agents to know this is historical context

    # Rest of normal processing...
```

#### Combining Listen Mode with Offline Buffering

The two features are complementary:

| Scenario | Frontend Buffer | Backend Buffer |
|----------|-----------------|----------------|
| Online + Feedback mode | Not used | Not used |
| Online + Listen mode | Not used | **Active** |
| Offline + Feedback mode | **Active** | Not applicable |
| Offline + Listen mode | **Active** | Will receive on reconnect |

**Flow for "Offline + Listen mode"**:
1. User is in listen mode, connection drops
2. Frontend buffers messages locally (IndexedDB)
3. Connection restores
4. Frontend sends buffered messages
5. Backend receives them and buffers in listen mode state
6. User says "AGORA start" → both buffers processed

---

### Important Consideration: Buffer Persistence

**Challenge**: The current implementation stores the buffer in graph state, which is session-scoped. When in listen mode, each message invocation would normally start with a fresh state.

**Solution**: Use the LangGraph checkpointer to persist state between invocations:

```python
# In orchestrator.py - the checkpointer already persists state per thread_id
config = {"configurable": {"thread_id": thread_id}}

# When invoking, the graph will:
# 1. Load previous state from checkpoint (including message_buffer)
# 2. Apply the new input
# 3. Save the updated state
```

The existing `AsyncSqliteSaver` checkpointer should handle this automatically. However, we need to ensure:
1. The `message_buffer` field is properly initialized on first run
2. The checkpoint is saved after buffering (not just after full runs)

**Alternative**: Store buffer in a separate table outside of graph state, keyed by session_id. This gives more control but requires additional infrastructure.

## Code References

- `server-langgraph/src/agora_langgraph/core/state.py:12-28` - Current AgentState definition
- `server-langgraph/src/agora_langgraph/core/graph.py:58-98` - Current routing logic
- `server-langgraph/src/agora_langgraph/core/graph.py:319-419` - Graph construction
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:121-227` - Message processing
- `server-langgraph/src/agora_langgraph/core/tools.py:77-139` - User settings tool

## Architecture Insights

1. **Minimal Graph Changes**: The approach adds 2 new nodes and 1 conditional edge without modifying existing agent logic
2. **State-Based Mode**: Mode is read from user preferences, consistent with existing `spoken_text_type` pattern
3. **Accumulator Pattern**: Uses LangGraph's reducer pattern already proven with `written`/`spoken` accumulators
4. **Clean Flush**: `Overwrite([])` cleanly resets buffer without requiring custom reducer logic
5. **Checkpointer Integration**: The existing `AsyncSqliteSaver` should persist buffer state between invocations

## Trade-offs Considered

| Approach | Pros | Cons |
|----------|------|------|
| **State-based routing (recommended)** | Minimal graph changes, uses existing patterns, checkpointer handles persistence | Requires mode in every request |
| **Separate subgraph** | Clean separation | More complex, harder to share state |
| **Interrupt-based** | True pause/resume | Requires client-side resume handling |
| **External storage** | Full control over persistence | More infrastructure, not LangGraph-native |
| **Background thread** | Non-blocking | Complex coordination, not serverless-friendly |

## Real-World Analogies

This pattern is similar to:
1. **Meeting transcription assistants** (Otter.ai, Fireflies) - passively listen, summarize later
2. **Healthcare ambient AI scribes** - collect during consultation, generate notes after
3. **LangMem's ReflectionExecutor** - observe now, process delayed

## Open Questions

1. **Buffer persistence**: The checkpointer should handle this, but needs testing
2. **Buffer limits**: Should there be a max buffer size to prevent unbounded growth?
3. **Partial processing**: Should buffer be processed incrementally during listen mode?
4. **Context injection point**: Should buffer context go in system prompt or as a separate message?
5. **Mode change detection**: Should we track `previous_mode` to detect transitions?

## Related Research

- `thoughts/shared/research/2026-01-15-add-feedback-listen-setting.md` - User preference implementation (setting storage)
- `thoughts/shared/research/2026-01-15-langgraph-deterministic-agent-flows.md` - Graph routing patterns

## External References

- [LangMem Delayed Background Processing](https://langchain-ai.github.io/langmem/guides/delayed_processing/)
- [LangGraph State Reducers](https://medium.com/fundamentals-of-artificial-intelligence/langgraph-reducer-function-03cdd621030e)
- [LangGraph Conditional Edges](https://dev.to/jamesli/advanced-langgraph-implementing-conditional-edges-and-tool-calling-agents-3pdn)
- [LangGraph Types Reference (Overwrite)](https://reference.langchain.com/python/langgraph/types/)
- [Introducing Ambient Agents - LangChain](https://www.blog.langchain.com/introducing-ambient-agents/)

## Next Steps

### Phase 1: Core Listen Mode (Backend)
1. Implement state changes in `state.py` - add `interaction_mode`, `message_buffer`, `buffer_context`
2. Add routing and buffer nodes in `graph.py`
3. Update orchestrator to pass `interaction_mode` and handle buffer persistence
4. Test buffer accumulation across multiple invocations
5. Test mode transition and buffer processing

### Phase 2: Wake Word Detection (Backend)
6. Add `WAKE_PHRASES` configuration
7. Implement `detect_wake_phrase()` function
8. Add `wake_word_handler_node` to graph
9. Test wake word triggers: "AGORA start", "AGORA luister", etc.

### Phase 3: Frontend Integration
10. Update frontend to show listen mode indicator
11. Add offline buffer using IndexedDB (`offlineBuffer.ts`)
12. Handle reconnection and batch replay
13. Show offline indicator when disconnected

### Phase 4: Reporting Integration
14. Test report generation with buffered context
15. Ensure `buffer_context` flows through handoffs to reporting agent
