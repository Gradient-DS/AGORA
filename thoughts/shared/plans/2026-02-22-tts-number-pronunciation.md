# TTS Number Pronunciation Fix — Implementation Plan

## Overview

Improve TTS pronunciation of numbers and codes in the spoken (summarize) channel by adding consistent rules to all `SPOKEN_AGENT_PROMPTS`. Numbers and codes currently cause garbled TTS output because ElevenLabs tries to pronounce them as words. Fix this by:
1. Spelling short numbers digit-by-digit (KVK, phone numbers)
2. Omitting complex codes entirely and referring users to the chat

## Current State Analysis

The system uses a dual-channel architecture: written text and spoken text are generated in parallel by separate LLM calls. Spoken prompts (`SPOKEN_AGENT_PROMPTS`) control TTS output in `summarize` mode.

**Problem areas:**
- **Langgraph reporting-agent** (line 291-307): Explicitly instructs to say the report ID: `'Rapport INS-2024-AB12CD is aangemaakt en verzonden naar jan@bedrijf.nl.'`
- **OpenAI reporting-agent** (line 295-307): No number guidance at all
- **All agents**: No general rules for handling KVK numbers, postcodes, or other numeric identifiers
- **Only exception**: regulation-agent already handles regulation-specific numbers (`22°C`, `EU 852/2004`)

### Key Discoveries:
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:245-327` — SPOKEN_AGENT_PROMPTS (langgraph)
- `server-openai/src/agora_openai/core/agent_definitions.py:257-327` — SPOKEN_AGENT_PROMPTS (openai)
- Report IDs use format `HAP-{YYYYMMDD}-{8-char-UUID}` (e.g., `HAP-20251218-39A787FB`)
- Spoken prompts are independent from written output — zero risk of affecting written responses

## Desired End State

All 4 spoken agent prompts (x2 orchestrators = 8 total) include consistent TTS number/code rules via a shared constant. After this change:

1. Short numbers (KVK, phone, postcode) are spelled digit-by-digit: `'12345678'` → `'één twee drie vier vijf zes zeven acht'`
2. Complex codes (report IDs, email addresses, URLs, UUIDs) are omitted with a reference to the chat
3. The reporting-agent no longer instructs to say the report ID

### Verification:
- Read both files and confirm the shared constant exists and is prepended to all spoken prompts
- Confirm the reporting-agent no longer mentions report IDs or email addresses in spoken output
- Manual test: trigger spoken output in summarize mode and verify TTS handles numbers naturally

## What We're NOT Doing

- **Dictate mode**: Not changing anything for dictate mode users (would require code changes, not prompt changes)
- **Written prompts**: Not modifying any main agent prompts — only spoken prompts
- **Code changes**: This is a prompt-only change, no Python logic changes
- **Regulation-agent existing rules**: Keeping the existing regulation-specific number rules (they're already good)

## Implementation Approach

Create a shared `SPOKEN_TTS_RULES` constant containing the number/code handling rules, and prepend it to each agent's spoken prompt. This avoids duplication and makes future TTS rule changes a single-edit change.

## Phase 1: Update Langgraph Spoken Prompts

### Overview
Add the shared TTS rules constant and update all 4 spoken prompts in the langgraph orchestrator.

### Changes Required:

#### 1. Add shared TTS rules constant
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
**Where**: Before `SPOKEN_AGENT_PROMPTS` (before line 245)

```python
# Shared TTS rules prepended to all spoken agent prompts
_SPOKEN_TTS_NUMBER_RULES = (
    "NUMMERS EN CODES - UITSPRAAKREGELS:\n"
    "- Korte nummers (KVK, telefoonnummers, postcodes) cijfer voor cijfer uitspreken:\n"
    "  * '12345678' → 'één twee drie vier vijf zes zeven acht'\n"
    "  * '1234AB' → 'één twee drie vier A B'\n"
    "  * '06-12345678' → 'nul zes, één twee drie vier vijf zes zeven acht'\n"
    "- Noem GEEN complexe codes, rapport-IDs, referentienummers, e-mailadressen of URLs\n"
    "- Verwijs hiervoor naar de chat:\n"
    "  * In plaats van 'Rapport HAP-2842A-2 is aangemaakt' → 'Het rapport is aangemaakt, de details staan in de chat'\n"
    "  * In plaats van 'KVK nummer 12345678' → 'Het Kamer van Koophandel nummer is één twee drie vier vijf zes zeven acht'\n"
    "  * In plaats van 'verzonden naar jan@bedrijf.nl' → 'het rapport is verzonden, het e-mailadres staat in de chat'\n\n"
)
```

#### 2. Prepend rules to each spoken prompt
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`

Update each `SPOKEN_AGENT_PROMPTS` value to prepend `_SPOKEN_TTS_NUMBER_RULES`:

```python
SPOKEN_AGENT_PROMPTS: dict[str, str] = {
    "general-agent": (
        _SPOKEN_TTS_NUMBER_RULES +
        "Je bent AGORA, een vriendelijke NVWA inspectie-assistent die KORTE "
        # ... rest unchanged ...
    ),
    "regulation-agent": (
        _SPOKEN_TTS_NUMBER_RULES +
        "Je bent een regelgeving-expert die KORTE gesproken antwoorden geeft.\n\n"
        # ... rest unchanged ...
    ),
    "reporting-agent": (
        _SPOKEN_TTS_NUMBER_RULES +
        "Je bent een rapportage-specialist die ZEER KORTE gesproken statusupdates "
        # ... rest mostly unchanged, but fix section 2 below ...
    ),
    "history-agent": (
        _SPOKEN_TTS_NUMBER_RULES +
        "Je bent een bedrijfshistorie-specialist die KORTE gesproken "
        # ... rest unchanged ...
    ),
}
```

#### 3. Fix reporting-agent spoken prompt (langgraph)
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`

Replace the problematic section (lines 301-303):

**Before:**
```python
"2. Bij rapport generatie: Zeg alleen rapport ID en ontvanger.\n"
"   Voorbeeld: 'Rapport INS-2024-AB12CD is aangemaakt en verzonden "
"naar jan@bedrijf.nl.'\n\n"
```

**After:**
```python
"2. Bij rapport generatie: Bevestig kort dat het rapport is aangemaakt.\n"
"   Voorbeeld: 'Het rapport is aangemaakt en verzonden. De details staan in de chat.'\n\n"
```

---

## Phase 2: Update OpenAI Spoken Prompts

### Overview
Same changes for the OpenAI orchestrator — add shared constant and prepend to all 4 prompts.

### Changes Required:

#### 1. Add shared TTS rules constant
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`
**Where**: Before `SPOKEN_AGENT_PROMPTS` (before line 257)

Add the exact same `_SPOKEN_TTS_NUMBER_RULES` constant as in Phase 1.

#### 2. Prepend rules to each spoken prompt
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`

Same pattern as Phase 1 — prepend `_SPOKEN_TTS_NUMBER_RULES +` to each spoken prompt string.

Note: The OpenAI reporting-agent spoken prompt (lines 295-307) does NOT have the explicit "say the report ID" instruction, but it also lacks any guidance about omitting codes. The shared constant covers this.

### Success Criteria:

#### Automated Verification:
- [x] Both files parse without syntax errors: `python -c "from agora_langgraph.core.agent_definitions import SPOKEN_AGENT_PROMPTS"` and `python -c "from agora_openai.core.agent_definitions import SPOKEN_AGENT_PROMPTS"`
- [x] All 4 spoken prompts in each file start with the shared TTS rules
- [x] The langgraph reporting-agent no longer contains "rapport ID" or "jan@bedrijf.nl" in its spoken prompt
- [ ] Linting passes: `ruff check server-langgraph/src/ server-openai/src/` (ruff not available locally - verify in CI)
- [ ] Type checking passes: `mypy server-langgraph/src/ server-openai/src/` (mypy not available locally - verify in CI)

#### Manual Verification:
- [ ] Start a conversation in summarize mode, trigger the history-agent with a KVK number → spoken output should spell digits, not say the full number
- [ ] Generate a report → spoken output should say "het rapport is aangemaakt" without mentioning the report ID or email
- [ ] General agent greeting → spoken output remains natural and unchanged
- [ ] Regulation agent → existing number rules (22°C, EU 852/2004) still work correctly alongside new rules

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful.

## Testing Strategy

### Automated:
- Import both modules to verify syntax
- Verify `_SPOKEN_TTS_NUMBER_RULES` appears in all 8 prompts (grep/assertion)

### Manual Testing Steps:
1. Start AGORA with summarize mode enabled
2. Say "Start inspectie bij Bakkerij Jansen KVK 12345678" → listen for digit-by-digit pronunciation
3. Complete an inspection and generate a report → verify no report ID or email in spoken output
4. Ask a regulation question mentioning temperatures → verify "tweeëntwintig graden Celsius" still works
5. Compare spoken output quality before and after the change

## References

- Research: `thoughts/shared/research/2026-02-22-tts-number-pronunciation.md`
- Langgraph spoken prompts: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:245-327`
- OpenAI spoken prompts: `server-openai/src/agora_openai/core/agent_definitions.py:257-327`
- Report ID format: `mcp-servers/reporting/storage/session_manager.py` — `HAP-{YYYYMMDD}-{8-char-UUID}`
