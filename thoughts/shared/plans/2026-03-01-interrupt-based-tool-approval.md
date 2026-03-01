# Interrupt-Based Tool Approval Implementation Plan

## Overview

Convert the tool approval mechanism for high-risk tools (like `generate_final_report`) from the broken `asyncio.Future`-based pattern to LangGraph's native `interrupt()` pattern, matching how `request_clarification` already works. This fixes the double-execution bug where tools execute before the user approves them.

## Current State Analysis

### The Bug
The `asyncio.Future` pattern in `orchestrator.py:117-158` blocks the orchestrator's event-processing loop but **not** the LangGraph graph execution. `astream_events` runs graph execution in a separate coroutine and buffers events. When the orchestrator `await`s the future on `on_tool_start`, the ToolNode has already executed the tool. The agent sees the result, may issue another call, and when the future resolves, queued events replay — causing double execution.

### Working Pattern
`request_clarification` (`tools.py:78-107`) calls `interrupt()` **inside** the tool function. This truly pauses graph execution at the ToolNode level. State is persisted, and the graph resumes only when `Command(resume=...)` is invoked. No double execution.

### Key Discoveries
- Approval logic (pure function): `core/approval_logic.py:28-68`
- Future-based approval: `orchestrator.py:76` (`pending_approvals`), `117-158` (`_handle_tool_approval_flow`), `160-172` (`handle_approval_response`)
- Called during event loop: `orchestrator.py:676` (`await self._handle_tool_approval_flow(...)`)
- Rejection exception handler: `orchestrator.py:441-448`
- Interrupt detection post-stream: `orchestrator.py:837-913`
- Resume logic: `orchestrator.py:340-354` (`Command(resume=user_content)`)
- Resume event suppression: `orchestrator.py:542-545, 655-662, 706-716`
- Hardcoded `reporting-agent` for resume: `orchestrator.py:380, 545`
- Frontend contract unchanged: sends `agora:tool_approval_response` custom event with `{approvalId, approved, feedback}`
- Server WebSocket handler: `server.py:596-597`

## Desired End State

1. High-risk tools call `interrupt()` **before** executing, pausing the graph
2. The orchestrator detects the approval-type interrupt, sends `agora:tool_approval_request` to the frontend
3. When the user approves/rejects, the graph resumes via `Command(resume={"approved": True/False})`
4. If approved, the original MCP tool executes; if rejected, a rejection message is returned to the agent
5. No `asyncio.Future` remains — the interrupt mechanism is the single HITL pattern
6. The interrupt/resume flow is generalized (not hardcoded to `reporting-agent` or `request_clarification`)
7. Frontend is unchanged — same custom event contract

### Verification
- High-risk tool (`generate_final_report`) does NOT execute before user approval
- Only ONE approval request is shown to the user (no duplicates)
- Approval → tool executes → agent responds normally
- Rejection → agent receives rejection message → responds naturally (e.g., "OK, I won't generate the report")
- `request_clarification` continues to work identically
- No regressions in normal tool execution (non-approval tools)

## What We're NOT Doing

- Changing the frontend (HAI) — the custom event contract stays identical
- Changing `server-openai` — this is a LangGraph-specific fix
- Changing `approval_logic.py` — the business rules for what requires approval stay the same
- Adding new approval UI patterns — reusing existing `agora:tool_approval_request/response`

## Implementation Approach

Wrap MCP tools that may require approval with an `interrupt()`-based gate in `get_tools_for_agent()`. Generalize the orchestrator's interrupt handling to distinguish between interrupt types (`clarification_request` vs `tool_approval_request`). Replace the Future-based approval response handler with graph resumption via `Command(resume=...)`.

---

## Phase 1: Tool Wrapping with `interrupt()`

### Overview
Create a wrapper that intercepts high-risk tool execution, calls `interrupt()` before the MCP call, and only proceeds if the user approves.

### Changes Required

#### 1. Add `wrap_tool_with_approval` in `tools.py`
**File**: `server-langgraph/src/agora_langgraph/core/tools.py`
**Changes**: Add a new function that wraps any `BaseTool` with an interrupt-based approval gate. Apply it in `get_tools_for_agent()`.

```python
from agora_langgraph.common.schemas import ToolCall as ToolCallSchema
from agora_langgraph.core.approval_logic import requires_human_approval


def wrap_tool_with_approval(tool: BaseTool) -> BaseTool:
    """Wrap a tool with interrupt-based approval if it may require human approval.

    When the wrapped tool is called by the ToolNode:
    1. Checks requires_human_approval with actual parameters
    2. If approval needed: calls interrupt() to pause the graph
    3. On resume: checks the approval decision
    4. If approved: executes the original tool
    5. If rejected: returns a rejection message without executing

    Args:
        tool: The original tool to wrap

    Returns:
        A new tool with the same name/schema but approval gating
    """
    original_func = tool.func
    original_coroutine = tool.coroutine

    def _check_and_interrupt(kwargs: dict) -> bool | None:
        """Check approval and interrupt if needed. Returns None if no approval needed,
        True if approved, False if rejected."""
        tc = ToolCallSchema(tool_name=tool.name, parameters=kwargs)
        needs, reason, risk = requires_human_approval([tc], {})

        if not needs:
            return None  # No approval needed

        response = interrupt({
            "type": "tool_approval_request",
            "tool_name": tool.name,
            "parameters": kwargs,
            "reason": reason,
            "risk_level": risk,
        })

        if isinstance(response, dict) and response.get("approved"):
            return True
        return False

    if original_coroutine:
        async def gated_coroutine(**kwargs):
            result = _check_and_interrupt(kwargs)
            if result is False:
                return "Actie geannuleerd door gebruiker."
            return await original_coroutine(**kwargs)

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            coroutine=gated_coroutine,
        )
    elif original_func:
        def gated_func(**kwargs):
            result = _check_and_interrupt(kwargs)
            if result is False:
                return "Actie geannuleerd door gebruiker."
            return original_func(**kwargs)

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            func=gated_func,
        )
    else:
        # Tool has neither func nor coroutine — return as-is
        log.warning(f"Cannot wrap tool {tool.name}: no func or coroutine")
        return tool
```

#### 2. Apply wrapping in `get_tools_for_agent()`
**File**: `server-langgraph/src/agora_langgraph/core/tools.py`
**Changes**: After collecting MCP tools for an agent, wrap each one with `wrap_tool_with_approval`.

```python
def get_tools_for_agent(
    agent_id: str,
    mcp_tools_by_server: dict[str, list[BaseTool]],
) -> list[Any]:
    # ... existing handoff/settings/clarification tool assignment ...

    mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
    for server_name in mcp_server_names:
        if server_name in mcp_tools_by_server:
            mcp_tools = mcp_tools_by_server[server_name]
            # Wrap MCP tools with approval gating
            wrapped_tools = [wrap_tool_with_approval(t) for t in mcp_tools]
            tools.extend(wrapped_tools)
            tool_names = [getattr(t, "name", str(t)) for t in wrapped_tools]
            log.info(f"{agent_id} gets MCP tools from {server_name}: {tool_names}")

    log.info(f"{agent_id} total tools: {len(tools)}")
    return tools
```

### Success Criteria

#### Automated Verification:
- [ ] Server starts without errors: `cd server-langgraph && python -m agora_langgraph.api.server`
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`

#### Manual Verification:
- [ ] When `generate_final_report` is called, graph pauses (interrupt fires) before executing the MCP call
- [ ] The interrupt value contains `type: "tool_approval_request"` with correct tool name and parameters

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the interrupt fires correctly before proceeding.

---

## Phase 2: Generalized Interrupt Handling in Orchestrator

### Overview
Modify the post-stream interrupt detection to distinguish between interrupt types and handle each appropriately. Remove the Future-based approval code. Store context needed for approval resumption.

### Changes Required

#### 1. Remove Future-based approval code
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Remove:
- `self.pending_approvals: dict[str, asyncio.Future[bool]] = {}` (line 76)
- `_handle_tool_approval_flow` method (lines 117-158)
- `handle_approval_response` method (lines 160-172)
- `await self._handle_tool_approval_flow(...)` call in `on_tool_start` handler (line 676-678)
- The rejection exception handler in `process_message` (lines 441-448)

#### 2. Add approval context storage
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Replace `self.pending_approvals` with:

```python
# Context for resuming after interrupt-based approval
self._pending_approval_context: dict[str, Any] | None = None
```

This stores the context (thread_id, run_id, message_id, user_id, interaction_mode) needed to resume after an approval response arrives.

#### 3. Generalize post-stream interrupt handling
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In `_stream_response`, after the `astream_events` loop (around line 809), the existing interrupt detection code checks `final_state.next` and sends clarification text. Modify this to:

1. Extract the interrupt value
2. Check `interrupt_value["type"]`
3. If `"clarification_request"`: existing behavior (send clarification text)
4. If `"tool_approval_request"`: send `agora:tool_approval_request` custom event and store context for resumption

```python
# After astream_events loop completes:
if final_state and final_state.next:
    # Extract interrupt payload
    interrupt_value = None
    if final_state.tasks:
        for task in final_state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupt_value = task.interrupts[0].value
                break

    interrupt_type = interrupt_value.get("type") if isinstance(interrupt_value, dict) else None

    # Close any active tool calls that were interrupted
    if active_tool_calls and protocol_handler.is_connected:
        for tool_run_id, tool_name in list(active_tool_calls.items()):
            await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
            result_content = ""
            if interrupt_type == "clarification_request" and isinstance(interrupt_value, dict):
                result_content = interrupt_value.get("display_text", "")
            elif interrupt_type == "tool_approval_request":
                result_content = "Wachten op goedkeuring..."
            await protocol_handler.send_tool_call_result(
                message_id=f"tool-result-{tool_run_id}",
                tool_call_id=tool_run_id,
                content=result_content or "Wachten op invoer...",
            )
        active_tool_calls.clear()

    if interrupt_type == "tool_approval_request":
        # Store context for resumption when approval response arrives
        approval_id = str(uuid.uuid4())
        self._pending_approval_context = {
            "approval_id": approval_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "message_id": message_id,
            "user_id": user_id,
            "interaction_mode": interaction_mode,
        }

        # Send approval request to frontend (same contract as before)
        tool_name = interrupt_value.get("tool_name", "unknown")
        await protocol_handler.send_tool_approval_request(
            tool_name=tool_name,
            tool_description=f"Tool call: {tool_name}",
            parameters=interrupt_value.get("parameters", {}),
            reasoning=interrupt_value.get("reason", "Operation requires human approval"),
            risk_level=interrupt_value.get("risk_level", "high"),
            approval_id=approval_id,
            tool_display_name=get_tool_display_name(tool_name),
        )
        await self.audit.log_approval_request(
            thread_id, tool_name, interrupt_value.get("risk_level", "high"), approval_id
        )

    elif interrupt_type == "clarification_request":
        # Existing clarification handling (send questions as text message)
        # ... (keep existing code from lines 874-913)
```

#### 4. Generalize resume detection in `process_message`
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Change the hardcoded `reporting-agent` references:

```python
# Line 380 - determine agent from state, not hardcoded
if is_interrupted:
    initial_agent = existing_state.values.get("current_agent", "general-agent")
else:
    initial_agent = "general-agent"
```

#### 5. Generalize resume handling in `_stream_response`
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Replace the hardcoded `request_clarification` / `reporting-agent` resume logic:

```python
# Lines 542-545 - determine agent from graph input or state
is_resuming_from_interrupt = isinstance(graph_input, Command)
resumed_tool_handled = False
if is_resuming_from_interrupt:
    # Determine agent from persisted state (set by process_message or resume_with_approval)
    current_agent_id = self._resuming_agent_id or "general-agent"
else:
    current_agent_id = graph_input.get("current_agent", "general-agent")
```

And for the `on_tool_start` skip logic (lines 655-662):

```python
# When resuming from interrupt, skip TOOL_CALL_START for the first tool
# (events were already sent during interrupt handling in the previous stream)
if is_resuming_from_interrupt and not resumed_tool_handled:
    log.info(f"Skipping TOOL_CALL_START for resumed tool: {tool_name} ({tool_run_id})")
    resumed_tool_handled = True
    active_tool_calls[tool_run_id] = f"_resumed_{tool_name}"
    continue
```

(Remove the `tool_name == "request_clarification"` check — skip any first tool on resume.)

#### 6. Add `resume_with_approval` method
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

New async method that resumes the graph after an approval response:

```python
async def resume_with_approval(
    self,
    response: ToolApprovalResponsePayload,
    protocol_handler: Any,
) -> AGUIMessage | None:
    """Resume an interrupted graph with an approval decision.

    Called when a ToolApprovalResponsePayload arrives. Resumes the graph
    with Command(resume={"approved": ..., "feedback": ...}).
    """
    ctx = self._pending_approval_context
    if not ctx or ctx["approval_id"] != response.approval_id:
        log.warning(f"No matching pending approval for ID: {response.approval_id}")
        return None

    self._pending_approval_context = None

    thread_id = ctx["thread_id"]
    run_id = ctx["run_id"]
    message_id = ctx["message_id"]
    user_id = ctx["user_id"]
    interaction_mode = ctx["interaction_mode"]
    config = {"configurable": {"thread_id": thread_id}}

    await self.audit.log_approval_response(thread_id, response.approval_id, response.approved)

    if not response.approved:
        log.info(f"Tool rejected by user (approval_id: {response.approval_id})")

    # Store the agent we're resuming into for _stream_response
    try:
        existing_state = await self.graph.aget_state(config)
        self._resuming_agent_id = (
            existing_state.values.get("current_agent", "general-agent")
            if existing_state and existing_state.values
            else "general-agent"
        )
    except Exception:
        self._resuming_agent_id = "general-agent"

    graph_input = Command(resume={
        "approved": response.approved,
        "feedback": response.feedback,
    })

    if protocol_handler:
        await protocol_handler.send_run_started(thread_id, run_id)
        await protocol_handler.send_step_started("routing")
        await protocol_handler.send_state_snapshot({
            "thread_id": thread_id,
            "run_id": run_id,
            "current_agent": self._resuming_agent_id,
            "status": "processing",
        })

        response_content, active_agent_id = await self._stream_response(
            graph_input, config, thread_id, run_id, message_id,
            user_id, protocol_handler, interaction_mode,
        )

        if protocol_handler.is_connected:
            await protocol_handler.send_state_snapshot({
                "thread_id": thread_id,
                "run_id": run_id,
                "current_agent": active_agent_id,
                "status": "completed",
            })
            await protocol_handler.send_run_finished(thread_id, run_id)

        self._resuming_agent_id = None
        return self._create_response_message(response_content, message_id)

    return None
```

### Success Criteria

#### Automated Verification:
- [ ] Server starts without errors: `cd server-langgraph && python -m agora_langgraph.api.server`
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`

#### Manual Verification:
- [ ] `generate_final_report` triggers approval dialog in the frontend (same UI as before)
- [ ] Approving causes the tool to execute and agent to respond
- [ ] Rejecting causes the agent to respond with a natural "OK, cancelled" message
- [ ] `request_clarification` still works correctly (clarification questions appear, response resumes flow)
- [ ] Normal (non-approval) tools execute without delay

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that both approval and clarification flows work correctly before proceeding.

---

## Phase 3: Server WebSocket Handler Update

### Overview
Update `server.py` to call `resume_with_approval` instead of the removed `handle_approval_response`.

### Changes Required

#### 1. Update approval response handling
**File**: `server-langgraph/src/agora_langgraph/api/server.py`

Change the `ToolApprovalResponsePayload` handler (lines 596-597):

```python
elif isinstance(message, ToolApprovalResponsePayload):
    # Cancel any active task (the previous stream completed when
    # the graph interrupted for approval)
    if active_task and not active_task.done():
        active_task.cancel()
        try:
            await active_task
        except asyncio.CancelledError:
            pass

    async def approval_wrapper(approval_msg: ToolApprovalResponsePayload) -> None:
        try:
            await orchestrator.resume_with_approval(approval_msg, handler)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("Error resuming after approval: %s", e, exc_info=True)
            if handler.is_connected:
                await handler.send_error("processing_error", str(e))

    active_task = asyncio.create_task(approval_wrapper(message))
```

#### 2. Update `process_message` resume to also set `_resuming_agent_id`
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In `process_message`, when `is_interrupted` and building `Command(resume=user_content)` (around line 350-354), also set `_resuming_agent_id`:

```python
if is_interrupted:
    graph_input = Command(resume=user_content)
    self._resuming_agent_id = existing_state.values.get(
        "current_agent", "general-agent"
    ) if existing_state and existing_state.values else "general-agent"
```

And clear it after `_stream_response` returns (add after line 400):

```python
self._resuming_agent_id = None
```

### Success Criteria

#### Automated Verification:
- [ ] Server starts without errors
- [ ] Type checking passes
- [ ] Linting passes

#### Manual Verification:
- [ ] Complete end-to-end flow: ask reporting agent to generate report → approval dialog appears → approve → report generates → agent responds
- [ ] Complete rejection flow: ask for report → approval dialog → reject → agent acknowledges cancellation
- [ ] Clarification flow still works: reporting agent asks questions → user answers → report continues
- [ ] No double tool execution
- [ ] No duplicate approval dialogs

**Implementation Note**: After completing this phase, the fix is complete. Run the full end-to-end test.

---

## Testing Strategy

### Manual Testing Steps
1. **Approval → Approve**: Ask AGORA to generate a final inspection report. Verify:
   - Tool does NOT execute before approval
   - Approval dialog appears with correct tool name/parameters
   - After approving, tool executes exactly once
   - Agent responds with the report result
2. **Approval → Reject**: Same as above but click reject. Verify:
   - Agent receives "Actie geannuleerd door gebruiker." and responds naturally
   - No MCP call was made
3. **Clarification flow**: Trigger `request_clarification` (e.g., start a report with missing data). Verify:
   - Questions appear as text
   - User answer resumes the flow correctly
   - Report generates successfully
4. **Non-approval tools**: Use regulation or history agents. Verify:
   - Tools execute immediately without approval prompts
   - No performance regression
5. **Rapid interactions**: Send multiple messages while approval is pending. Verify no crashes or state corruption.

## References

- Existing `request_clarification` implementation: `server-langgraph/src/agora_langgraph/core/tools.py:78-107`
- Approval logic: `server-langgraph/src/agora_langgraph/core/approval_logic.py`
- Orchestrator: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
- Graph definition: `server-langgraph/src/agora_langgraph/core/graph.py`
- Server WebSocket handler: `server-langgraph/src/agora_langgraph/api/server.py:560-629`
- Frontend approval contract: `HAI/src/types/schemas.ts:159-173` (unchanged)
