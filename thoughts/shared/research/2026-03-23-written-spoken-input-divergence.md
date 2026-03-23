---
date: 2026-03-23T11:30:00+01:00
researcher: Claude
git_commit: 37b4dd8
branch: fix/double-spoken
repository: AGORA
topic: "Written vs spoken generation input divergence and sequential approach analysis"
tags: [research, codebase, spoken-text, tts, orchestrator, consistency]
status: complete
last_updated: 2026-03-23
last_updated_by: Claude
---

# Research: Written vs Spoken Generation Input Divergence

**Date**: 2026-03-23
**Researcher**: Claude
**Git Commit**: 37b4dd8
**Branch**: fix/double-spoken
**Repository**: AGORA

## Research Question

1. Are the inputs to written and spoken generation the same? (They produce different content: written asks for postcode, spoken says "I'll look it up")
2. What would it take to change to a sequential written→spoken approach where spoken is generated from the written text?

## Summary

**The inputs are NOT the same.** Written and spoken generation use different system prompts, different message filtering, different timing for context capture, and potentially different LLM models. This is the root cause of the observed divergence. The spoken LLM independently interprets the conversation and can reach a completely different conclusion than the written agent.

**A sequential approach is feasible** with moderate changes to `_stream_response()`. The existing fallback sequential path (lines 1328-1354) already demonstrates the pattern. The key change: pass the completed written text as context to `_generate_spoken()`.

## Detailed Findings

### 1. Why Written and Spoken Diverge

The observed behavior — written asks for postcode while spoken says "I'll look it up" — happens because:

| Aspect | Written (agent node) | Spoken (`_generate_spoken`) |
|--------|---------------------|---------------------------|
| **System prompt** | Detailed agent instructions with workflow steps, tool usage, formatting rules | Short TTS-optimized prompt: "1-3 sentences, no markdown, conversational" |
| **Message history** | Full current turn: tool calls, ToolMessages, intermediate AI, handoffs | Stripped: only HumanMessage + non-tool-calling AIMessage from current turn |
| **Tool results** | Actual ToolMessages in conversation | Injected as a single HumanMessage string: `[Uitgevoerde tools en resultaten]...` |
| **Timing** | Messages accumulate during graph execution | Snapshot taken **before** graph runs (line 813), tool results appended when spoken task starts (line 868) |
| **LLM model** | Agent's configured LLM | `get_llm_for_spoken()` — uses `spoken_provider_chain`, potentially different model |
| **Sees written response?** | N/A (IS the written response) | **No** — spoken starts in parallel on first written chunk (line 861) |

The critical issue: **spoken generation starts on the first written text chunk and runs in parallel**. The spoken LLM never sees the written response. It independently decides what to say based on the conversation history + tool results snapshot.

### 2. Current Architecture (Parallel)

```
User message
    │
    ├─→ Graph execution (agent node) ──→ Written text (streamed)
    │       │
    │       └─ on first text chunk ──→ asyncio.create_task(_generate_spoken)
    │                                      │
    │                                      └──→ Spoken text (streamed in parallel)
    │
    └─→ Context snapshot (before graph) + tool results ──→ Spoken LLM input
```

**Spoken context construction (lines 809-826):**
1. `aget_state(config)` — gets conversation history BEFORE the graph runs
2. Appends the current human message from `graph_input`
3. Filters through `_build_spoken_messages()` — strips tool calls, ToolMessages
4. At task creation: appends accumulated tool results as text (lines 868-873)

**Spoken task creation (lines 861-886):** Triggered on the first `on_chat_model_stream` chunk from an agent node, meaning spoken starts before the written response is complete.

### 3. Sequential Approach: What Would Change

**Goal:** Generate written text first, then generate spoken from the written text.

**Scope of changes:** Primarily `orchestrator.py:_stream_response()` and `_generate_spoken()`.

#### Option A: Pass written text as context to spoken LLM (Recommended)

Modify `_generate_spoken` to accept the completed written text. The spoken prompt would instruct: "Here is the written response. Generate a natural spoken summary of it."

**Changes required:**

1. **`_generate_spoken()` (line 685):** Add `written_text: str` parameter. Include the written text in the message list (e.g., as an AIMessage or appended to system prompt).

2. **Remove parallel task creation (lines 861-886):** Delete the `asyncio.create_task` block that starts spoken on first written chunk.

3. **Move spoken generation to after graph completion (around line 1311):** Replace the `if spoken_task:` block with direct sequential call:
   ```python
   if spoken_mode == "summarize" and not graph_was_interrupted and message_started:
       written_text = "".join(full_response)
       # Build context with full state including the written response
       state_messages = final_state.values.get("messages", []) if final_state and final_state.values else []
       spoken_messages = self._build_spoken_messages(state_messages)
       spoken_content = await self._generate_spoken(
           agent_id=current_agent_id,
           messages=spoken_messages,
           message_id=message_id,
           protocol_handler=protocol_handler,
           written_text=written_text,  # NEW
       )
   ```

4. **Update spoken prompts** in `agent_definitions.py`: Add instruction like "Je krijgt de geschreven respons als context. Vat deze samen in gesproken taal."

5. **Remove `spoken_context_messages` pre-computation (lines 807-826):** No longer needed since we use post-execution state.

**Estimated latency impact:** Spoken generation starts only after written completes. For a typical response (~2-3s written streaming), spoken will start ~2-3s later. Total latency = written time + spoken time (sequential) vs max(written, spoken) (current parallel).

#### Option B: Use the existing fallback sequential path

The fallback at lines 1328-1354 already generates spoken sequentially using `final_state.values["messages"]`. This includes the agent's written response in the message history. Simply making this the default path (instead of a fallback) would ensure spoken always sees the written text.

**Changes required:**
1. Remove the parallel task creation block (lines 861-886)
2. Remove the `spoken_context_messages` pre-computation (lines 807-826)
3. Make the fallback path (lines 1328-1354) the primary path

**Downside:** The spoken LLM still independently generates text from conversation history. It's more consistent because it sees the written response, but the spoken prompt still makes its own decisions about what to say.

#### Option A vs Option B

| | Option A (explicit written context) | Option B (use existing fallback) |
|--|---|---|
| **Consistency** | High — spoken is explicitly derived from written | Medium — spoken sees written but can still diverge |
| **Code changes** | Moderate — modify `_generate_spoken`, update prompts | Small — remove parallel path, promote fallback |
| **Latency** | Same | Same |
| **Recommendation** | Better for guaranteed consistency | Good first step, easy to implement |

### 4. Impact on Dictate Mode

Dictate mode (line 897-917) already copies written text directly to spoken channel. No changes needed for dictate mode.

### 5. Impact on Other Spoken Paths

- **Clarification handler (line 1222-1246):** Already sequential (spoken generated after clarification text is known). No change needed.
- **Listen mode (line 1274-1282):** Uses `final_spoken` from graph state. No change needed.

## Code References

- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:649-683` — `_build_spoken_messages()`: message filtering for spoken
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:685-736` — `_generate_spoken()`: spoken LLM call with streaming
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:809-826` — Spoken context snapshot (pre-graph)
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:858-886` — Parallel spoken task creation
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:1311-1354` — Spoken task await + sequential fallback
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:325-441` — Spoken prompts (`SPOKEN_AGENT_PROMPTS`)
- `server-langgraph/src/agora_langgraph/core/agents.py:260` — `get_llm_for_spoken()`

## Related Research

- `thoughts/shared/research/2026-03-23-double-spoken-output-investigation.md` — Double spoken output investigation
- `thoughts/shared/research/2026-03-22-spoken-text-markdown-cleanup.md` — Markdown in spoken text
- `thoughts/shared/research/2026-03-01-spoken-written-divergence.md` — Earlier spoken/written divergence analysis

## Open Questions

1. What is the acceptable latency budget for spoken generation? (Sequential adds ~2-3s)
2. Should spoken prompts be rewritten to be "summarize this written text" instead of "independently answer the question"?
3. Should dictate mode remain as a user preference, or should sequential summarize replace it?
4. Does `server-openai` need the same changes? (Same pattern exists there)
