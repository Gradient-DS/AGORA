---
date: 2026-01-27T14:30:00+01:00
researcher: Claude
git_commit: 9fd45e82324c36562bd720283ef67e395d0e13cb
branch: main
repository: AGORA
topic: "Request clarification tool call stuck in loading state"
tags: [research, codebase, server-langgraph, tool-calls, interrupt, ag-ui-protocol]
status: complete
last_updated: 2026-01-27
last_updated_by: Claude
---

# Research: Request Clarification Tool Call Stuck in Loading State

**Date**: 2026-01-27T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 9fd45e82324c36562bd720283ef67e395d0e13cb
**Branch**: main
**Repository**: AGORA

## Research Question

The "Opvragen aanvullende informatie" (request_clarification) tool call does not transition to the done/completed state after being processed. It remains stuck in loading until the app is refreshed. After refreshing, only the completed tool call remains, suggesting duplicate tool calls where one never completes.

## Summary

**Root Cause Identified**: Missing `message_id` parameter in the interrupt handling code at `orchestrator.py:632-635`. The call to `send_tool_call_result` fails with a TypeError because `message_id` is a required parameter, but only `tool_call_id` and `content` are provided. The exception is silently caught, preventing the TOOL_CALL_RESULT event from being sent.

**Secondary Issue**: When the graph resumes after user input, LangGraph emits a new tool execution with a different `run_id`. This creates a duplicate tool call in the frontend that completes successfully, while the original interrupted tool call remains stuck.

## Detailed Findings

### 1. The Bug: Missing `message_id` Parameter

**Location**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:632-635`

The interrupt handling code attempts to close interrupted tool calls:

```python
await protocol_handler.send_tool_call_result(
    tool_call_id=tool_run_id,
    content=result_content or "Clarification requested",
)
```

But the function signature at `ag_ui_handler.py:317-322` requires `message_id`:

```python
async def send_tool_call_result(
    self,
    message_id: str,  # REQUIRED - but not provided!
    tool_call_id: str,
    content: str,
) -> None:
```

This causes a `TypeError: send_tool_call_result() missing 1 required positional argument: 'message_id'` which is caught by the try/except at line 678-679 and only logged as a warning.

### 2. Event Flow During Interrupt

When `request_clarification` is called:

1. **Tool Start**: `on_tool_start` event fires -> `TOOL_CALL_START` sent -> frontend creates tool call with `status: 'started'`
2. **Interrupt**: `interrupt()` is called at `tools.py:101` -> graph execution pauses
3. **No Tool End**: Since the tool function hasn't returned, NO `on_tool_end` event is emitted
4. **Interrupt Handling** (lines 622-636):
   - `send_tool_call_end` succeeds (line 627)
   - `send_tool_call_result` FAILS due to missing `message_id` (lines 632-635)
   - Exception is caught and logged (lines 678-679)
5. **Frontend State**: Receives `TOOL_CALL_END` but NO `TOOL_CALL_RESULT`

### 3. Frontend Event Handling

At `HAI/src/hooks/useWebSocket.ts:204-219`:

```typescript
case EventType.TOOL_CALL_END:
  // TOOL_CALL_END now just signals end of streaming, result comes via TOOL_CALL_RESULT
  break;  // NO-OP!

case EventType.TOOL_CALL_RESULT:
  updateToolCall(event.toolCallId, {
    status: 'completed',  // Only this updates the status!
    result: event.content,
  });
```

The frontend explicitly ignores `TOOL_CALL_END` and only marks tool calls as completed when `TOOL_CALL_RESULT` is received. Since the backend fails to send `TOOL_CALL_RESULT`, the tool call stays in `'started'` status forever.

### 4. Duplicate Tool Call on Resume

When the user responds (e.g., "ja ja ja"):

1. **Resume Detection**: `orchestrator.py:218-221` detects interrupted state via `aget_state()`
2. **Command Resume**: Graph resumes with `Command(resume=user_content)` at line 232
3. **Tool Execution Replays**: LangGraph emits a NEW `on_tool_start` event with a different `run_id`
4. **Tool Completes**: The tool returns the user response, emitting `on_tool_end`
5. **Result Sent**: Normal flow sends `TOOL_CALL_END` and `TOOL_CALL_RESULT`

This creates TWO tool calls in the frontend:
- **First (stuck)**: Original `run_id`, never received `TOOL_CALL_RESULT`
- **Second (completed)**: New `run_id`, properly completed

### 5. Why Refresh Fixes It

At `HAI/src/lib/api/sessions.ts:148` and `168`, history loading always marks tool calls as completed:

```typescript
// Line 148: For message store
toolStatus: 'completed',

// Line 168: For tool call store
status: 'completed',
```

The stuck tool call only exists in frontend memory - it was never persisted because it didn't have a result.

## Code References

- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:632-635` - Missing `message_id` in `send_tool_call_result` call
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:317-322` - Function signature requiring `message_id`
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:678-679` - Silent exception handling
- `server-langgraph/src/agora_langgraph/core/tools.py:101` - `interrupt()` call in `request_clarification`
- `HAI/src/hooks/useWebSocket.ts:204-206` - `TOOL_CALL_END` is no-op
- `HAI/src/hooks/useWebSocket.ts:208-219` - Only `TOOL_CALL_RESULT` updates status

## Architecture Insights

### AG-UI Protocol Tool Call Flow

The protocol requires this sequence:
1. `TOOL_CALL_START` - Creates tool call with `status: 'started'`
2. `TOOL_CALL_ARGS` - Updates parameters
3. `TOOL_CALL_END` - Signals argument streaming complete (frontend no-op)
4. `TOOL_CALL_RESULT` - **Required** to mark as `status: 'completed'`

### LangGraph Interrupt Pattern

When a tool calls `interrupt()`:
- Graph execution pauses, state is persisted
- Tool function has NOT returned, so no `on_tool_end` event
- Manual cleanup required in post-streaming code
- Resume creates a new tool execution with different `run_id`

## Solutions

### Primary Fix (Required)

Add the missing `message_id` parameter at `orchestrator.py:632-635`:

```python
await protocol_handler.send_tool_call_result(
    message_id=f"tool-result-{tool_run_id}",  # ADD THIS
    tool_call_id=tool_run_id,
    content=result_content or "Clarification requested",
)
```

### Secondary Fix (Recommended)

Prevent duplicate tool calls on resume by tracking the original `run_id` and not emitting new `TOOL_CALL_START` events for resumed tools.

Options:
1. Store interrupted tool `run_id`s in state and skip `on_tool_start` for matching IDs on resume
2. Use the same `run_id` for resumed tool execution
3. Add frontend deduplication by tool name + timestamp proximity

### Defensive Fix (Optional)

Make the exception handling more visible at `orchestrator.py:678-679`:

```python
except Exception as e:
    log.error(f"Failed to check interrupt state: {e}", exc_info=True)  # ERROR not warning
```

## Open Questions

1. **Should resumed tools emit new events?** LangGraph's behavior of creating new `run_id`s on resume may be intentional for state tracking, but it creates confusion in the UI.

2. **Should TOOL_CALL_END mark completion?** The current protocol relies entirely on TOOL_CALL_RESULT for status updates. Consider whether TOOL_CALL_END should also update status as a fallback.

3. **Should there be a timeout?** Tool calls stuck in 'started' state could be automatically failed after a configurable timeout.
