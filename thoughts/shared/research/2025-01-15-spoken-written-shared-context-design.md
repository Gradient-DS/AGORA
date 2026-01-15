---
date: 2025-01-15T11:30:00+01:00
researcher: Claude
git_commit: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
branch: main
repository: AGORA
topic: "Design: Shared Context for Written and Spoken Text Generation"
tags: [research, design, server-langgraph, dual-generation, tts, spoken-text, streaming]
status: complete
last_updated: 2025-01-15
last_updated_by: Claude
---

# Design: Shared Context for Written and Spoken Text Generation

**Date**: 2025-01-15T11:30:00+01:00
**Researcher**: Claude
**Git Commit**: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
**Branch**: main
**Repository**: AGORA

## Problem Statement

The current dual-generation pattern produces inconsistent outputs because the spoken text is generated from **incomplete context**:

- **Written text**: Receives full conversation history including all tool call results
- **Spoken text**: Only receives the initial `HumanMessage` and system prompt, missing tool results

### Example from Logs

**User query**: "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854"

**Tool results available**: Company has 1 hygiene warning from 2022, open follow-up action

**Written output** (correct):
> "Er is een waarschuwing gegeven voor hygiënemaatregelen in 2022... OPENSTAANDE ACTIES voor follow-up"

**Spoken output** (incorrect):
> "Restaurant Bella Rosa heeft geen eerdere overtredingen."

## Root Cause Analysis

**Location**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:372-374`

```python
# BUG: input_state is captured BEFORE graph execution (line 201-207)
# It only contains the initial HumanMessage, not tool results
messages = list(input_state.get("messages", []))
spoken_messages = [SystemMessage(content=spoken_prompt)] + messages
```

**Timeline**:
```
1. input_state created (line 201-207) ──────────► Contains only HumanMessage
2. graph.astream_events() starts
3. Tools execute (check_company_exists, get_inspection_history)
4. First content chunk arrives
5. generate_spoken_parallel() starts ──────────► Still uses stale input_state!
6. Written stream completes with full context
7. Spoken stream produces incorrect summary
```

## Design Approaches

### Approach 1: Summarize-After-Write (Recommended)

**Concept**: Generate spoken text as a summary of the already-generated written text.

**Flow**:
```
Written LLM ─────────────────────────────────────► Full Response
                                                        │
                                                        ▼
                                        ┌───────────────────────────┐
                                        │  Spoken LLM (summary)     │
                                        │  Input: written response  │
                                        └───────────────────────────┘
                                                        │
                                                        ▼
                                                  Spoken Summary
```

**Implementation**:
```python
async def _stream_response(...):
    # ... existing streaming code ...

    # After written stream completes
    full_written_text = "".join(full_response)

    # Generate spoken as summary of written
    if spoken_mode == "summarize":
        spoken_task = asyncio.create_task(
            generate_spoken_from_written(current_agent_id, full_written_text)
        )
        asyncio.create_task(stream_spoken_to_frontend())

async def generate_spoken_from_written(agent_id: str, written_text: str) -> None:
    """Generate spoken summary from the written response."""
    spoken_prompt = get_spoken_prompt(agent_id)
    llm = get_llm_for_agent(agent_id)

    # Instruct LLM to summarize the written response for TTS
    messages = [
        SystemMessage(content=spoken_prompt),
        HumanMessage(content=f"Vat het volgende antwoord samen in 2-3 zinnen voor spraak:\n\n{written_text}")
    ]

    async for chunk in llm.astream(messages):
        if chunk.content:
            await spoken_queue.put(str(chunk.content))
    await spoken_queue.put(None)
```

**Pros**:
- Perfect consistency (spoken literally summarizes written)
- Simple implementation
- No context reconstruction needed
- Spoken can never be more "informed" than written

**Cons**:
- Spoken stream starts after written completes (added latency)
- User sees written response complete before hearing anything

**Latency Impact**: ~2-3 seconds additional delay (TTS summary generation time)

---

### Approach 2: Deferred Context Injection

**Concept**: Start spoken generation when we have complete context, not at first content chunk.

**Flow**:
```
graph.astream_events()
        │
        ├── on_tool_end ────────► Accumulate tool results
        │
        ├── on_chat_model_stream ──► Stream written text
        │                              │
        │                              ▼ (first chunk)
        │                         send_text_message_start()
        │                         send_spoken_text_start()
        │                              │
        │                              ▼ (stream continues...)
        │
        └── Event stream ends ──► NOW start spoken with full context
                                        │
                                        ▼
                              generate_spoken_parallel(final_state)
```

**Implementation**:
```python
async def _stream_response(...):
    accumulated_messages: list[BaseMessage] = list(input_state.get("messages", []))

    async for event in self.graph.astream_events(...):
        if kind == "on_chat_model_stream":
            # ... stream written content ...

        elif kind == "on_tool_end":
            # Accumulate tool messages for later spoken generation
            tool_msg = ToolMessage(
                content=str(output),
                tool_call_id=tool_run_id,
                name=tool_name
            )
            accumulated_messages.append(tool_msg)

        elif kind == "on_chat_model_end":
            # Capture AI response with tool calls if any
            ai_msg = event.get("data", {}).get("output")
            if ai_msg:
                accumulated_messages.append(ai_msg)

    # After stream completes, generate spoken with full context
    if spoken_mode == "summarize":
        spoken_task = asyncio.create_task(
            generate_spoken_parallel(current_agent_id, accumulated_messages)
        )

async def generate_spoken_parallel(agent_id: str, full_messages: list) -> None:
    spoken_prompt = get_spoken_prompt(agent_id)
    llm = get_llm_for_agent(agent_id)

    spoken_messages = [SystemMessage(content=spoken_prompt)] + full_messages
    async for chunk in llm.astream(spoken_messages):
        await spoken_queue.put(str(chunk.content))
```

**Pros**:
- Same context structure as written (messages + tool results)
- More faithful to original dual-generation intent
- Spoken prompt can still produce concise output

**Cons**:
- More complex message accumulation logic
- Need to track AI messages with tool_calls for context continuity
- Similar latency to Approach 1

---

### Approach 3: Progressive Spoken Start with Context Sync

**Concept**: Start spoken stream when we have "enough" context (key tool results received).

**Flow**:
```
on_tool_end("check_company_exists") ──► Minor tool, don't start yet
on_tool_end("get_inspection_history") ──► Key tool! Start spoken now
                                               │
                                               ▼
                                    generate_spoken_parallel()
                                    (with accumulated context)
```

**Implementation**:
```python
KEY_TOOLS = {"get_inspection_history", "search_regulations", "generate_report"}

async def _stream_response(...):
    accumulated_context: list[BaseMessage] = []
    spoken_started = False

    async for event in self.graph.astream_events(...):
        if kind == "on_tool_end":
            # ... accumulate tool result ...

            # Start spoken after key tool completes
            if tool_name in KEY_TOOLS and not spoken_started:
                spoken_started = True
                spoken_task = asyncio.create_task(
                    generate_spoken_parallel(current_agent_id, accumulated_context.copy())
                )
```

**Pros**:
- Reduces latency by starting spoken earlier
- Spoken begins with contextually relevant information

**Cons**:
- Requires maintaining list of "key" tools per agent
- May miss context from tools that run after spoken starts
- Complex to maintain and debug

---

### Approach 4: Single LLM with Dual Output (Structured Output)

**Concept**: Use a single LLM call that produces both written and spoken versions simultaneously.

**Flow**:
```
Single LLM Call
        │
        ├── structured_output.written ──► Written stream
        │
        └── structured_output.spoken ───► Spoken stream (or generated inline)
```

**Implementation**:
```python
from pydantic import BaseModel

class DualResponse(BaseModel):
    written: str  # Full detailed response
    spoken: str   # 2-3 sentence TTS summary

async def _stream_response(...):
    llm_with_structured = llm.with_structured_output(DualResponse)

    # Single call produces both outputs
    response = await llm_with_structured.ainvoke(messages)

    # Stream written
    await protocol_handler.send_text_message_content(message_id, response.written)

    # Stream spoken
    await protocol_handler.send_spoken_text_content(message_id, response.spoken)
```

**Pros**:
- Single LLM call (cost efficient)
- Perfect context consistency (same call produces both)
- No timing/coordination issues

**Cons**:
- Cannot stream (structured output is non-streaming in most frameworks)
- Changes the fundamental streaming architecture
- May produce worse quality (LLM has two objectives)
- Breaks existing AG-UI Protocol streaming expectations

---

### Approach 5: Parallel Start with Shared Context Queue

**Concept**: Both streams start together, but spoken waits for context updates via queue.

**Flow**:
```
┌─────────────────────────────────────────────────────────────┐
│                    Context Queue                             │
│  [HumanMsg] → [ToolResult1] → [ToolResult2] → [DONE]        │
└─────────────────────────────────────────────────────────────┘
        │                                    │
        ▼                                    ▼
┌───────────────┐                  ┌──────────────────────┐
│  Written LLM  │                  │    Spoken LLM        │
│  (streaming)  │                  │  (waits for DONE     │
│               │                  │   then generates)    │
└───────────────┘                  └──────────────────────┘
```

**Implementation**:
```python
async def _stream_response(...):
    context_queue: asyncio.Queue[BaseMessage | None] = asyncio.Queue()

    # Start both tasks
    spoken_task = asyncio.create_task(
        generate_spoken_with_context_queue(agent_id, context_queue)
    )

    async for event in self.graph.astream_events(...):
        if kind == "on_tool_end":
            await context_queue.put(tool_message)
        # ... stream written ...

    # Signal context complete
    await context_queue.put(None)

async def generate_spoken_with_context_queue(agent_id: str, context_queue: Queue) -> None:
    messages = [SystemMessage(content=get_spoken_prompt(agent_id))]

    # Accumulate all context first
    while True:
        msg = await context_queue.get()
        if msg is None:
            break
        messages.append(msg)

    # Now generate with full context
    async for chunk in llm.astream(messages):
        await spoken_queue.put(str(chunk.content))
```

**Pros**:
- Clean separation via queue
- Spoken waits for complete context naturally
- Easy to extend with additional context sources

**Cons**:
- Same latency as Approach 1/2 (spoken still waits)
- Added complexity of queue coordination

---

## Recommendation

**Primary: Approach 1 (Summarize-After-Write)**

This is the most elegant solution because:

1. **Guaranteed Consistency**: Spoken literally summarizes written output
2. **Simplicity**: No complex context reconstruction or message tracking
3. **Debuggability**: Easy to log and verify spoken input
4. **User Experience**: Users can read while waiting for audio
5. **Correctness**: Impossible for spoken to have different information than written

**Implementation Effort**: ~30 lines of code change

**Alternative: Approach 2 (Deferred Context Injection)**

If you want to maintain the original "same context, different prompt" pattern:
- More complex but preserves the dual-prompt architecture
- Better if you want spoken to have different emphasis than written

## Implementation Sketch (Approach 1)

```python
# orchestrator.py changes

async def _stream_response(...):
    # ... existing code until line 558 ...

    full_written_text = "".join(full_response)
    print(f"Full response: {full_written_text}")
    print("########################################################")

    # Generate spoken AFTER written completes (Approach 1)
    if spoken_mode == "summarize" and full_written_text:
        spoken_task = asyncio.create_task(
            generate_spoken_from_written(current_agent_id, full_written_text)
        )
        asyncio.create_task(stream_spoken_to_frontend())

        # Wait for spoken to complete
        try:
            await spoken_task
        except Exception as e:
            log.error(f"Spoken task failed: {e}")

async def generate_spoken_from_written(agent_id: str, written_text: str) -> None:
    """Generate spoken summary from completed written response."""
    try:
        spoken_prompt = get_spoken_prompt(agent_id)
        if not spoken_prompt:
            log.warning(f"No spoken prompt for agent {agent_id}")
            return

        llm = get_llm_for_agent(agent_id)

        # Ask LLM to summarize the written response for TTS
        messages = [
            SystemMessage(content=spoken_prompt),
            HumanMessage(content=f"Vat dit antwoord samen voor spraak:\n\n{written_text}")
        ]

        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                await spoken_queue.put(str(chunk.content))
    except Exception as e:
        log.error(f"Error generating spoken: {e}")
    finally:
        await spoken_queue.put(None)
```

## Timing Considerations

| Approach | Written Latency | Spoken Start | Total Experience |
|----------|-----------------|--------------|------------------|
| Current (broken) | Normal | Immediate (wrong) | Fast but incorrect |
| Approach 1 | Normal | After written | +2-3s for spoken |
| Approach 2 | Normal | After written | +2-3s for spoken |
| Approach 3 | Normal | After key tool | Variable |
| Approach 4 | Blocked | With written | Different UX |
| Approach 5 | Normal | After written | +2-3s for spoken |

The 2-3 second additional latency for spoken is acceptable because:
1. User already has written text to read
2. TTS audio is a supplementary feature
3. Correctness matters more than speed for safety-critical inspection data

## Open Questions

1. **Prompt Adjustment**: Should the spoken prompt be modified to explicitly say "summarize this response" rather than "answer this question"?

2. **Streaming Start**: Should we start the spoken stream (`send_spoken_text_start`) immediately (for UI feedback) or wait until we have content?

3. **Dictate Mode**: Does dictate mode need any changes? (Currently duplicates written to spoken, which is already consistent)

## References

- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:309-577` - Streaming implementation
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:248-320` - Spoken prompts
- `thoughts/shared/research/2025-01-15-server-langgraph-agent-flow-dual-generation.md` - Previous research on dual generation
