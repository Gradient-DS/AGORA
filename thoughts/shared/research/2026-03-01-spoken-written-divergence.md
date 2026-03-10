---
date: 2026-03-01T20:30:00+01:00
researcher: claude
git_commit: e263eb30d3b6267eb8af00bf84ffcc706113dd60
branch: feat/comments-youri
repository: AGORA
topic: "Written vs spoken output divergence after image-containing turns"
tags: [research, codebase, parallel-generation, spoken-written, multimodal, tts]
status: complete
last_updated: 2026-03-09
last_updated_by: claude
last_updated_note: "Added follow-up: message ordering fix, spoken prompt anchoring, extract_text fallback"
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

## Follow-up Research 2026-03-09: New Divergence Instances and Fixes

**Branch**: feat/tool-description
**Git Commit**: ecf14f4d0261f9c0c80f6696635e948297e92954

### New Instances Discovered

Three new divergence cases were reported from demo testing:

| Timestamp | Agent | Written | Spoken | Issue Type |
|-----------|-------|---------|--------|------------|
| 15:30:55 | regulation-agent | Full image analysis (food on floor, cross-contamination) | "Stuur me de afbeelding" (asks for image) | Context divergence — spoken didn't know about image |
| 15:29:46 | general-agent | New status summary for current inspection | Repeated previous turn's temperature answer | **Message ordering bug** |
| 16:16:28 | history-agent | 0 chars (2 chunks, 0 chars extracted) | 305 chars of useful content | Content extraction bug |

### Root Cause Analysis Update

#### Issue #1 (Image analysis): Already Fixed
The image is now fully decoupled from LLM context (`orchestrator.py:136-158`). Images are:
- Forwarded to reporting MCP server for PDF evidence (background task)
- Described by `gpt-4o-mini` (hardcoded, NOT the main thread model) for report captions only
- Never sent to the agent LLM or the spoken/written generation models
- Image-only messages skip LLM entirely (`orchestrator.py:184-191`)

This issue should not recur with the current code.

#### Issue #2 (Spoken repeats previous answer): **Message Ordering Bug — FIXED**
Root cause identified in `_create_parallel_sends()` (`graph.py:385-400`):

The tool context was injected as the **last message** in the conversation:
```
[HumanMessage: earlier question]
[AIMessage: earlier answer]
[HumanMessage: user's LATEST question]  ← buried
[HumanMessage: "[Uitgevoerde tools en resultaten]\n..."]  ← LAST
```

Industry standard for LLM message ordering is: **System Prompt → Context/History → User's Latest Question (always last)**. This is backed by:

- **"Lost in the Middle" (Liu et al., 2023)**: LLMs exhibit a U-shaped performance curve — accuracy is highest at beginning/end, degrades 30%+ in the middle. [arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)
- **Anthropic docs**: "Place long documents near the top, above your query. Queries at the end improve quality by up to 30%." [docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips)
- **OpenAI GPT-4.1 guide**: "If there are conflicting instructions, GPT-4.1 tends to follow the one closer to the end of the prompt." [cookbook.openai.com/examples/gpt4-1_prompting_guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)
- **OpenAI Chat API**: Structurally requires tool results between tool calls and the next user message, naturally placing the user's question last.
- **LangChain convention**: "Always maintain chronological order: SystemMessage → HumanMessage → AIMessage → ... → HumanMessage."

**Fix applied**: Tool context is now inserted BEFORE the last HumanMessage:
```
[HumanMessage: earlier question]
[AIMessage: earlier answer]
[HumanMessage: "[Uitgevoerde tools en resultaten]\n..."]  ← context
[HumanMessage: user's LATEST question]  ← LAST (anchors response)
```

Additionally, all spoken prompts now include `_SPOKEN_LATEST_MESSAGE_ANCHOR` — an explicit instruction to answer only the LAST user message. Applied to both `server-langgraph` and `server-openai`.

#### Issue #3 (Written empty): **Content Extraction Fallback — FIXED**
The `extract_text()` function in `message_utils.py` silently skipped dict parts with unrecognized `type` values. Some LLM providers (especially via OpenAI-compatible routers) return non-standard content part types.

**Fix applied**: For dict parts with types other than `"text"`, `None`, `"image_url"`, or `"binary"`, the function now attempts to extract the `"text"` key as a fallback before skipping.

### Files Changed

- `server-langgraph/src/agora_langgraph/core/graph.py:385-410` — Reordered tool context injection to preserve user question as last message
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:330-342` — Added `_SPOKEN_LATEST_MESSAGE_ANCHOR` to all spoken prompts
- `server-langgraph/src/agora_langgraph/common/message_utils.py:38-48` — Added fallback for unrecognized content part types
- `server-openai/src/agora_openai/core/agent_definitions.py:330-342` — Added same `_SPOKEN_LATEST_MESSAGE_ANCHOR` (server-openai doesn't have the message ordering issue since it uses raw AG-UI messages)

### Test Results
All tests pass in both `server-langgraph` (12 passed) and `server-openai` (21 passed).
