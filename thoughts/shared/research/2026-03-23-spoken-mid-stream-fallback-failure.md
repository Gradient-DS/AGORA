---
date: 2026-03-23T12:00:00+01:00
researcher: Claude
git_commit: 37b4dd8
branch: fix/double-spoken
repository: AGORA
topic: "Spoken generation mid-stream failure: LangChain fallback doesn't cover streaming errors"
tags: [research, codebase, spoken, fallback, langchain, streaming, reliability]
status: complete
last_updated: 2026-03-23
last_updated_by: Claude
---

# Research: Spoken generation mid-stream failure

**Date**: 2026-03-23T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: 37b4dd8
**Branch**: fix/double-spoken
**Repository**: AGORA

## Research Question

Why does spoken generation fail with `openai.APIError: Encountered a server error` despite having a fallback chain configured? Is LangChain's `.with_fallbacks()` broken for streaming?

## Summary

Two independent issues cause spoken generation to fail without recovery:

1. **LangChain's `with_fallbacks().astream()` only handles first-chunk errors** — once the first chunk succeeds, mid-stream errors propagate directly without trying fallback providers.
2. **`openai.APIError` (base class) is not in `FALLBACK_EXCEPTIONS`** — only its subclass `APIStatusError` is listed, so even first-chunk failures of this type wouldn't trigger fallback.

## Detailed Findings

### Issue 1: LangChain fallback doesn't cover mid-stream errors

**File**: `langchain_core/runnables/fallbacks.py:550-591`

The `astream` implementation in `RunnableWithFallbacks`:

```python
# Lines 560-574: Only the FIRST chunk is tried with fallback
for runnable in self.runnables:
    try:
        stream = runnable.astream(input, ...)
        chunk = await anext(stream)       # ← fallback catches errors HERE only
    except self.exceptions_to_handle:
        last_error = e                     # ← tries next provider
    else:
        break                              # ← committed to this provider

# Lines 582-589: Subsequent chunks have NO fallback
yield chunk
async for chunk in stream:                 # ← errors here re-raise directly
    yield chunk
```

Once the first chunk succeeds, the fallback chain commits to that provider. Any mid-stream error (like a server error partway through generation) propagates straight up to the caller.

### Issue 2: `openai.APIError` not in FALLBACK_EXCEPTIONS

**File**: `server-langgraph/src/agora_langgraph/core/agents.py:40-55`

The openai exception hierarchy:
```
openai.APIError              ← raised in the traceback (base class)
├── APIStatusError           ← in FALLBACK_EXCEPTIONS (subclass)
├── APIConnectionError       ← in FALLBACK_EXCEPTIONS
└── APITimeoutError          ← in FALLBACK_EXCEPTIONS
```

The error `openai.APIError: Encountered a server error, please try again` is raised as the **base** `APIError` class (from `openai/_streaming.py:192`), not as `APIStatusError`. Since `APIError` is the parent — not a subclass — of `APIStatusError`, it's not matched by `FALLBACK_EXCEPTIONS`.

### Current error handling in `_generate_spoken`

**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:719-741`

```python
try:
    async for chunk in llm.astream(full_messages, config={"callbacks": []}):
        # ... process chunks
except Exception as e:
    log.error(f"Spoken generation failed: {e}", exc_info=True)
    # Returns empty string — no retry, no fallback
```

A bare try/except that logs and returns empty. No retry logic, no manual fallback.

## Code References

- `server-langgraph/src/agora_langgraph/core/agents.py:40-55` — `FALLBACK_EXCEPTIONS` definition (missing `APIError`)
- `server-langgraph/src/agora_langgraph/core/agents.py:220-234` — `get_llms_for_spoken()` returns list of individual LLMs
- `server-langgraph/src/agora_langgraph/core/agents.py:237-252` — `build_fallback_chain()` wraps with `.with_fallbacks()`
- `server-langgraph/src/agora_langgraph/core/agents.py:260-262` — `get_llm_for_spoken()` returns fallback-wrapped chain
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:700-741` — `_generate_spoken()` with bare try/except
- `langchain_core/runnables/fallbacks.py:550-591` — LangChain astream fallback (first-chunk only)

## Proposed Fix

### Approach: Bypass LangChain fallback for spoken streaming

Since LangChain's fallback is fundamentally broken for streaming, bypass it in `_generate_spoken()` and iterate over providers manually:

```python
async def _generate_spoken(self, ...):
    from agora_langgraph.core.agents import get_llms_for_spoken

    llms = get_llms_for_spoken()  # [primary, fallback1, fallback2]

    for i, llm in enumerate(llms):
        try:
            spoken_parts = []
            async for chunk in llm.astream(full_messages, config={"callbacks": []}):
                if hasattr(chunk, "content") and chunk.content:
                    content = extract_text(chunk.content)
                    if content:
                        spoken_parts.append(content)
                        # ... send to protocol_handler
            return "".join(spoken_parts)
        except Exception as e:
            if i < len(llms) - 1:
                log.warning(f"Spoken provider {i+1} failed ({e}), trying next")
                spoken_parts.clear()
            else:
                log.error(f"All spoken providers exhausted: {e}")
                return ""
```

### Secondary fix: Add `openai.APIError` to `FALLBACK_EXCEPTIONS`

This fixes the first-chunk case for agent nodes using `build_fallback_chain` with `ainvoke` (which doesn't have the mid-stream problem):

```python
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError

FALLBACK_EXCEPTIONS = (
    *FALLBACK_EXCEPTIONS,
    APIError,           # ← add base class
    APIStatusError,
    APIConnectionError,
    APITimeoutError,
)
```

### Complexity note on protocol_handler

The `_generate_spoken` method sends `spoken_text_start` on the first chunk. If we retry with a new provider after partial streaming, we'd need to handle the already-sent start event. Options:
- Send a spoken error event and re-start (cleanest for frontend)
- Only retry if no chunks were successfully sent yet (simpler)

## Open Questions

- Should agent node streaming (in `_stream_response`) also get manual fallback for mid-stream errors, or is this only critical for spoken?
- What's the frequency of this error? Is it specific to one provider or load-related?
- Should partial spoken output be sent even on failure, or discard and retry?
