# Handoff Tool Spoken Descriptions Implementation Plan

## Overview

Add spoken TTS descriptions for handoff tool calls so the inspector hears "Ik geef het door aan de [agent name]" when the system transfers between agents. Only handoff tools get spoken descriptions — regular tools remain silent in TTS.

## Current State Analysis

The AG-UI protocol, frontend Zod schema, and TTS hooks already support `toolDescription` on `TOOL_CALL_START` events. The frontend speaks it via ElevenLabs when present. The only gap is that **neither backend populates this field**.

### Key Discoveries:
- `toolDescription` is already in asyncapi.yaml, JSON schemas, and frontend Zod schema (`HAI/src/types/schemas.ts:96`)
- `useWebSocket.ts:207-213` emits a TTS event when `toolDescription` is present
- `useTTS.ts:99-108` speaks the content via ElevenLabs
- `ToolCallStartEvent` uses `extra="allow"` so extra kwargs like `toolDescription` pass through without model changes
- Both `tool_display_names.py` files are identical (keep them in sync)
- Both `ag_ui_handler.py` `send_tool_call_start` methods are identical except for one debug log line in langgraph

## Desired End State

When a handoff tool executes, the inspector hears a spoken announcement like "Ik geef het door aan de rapportage agent" via TTS. Non-handoff tools remain silent (no `toolDescription` field sent).

### Verification:
- Run the system with TTS enabled, trigger a handoff → spoken announcement plays
- Non-handoff tool calls → no spoken announcement
- Both backends produce identical `toolDescription` values for the same handoff tools

## What We're NOT Doing

- No spoken descriptions for non-handoff tools (keeps TTS non-verbose)
- No frontend changes (already fully wired)
- No protocol spec changes (already specified)
- No changes to the mock server

## Implementation Approach

Three layers need a one-line-each change in both backends:
1. **Registry** — add `TOOL_SPOKEN_DESCRIPTIONS` dict + accessor function
2. **Handler** — add `tool_description` parameter to `send_tool_call_start()`
3. **Orchestrator** — pass the spoken description at the call site

## Phase 1: Add Spoken Description Registry

### Changes Required:

#### 1. server-openai tool_display_names.py
**File**: `server-openai/src/agora_openai/core/tool_display_names.py`

Add after line 50 (after `get_tool_display_name`):

```python


TOOL_SPOKEN_DESCRIPTIONS: dict[str, str] = {
    "transfer_to_reporting": "Ik geef het door aan de rapportage agent.",
    "transfer_to_regulation": "Ik geef het door aan de regelgeving agent.",
    "transfer_to_history": "Ik geef het door aan de inspectiehistorie agent.",
    "transfer_to_general": "Ik geef het door aan de algemene agent.",
    "transfer_to_triage": "Ik geef het door aan de triage agent.",
    "transfer_to_agent": "Ik geef het door aan de specialist.",
}


def get_tool_spoken_description(tool_name: str) -> str | None:
    """Get spoken TTS description for a tool, or None for no announcement."""
    return TOOL_SPOKEN_DESCRIPTIONS.get(tool_name)
```

#### 2. server-langgraph tool_display_names.py
**File**: `server-langgraph/src/agora_langgraph/core/tool_display_names.py`

Identical addition as above (keep files in sync).

---

## Phase 2: Wire toolDescription Through ag_ui_handler

### Changes Required:

#### 1. server-openai ag_ui_handler.py
**File**: `server-openai/src/agora_openai/api/ag_ui_handler.py`

Change `send_tool_call_start` (lines 278-296) to add `tool_description` parameter:

```python
    async def send_tool_call_start(
        self,
        tool_call_id: str,
        tool_call_name: str,
        tool_display_name: str | None = None,
        tool_description: str | None = None,
        parent_message_id: str | None = None,
    ) -> None:
        """Emit TOOL_CALL_START event."""
        # Build kwargs with optional toolDisplayName
        kwargs: dict[str, Any] = {
            "tool_call_id": tool_call_id,
            "tool_call_name": tool_call_name,
            "parent_message_id": parent_message_id,
            "timestamp": _now_timestamp(),
        }
        if tool_display_name:
            kwargs["toolDisplayName"] = tool_display_name
        if tool_description:
            kwargs["toolDescription"] = tool_description
        event = ToolCallStartEvent(**kwargs)
        await self._send_event(event)
```

#### 2. server-langgraph ag_ui_handler.py
**File**: `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py`

Same change (lines 285-304), keeping the existing debug log line:

```python
    async def send_tool_call_start(
        self,
        tool_call_id: str,
        tool_call_name: str,
        tool_display_name: str | None = None,
        tool_description: str | None = None,
        parent_message_id: str | None = None,
    ) -> None:
        """Emit TOOL_CALL_START event."""
        # Build kwargs with optional toolDisplayName
        kwargs: dict[str, Any] = {
            "tool_call_id": tool_call_id,
            "tool_call_name": tool_call_name,
            "parent_message_id": parent_message_id,
            "timestamp": _now_timestamp(),
        }
        if tool_display_name:
            kwargs["toolDisplayName"] = tool_display_name
        if tool_description:
            kwargs["toolDescription"] = tool_description
        event = ToolCallStartEvent(**kwargs)
        log.info(f"[DEBUG] TOOL_CALL_START JSON: {event.model_dump_json(by_alias=True, exclude_none=True)}")
        await self._send_event(event)
```

---

## Phase 3: Pass Spoken Description at Orchestrator Call Sites

### Changes Required:

#### 1. server-openai orchestrator.py
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`

Update import (line 28):
```python
from agora_openai.core.tool_display_names import get_tool_display_name, get_tool_spoken_description
```

Update call site (lines 424-429):
```python
                        await protocol_handler.send_tool_call_start(
                            tool_call_id=tool_call_id,
                            tool_call_name=tool_name,
                            tool_display_name=get_tool_display_name(tool_name),
                            tool_description=get_tool_spoken_description(tool_name),
                            parent_message_id=message_id,
                        )
```

#### 2. server-langgraph orchestrator.py
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Update import (line 26):
```python
from agora_langgraph.core.tool_display_names import get_tool_display_name, get_tool_spoken_description
```

Update call site (lines 553-558):
```python
                    await protocol_handler.send_tool_call_start(
                        tool_call_id=tool_run_id,
                        tool_call_name=tool_name,
                        tool_display_name=get_tool_display_name(tool_name),
                        tool_description=get_tool_spoken_description(tool_name),
                        parent_message_id=message_id,
                    )
```

---

## Testing Strategy

### Manual Testing Steps:
1. Start the system with TTS enabled (ElevenLabs configured)
2. Begin a conversation and request something that triggers a handoff (e.g., ask about regulations to trigger `transfer_to_regulation`)
3. Verify the inspector hears "Ik geef het door aan de regelgeving agent."
4. Verify non-handoff tool calls (e.g., `search_regulations`) do NOT produce spoken announcements
5. Test with both server-openai and server-langgraph backends

### Automated Verification:
- [x] Type check passes: `cd server-openai && mypy src/` (pre-existing errors only)
- [x] Type check passes: `cd server-langgraph && mypy src/` (pre-existing errors only)
- [x] Lint passes: `cd server-openai && ruff check src/` (pre-existing errors only)
- [x] Lint passes: `cd server-langgraph && ruff check src/` (pre-existing errors only)
- [x] Tests pass: `cd server-openai && pytest` (21 passed)
- [x] Tests pass: `cd server-langgraph && pytest` (12 passed)

## Spoken Descriptions Reference

| Tool Name | Spoken Description |
|-----------|-------------------|
| `transfer_to_reporting` | "Ik geef het door aan de rapportage agent." |
| `transfer_to_regulation` | "Ik geef het door aan de regelgeving agent." |
| `transfer_to_history` | "Ik geef het door aan de inspectiehistorie agent." |
| `transfer_to_general` | "Ik geef het door aan de algemene agent." |
| `transfer_to_triage` | "Ik geef het door aan de triage agent." |
| `transfer_to_agent` | "Ik geef het door aan de specialist." |

## References

- Research: `thoughts/shared/research/2026-02-22-tool-call-spoken-equivalents.md`
- Protocol spec: `docs/hai-contract/asyncapi.yaml:580-586`
- Mock server reference: `docs/hai-contract/mock_server.py:980-1005`
