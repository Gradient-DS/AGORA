# Parallel Dual Text Generation Implementation Plan

## Overview

Implement true parallel generation of written and spoken text, where both streams start at the **exact same moment** with **identical context** (all tool results) but **different system prompts**.

## Current State Analysis

### The Bug
**Location**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:352-374`

```python
# BUG: input_state is captured BEFORE graph execution
messages = list(input_state.get("messages", []))  # Only HumanMessage!
spoken_messages = [SystemMessage(content=spoken_prompt)] + messages
```

The spoken generation starts with stale context (only `HumanMessage`), missing all tool results.

### Current Flow (Broken)
```
Graph starts → LLM decides → Tool 1 → Tool 2 → LLM streams →
Written starts (from graph) → Spoken starts (stale context!)
```

### Key Discoveries
- `parallel_streaming.py:45-158` already has `generate_parallel_streams()` that starts both LLM calls simultaneously
- Graph routes to `END` when LLM has no tool_calls (`graph.py:85-87`)
- Agent nodes use `llm.ainvoke()` internally, streaming comes from graph event system
- Tool results ARE tracked in LangGraph state but NOT accumulated for spoken generation

## Desired End State

### Target Flow
```
Graph executes → Tool 1 result → Tool 2 result → Graph ends →
BOTH written and spoken start SIMULTANEOUSLY with [Tool 1, Tool 2] context
```

### Success Verification
1. Run: `python -c "from agora_langgraph.pipelines.orchestrator import Orchestrator"`
2. Send message requiring tools (e.g., "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854")
3. Verify in logs that both `stream_written()` and `stream_spoken()` start at the same timestamp
4. Verify spoken output contains information from tool results (not "geen eerdere overtredingen")

## What We're NOT Doing

- NOT modifying the graph structure (keeping ReAct pattern intact)
- NOT changing how tools are executed or routed
- NOT adding new dependencies
- NOT changing the AG-UI Protocol events (same event types, different timing)

## Implementation Approach

**Key insight**: We already have `generate_parallel_streams()` that does true parallel generation. We need to:

1. Let the graph run to completion (executing tools)
2. Accumulate messages during graph execution (DON'T stream text)
3. After graph ends, extract accumulated messages including tool results
4. Call `generate_parallel_streams()` with accumulated context
5. Stream both written and spoken to frontend

**Trade-off accepted**: The graph's final LLM call (in the agent node) produces output we'll discard. We regenerate with dual prompts. This adds one "wasted" LLM call but achieves true parallel start with shared context. Future optimization can modify the graph to skip final generation.

---

## Phase 1: Message Accumulation During Graph Execution

### Overview
Modify `_stream_response` to accumulate all messages during graph execution without streaming text to frontend. Tool events continue to stream normally.

### Changes Required:

#### 1. Add Message Accumulation Logic
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Add after the variable initialization block (around line 350):

```python
# Message accumulation for deferred dual generation
accumulated_messages: list[BaseMessage] = list(input_state.get("messages", []))
tools_executed = False
```

#### 2. Accumulate Tool Messages
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In the `on_tool_end` handler (around line 491-513), add accumulation:

```python
elif kind == "on_tool_end":
    tool_run_id = event.get("run_id", "")
    tool_name = active_tool_calls.pop(tool_run_id, "unknown")
    output = event.get("data", {}).get("output", "")

    # Mark that tools have executed
    tools_executed = True

    # Accumulate tool message for later dual generation
    tool_message = ToolMessage(
        content=str(output) if output else "",
        tool_call_id=tool_run_id,
        name=tool_name,
    )
    accumulated_messages.append(tool_message)

    # Continue sending to frontend (existing code)
    result_str = str(output)[:500] if output else ""
    # ... rest of existing code ...
```

#### 3. Accumulate AI Messages with Tool Calls
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In the `on_chat_model_end` handler (add new handler around line 520):

```python
elif kind == "on_chat_model_end":
    # Capture AI message with tool_calls for context continuity
    output = event.get("data", {}).get("output")
    if output and hasattr(output, "tool_calls") and output.tool_calls:
        accumulated_messages.append(output)
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Unit tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Add debug logging to verify `accumulated_messages` contains tool results after graph execution

**Implementation Note**: After completing this phase and all automated verification passes, proceed to Phase 2.

---

## Phase 2: Remove Text Streaming from Graph Events

### Overview
Stop streaming text content during graph execution. We'll generate it ourselves in Phase 3.

### Changes Required:

#### 1. Disable Text Streaming in `on_chat_model_stream`
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Modify the `on_chat_model_stream` handler (around line 420-454):

```python
elif kind == "on_chat_model_stream":
    chunk = event.get("data", {}).get("chunk")
    if chunk and hasattr(chunk, "content") and chunk.content:
        content = str(chunk.content)
        # Still accumulate for debugging/fallback
        full_response.append(content)

        # DON'T stream to frontend during graph execution
        # Text will be generated via dual parallel streams after graph completes

        # REMOVE these lines (or comment out):
        # if protocol_handler.is_connected:
        #     if not message_started:
        #         await protocol_handler.send_text_message_start(...)
        #         ...
        #     await protocol_handler.send_text_message_content(message_id, content)
```

#### 2. Remove Old Spoken Generation Trigger
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Remove the existing `generate_spoken_parallel` function definition (lines 352-392) and its invocation in `on_chat_model_stream` (lines 438-443).

Also remove the `stream_spoken_to_frontend` function (lines 394-406).

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`

#### Manual Verification:
- [ ] Sending a message shows tool events but NO text streaming (text appears only after Phase 3)

**Implementation Note**: After completing this phase, the system will be temporarily broken (no text output). Proceed immediately to Phase 3.

---

## Phase 3: Implement True Parallel Dual Generation

### Overview
After graph completes, use `generate_parallel_streams()` to start both written and spoken generation simultaneously with full context.

### Changes Required:

#### 1. Add Imports
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Add at top of file:

```python
from agora_langgraph.core.parallel_streaming import generate_parallel_streams, StreamChunk
from agora_langgraph.core.agent_definitions import get_agent_by_id
```

#### 2. Implement Dual Generation After Graph Completes
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

After the main event loop ends (around line 560), add:

```python
# After graph completes, generate both written and spoken in TRUE PARALLEL
if protocol_handler.is_connected and spoken_mode == "summarize":
    # Get prompts for current agent
    agent_config = get_agent_by_id(current_agent_id)
    written_prompt = agent_config["instructions"] if agent_config else ""
    spoken_prompt = get_spoken_prompt(current_agent_id) or ""

    if written_prompt and spoken_prompt:
        # Get LLM for this agent
        llm = get_llm_for_agent(current_agent_id)

        # Filter out system messages from accumulated (we'll add our own)
        context_messages = [
            m for m in accumulated_messages
            if not isinstance(m, SystemMessage)
        ]

        # Send message starts for both streams
        await protocol_handler.send_text_message_start(message_id, "assistant")
        await protocol_handler.send_spoken_text_start(message_id, "assistant")
        message_started = True
        spoken_message_started = True

        # Generate BOTH streams in TRUE PARALLEL
        full_written: list[str] = []
        full_spoken: list[str] = []

        async for chunk in generate_parallel_streams(
            llm=llm,
            messages=context_messages,
            written_prompt=written_prompt,
            spoken_prompt=spoken_prompt,
            on_spoken_error=lambda code, msg: protocol_handler.send_spoken_text_error(
                message_id, code, msg
            ),
        ):
            if chunk.stream_type == "written":
                full_written.append(chunk.content)
                await protocol_handler.send_text_message_content(message_id, chunk.content)
            else:  # spoken
                full_spoken.append(chunk.content)
                await protocol_handler.send_spoken_text_content(message_id, chunk.content)

        # Update full_response for logging
        full_response = full_written

        log.info(f"Dual generation complete: written={len(''.join(full_written))} chars, spoken={len(''.join(full_spoken))} chars")
```

#### 3. Handle Dictate Mode (Fallback)
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Add after the parallel generation block:

```python
elif protocol_handler.is_connected and spoken_mode == "dictate":
    # In dictate mode, we still need to generate written text
    # and duplicate it to spoken (no parallel generation needed)
    agent_config = get_agent_by_id(current_agent_id)
    written_prompt = agent_config["instructions"] if agent_config else ""

    if written_prompt:
        llm = get_llm_for_agent(current_agent_id)
        context_messages = [
            m for m in accumulated_messages
            if not isinstance(m, SystemMessage)
        ]

        written_messages = [SystemMessage(content=written_prompt)] + context_messages

        await protocol_handler.send_text_message_start(message_id, "assistant")
        await protocol_handler.send_spoken_text_start(message_id, "assistant")
        message_started = True
        spoken_message_started = True

        async for chunk in llm.astream(written_messages):
            if hasattr(chunk, "content") and chunk.content:
                content = str(chunk.content)
                full_response.append(content)
                await protocol_handler.send_text_message_content(message_id, content)
                # Dictate: same content to spoken
                await protocol_handler.send_spoken_text_content(message_id, content)
```

#### 4. Handle No Tools Case
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

When no tools were executed, we can still use dual generation with just the user message:

```python
# If no tools were executed, accumulated_messages is just [HumanMessage]
# The dual generation still works - both streams get the same (minimal) context
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Unit tests pass: `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Send message requiring tools (e.g., "Start inspectie bij Restaurant Bella Rosa")
- [ ] Verify BOTH text and spoken text appear in UI
- [ ] Verify spoken text contains information from tool results
- [ ] Verify both streams start at approximately the same time (check timestamps in logs)
- [ ] Verify tool events still stream in real-time before text generation starts

**Implementation Note**: After completing this phase and all verification passes, pause for manual confirmation.

---

## Phase 4: Cleanup and Optimization

### Overview
Remove dead code, add logging, and document the new architecture.

### Changes Required:

#### 1. Remove Unused Variables
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Remove these now-unused variables:
- `spoken_task` (line 349)
- `spoken_queue` (line 350)

#### 2. Add Performance Logging
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Add timing logs:

```python
import time

# Before dual generation
dual_gen_start = time.time()
log.info(f"Starting dual generation after {len(accumulated_messages)} messages accumulated")

# After dual generation
log.info(f"Dual generation completed in {time.time() - dual_gen_start:.2f}s")
```

#### 3. Update Debug Prints
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Update the debug prints (around line 558) to reflect new architecture:

```python
print(f"Accumulated {len(accumulated_messages)} messages for dual generation")
print(f"Tools executed: {tools_executed}")
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] No unused imports: `ruff check src/ --select F401`

#### Manual Verification:
- [ ] Logs show timing information
- [ ] No runtime errors during normal operation

---

## Testing Strategy

### Unit Tests
Add tests in `server-langgraph/tests/`:

```python
# test_parallel_generation.py
import pytest
from agora_langgraph.core.parallel_streaming import generate_parallel_streams

@pytest.mark.asyncio
async def test_parallel_streams_start_simultaneously():
    """Both streams should start at approximately the same time."""
    # TODO: Mock LLM and verify both tasks start within 100ms of each other
    pass

@pytest.mark.asyncio
async def test_parallel_streams_same_context():
    """Both streams should receive identical message context."""
    # TODO: Verify messages passed to both streams are identical
    pass
```

### Integration Tests
```python
# test_orchestrator_dual_gen.py
@pytest.mark.asyncio
async def test_spoken_receives_tool_results():
    """Spoken generation should have access to tool results."""
    # Send message that triggers tools
    # Verify spoken output contains information from tool results
    pass
```

### Manual Testing Steps
1. Start the server: `python -m agora_langgraph.api.server`
2. Connect HAI frontend
3. Send: "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854"
4. Observe:
   - Tool events stream first (company lookup, history check)
   - THEN both written and spoken start streaming
   - Spoken output should mention any warnings/violations found

## Performance Considerations

### Added Latency
- **Before**: Text streaming started during graph execution
- **After**: Text streaming starts after graph completes

This adds latency equal to the graph execution time (typically 1-5 seconds for tool calls). However, the user explicitly requested this trade-off for consistency.

### LLM Call Overhead
- The graph's final LLM call is now "wasted" (we regenerate with dual prompts)
- Future optimization: Modify graph to skip final generation when dual-gen is enabled

### Memory
- `accumulated_messages` stores all messages in memory during graph execution
- This is bounded by conversation length and should not be a concern

## Migration Notes

### Breaking Changes
- None for external APIs
- Internal: `generate_spoken_parallel` function removed
- Internal: `stream_spoken_to_frontend` function removed

### Rollback
If issues arise, revert to previous commit. The changes are isolated to `orchestrator.py`.

## Future Optimizations

1. **Skip graph's final LLM call**: Modify graph to return before final generation when `spoken_mode == "summarize"`
2. **Streaming tool results**: Could potentially start dual-gen as soon as "key" tools complete (Approach 3 from research)
3. **Caching**: Cache tool results to avoid re-fetching if user asks follow-up questions

## References

- Research document: `thoughts/shared/research/2025-01-15-spoken-written-shared-context-design.md`
- Existing parallel streaming utility: `server-langgraph/src/agora_langgraph/core/parallel_streaming.py`
- Graph structure: `server-langgraph/src/agora_langgraph/core/graph.py`
- Agent definitions: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
