---
date: 2026-03-22T12:00:00+01:00
researcher: Claude
git_commit: 2bce6b7784033ac1638d4fade77312e575937e53
branch: feat/tool-description
repository: AGORA
topic: "Spoken text markdown contamination and cleanup"
tags: [research, codebase, spoken-text, tts, markdown, fallback-model]
status: complete
last_updated: 2026-03-22
last_updated_by: Claude
---

# Research: Spoken Text Markdown Contamination and Cleanup

**Date**: 2026-03-22
**Researcher**: Claude
**Git Commit**: 2bce6b7
**Branch**: feat/tool-description
**Repository**: AGORA

## Research Question
Sometimes the spoken text contains markdown, which trips up the TTS voice agent. This mostly occurs with the fallback model. Do we already instruct the model not to emit markdown, and could we add a post-processing fallback to strip markdown?

## Summary

**Q1: Do we instruct the model not to emit markdown?**
Yes, partially. The spoken prompts include `"Geen opsommingstekens, nummering of markdown"` (general-agent, line 360) and equivalents like `"Geen lijsten"` / `"Geen tabellen, lijsten"` for specialist agents. However, only the **general-agent** explicitly mentions "markdown" by name. The specialist agents prohibit specific markdown artifacts (lists, tables, links) but don't use the word "markdown" — leaving room for bold (`**`), italic (`*`), code backticks, and headers (`#`) to slip through.

**Q2: Is there a post-processing markdown strip?**
No. The mock server (`docs/hai-contract/mock_server.py:758-778`) has a `to_spoken_text()` function that strips markdown, but this is **only used in the mock server**. Neither `server-openai` nor `server-langgraph` applies any post-processing to the spoken text before sending it to the frontend. The spoken LLM output is streamed directly to the client without sanitization.

## Detailed Findings

### Current Spoken Prompt Instructions

All four agents have spoken prompts in `SPOKEN_AGENT_PROMPTS` (both backends):

| Agent | Anti-markdown instruction | File:Line (langgraph) |
|-------|--------------------------|----------------------|
| general-agent | "Geen opsommingstekens, nummering of markdown" | `agent_definitions.py:360` |
| regulation-agent | "Gebruik vloeiende zinnen, geen opsommingen" | `agent_definitions.py:386` |
| reporting-agent | "Geen lijsten, download links of formulier-achtige informatie" | `agent_definitions.py:407` |
| history-agent | "Geen tabellen, lijsten of gedetailleerde historiek" | `agent_definitions.py:426` |

The general-agent explicitly says "no markdown". The others ban specific patterns (lists, tables) but **don't explicitly ban bold, italic, headers, or code blocks**.

### Fallback Model Risk

The spoken text uses a fallback chain (`server-langgraph/src/agora_langgraph/core/agents.py:220-262`). When the primary model is unavailable, a fallback model is used. The fallback model may:
- Have different instruction-following fidelity
- Default to markdown formatting (many LLMs default to markdown)
- Not respect the "geen markdown" instruction as reliably

Configuration is in `config.py:44-66` via `LANGGRAPH_SPOKEN_PROVIDERS` env var.

### Existing Markdown Stripping (Mock Server Only)

`docs/hai-contract/mock_server.py:758-778` implements `to_spoken_text()`:
```python
def to_spoken_text(text: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)  # Italic
    text = re.sub(r"`([^`]+)`", r"\1", text)  # Code
    text = text.replace("- ", "")  # List bullets
    # + emoji replacements and abbreviation expansions
```

This is **not used** in either production backend.

### Where Spoken Text Is Sent (No Sanitization)

- **server-langgraph** (`orchestrator.py:684-735`): Streams raw LLM chunks directly via `agora:spoken_text_content` events
- **server-openai** (`orchestrator.py:262-363`): Same pattern — raw chunks from OpenAI API to frontend
- Neither backend applies any text transformation between receiving LLM output and sending it to the client

## Recommendations

### 1. Strengthen spoken prompts across all agents
Add explicit "geen markdown" to all four spoken prompts, not just general-agent. Consider adding:
```
"Gebruik GEEN markdown opmaak: geen **, geen *, geen #, geen `, geen opsommingstekens"
```

### 2. Add server-side markdown stripping as safety net
Port the mock server's `to_spoken_text()` to a shared utility and apply it to spoken text before sending events. Best locations:
- **server-langgraph**: In `_generate_spoken()` at `orchestrator.py:729` (before sending `agora:spoken_text_content`)
- **server-openai**: In `generate_spoken_parallel()` at `orchestrator.py:328` (before queueing chunks)

Considerations:
- Stripping must work on partial chunks (streaming), so regex-based stripping on partial text is tricky
- Alternative: accumulate full spoken text, strip once, then send as single event — but this adds latency
- Best approach: strip on the **accumulated buffer** before TTS playback on the frontend, or strip chunk-by-chunk for simple patterns (remove `*`, `#`, `` ` ``)

### 3. Frontend fallback (simplest, least latency impact)
Strip markdown in `useTTS.ts` before calling `client.speak(text)` at line 88. The full text is already buffered there:
```typescript
// In useTTS.ts, before speak()
const cleanText = spokenText
  .replace(/\*\*([^*]+)\*\*/g, '$1')
  .replace(/\*([^*]+)\*/g, '$1')
  .replace(/`([^`]+)`/g, '$1')
  .replace(/^#{1,6}\s+/gm, '')
  .replace(/^[-*]\s+/gm, '')
  .replace(/\n{2,}/g, '. ');
```

## Code References

- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:348-438` - Spoken prompts
- `server-openai/src/agora_openai/core/agent_definitions.py:347-435` - Spoken prompts (server-openai)
- `server-langgraph/src/agora_langgraph/core/agents.py:220-262` - Spoken LLM fallback chain
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:684-735` - Spoken generation (no sanitization)
- `server-openai/src/agora_openai/pipelines/orchestrator.py:262-363` - Spoken generation (no sanitization)
- `docs/hai-contract/mock_server.py:758-778` - `to_spoken_text()` markdown stripper (mock only)
- `HAI/src/hooks/useTTS.ts:84-96` - Frontend TTS buffer + speak (best place for frontend strip)

## Related Research

- `thoughts/shared/research/2026-03-01-spoken-written-divergence.md` - Spoken/written output divergence
- `thoughts/shared/research/2026-02-22-tts-number-pronunciation.md` - TTS number pronunciation
- `thoughts/shared/research/2026-03-01-llm-provider-fallback-strategy.md` - LLM fallback strategy

## Open Questions

- Which fallback model specifically causes the most markdown leakage? (Would help tune prompts)
- Should we strip on backend (chunk-level) or frontend (full-buffer)? Frontend is simpler but backend catches all clients
- Should the stripping also handle numbered lists (`1. `, `2. `) and blockquotes (`> `)?
