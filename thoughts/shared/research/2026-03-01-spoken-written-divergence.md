---
date: 2026-03-01T20:30:00+01:00
researcher: claude
git_commit: e263eb30d3b6267eb8af00bf84ffcc706113dd60
branch: feat/comments-youri
repository: AGORA
topic: "Written vs spoken output divergence after image-containing turns"
tags: [research, codebase, parallel-generation, spoken-written, multimodal, tts]
status: complete
last_updated: 2026-03-01
last_updated_by: claude
---

# Research: Written vs Spoken Output Divergence After Image-Containing Turns

**Date**: 2026-03-01T20:30:00+01:00
**Researcher**: claude
**Git Commit**: e263eb30d3b6267eb8af00bf84ffcc706113dd60
**Branch**: feat/comments-youri
**Repository**: AGORA

## Research Question
Why do the spoken and written outputs diverge significantly after image-containing turns? Are the models receiving different context?

## Summary

**The models DO receive the same message context** (minus images), so the context hypothesis is only partially correct. The divergence is caused by a combination of three factors:

1. **Prompt-driven hallucination** (primary cause): The reporting-agent's spoken prompt contains a hardcoded example `'Het rapport is aangemaakt en verzonden. De details staan in de chat.'` which the spoken model copies verbatim regardless of whether the report was actually generated.
2. **Model capability gap**: The spoken model (`gpt-oss-120b`) is less capable than the written model (`gemini-3-flash-preview`) and more susceptible to blindly following prompt examples.
3. **Image context loss**: While the spoken model can't see images, it DOES see the written AI responses from previous turns that reference the image. This is sufficient for context continuity but requires a model capable enough to follow indirect references.

## Detailed Findings

### 1. Context Assembly — Both Models Get the Same Messages

`_create_parallel_sends()` at `server-langgraph/src/agora_langgraph/core/graph.py:324-456` builds the context for both streams. The process:

1. **Tool context extraction** (lines 355-370): All tool calls and results are converted to plain text (`[Tool aanroep: name(args)]`, `[Resultaat: content]`)
2. **Message filtering** (lines 372-383): Only `HumanMessage` and plain-text `AIMessage` survive
3. **Agent response removal** (lines 387-391): The agent's "wasted" final response is stripped
4. **Tool context injection** (lines 395-397): Tool results are re-added as a `HumanMessage`

Both streams receive this same filtered message list. The ONLY difference in messages is at lines 411-430 where images are handled for spoken:

```python
# For spoken: image parts are stripped, replaced with placeholder
text += "\n\n[De gebruiker heeft een afbeelding bijgevoegd.]"
```

### 2. Previous Written Responses Are Visible to Both Models

`merge_parallel_outputs()` at `graph.py:547-596` stores only the **written** content as the `AIMessage.content`. The spoken text goes into `additional_kwargs["spoken_text"]` (which LLMs don't see).

This means on subsequent turns, **both** the written and spoken models see the **written** AI responses from previous turns. The spoken model at Turn 3 can read the Turn 2 written response about the poster ("De poster die u laat zien is een instructie voor handhygiëne").

### 3. The Smoking Gun: Spoken Prompt for reporting-agent

The reporting-agent spoken prompt at `server-langgraph/src/agora_langgraph/core/agent_definitions.py:308-325` contains:

```
SPECIFIEKE SITUATIES:

2. Bij rapport generatie: Bevestig kort dat het rapport is aangemaakt.
   Voorbeeld: 'Het rapport is aangemaakt en verzonden. De details staan in de chat.'
```

The actual spoken output at Turn 3 was:
> "Het rapport is aangemaakt en verzonden. De details staan in de chat."

This is an **exact copy** of the prompt example. The spoken model blindly followed the example instead of understanding the actual context (reporting-agent was asking follow-up questions, not generating a report).

Additionally, the shared `_SPOKEN_TTS_NUMBER_RULES` prefix (lines 244-258) contains:
```
In plaats van 'Rapport HAP-2842A-2 is aangemaakt' → 'Het rapport is aangemaakt, de details staan in de chat'
```

This reinforces the pattern across ALL spoken agents.

### 4. Model Selection — Different Models for Each Stream

At `graph.py:482`:
```python
llm = get_llm_for_spoken() if stream_type == "spoken" else get_llm_for_agent(agent_id)
```

From the logs:
- **Written model**: `gemini-3-flash-preview` (primary, with `gpt-4o` and `gpt-4o-mini` as fallbacks)
- **Spoken model**: `gpt-oss-120b` (with two OpenAI-compatible fallbacks)

The spoken model is likely less capable and more susceptible to prompt-following vs context-understanding.

### 5. Architecture of Parallel Generation

The written and spoken models generate **independently** — they don't share outputs. This is by design (via LangGraph `Send` API), but it means they can completely diverge if one model misinterprets the context.

```
Agent ReAct loop → No more tool calls → route_from_agent
    ├── Send("generate_written", messages + written_prompt + agent LLM)
    └── Send("generate_spoken", spoken_messages + spoken_prompt + spoken LLM)
         (runs in parallel)
    → merge_parallel_outputs → AIMessage(content=written, kwargs.spoken_text=spoken)
```

### 6. No Branch-Specific Bugs

The parallel generation code (`graph.py`, `agents.py`) has **not changed** between `main` and `feat/comments-youri`. The changes on this branch are primarily:
- `extract_text()` replacing `str()` for content normalization (provider compatibility)
- Multi-provider fallback chains (new in `agents.py`)
- Image handling in orchestrator (save, forward to reporting MCP)
- Interrupt-based approval flow (replacing Future-based approach)

None of these changes affect the message context assembly for parallel generation.

## Code References

- `server-langgraph/src/agora_langgraph/core/graph.py:324-456` — `_create_parallel_sends()`: builds context for both streams
- `server-langgraph/src/agora_langgraph/core/graph.py:411-430` — Image stripping for spoken messages
- `server-langgraph/src/agora_langgraph/core/graph.py:459-526` — `_generate_stream()`: LLM invocation
- `server-langgraph/src/agora_langgraph/core/graph.py:547-596` — `merge_parallel_outputs()`: stores written as AIMessage content
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:308-325` — Reporting-agent spoken prompt with hardcoded example
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:244-258` — Shared TTS number rules with "rapport aangemaakt" example
- `server-langgraph/src/agora_langgraph/core/agents.py:133-147` — Spoken LLM configuration
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:636-683` — Streaming chunks to frontend

## Root Cause Analysis

| Log Turn | Agent | Written Output | Spoken Output | Cause of Divergence |
|----------|-------|---------------|---------------|-------------------|
| Turn 1 | history-agent | Detailed history overview | Short summary of key warning | Expected — different prompts, same content |
| Turn 2 | regulation-agent | Analysis of poster image | General statement about 2022 warning | Expected — spoken model can't see image |
| Turn 3 | reporting-agent | **Asks follow-up questions** | **"Rapport is aangemaakt en verzonden"** | **BUG — spoken prompt example blindly copied** |
| Turn 4 | general-agent | Report generated + download links | Report summary + download links | Roughly aligned — report IS generated |

## Recommended Fixes

### Fix 1: Revise reporting-agent spoken prompt (quick win)
Remove/rephrase the hardcoded "rapport is aangemaakt" example. Replace with context-aware guidance:

```python
"reporting-agent": (
    _SPOKEN_TTS_NUMBER_RULES +
    "Je bent een rapportage-specialist die ZEER KORTE gesproken statusupdates geeft.\n\n"
    "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
    "- Maximaal 1-2 zinnen per update\n"
    "- Geef alleen de kernactie of kernvraag, geen details\n"
    "- Geen lijsten, download links of formulier-achtige informatie\n\n"
    "SITUATIES:\n"
    "- Als je vragen stelt aan de inspecteur: Stel de belangrijkste vraag kort.\n"
    "- Als een rapport is gegenereerd: Bevestig kort, verwijs naar de chat voor details.\n"
    "- Bij tussentijdse updates: Korte status.\n\n"
    "NOOIT noemen: downloadlinks, PDF, JSON, rapport-IDs, e-mailadressen of URLs.\n"
    "Die staan in de geschreven versie."
),
```

### Fix 2: Two-phase generation (architectural improvement)
Instead of generating written and spoken in parallel (independently), generate sequentially:
1. Generate written response first
2. Feed the written response to the spoken model as context to summarize

This ensures the spoken output is always a summary of the written output, not a potentially divergent independent generation. Tradeoff: adds latency (~1-2s).

### Fix 3: Use a more capable spoken model
The `gpt-oss-120b` model appears prone to example-copying. A more capable model might better distinguish between prompt examples and actual context.

## Open Questions

1. Should the spoken model see the written output before generating? (Fix 2)
2. Is there a way to detect when spoken/written outputs are semantically misaligned and trigger a retry?
3. Should the spoken prompts be reworked to avoid concrete examples that models might copy verbatim?
