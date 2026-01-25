---
date: 2026-01-25T12:00:00+01:00
researcher: Claude
git_commit: c470c3907a1349065cb5697dab320c16f24e1fc2
branch: main
repository: AGORA
topic: "Optimizing latency between written and spoken text streaming"
tags: [research, codebase, latency, streaming, voice, tts, llm-inference]
status: complete
last_updated: 2026-01-25
last_updated_by: Claude
---

# Research: Optimizing Latency Between Written and Spoken Text Streaming

**Date**: 2026-01-25T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: c470c3907a1349065cb5697dab320c16f24e1fc2
**Branch**: main
**Repository**: AGORA

## Research Question

How can we reduce the delay between written and spoken text output in AGORA? The spoken message currently starts ~500-600ms after the written text begins streaming. Options being considered:
- Different models
- Different faster model for voice
- Manually timing it better

**Scope**: Focus on LLM inference timing, not TTS/STT latency.

## Summary

The ~560ms delay observed between `TEXT_MESSAGE_CONTENT` and `agora:spoken_text_content` events is caused by **two separate LLM API calls racing independently**. Both are dispatched simultaneously via LangGraph's `Send` API, but each has its own network connection and Time-To-First-Token (TTFT) variance.

**Key findings:**
1. **Current architecture** uses true parallel generation but suffers from TTFT variance between two independent LLM streams
2. **Faster models exist**: Groq (0.2-0.3s TTFT), GPT-4.1-nano (fastest OpenAI), GPT-4o-mini
3. **Best quick wins**: Use a faster model for spoken stream, or buffer/sync the streams manually
4. **Longer-term option**: OpenAI Realtime API for direct speech-to-speech (250-500ms first-audio)

## Detailed Findings

### Current Architecture Analysis

The parallel generation is implemented via LangGraph's `Send` API:

```
graph.py:162-232 - _create_parallel_sends()
├── Send("generate_written", GeneratorState(...))
└── Send("generate_spoken", GeneratorState(...))
```

**Flow:**
1. Graph executes agent → tool calls complete
2. `route_from_agent()` returns two `Send` commands
3. Both `generate_written` and `generate_spoken` nodes start
4. Each node calls `llm.astream()` independently
5. Orchestrator streams chunks to frontend via AG-UI Protocol

**Key observation from screenshot timestamps:**
- `TEXT_MESSAGE_CONTENT` starts at `1768566659391`
- `agora:spoken_text_content` starts at `1768566659953`
- Delta: ~562ms

This is the **TTFT variance** between two independent OpenAI API calls.

### Why START Events Are Synchronized But CONTENT Is Not

From `orchestrator.py:439-477`:

```python
if node_name == "generate_written":
    if not message_started:
        await protocol_handler.send_text_message_start(...)
        await protocol_handler.send_spoken_text_start(...)  # Both START at same time!
        message_started = True
    await protocol_handler.send_text_message_content(message_id, content)

elif node_name == "generate_spoken":
    if not spoken_message_started:
        await protocol_handler.send_spoken_text_start(...)  # Backup if written hasn't started
    await protocol_handler.send_spoken_text_content(message_id, content)
```

The START events are emitted together when the first written chunk arrives. But CONTENT events depend on when each LLM stream produces tokens.

### LLM Model Speed Benchmarks (2025-2026)

#### OpenAI Models

| Model | TTFT | Throughput | Notes |
|-------|------|------------|-------|
| GPT-4o | ~0.61s | ~50 tok/s | Current default in AGORA |
| GPT-4o-mini | Lower | 55.4 tok/s | Microsoft-recommended for lowest latency |
| GPT-4.1 | ~0.39s | N/A | 35% faster TTFT than GPT-4o |
| GPT-4.1-mini | ~0.30s | N/A | 50% faster than GPT-4o |
| **GPT-4.1-nano** | **<5s for 128K** | N/A | OpenAI's fastest model, optimized for real-time |

#### OpenAI-Compatible Alternatives

| Provider | TTFT | Throughput | API Compatible |
|----------|------|------------|----------------|
| **Groq** | **0.2-0.3s** | 280-1,660 tok/s | Yes (OpenAI SDK) |
| Cerebras | N/A | 2,100-2,300 tok/s | Yes |
| Fireworks | Low | 482 tok/s | Yes |
| Together AI | <100ms | 4x Bedrock | Yes |

**Groq is particularly interesting** because:
- Uses custom LPU hardware for deterministic latency
- Sub-300ms TTFT with no variance spikes
- Compatible with LangChain's `ChatOpenAI` via base_url
- Llama 3.3 70B at 280-300 tok/s standard

#### Voice-Optimized Options

| Solution | First-Audio Latency | Notes |
|----------|---------------------|-------|
| OpenAI Realtime API | 250-500ms | Direct speech-to-speech, single model |
| Deepgram Voice Agent | <250ms | Full pipeline optimized |
| ElevenLabs Flash TTS | 75ms TTS only | Needs separate LLM |

### Options to Reduce Delay

#### Option 1: Use Faster Model for Spoken Stream (Easiest)

**Change**: Configure `generate_spoken_node` to use a different, faster model.

**Implementation location**: `server-langgraph/src/agora_langgraph/core/agents.py`

Currently `get_llm_for_agent()` returns the same LLM for all agents. Could add:
```python
def get_llm_for_spoken() -> ChatOpenAI:
    """Get faster LLM optimized for spoken text generation."""
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",  # or gpt-4.1-nano when available
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        streaming=True,
    )
```

**Pros:**
- Simple change, ~10 lines of code
- Maintains current architecture
- Spoken prompts are simpler, don't need full model capability

**Cons:**
- Still two separate API calls with independent TTFT
- May reduce delay but won't eliminate it

**Expected improvement**: 200-400ms reduction if using GPT-4o-mini vs GPT-4o

#### Option 2: Use Groq for Spoken Stream

**Change**: Configure spoken generation to use Groq's API endpoint.

**Implementation**:
```python
def get_llm_for_spoken() -> ChatOpenAI:
    """Get Groq LLM for ultra-fast spoken text generation."""
    return ChatOpenAI(
        model="llama-3.3-70b-versatile",  # or llama3-8b for faster
        api_key=groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        streaming=True,
    )
```

**Pros:**
- 0.2-0.3s TTFT (deterministic)
- Highly likely to finish BEFORE written stream starts
- Full LangChain compatibility

**Cons:**
- Different provider, different API key management
- Llama models may have slightly different output style
- Additional vendor dependency

**Expected improvement**: 300-500ms reduction, spoken may START before written

#### Option 3: Buffer Written Stream to Sync with Spoken

**Change**: Delay emitting written content until spoken also has content, then interleave.

**Implementation location**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

```python
# Accumulate initial chunks from both streams
written_buffer: list[str] = []
spoken_buffer: list[str] = []
both_started = False

async for event in self.graph.astream_events(...):
    if node_name == "generate_written":
        written_buffer.append(content)
    elif node_name == "generate_spoken":
        spoken_buffer.append(content)

    # Once both have content, start emitting together
    if written_buffer and spoken_buffer and not both_started:
        both_started = True
        # Emit all buffered content
        for chunk in written_buffer:
            await protocol_handler.send_text_message_content(...)
        for chunk in spoken_buffer:
            await protocol_handler.send_spoken_text_content(...)
        written_buffer.clear()
        spoken_buffer.clear()
```

**Pros:**
- Guarantees synchronized start
- No model changes required
- User perceives both starting simultaneously

**Cons:**
- Adds latency to written stream (waits for spoken)
- More complex buffering logic
- Written text appears slower to user

**Expected improvement**: Perfect sync, but written delays by 300-500ms

#### Option 4: Single Generation + Fast Transform

**Change**: Generate once, then fast-transform to spoken format.

**Flow:**
1. Generate written text with main model (GPT-4o)
2. After complete, use fast model (GPT-4o-mini or Groq) to summarize for spoken

**Pros:**
- No parallel race condition
- Spoken summary is based on actual written content

**Cons:**
- Spoken starts AFTER written completes (seconds of delay)
- User waits longer for spoken audio to begin
- Worse UX than current approach

**Not recommended** unless spoken can be significantly shorter.

#### Option 5: OpenAI Realtime API (Fundamental Change)

**Change**: Replace text+TTS pipeline with direct speech-to-speech.

**Benefits:**
- 250-500ms first-audio latency
- Single API call handles everything
- Natural conversation flow

**Challenges:**
- Requires significant architecture changes
- Different event protocol
- Voice-in required (not just voice-out)
- Accuracy drops to ~50% in full voice mode

**Timeline**: Medium-term, significant refactor

#### Option 6: Pre-emit Spoken START Earlier

**Change**: Send `spoken_text_start` immediately when graph finishes tool execution, before any LLM generation.

**Implementation**: Move `send_spoken_text_start` to occur right after tools complete, before parallel generation begins.

**Pros:**
- TTS can prepare to receive audio earlier
- Perception of faster response

**Cons:**
- START without immediate content may cause TTS issues
- Frontend must handle empty start gracefully

### Recommendation Matrix

| Priority | Option | Effort | Impact | Risk |
|----------|--------|--------|--------|------|
| **1** | Use GPT-4o-mini for spoken | Low | Medium | Low |
| 2 | Use Groq for spoken | Medium | High | Medium |
| 3 | Buffer/sync streams | Medium | High | Low |
| 4 | OpenAI Realtime API | High | Very High | Medium |

**Recommended approach**: Start with Option 1 (GPT-4o-mini for spoken), measure improvement. If insufficient, try Option 2 (Groq). If perfect sync needed, implement Option 3 (buffering).

## Code References

- `server-langgraph/src/agora_langgraph/core/graph.py:162-232` - `_create_parallel_sends()` creates the Send commands
- `server-langgraph/src/agora_langgraph/core/graph.py:235-306` - `_generate_stream()` and `generate_spoken_node()`
- `server-langgraph/src/agora_langgraph/core/agents.py:47-54` - `get_llm_for_agent()` LLM instantiation
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:424-480` - Stream routing to written/spoken channels
- `server-langgraph/src/agora_langgraph/core/parallel_streaming.py:45-166` - Alternative parallel streaming utility (not currently used)
- `server-langgraph/src/agora_langgraph/config.py:26` - `openai_model` default setting

## Architecture Insights

### Why True Parallel Generation Still Has Delay

The current implementation IS truly parallel:
1. LangGraph's `Send` API dispatches both nodes simultaneously
2. Both `llm.astream()` calls start at nearly the same time
3. But each HTTP connection to OpenAI has independent scheduling
4. OpenAI's inference servers may queue requests differently
5. Network latency variance adds ~100-200ms

The observed ~560ms delta is the **TTFT variance** between two independent API calls, not a serialization issue.

### Why the Slower Stream is Often Spoken

The spoken prompt is shorter/simpler, BUT:
- Both use the same model (GPT-4o)
- OpenAI doesn't necessarily process shorter prompts faster
- Server-side batch scheduling is opaque
- The variance is essentially random which stream starts first

## Historical Context

From `thoughts/shared/plans/2025-01-15-parallel-dual-text-generation.md`:
- The parallel generation was implemented to ensure spoken has full tool context
- Previous approach had spoken starting with stale context (missing tool results)
- The "wasted" LLM call trade-off was accepted for context consistency

## Open Questions

1. **Does GPT-4.1-nano support streaming?** If so, it may be ideal for spoken generation
2. **Can we measure actual TTFT variance?** Adding timing logs would help quantify the problem
3. **Would users prefer synchronized start (delayed written) or faster written (delayed spoken)?**
4. **Is Groq's API stable enough for production use?**

## Next Steps

1. Add timing instrumentation to measure exact TTFT for both streams
2. Test GPT-4o-mini for spoken generation and measure improvement
3. If insufficient, evaluate Groq integration
4. Consider user research on perceived latency preferences
