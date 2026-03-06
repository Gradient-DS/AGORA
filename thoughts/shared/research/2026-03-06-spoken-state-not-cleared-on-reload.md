---
date: 2026-03-06T14:30:00+01:00
researcher: claude
git_commit: 9faed220287ab47545229b2394a0a9759336476e
branch: feat/tool-description
repository: AGORA
topic: "Spoken conversation state not cleared on reload - stale spoken content on new messages"
tags: [research, codebase, spoken-text, tts, state-management, langgraph, bug]
status: complete
last_updated: 2026-03-06
last_updated_by: claude
---

# Research: Spoken State Not Cleared on Reload

**Date**: 2026-03-06T14:30:00+01:00
**Researcher**: claude
**Git Commit**: 9faed220287ab47545229b2394a0a9759336476e
**Branch**: feat/tool-description
**Repository**: AGORA

## Research Question
Why does stale spoken content from a previous conversation appear on new messages after reloading? The written (Geschreven) content is a correct greeting, but the spoken (Gesproken) content shows old content about raw fish violations.

## Summary

The bug has **two contributing causes**, both in the **LangGraph backend** (server-langgraph):

1. **Primary cause — Spoken generator receives full conversation history**: The spoken LLM independently generates content based on the entire conversation context. After a reload, when the user sends a simple message like "hie", the spoken model may summarize the previous conversation topic instead of responding to the greeting, while the written model correctly handles it.

2. **Secondary cause — Accumulated `spoken` state in LangGraph checkpoint**: The `spoken` list in `AgentState` uses `operator.add` and accumulates across turns. If the spoken generator fails or produces empty output, `merge_parallel_outputs()` falls back to the previous turn's spoken content via `spoken_parts[-1]`.

The **server-openai** implementation is NOT affected because its spoken agent only receives the current user message (`agent_input.messages`), not the full conversation history.

## Detailed Findings

### 1. Root Cause: Spoken Generator Context in LangGraph

In the LangGraph implementation, both the written and spoken generators receive the **full conversation history** from the checkpoint:

**`server-langgraph/src/agora_langgraph/core/graph.py:424-430`** — The `Send` API passes `state.messages` (full history) to the spoken generator:
```python
Send(
    "generate_spoken",
    GeneratorState(
        messages=messages,  # FULL conversation history
        system_prompt=spoken_prompt,
        stream_type="spoken",
        agent_id=agent_id,
    ),
),
```

**`server-langgraph/src/agora_langgraph/core/graph.py:464-466`** — The generator prepends the system prompt:
```python
full_messages = [SystemMessage(content=system_prompt)] + list(messages)
```

When the user sends "hie" after a conversation about fish violations, the spoken LLM receives:
- System prompt: "give SHORT spoken answers, summarize in 2-3 sentences"
- Full history: previous exchanges about fish violations
- Current message: "hie"

The spoken LLM may interpret this as "summarize the ongoing topic" rather than "respond to a greeting." The written model (typically more capable) correctly recognizes the greeting.

**Contrast with server-openai** (`server-openai/src/agora_openai/pipelines/orchestrator.py:293`):
```python
for m in agent_input.messages:  # Only current user message!
```
The OpenAI implementation passes only `agent_input.messages` (the single current user message from the frontend), so stale context cannot influence the spoken output.

### 2. Accumulated State Bug in LangGraph

**`server-langgraph/src/agora_langgraph/core/state.py:39-40`**:
```python
written: Annotated[list[str], operator.add]  # Accumulates across turns
spoken: Annotated[list[str], operator.add]   # Accumulates across turns
```

**`server-langgraph/src/agora_langgraph/core/graph.py:547-548`** — `merge_parallel_outputs` takes the last element:
```python
spoken_parts = state.get("spoken", [])
spoken_content = spoken_parts[-1] if spoken_parts else ""
```

If `generate_spoken` fails with an exception (API error, timeout, etc.):
- No new entry is added to the `spoken` list
- `spoken_parts[-1]` returns the **previous turn's** spoken content
- This stale content gets stored in `additional_kwargs["spoken_text"]` (line 570)
- On next reload, the history API returns this stale spoken text

### 3. LangGraph History Returns spoken_text (server-openai Does Not)

**LangGraph** (`server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:1182-1230`):
```python
spoken_text = msg.additional_kwargs.get("spoken_text")
history.append({
    "role": "assistant",
    "content": extract_text(msg.content),
    "spoken_text": spoken_text,  # Returned to frontend!
})
```

**OpenAI** (`server-openai/src/agora_openai/core/agent_runner.py:560-569`):
```python
history.append({
    "role": "assistant",
    "content": content,
    "agent_id": current_agent_id,
    # NO spoken_text field — never stored, never returned
})
```

The frontend maps `spoken_text` to `spokenContent` at `HAI/src/lib/api/sessions.ts:137`. With the LangGraph backend, history messages carry spoken content; with OpenAI, they don't.

### 4. Frontend State Management is Correct

The frontend properly clears state on reload:
- `useMessageStore` initializes with `messages: []`, `spokenBuffers: new Map()` (line 37-41)
- `clearMessages()` resets both (line 188-189)
- `replaceMessages()` also resets `spokenBuffers` (line 192-193)
- Message IDs are unique UUIDs — no collision between history and new messages
- Events are properly keyed by `messageId`

The frontend is **not** the source of this bug.

### 5. Additional Risk: No Session Filtering on Frontend Events

`HAI/src/hooks/useWebSocket.ts` processes ALL incoming events without checking `threadId`. If events from a different session arrive (e.g., from offline buffer replay or backend processing overlap), they would be processed. This is a separate risk but could compound the issue.

### 6. Related Previous Research

`thoughts/shared/research/2026-03-01-spoken-written-divergence.md` documented a related issue where the spoken model diverges from written output. That research identified prompt-driven hallucination and model capability gaps. This bug is a different manifestation of the same architectural issue: **independent parallel generation without shared context**.

## Bug Reproduction Scenario

1. Use the **LangGraph backend** with `showSpokenComparison` enabled
2. Have a multi-turn conversation about a specific topic (e.g., fish regulation violations)
3. Reload the page (or start a new inspection within the same session)
4. Send a simple greeting like "hie"
5. Observe: Written content = correct greeting; Spoken content = summary of previous fish topic

## Recommended Fixes

### Fix 1: Strip history for spoken generator (targeted fix)
In `_create_parallel_sends()`, pass only the current user message to the spoken generator instead of the full history:
```python
Send(
    "generate_spoken",
    GeneratorState(
        messages=[messages[-1]],  # Only current user message
        system_prompt=spoken_prompt,
        stream_type="spoken",
        agent_id=agent_id,
    ),
),
```
This matches the server-openai behavior and prevents context bleed.

### Fix 2: Reset spoken/written accumulators per turn
Clear the accumulated lists at the start of each turn to prevent stale fallback:
```python
# In route_from_agent or _create_parallel_sends:
# Use Overwrite to reset instead of accumulate
return {
    "written": Overwrite([]),  # Reset for this turn
    "spoken": Overwrite([]),
    ...
}
```

### Fix 3: Guard against empty spoken content in merge
Add a check in `merge_parallel_outputs` to avoid using stale content:
```python
# Count expected entries (1 per turn)
expected_count = len(written_parts)  # written always succeeds
if len(spoken_parts) < expected_count:
    spoken_content = ""  # Don't fall back to previous turn
else:
    spoken_content = spoken_parts[-1]
```

### Fix 4: Two-phase generation (architectural, from previous research)
Generate spoken content AFTER written content, using the written response as input. This eliminates divergence entirely but adds latency.

## Code References

- `server-langgraph/src/agora_langgraph/core/state.py:39-40` — `spoken` list with `operator.add` reducer
- `server-langgraph/src/agora_langgraph/core/graph.py:424-430` — Full history passed to spoken generator via Send
- `server-langgraph/src/agora_langgraph/core/graph.py:464-466` — Message assembly in `_generate_stream()`
- `server-langgraph/src/agora_langgraph/core/graph.py:547-548` — `merge_parallel_outputs()` taking `[-1]`
- `server-langgraph/src/agora_langgraph/core/graph.py:570` — Spoken text stored in `additional_kwargs`
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:1182-1230` — History API returns `spoken_text`
- `server-openai/src/agora_openai/pipelines/orchestrator.py:293` — OpenAI spoken agent only gets current message
- `server-openai/src/agora_openai/core/agent_runner.py:560-569` — OpenAI history does NOT return spoken_text
- `HAI/src/lib/api/sessions.ts:137` — Frontend maps `spoken_text` to `spokenContent`
- `HAI/src/stores/useMessageStore.ts:37-41` — Frontend store initialization (correctly clean)
- `HAI/src/hooks/useWebSocket.ts:294-328` — Spoken event handling (no threadId filtering)

## Open Questions

1. Which backend is the user running? If server-openai, the context bleed cause is eliminated and the bug source needs further investigation.
2. Should the spoken generator ever see conversation history, or should it always operate on just the current message?
3. Is the `operator.add` accumulation pattern necessary, or can `written`/`spoken` be simple `str` fields that get overwritten each turn?
