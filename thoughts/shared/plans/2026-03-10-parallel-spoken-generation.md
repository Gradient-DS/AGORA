# Parallel Spoken Generation — Implementation Plan

## Overview

Move spoken text generation out of the LangGraph state graph and into the orchestrator as a direct async LLM call. This eliminates the sequential dependency where spoken generation blocks the graph from ending, and allows the graph to finish immediately after the agent responds.

## Current State Analysis

After the context window optimization (Phases 1-3), the flow is:

```
Agent streams text → route_from_agent → Send(generate_spoken) → generate_spoken (LLM) → merge → END
                     ^^^ graph continues running ^^^
```

The spoken LLM call adds latency between the agent finishing and the graph ending. During this time:
- The orchestrator is still in the `astream_events` loop
- The client has already received all written text
- The graph is just waiting for spoken generation + merge

### Key files

- `core/graph.py:253-293` — `route_from_agent`: returns `_create_spoken_send(state)` when no tool calls
- `core/graph.py:325-393` — `_create_spoken_send`: builds filtered messages for spoken model
- `core/graph.py:396-471` — `_generate_stream`: the LLM call for spoken generation
- `core/graph.py:474-480` — `generate_spoken_node`: graph node wrapper
- `core/graph.py:483-545` — `merge_parallel_outputs`: stamps `is_final_response` + `spoken_text` on AIMessage
- `core/graph.py:601-684` — `build_agent_graph`: graph construction with spoken nodes + edges
- `core/state.py:38-39` — `spoken: Annotated[list[str], operator.add]` accumulator
- `core/state.py:49-57` — `GeneratorState` (only used by spoken generation)
- `core/agents.py:260-262` — `get_llm_for_spoken()`: cached spoken LLM singleton
- `core/agent_definitions.py:350-436` — `SPOKEN_AGENT_PROMPTS`: per-agent spoken prompts
- `pipelines/orchestrator.py:612-1101` — `_stream_response`: event streaming + post-stream handling
- `pipelines/orchestrator.py:726-740` — spoken chunk routing from `generate_spoken` events

### Key discovery: `final_spoken` is only used as listen-mode fallback

In the normal streaming path (feedback mode), the orchestrator streams spoken chunks directly from `on_chat_model_stream` events tagged with `node_name == "generate_spoken"`. The `final_spoken` graph state value is only read in the post-stream section (line 1050) as a fallback for listen mode responses where no LLM streaming occurs.

### Key discovery: `merge_parallel_outputs` does two things

1. Stamps `is_final_response=True` on the agent's AIMessage (used by Phase 2 context filtering in `_build_agent_messages`)
2. Sets `spoken_text` in `additional_kwargs` (used by `_build_history` for conversation history reconstruction)

Both need to be preserved when removing merge from the graph.

## Desired End State

```
Agent streams text → finalize_response (stamps is_final_response) → END  ← graph ends immediately
                                                                         ← orchestrator calls spoken LLM directly
                                                                         ← spoken streams to client
```

### Expected results

| Metric | Before | After |
|--------|--------|-------|
| Graph duration after agent finishes | spoken_LLM_time + merge | ~0ms (just finalize) |
| Spoken generation latency | Same | Same (but no longer blocks graph) |
| Total end-to-end time | agent + graph_overhead + spoken + merge | agent + spoken (overlaps with post-stream) |

### How to verify

1. Run the demo scenario (postcode lookup → regulation question → report)
2. Observe that written text appears immediately when agent finishes
3. Observe that spoken audio follows shortly after
4. Check `context_window.log` — no `generate_spoken` entries
5. Check conversation history (`GET /sessions/{id}/history`) still contains `spoken_text`

## What We're NOT Doing

- Not changing the spoken LLM provider configuration (same model, same prompts)
- Not changing dictate mode behavior (still duplicates written to spoken channel)
- Not changing listen mode behavior (still uses `final_spoken` from graph state for wake word responses)
- Not changing the spoken prompt content
- Not removing context_window.log instrumentation

## Implementation Approach

Two phases:

1. **Remove spoken from graph** — replace `generate_spoken` + `merge` with a `finalize_response` node, route agent → finalize → END
2. **Add spoken generation to orchestrator** — after graph stream ends, call spoken LLM directly, stream chunks, update AIMessage with `spoken_text`

---

## Phase 1: Remove Spoken Generation from Graph

### Overview

Remove `generate_spoken_node`, `merge_parallel_outputs`, `_create_spoken_send`, `_generate_stream`, and associated graph nodes/edges. Replace with a simple `finalize_response` node that stamps `is_final_response` on the agent's AIMessage and sets `final_written`.

### Changes Required

#### 1. Add `finalize_response` node, remove spoken/merge nodes

**File**: `core/graph.py`

Replace `_create_spoken_send`, `_generate_stream`, `generate_spoken_node`, and `merge_parallel_outputs` with a single `finalize_response` function:

```python
def finalize_response(state: AgentState) -> dict[str, Any]:
    """Mark the agent's response as final and set final_written.

    This replaces the old merge_parallel_outputs node. It stamps
    is_final_response on the agent's AIMessage (used by _build_agent_messages
    for context filtering) and sets final_written for listen-mode fallback.
    """
    messages = state.get("messages", [])
    written_content = ""
    agent_msg = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            written_content = extract_text(msg.content)
            agent_msg = msg
            break

    log.info(f"finalize_response: {len(written_content)} chars")

    result: dict[str, Any] = {
        "final_written": written_content,
    }

    # Update the agent's AIMessage with is_final_response marker
    # Using the same ID triggers add_messages reducer to REPLACE (not append)
    if agent_msg:
        updated_kwargs = {**agent_msg.additional_kwargs}
        updated_kwargs["is_final_response"] = True
        updated_msg = AIMessage(
            content=agent_msg.content,
            id=agent_msg.id,
            additional_kwargs=updated_kwargs,
        )
        result["messages"] = [updated_msg]

    return result
```

#### 2. Update `route_from_agent` to return `"finalize_response"`

**File**: `core/graph.py`

Change the return type and all returns of `_create_spoken_send(state)` to `"finalize_response"`:

```python
def route_from_agent(
    state: AgentState,
) -> Literal["tools", "finalize_response"]:
    """Route from any agent based on the last message."""
    current_agent = state.get("current_agent", "unknown")
    messages = state.get("messages", [])

    log.info(
        f"route_from_agent: current_agent={current_agent}, num_messages={len(messages)}"
    )

    if not messages:
        return "finalize_response"

    last_message = messages[-1]

    if not isinstance(last_message, AIMessage):
        return "finalize_response"

    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        log.info("route_from_agent: No tool calls, finalizing response")
        return "finalize_response"

    tool_name = tool_calls[0].get("name", "")
    log.info(f"route_from_agent: Tool call '{tool_name}' → routing to ToolNode first")
    return "tools"
```

#### 3. Update graph construction in `build_agent_graph`

**File**: `core/graph.py` — `build_agent_graph`

Replace spoken/merge nodes with finalize_response:

```python
# REMOVE these lines:
graph.add_node("generate_spoken", generate_spoken_node)
graph.add_node("merge", merge_parallel_outputs)

# ADD:
graph.add_node("finalize_response", finalize_response)

# UPDATE conditional edges — replace ["tools", "generate_spoken"] with ["tools", "finalize_response"]:
graph.add_conditional_edges(
    agent_id,
    route_from_agent,
    ["tools", "finalize_response"],
)

# For no-tools case:
graph.add_conditional_edges(
    agent_id,
    route_from_agent,
    ["finalize_response"],
)

# REMOVE these edges:
graph.add_edge("generate_spoken", "merge")
graph.add_edge("merge", END)

# ADD:
graph.add_edge("finalize_response", END)
```

#### 4. Remove dead code from `graph.py`

Delete these functions (no longer used):
- `_create_spoken_send`
- `_generate_stream`
- `generate_spoken_node`
- `merge_parallel_outputs`

Remove now-unused imports:
- `Send` from `langgraph.types` (check if still used elsewhere in file first)
- `get_spoken_prompt` from `agent_definitions` (moves to orchestrator)
- `get_llm_for_spoken` from `agents` (moves to orchestrator)
- `_log_context_window` from `agents` (was only used in `_generate_stream`)
- `GeneratorState` from `state` (no longer needed in graph)

#### 5. Remove `spoken` accumulator and `GeneratorState` from state

**File**: `core/state.py`

```python
# REMOVE:
spoken: Annotated[list[str], operator.add]

# REMOVE operator import if unused after this
# Check: is operator.add still used anywhere? No — spoken was the last user.

# REMOVE GeneratorState class entirely (only used by generate_spoken_node)
```

Also remove `final_spoken` from `AgentState` — the orchestrator will handle spoken text entirely outside the graph. The listen-mode spoken responses (`wake_word_handler_node` at graph.py:167 sets `final_spoken`) need to be handled differently — see Phase 2.

Wait — `wake_word_handler_node` and `buffer_message_node` set `final_spoken`. These listen-mode responses need spoken text without an LLM call. Keep `final_spoken` in `AgentState` for this purpose.

```python
# KEEP final_spoken (used by listen mode nodes)
# REMOVE spoken accumulator and GeneratorState only
```

### Success Criteria

#### Automated Verification:
- [x] Server starts without errors
- [x] All existing tests pass
- [x] No references to `generate_spoken` node name in graph construction
- [x] No references to `merge` node name in graph construction
- [x] `_create_spoken_send`, `_generate_stream`, `generate_spoken_node`, `merge_parallel_outputs` are all removed

#### Manual Verification:
- [ ] Written response appears immediately when agent finishes
- [ ] Graph ends quickly after agent response (check server logs for timing)
- [ ] Listen mode still works (buffer messages, wake word activation)

**Implementation Note**: After completing this phase and all automated verification passes, proceed to Phase 2 immediately (spoken generation will be missing until Phase 2 is complete).

---

## Phase 2: Add Spoken Generation to Orchestrator

### Overview

After the graph stream ends, the orchestrator calls the spoken LLM directly and streams chunks to the client. This runs immediately after the graph finishes — the graph no longer waits for spoken generation.

### Changes Required

#### 1. Add `_generate_spoken` method to Orchestrator

**File**: `pipelines/orchestrator.py`

Add a new method that generates spoken text outside the graph:

```python
async def _generate_spoken(
    self,
    agent_id: str,
    messages: list[BaseMessage],
    message_id: str,
    protocol_handler: Any,
) -> str:
    """Generate spoken text outside the graph and stream to client.

    Called after the graph finishes. Uses the same spoken LLM and prompts
    as the old generate_spoken graph node, but runs independently.

    Args:
        agent_id: Current agent ID (for prompt selection)
        messages: Filtered conversation messages for spoken context
        message_id: AG-UI message ID for protocol events
        protocol_handler: WebSocket protocol handler

    Returns:
        Complete spoken text content
    """
    from agora_langgraph.core.agent_definitions import get_spoken_prompt
    from agora_langgraph.core.agents import get_llm_for_spoken

    spoken_prompt = get_spoken_prompt(agent_id)
    if not spoken_prompt:
        log.warning(f"No spoken prompt for {agent_id}, skipping spoken generation")
        return ""

    llm = get_llm_for_spoken()
    full_messages: list[BaseMessage] = [SystemMessage(content=spoken_prompt)] + list(messages)

    spoken_parts: list[str] = []
    spoken_started = False

    try:
        async for chunk in llm.astream(full_messages):
            if hasattr(chunk, "content") and chunk.content:
                content = extract_text(chunk.content)
                if not content:
                    continue

                if not spoken_started and protocol_handler.is_connected:
                    await protocol_handler.send_spoken_text_start(message_id, "assistant")
                    spoken_started = True

                spoken_parts.append(content)
                if protocol_handler.is_connected:
                    await protocol_handler.send_spoken_text_content(message_id, content)
    except Exception as e:
        log.error(f"Spoken generation failed: {e}", exc_info=True)

    return "".join(spoken_parts)
```

#### 2. Add `_build_spoken_messages` helper

**File**: `pipelines/orchestrator.py`

Build the filtered message list for spoken context (equivalent to what `_create_spoken_send` did):

```python
@staticmethod
def _build_spoken_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Build filtered message list for spoken generation.

    Prior completed turns: only HumanMessages + final AI responses
    Current turn: only HumanMessages + agent's final AIMessage
    No tool results — the agent's response already incorporates them.
    """
    # Find the last completed turn boundary
    last_final_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if (
            isinstance(messages[i], AIMessage)
            and messages[i].additional_kwargs.get("is_final_response")
        ):
            last_final_idx = i
            break

    filtered: list[BaseMessage] = []

    # Prior turns: only HumanMessages + final responses
    if last_final_idx >= 0:
        for msg in messages[: last_final_idx + 1]:
            if isinstance(msg, HumanMessage):
                filtered.append(msg)
            elif (
                isinstance(msg, AIMessage)
                and msg.additional_kwargs.get("is_final_response")
            ):
                filtered.append(msg)

    # Current turn: only HumanMessages + agent's final AIMessage
    for msg in messages[last_final_idx + 1 :]:
        if isinstance(msg, HumanMessage):
            filtered.append(msg)
        elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            filtered.append(msg)

    return filtered
```

#### 3. Update `_stream_response` — remove spoken event routing, add post-stream spoken generation

**File**: `pipelines/orchestrator.py` — `_stream_response`

**3a. Remove spoken chunk routing from the event loop.**

Remove the `elif node_name == "generate_spoken":` block (lines ~726-740). The graph no longer emits spoken stream events.

**3b. After the graph stream loop ends and interrupt checking completes, generate spoken text.**

In the post-stream section (after interrupt detection, before channel finalization), add:

```python
# Generate spoken text outside the graph (only in summarize mode, non-interrupt)
if spoken_mode == "summarize" and not graph_was_interrupted and message_started:
    try:
        # Get conversation messages from final state
        state_messages = final_state.values.get("messages", []) if final_state and final_state.values else []
        if state_messages:
            spoken_messages = self._build_spoken_messages(state_messages)
            spoken_content = await self._generate_spoken(
                agent_id=current_agent_id,
                messages=spoken_messages,
                message_id=message_id,
                protocol_handler=protocol_handler,
            )
            spoken_message_started = bool(spoken_content)

            # Update AIMessage in graph state with spoken_text for history
            if spoken_content and final_state:
                # Find the agent's final AIMessage and update it
                for msg in reversed(state_messages):
                    if (
                        isinstance(msg, AIMessage)
                        and msg.additional_kwargs.get("is_final_response")
                    ):
                        updated_kwargs = {**msg.additional_kwargs}
                        updated_kwargs["spoken_text"] = spoken_content
                        updated_msg = AIMessage(
                            content=msg.content,
                            id=msg.id,
                            additional_kwargs=updated_kwargs,
                        )
                        await self.graph.aupdate_state(
                            config,
                            {"messages": [updated_msg]},
                        )
                        break
    except Exception as e:
        log.warning(f"Failed to generate spoken text: {e}", exc_info=True)
```

**3c. Update the listen-mode fallback.**

The listen-mode section (line ~1048-1081) reads `final_spoken` from graph state. This still works because `wake_word_handler_node` and `buffer_message_node` set `final_spoken` directly. No changes needed here.

#### 4. Add `SystemMessage` import to orchestrator

**File**: `pipelines/orchestrator.py`

Add `SystemMessage` to the existing `langchain_core.messages` import (currently only imports `AIMessage, HumanMessage`):

```python
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
```

Also add `BaseMessage` if not already imported (needed for type hints in `_build_spoken_messages`).

#### 5. Clean up graph.py imports

**File**: `core/graph.py`

After removing the spoken generation functions, clean up imports that are no longer used:
- `Send` from `langgraph.types` — check if still used; if only by `_create_spoken_send`, remove
- `get_spoken_prompt` from `agent_definitions` — only used by removed `_create_spoken_send`
- `get_llm_for_spoken`, `get_llm_for_agent` from `agents` — only used by removed `_generate_stream`
- `_log_context_window` from `agents` — only used by removed `_generate_stream`
- `GeneratorState` from `state` — only used by removed `_create_spoken_send`
- `SystemMessage` from `langchain_core.messages` — check if still used elsewhere in graph.py

Keep: `AIMessage`, `BaseMessage`, `HumanMessage`, `ToolMessage` (used by routing functions), `extract_text` (used by multiple functions).

### Success Criteria

#### Automated Verification:
- [x] Server starts without errors
- [x] All existing tests pass
- [x] No references to `generate_spoken`, `merge`, `_create_spoken_send`, `_generate_stream` in codebase
- [x] `GeneratorState` class removed from state.py
- [x] `spoken` accumulator removed from AgentState

#### Manual Verification:
- [ ] Written response appears immediately when agent finishes
- [ ] Spoken audio summary generates and plays correctly (summarize mode)
- [ ] Dictate mode still works (written text duplicated to spoken channel)
- [ ] Listen mode → wake word → feedback mode transition still works
- [ ] Tool approval flow (reporting-agent) still works
- [ ] Clarification request flow still works
- [ ] Conversation history (`GET /sessions/{id}/history`) contains `spoken_text`
- [ ] `context_window.log` shows NO `generate_spoken` entries

---

## Code Cleanup After Both Phases

- Remove `is_handoff_tool` from graph.py if confirmed unused (currently defined but never called after Phase 1-3 changes)
- Update comments referencing "parallel generation" or "generate_spoken node"
- Update `get_conversation_history` docstring (line 1108) — remove reference to "parallel generation architecture"

## Testing Strategy

### Full scenario test (DEMO_SCENARIOS.md):
1. Start inspection: "Ik ga op inspectie bij postcode 2521 DJ huisnummer 45"
2. Listen mode: "luister modus"
3. Buffer messages during listen mode
4. Wake word: "Agora, welke regelgeving wordt hier overtreden?"
5. Report: "genereer rapport"

### Verify at each step:
- Written text streams immediately from agent
- Spoken text generates after graph ends (check timing in logs)
- No `generate_spoken` node appears in astream_events
- `spoken_text` appears in conversation history

### Edge cases:
- First message in new session (no prior turns)
- Listen mode → wake word transition (uses `final_spoken` from graph state, not orchestrator)
- Clarification request interrupt (no spoken generation should fire)
- Tool approval interrupt (no spoken generation should fire)
- Dictate mode (spoken comes from written duplication, no spoken LLM call)
- Empty agent response (edge case — no spoken generation)
- Spoken LLM failure (should not crash, log warning)

## References

- Context window optimization plan: `thoughts/shared/plans/2026-03-10-context-window-optimization.md`
- Spoken prompts: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:350-436`
