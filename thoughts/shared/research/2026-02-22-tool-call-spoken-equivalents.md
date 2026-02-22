---
date: 2026-02-22T15:44:22+01:00
researcher: claude
git_commit: ac8982c58a640949daafc8331ab97bda483e9e44
branch: main
repository: Gradient-DS/AGORA
topic: "Spoken equivalents for tool calls in the AG-UI protocol"
tags: [research, codebase, tts, tool-calls, ag-ui-protocol, tool-display-names]
status: complete
last_updated: 2026-02-22
last_updated_by: claude
---

# Research: Spoken Equivalents for Tool Calls in the AG-UI Protocol

**Date**: 2026-02-22T15:44:22+01:00
**Researcher**: claude
**Git Commit**: ac8982c
**Branch**: main
**Repository**: Gradient-DS/AGORA

## Research Question

Does AGORA already provide spoken equivalents for tool calls? If so, where can they be edited? If not, what would it take to add them to the AG-UI protocol?

## Summary

**Yes, the infrastructure already exists but is not wired up in the production backends.** There are two separate fields on `TOOL_CALL_START` events:

| Field | Purpose | Populated in production? | Frontend wired? |
|-------|---------|-------------------------|-----------------|
| `toolDisplayName` | Visual UI label (Dutch) | Yes | Yes (display only, not TTS) |
| `toolDescription` | Spoken TTS announcement | **No** (only mock server) | **Yes** (speaks via ElevenLabs) |

The `toolDescription` field is fully specified in the AG-UI protocol (asyncapi.yaml, JSON schemas, HAI_API_CONTRACT.md), the frontend Zod schema validates it, and the `useTTS` hook already speaks it aloud when present. The only missing piece is that **neither production backend populates this field** -- the `send_tool_call_start()` method doesn't accept a `tool_description` parameter.

**To enable spoken tool call announcements, you need to:**
1. Add a `TOOL_SPOKEN_DESCRIPTIONS` registry (or extend `TOOL_DISPLAY_NAMES`) in both backends
2. Wire `tool_description` through `send_tool_call_start()` in both `ag_ui_handler.py` files
3. Pass the spoken description at the orchestrator call sites

No frontend or protocol spec changes needed -- it's all already in place.

## Detailed Findings

### The Two Fields: `toolDisplayName` vs `toolDescription`

#### `toolDisplayName` (visual display -- fully operational)

Defined in `tool_display_names.py` (identical in both backends):

```python
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "check_company_exists": "Controleren bedrijfsgegevens",
    "search_regulations": "Zoeken in regelgeving",
    "transfer_to_reporting": "Overdracht naar rapportage",
    # ... 20+ entries
}
```

- Sent in every `TOOL_CALL_START` event via `toolDisplayName` field
- Rendered in the chat (ToolCallReference), debug panel (ToolCallCard), and loading indicator
- **Not spoken** -- the frontend uses it purely for visual display

#### `toolDescription` (spoken TTS -- specified but not populated)

Protocol spec in asyncapi.yaml:
```yaml
toolDescription:
  type: string
  nullable: true
  description: |
    Human-readable spoken description of the tool action.
    Used for TTS to announce what the agent is doing.
    Example: "Ik ga de regelgeving doorzoeken"
```

Frontend handling in `useWebSocket.ts:207-213`:
```typescript
if (toolEvent.toolDescription) {
  emitTTSEvent({
    type: 'tool_description',
    content: toolEvent.toolDescription,
  });
}
```

TTS playback in `useTTS.ts:99-108`:
```typescript
case 'tool_description':
  if (event.content && event.content.trim().length > 0) {
    await client.speak(event.content);
  }
  break;
```

**Gap**: The backend `send_tool_call_start()` method does not accept or pass `toolDescription`. The method signature only has `tool_display_name`.

### Mock Server Shows the Pattern

The mock server at `docs/hai-contract/mock_server.py:980-1005` demonstrates how it's meant to work for handoff tools:

```python
tool_descriptions = {
    Agents.HISTORY: "Ik schakel de bedrijfshistorie specialist in",
    Agents.REGULATION: "Ik schakel de regelgeving specialist in",
    Agents.REPORTING: "Ik schakel de rapportage specialist in",
}
```

Non-handoff tools in the mock server don't provide `toolDescription`, so they're silent in TTS.

### What Needs to Change (Implementation Guide)

**Step 1: Create spoken description registry** (2 files)

Add to both `tool_display_names.py` files (or a new file):

```python
TOOL_SPOKEN_DESCRIPTIONS: dict[str, str] = {
    # History agent tools
    "check_company_exists": "Ik controleer de bedrijfsgegevens",
    "get_inspection_history": "Ik haal de inspectiehistorie op",
    "get_company_violations": "Ik zoek naar overtredingen",
    # Regulation agent tools
    "search_regulations": "Ik doorzoek de regelgeving",
    "analyze_regulations": "Ik analyseer de regelgeving",
    # Reporting agent tools
    "generate_report": "Ik genereer het rapport",
    # Handoff tools
    "transfer_to_reporting": "Ik schakel de rapportage specialist in",
    "transfer_to_regulation": "Ik schakel de regelgeving specialist in",
    "transfer_to_history": "Ik schakel de inspectiehistorie specialist in",
    "transfer_to_general": "Ik schakel terug naar de algemene assistent",
}

def get_tool_spoken_description(tool_name: str) -> str | None:
    return TOOL_SPOKEN_DESCRIPTIONS.get(tool_name)
```

**Step 2: Wire through ag_ui_handler** (2 files)

In both `ag_ui_handler.py` files, add `tool_description` parameter:

```python
async def send_tool_call_start(
    self,
    tool_call_id: str,
    tool_call_name: str,
    tool_display_name: str | None = None,
    tool_description: str | None = None,      # NEW
    parent_message_id: str | None = None,
) -> None:
    kwargs = { ... }
    if tool_display_name:
        kwargs["toolDisplayName"] = tool_display_name
    if tool_description:                       # NEW
        kwargs["toolDescription"] = tool_description
    event = ToolCallStartEvent(**kwargs)
```

This works without modifying the upstream `ag_ui.core.ToolCallStartEvent` because it uses `extra="allow"` via Pydantic's `ConfiguredBaseModel`.

**Step 3: Pass at call sites** (2 files)

In both orchestrator files, add the lookup:

```python
await handler.send_tool_call_start(
    tool_call_id=tool_call_id,
    tool_call_name=tool_name,
    tool_display_name=get_tool_display_name(tool_name),
    tool_description=get_tool_spoken_description(tool_name),  # NEW
)
```

**No frontend changes needed** -- `useWebSocket.ts`, `useTTS.ts`, and the Zod schema already handle `toolDescription`.

### Architecture Context

The spoken text system uses a **dual-channel architecture**:
1. Written text → main agent prompt → `TEXT_MESSAGE_*` events
2. Spoken text → parallel LLM call with `SPOKEN_AGENT_PROMPTS` → `agora:spoken_text_*` custom events

Tool calls operate on a **separate timeline** from both channels. During tool execution, neither written nor spoken text streams are active. The `toolDescription` field provides a way to announce tool activity in the gap between text messages.

The complete data flow for spoken tool announcements:
```
Tool execution detected
  → get_tool_spoken_description(tool_name)
    → send_tool_call_start(..., tool_description="Ik doorzoek de regelgeving")
      → WebSocket: TOOL_CALL_START { toolDescription: "Ik doorzoek de regelgeving" }
        → useWebSocket: emitTTSEvent({ type: 'tool_description', content: ... })
          → useTTS: client.speak("Ik doorzoek de regelgeving")
            → ElevenLabs TTS → Audio output
```

## Code References

### Backend - Tool Display Names
- `server-langgraph/src/agora_langgraph/core/tool_display_names.py:7-45` -- TOOL_DISPLAY_NAMES registry
- `server-openai/src/agora_openai/core/tool_display_names.py:7-45` -- identical registry

### Backend - AG-UI Handler (where toolDescription needs wiring)
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:285-304` -- send_tool_call_start method
- `server-openai/src/agora_openai/api/ag_ui_handler.py:278-296` -- send_tool_call_start method

### Backend - Orchestrator Call Sites
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:553-558` -- tool start emission
- `server-openai/src/agora_openai/pipelines/orchestrator.py:424-429` -- tool start emission

### Frontend - Already Wired
- `HAI/src/hooks/useWebSocket.ts:207-213` -- emits TTS event for toolDescription
- `HAI/src/hooks/useTTS.ts:99-108` -- speaks toolDescription via ElevenLabs
- `HAI/src/types/schemas.ts:96` -- Zod validation for toolDescription field

### Protocol Specification
- `docs/hai-contract/asyncapi.yaml:580-586` -- toolDescription field spec
- `docs/hai-contract/schemas/messages.json:257-259` -- JSON Schema definition
- `docs/hai-contract/HAI_API_CONTRACT.md:769` -- human-readable documentation
- `docs/hai-contract/mock_server.py:980-1005` -- reference implementation

### Upstream AG-UI Package
- `ag_ui.core.types.ConfiguredBaseModel` -- `extra="allow"` enables extension fields
- `ag_ui.core.events.ToolCallStartEvent` -- base event class (no toolDescription field natively)

## Related Research

- `thoughts/shared/research/2026-02-22-tts-number-pronunciation.md` -- Related TTS research on number pronunciation in spoken agent prompts

## Open Questions

1. **Which tools should have spoken descriptions?** Only handoffs (like the mock server), or all tools? Speaking every tool call might be verbose during multi-tool sequences.
2. **Phrasing style**: Should descriptions be first-person ("Ik doorzoek de regelgeving") or impersonal ("Regelgeving wordt doorzocht")?
3. **Deduplication with toolDisplayName**: Should `toolDescription` be auto-derived from `toolDisplayName` (e.g., prefix "Ik ben bezig met...") or maintained as a separate independent registry?
4. **Timing considerations**: During rapid multi-tool sequences, should all descriptions be spoken or only the first/last? The current frontend implementation speaks each one immediately, which could queue up multiple TTS calls.
