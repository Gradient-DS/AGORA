---
date: 2026-01-12T14:30:00+01:00
researcher: Claude
git_commit: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
branch: main
repository: Gradient-DS/AGORA
topic: "Parallel Spoken Text Generation for TTS - Implementation Strategy"
tags: [research, codebase, spoken-text, tts, ag-ui-protocol, orchestrator, streaming]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Parallel Spoken Text Generation for TTS

**Date**: 2026-01-12T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
**Branch**: main
**Repository**: Gradient-DS/AGORA

## Research Question

How to implement parallel generation of written (UI) and spoken (TTS) message variants in the server-langgraph and server-openai backends? Should the architecture be revised to centralize responses through the main agent?

## Summary

The mock server already demonstrates the pattern using `agora:spoken_text_*` CUSTOM events running in parallel with `TEXT_MESSAGE_*` events. Both backends currently lack this implementation. The key finding is that **parallel generation can be implemented at the orchestrator layer without centralizing through a single agent** - the streaming callback/handler is already the natural chokepoint for all text output.

**Recommended approach**: Implement parallel generation in the orchestrator's stream handling. Two viable strategies exist:
1. **Post-processing transform** (like mock server) - minimal LLM cost, limited differentiation
2. **True parallel LLM generation** - better quality spoken text, doubles LLM cost

## Detailed Findings

### Current Protocol Support

The AG-UI protocol already defines the spoken text events in `docs/hai-contract/HAI_API_CONTRACT.md:656-706`:

| Event | Purpose |
|-------|---------|
| `agora:spoken_text_start` | Begin spoken message stream (CUSTOM event) |
| `agora:spoken_text_content` | Stream spoken content chunk (CUSTOM event) |
| `agora:spoken_text_end` | End spoken message stream (CUSTOM event) |

These events:
- Run **in parallel** with regular `TEXT_MESSAGE_*` events
- Share the same `messageId` with their text counterparts
- Carry TTS-optimized content (abbreviations expanded, markdown removed)

### Mock Server Reference Implementation

`docs/hai-contract/mock_server.py:364-385` - Post-processing transform:

```python
def to_spoken_text(text: str) -> str:
    """Convert markdown text to speech-friendly text with Dutch expansions."""
    # Remove markdown formatting
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)      # Italic
    text = re.sub(r"`([^`]+)`", r"\1", text)        # Code
    text = text.replace("- ", "")                   # List bullets

    # Dutch abbreviation expansions
    text = text.replace("KVK", "Kamer van Koophandel")
    text = text.replace("°C", " graden Celsius")
    # ... etc
```

`docs/hai-contract/mock_server.py:977-1059` - Parallel event streaming:

```python
async def stream_response(websocket, thread_id, run_id, content_chunks, agent):
    # Start both streams
    await send_event(websocket, {"type": "TEXT_MESSAGE_START", ...})
    await send_event(websocket, {"type": "CUSTOM", "name": "agora:spoken_text_start", ...})

    for chunk in content_chunks:
        # Send regular text chunk
        await send_event(websocket, {"type": "TEXT_MESSAGE_CONTENT", "delta": chunk, ...})

        # Send spoken text chunk (transformed)
        spoken_chunk = to_spoken_text(chunk)
        if spoken_chunk:
            await send_event(websocket, {
                "type": "CUSTOM",
                "name": "agora:spoken_text_content",
                "value": {"messageId": message_id, "delta": spoken_chunk}
            })

    # End both streams
    await send_event(websocket, {"type": "TEXT_MESSAGE_END", ...})
    await send_event(websocket, {"type": "CUSTOM", "name": "agora:spoken_text_end", ...})
```

### Server-LangGraph: Current Text Streaming Architecture

**Entry point**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:300-454`

Text messages flow through `_stream_response()` which uses LangGraph's `astream_events`:

```python
async for event in self.graph.astream_events(input_state, config=config, version="v2"):
    kind = event.get("event")
    if kind == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        if chunk and hasattr(chunk, "content") and chunk.content:
            content = str(chunk.content)
            # TEXT_MESSAGE events emitted here (lines 333-341)
            if not message_started:
                await protocol_handler.send_text_message_start(message_id, "assistant")
                message_started = True
            await protocol_handler.send_text_message_content(message_id, content)
```

**Current state**: No spoken text handling exists. The `ag_ui_handler.py` only has `send_text_message_*` methods.

### Server-OpenAI: Current Text Streaming Architecture

**Entry point**: `server-openai/src/agora_openai/pipelines/orchestrator.py:177-205`

Text messages flow through a `stream_callback` closure:

```python
async def stream_callback(chunk: str, agent_id: str | None = None) -> None:
    if not message_started:
        await protocol_handler.send_text_message_start(message_id, "assistant")
        message_started = True
    await protocol_handler.send_text_message_content(message_id, chunk)
```

**Current state**: `unified_voice_handler.py` exists but is explicitly marked "not used yet" (line 1-2). No spoken text generation is integrated into the main AG-UI flow.

### Multi-Agent Architecture

Both backends implement a **triage pattern**:

1. `general-agent` receives all messages initially
2. Based on intent, hands off to: `regulation-agent`, `history-agent`, or `reporting-agent`
3. Each specialist has its own LLM instance and system prompt
4. **Each agent generates its own text responses directly**

**Key insight**: There is no central coordinator - whichever agent is active streams its response directly to the frontend.

Handoff configuration:
- LangGraph: `server-langgraph/src/agora_langgraph/core/tools.py:14-68` - explicit transfer tools
- OpenAI SDK: `server-openai/src/agora_openai/core/agent_definitions.py:15-68` - `handoffs` array per agent

## Architecture Insights

### Why Centralizing Through Main Agent is NOT Required

The user asked whether to revise the architecture so only the main agent answers. **This is not necessary** because:

1. **All text flows through one point**: Regardless of which agent is active, all text chunks pass through:
   - LangGraph: `orchestrator._stream_response()` → `ag_ui_handler.send_text_message_content()`
   - OpenAI SDK: `stream_callback()` → `ag_ui_handler.send_text_message_content()`

2. **Agent identity is tracked**: Both backends already track `current_agent_id`, so the orchestrator knows which agent is speaking.

3. **Transformation can happen at the protocol layer**: The orchestrator can intercept chunks and generate/transform spoken variants before sending to the handler.

### Recommended Implementation Strategy

**Option A: Post-Processing Transform (Low Cost)**

Add a `to_spoken_text()` function similar to mock server. For each chunk:
1. Send original chunk as `TEXT_MESSAGE_CONTENT`
2. Transform chunk via `to_spoken_text()`
3. Send transformed chunk as `agora:spoken_text_content`

Pros:
- Zero additional LLM cost
- Simple to implement
- Consistent latency

Cons:
- Limited to text transformation (removing markdown, expanding abbreviations)
- Cannot produce truly different spoken responses (shorter, different phrasing)

**Option B: True Parallel LLM Generation (High Quality)**

For each message, run two parallel LLM calls with different system prompts:
1. Original agent system prompt → written text for UI
2. Speech-optimized system prompt → spoken text for TTS

Implementation sketch:
```python
async def generate_parallel_responses(user_message: str, agent_id: str):
    written_prompt = get_agent_instructions(agent_id)  # Current prompt
    spoken_prompt = get_spoken_agent_instructions(agent_id)  # New shorter prompt

    # Run in parallel
    written_task = asyncio.create_task(llm.astream(messages + [system(written_prompt)]))
    spoken_task = asyncio.create_task(llm.astream(messages + [system(spoken_prompt)]))

    # Interleave streaming from both
    async for written_chunk, spoken_chunk in zip_async(written_task, spoken_task):
        yield ("written", written_chunk)
        yield ("spoken", spoken_chunk)
```

Pros:
- Truly different spoken responses (shorter, snappier, conversational)
- Higher quality TTS experience
- Each agent can have specialized spoken style

Cons:
- Doubles LLM API cost
- Added complexity in stream handling
- Potential latency differences between streams

**Option C: Hybrid Approach (Recommended)**

1. Use post-processing transform for simple cases (tool results, structured data)
2. Use parallel LLM generation only for main agent responses
3. Cache spoken versions for repeated/similar messages

### Implementation Location

Both backends should implement parallel generation in the same location:

**LangGraph** (`server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:300-454`):
- Modify `_stream_response()` to emit both event types
- Add `send_spoken_text_*` methods to `ag_ui_handler.py`

**OpenAI SDK** (`server-openai/src/agora_openai/pipelines/orchestrator.py:177-205`):
- Modify `stream_callback()` closure to emit both event types
- Add `send_spoken_text_*` methods to `ag_ui_handler.py`

### AG-UI Handler Changes Required

Add to both `ag_ui_handler.py` files:

```python
async def send_spoken_text_start(self, message_id: str, role: str = "assistant") -> None:
    event = CustomEvent(
        name="agora:spoken_text_start",
        value={"messageId": message_id, "role": role},
        timestamp=_now_timestamp(),
    )
    await self._send_event(event)

async def send_spoken_text_content(self, message_id: str, delta: str) -> None:
    if not delta:
        return
    event = CustomEvent(
        name="agora:spoken_text_content",
        value={"messageId": message_id, "delta": delta},
        timestamp=_now_timestamp(),
    )
    await self._send_event(event)

async def send_spoken_text_end(self, message_id: str) -> None:
    event = CustomEvent(
        name="agora:spoken_text_end",
        value={"messageId": message_id},
        timestamp=_now_timestamp(),
    )
    await self._send_event(event)
```

## Code References

- `docs/hai-contract/mock_server.py:364-385` - `to_spoken_text()` transformation function
- `docs/hai-contract/mock_server.py:977-1059` - `stream_response()` parallel event emission
- `docs/hai-contract/HAI_API_CONTRACT.md:656-706` - Spoken text event specification
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:300-454` - LangGraph streaming
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:186-214` - LangGraph text message methods
- `server-openai/src/agora_openai/pipelines/orchestrator.py:177-205` - OpenAI SDK streaming callback
- `server-openai/src/agora_openai/api/ag_ui_handler.py:180-208` - OpenAI SDK text message methods
- `server-openai/src/agora_openai/api/unified_voice_handler.py:1-2` - Placeholder for future voice (not implemented)

## Open Questions

1. **Cost vs Quality tradeoff**: Should we default to post-processing (Option A) and allow parallel LLM (Option B) as a configuration option?

2. **Stream synchronization**: When using parallel LLM generation, how to handle different response lengths? The written response might be 3 paragraphs while spoken is 2 sentences.

3. **Error handling**: If spoken generation fails, should we fall back to post-processing transform of the written text?

4. **Per-agent spoken prompts**: Should each specialist agent have its own spoken system prompt, or use a generic "make this concise" wrapper?

5. **Frontend TTS integration**: How will the HAI frontend consume spoken text events? Real-time TTS as chunks arrive, or buffer until `spoken_text_end`?

## Conclusion

Parallel spoken text generation can be implemented **without centralizing through the main agent**. The orchestrator's stream handling is already the natural chokepoint for all text output. The recommended approach is to start with the post-processing transform (low cost, quick implementation) and iterate toward parallel LLM generation if higher quality spoken responses are needed.

The protocol support already exists in the AG-UI contract - the implementation work is primarily in the orchestrator and ag_ui_handler layers of both backends.
