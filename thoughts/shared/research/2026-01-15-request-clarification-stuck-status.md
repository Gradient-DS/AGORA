---
date: 2026-01-15T14:30:00+01:00
researcher: Claude
git_commit: 278b51e374080b34b94afbbb0fb54f4030188060
branch: fix/parallel-stream-context
repository: AGORA
topic: "Request Clarification tool stuck on Uitvoeren status and missing Dutch name"
tags: [research, codebase, tool-calls, frontend, langgraph, i18n]
status: complete
last_updated: 2026-01-15
last_updated_by: Claude
---

# Research: Request Clarification Tool Status Issue

**Date**: 2026-01-15T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 278b51e374080b34b94afbbb0fb54f4030188060
**Branch**: fix/parallel-stream-context
**Repository**: AGORA

## Research Question

The "Request Clarification" tool call shows stuck "Uitvoeren" (executing) status in the UI when the tool completes. Additionally, the tool should have a Dutch name like other tools in the system.

## Summary

**Root Cause of Stuck Status**: The frontend only updates tool status to "completed" when receiving a `TOOL_CALL_RESULT` event. For `request_clarification`, the backend sends `TOOL_CALL_END` but never sends `TOOL_CALL_RESULT` because the interrupt mechanism pauses execution before the tool returns a result.

**Missing Dutch Name**: The `request_clarification` tool is not in the `TOOL_NAME_TRANSLATIONS` mapping in `toolNames.ts`, so it falls back to Title Case formatting ("Request Clarification").

## Detailed Findings

### Frontend Status Update Logic

The frontend handles tool call events in `useWebSocket.ts:168-219`:

```typescript
// TOOL_CALL_END does NOT update status (line 204-206)
case EventType.TOOL_CALL_END:
  // Don't update status here - just signals end of streaming, result comes via TOOL_CALL_RESULT
  break;

// Only TOOL_CALL_RESULT updates status to 'completed' (line 208-219)
case EventType.TOOL_CALL_RESULT:
  updateToolCall(event.toolCallId, {
    status: 'completed',
    result: event.content,
  });
```

The status config in `ToolCallCard.tsx:27-52` shows:
- `started` → "Uitvoeren" (blue, spinning loader)
- `completed` → "Afgerond" (green, checkmark)

### Backend Interrupt Handling

The `request_clarification` tool uses LangGraph's `interrupt()` mechanism (`tools.py:101-105`):

```python
user_response = interrupt({
    "type": "clarification_request",
    "questions": questions,
    "display_text": question_text,
})
```

When `interrupt()` is called:
1. LangGraph pauses execution immediately
2. The `on_tool_end` event is **never emitted** because the tool hasn't completed
3. The orchestrator detects the interrupt state and sends `TOOL_CALL_END` explicitly (`orchestrator.py:597-602`)
4. **But it never sends `TOOL_CALL_RESULT`**

Current cleanup code (`orchestrator.py:597-602`):
```python
if active_tool_calls and protocol_handler.is_connected:
    for tool_run_id, tool_name in list(active_tool_calls.items()):
        log.info(f"Closing interrupted tool call: {tool_name}")
        await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
    active_tool_calls.clear()
```

### Missing Dutch Translation

The `TOOL_NAME_TRANSLATIONS` in `toolNames.ts` includes tools for all agents, but `request_clarification` is missing:

```typescript
// Reporting agent tools (lines 23-31)
start_inspection_report: 'Starten inspectie rapport',
extract_inspection_data: 'Verwerken inspectiegegevens',
verify_inspection_data: 'Verifiëren inspectiegegevens',
submit_verification_answers: 'Verwerken antwoorden',
// ... request_clarification is MISSING
```

## Code References

- `HAI/src/hooks/useWebSocket.ts:204-219` - Frontend event handling (TOOL_CALL_END ignored, only TOOL_CALL_RESULT updates status)
- `HAI/src/components/chat/ToolCallCard.tsx:27-52` - Status display config
- `HAI/src/lib/utils/toolNames.ts:23-31` - Dutch translations (missing request_clarification)
- `server-langgraph/src/agora_langgraph/core/tools.py:78-107` - request_clarification tool definition
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:597-602` - Interrupt cleanup (sends TOOL_CALL_END only)

## Recommended Fix

### 1. Send TOOL_CALL_RESULT for Interrupted Tools

In `orchestrator.py`, after sending `TOOL_CALL_END`, also send `TOOL_CALL_RESULT` with the clarification questions as the result:

```python
if active_tool_calls and protocol_handler.is_connected:
    for tool_run_id, tool_name in list(active_tool_calls.items()):
        log.info(f"Closing interrupted tool call: {tool_name}")
        await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
        # NEW: Send TOOL_CALL_RESULT to mark as completed in frontend
        if interrupt_value and isinstance(interrupt_value, dict):
            result_content = interrupt_value.get("display_text", "Clarification requested")
            await protocol_handler.send_tool_call_result(
                tool_call_id=tool_run_id,
                content=result_content,
            )
    active_tool_calls.clear()
```

### 2. Add Dutch Translation

In `toolNames.ts`, add the Dutch name to `TOOL_NAME_TRANSLATIONS`:

```typescript
// In the Reporting agent tools section
request_clarification: 'Opvragen aanvullende informatie',
```

Alternative Dutch names:
- "Vragen om verduidelijking" (Asking for clarification)
- "Aanvullende vragen" (Additional questions)

## Architecture Insights

The interrupt-based HITL pattern creates an edge case where tools can "complete" from the user's perspective (questions shown, waiting for input) but the tool hasn't technically returned a result yet in the LangGraph execution model. The AG-UI Protocol's separation of `TOOL_CALL_END` (end of streaming) and `TOOL_CALL_RESULT` (actual result) makes this distinction clear, but both events are needed for proper frontend state.

## Open Questions

1. Should `TOOL_CALL_RESULT` content for request_clarification show the questions asked, or a generic "Awaiting user response" message?
2. Should this fix also apply to other potential interrupt-based tools in the future?
