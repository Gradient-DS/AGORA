# LangGraph Interrupt Pattern for Sticky Reporting Agent

## Overview

Implement LangGraph's native `interrupt()` pattern to make the reporting-agent deterministically "sticky" during multi-turn workflows (e.g., clarifying questions). This ensures that when the reporting-agent asks for user input, the user's response resumes execution at the exact point of interruption—no routing decisions needed.

## Current State Analysis

### Problem
After the reporting-agent asks clarifying questions, the graph run ends. When the user responds:
1. A new graph invocation starts
2. Routing logic (`route_from_start`) determines which agent handles it
3. This is non-deterministic—the general-agent might intercept and misinterpret the response
4. Can cause recursion issues (e.g., repeatedly calling `update_user_settings`)

### Current Flow
```
User: "Create a report for Restaurant Bella Rosa"
  → general-agent transfers to reporting-agent
  → reporting-agent calls verify_inspection_data
  → MCP returns questions: ["What is the address?", "Was hygiene OK?"]
  → Agent presents questions as text response
  → Graph run ENDS

User: "hoofdstraat 2, ja, nee"
  → NEW graph invocation
  → route_from_start() checks current_agent
  → Routes to reporting-agent (hopefully)
  → Agent must figure out context from history
```

### Key Files
- `server-langgraph/src/agora_langgraph/core/tools.py` - Tool definitions
- `server-langgraph/src/agora_langgraph/core/agents.py` - Agent node implementations
- `server-langgraph/src/agora_langgraph/core/graph.py` - Graph structure
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py` - Message processing
- `server-langgraph/src/agora_langgraph/core/state.py` - State schema

## Desired End State

### New Flow with `interrupt()`
```
User: "Create a report for Restaurant Bella Rosa"
  → general-agent transfers to reporting-agent
  → reporting-agent calls verify_inspection_data
  → MCP returns questions
  → Agent calls request_clarification(questions) tool
  → Tool calls interrupt(questions)
  → Graph PAUSES (state checkpointed)
  → Questions sent to frontend as regular text message

User: "hoofdstraat 2, ja, nee"
  → Backend detects thread is interrupted
  → Invokes graph with Command(resume="hoofdstraat 2, ja, nee")
  → Graph RESUMES at exact interrupt point
  → reporting-agent continues with user's answer
  → No routing decision needed - deterministic!
```

### Verification
- [ ] Reporting-agent stays active across clarifying question flow
- [ ] User responses resume at exact interrupt point
- [ ] No changes to frontend/AG-UI Protocol contracts
- [ ] Other agents (regulation, history) continue to work normally

## What We're NOT Doing

- NOT adding interrupt capability to all agents (only reporting-agent)
- NOT changing the AG-UI Protocol AsyncAPI contract
- NOT changing the frontend WebSocket handling
- NOT modifying the existing approval flow (separate mechanism)
- NOT changing how MCP tools work (verify_inspection_data stays the same)

## Implementation Approach

The interrupt is handled transparently in the backend:
1. Add a `request_clarification` tool that calls `interrupt()`
2. Detect interrupts in the orchestrator after graph execution
3. On next message, check if thread is interrupted and resume accordingly
4. Frontend sees regular text messages—no contract changes

## Phase 1: Add Interrupt Tool for Reporting Agent

### Overview
Create a `request_clarification` tool that wraps LangGraph's `interrupt()`. This tool is only available to reporting-agent.

### Changes Required:

#### 1. Add interrupt tool to tools.py
**File**: `server-langgraph/src/agora_langgraph/core/tools.py`

Add import and new tool:

```python
# Add to imports at top of file
from langgraph.types import interrupt

# Add after the handoff tools section (around line 74)

@tool
def request_clarification(questions: list[dict[str, Any]]) -> str:
    """Request clarification from the user during report creation.

    Use this tool when you need additional information from the inspector
    to complete the report. The graph will pause and wait for the user's
    response before continuing.

    Args:
        questions: List of question objects from verify_inspection_data tool.
                   Each has 'question', 'field', 'importance', and optional 'options'.

    Returns:
        The user's response to the questions.
    """
    # Format questions for display
    formatted = []
    for i, q in enumerate(questions, 1):
        formatted.append(f"{i}. {q.get('question', '')}")

    question_text = "\n".join(formatted)

    # This will pause the graph and return the user's response when resumed
    user_response = interrupt({
        "type": "clarification_request",
        "questions": questions,
        "display_text": question_text,
    })

    return user_response
```

#### 2. Assign tool only to reporting-agent
**File**: `server-langgraph/src/agora_langgraph/core/tools.py`

Modify `get_tools_for_agent()` function (around line 189):

```python
def get_tools_for_agent(
    agent_id: str,
    mcp_tools_by_server: dict[str, list[BaseTool]],
) -> list[Any]:
    """Get the appropriate tools for an agent."""
    tools: list[Any] = []

    if agent_id == "general-agent":
        tools.extend(
            [transfer_to_history, transfer_to_regulation, transfer_to_reporting]
        )
        settings_tool = create_update_user_settings_tool()
        tools.append(settings_tool)
        log.info(
            f"{agent_id} gets handoff tools: transfer_to_history, "
            "transfer_to_regulation, transfer_to_reporting + update_user_settings"
        )
    elif agent_id == "reporting-agent":
        # Reporting agent gets the clarification tool for multi-turn workflows
        tools.append(request_clarification)
        log.info(f"{agent_id} gets request_clarification tool")

    # MCP tools assignment continues as before...
    mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
    # ... rest unchanged
```

### Success Criteria:

#### Automated Verification:
- [x] Python syntax check passes: `python3 -m py_compile src/agora_langgraph/core/tools.py`
- [x] Import test passes: `python3 -c "from langgraph.types import interrupt; print('OK')"`

#### Manual Verification:
- [ ] Server starts without errors

---

## Phase 2: Update Reporting Agent Instructions

### Overview
Update the reporting-agent instructions to use the new `request_clarification` tool instead of just presenting questions in text.

### Changes Required:

#### 1. Update agent_definitions.py
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`

Update the reporting-agent instructions (around line 147-150):

```python
# Change this section in AGENT_DEFINITIONS["reporting-agent"]["instructions"]:

# FROM:
"3. VERIFY (if completion_percentage < 80% OR overall_confidence < 0.7):\n"
"   - Call verify_inspection_data to get verification questions\n"
"   - Ask inspector IN DUTCH for missing information\n"
"   - Call submit_verification_answers with responses\n"

# TO:
"3. VERIFY (if completion_percentage < 80% OR overall_confidence < 0.7):\n"
"   - Call verify_inspection_data to get verification questions\n"
"   - Call request_clarification with the questions list to pause and wait for user input\n"
"   - The user's response will be returned by request_clarification\n"
"   - Call submit_verification_answers with the user's responses\n"
```

### Success Criteria:

#### Automated Verification:
- [x] Python syntax check passes: `python3 -m py_compile src/agora_langgraph/core/agent_definitions.py`

#### Manual Verification:
- [ ] Agent instructions are clear about using request_clarification tool

---

## Phase 3: Handle Interrupts in Orchestrator

### Overview
Modify the orchestrator to detect when a graph run was interrupted and handle resumption on the next user message.

### Changes Required:

#### 1. Add interrupt detection after graph execution
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Add import at top:

```python
from langgraph.types import Command
```

#### 2. Modify _stream_response to detect interrupts
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

After the `astream_events` loop completes, check for interrupt state. Add around line 567 (after the streaming loop):

```python
        # After streaming completes, check if graph was interrupted
        # Get the final state to check for interrupts
        try:
            final_state = await self.graph.aget_state(config)
            if final_state and final_state.next:
                # Graph was interrupted - there are pending tasks
                log.info(
                    f"Graph interrupted at node(s): {final_state.next}, "
                    f"thread: {thread_id}"
                )
                # The interrupt value should be in the tasks
                if final_state.tasks:
                    for task in final_state.tasks:
                        if hasattr(task, 'interrupts') and task.interrupts:
                            interrupt_value = task.interrupts[0].value
                            log.info(f"Interrupt payload: {interrupt_value}")
                            # The questions were already streamed as part of agent response
                            # No additional action needed - state is checkpointed
        except Exception as e:
            log.warning(f"Failed to check interrupt state: {e}")
```

#### 3. Modify process_message to handle resume
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

In `process_message()`, after reading persisted state (around line 225), check if we need to resume:

```python
            # Read persisted current_agent from checkpoint state
            current_agent = "general-agent"
            is_interrupted = False

            try:
                existing_state = await self.graph.aget_state(config)
                if existing_state and existing_state.values:
                    persisted_agent = existing_state.values.get("current_agent")
                    if persisted_agent:
                        current_agent = persisted_agent
                        log.info(
                            f"Resuming with persisted agent: {current_agent} "
                            f"(thread: {thread_id})"
                        )

                    # Check if graph is in interrupted state
                    if existing_state.next:
                        is_interrupted = True
                        log.info(
                            f"Thread {thread_id} is interrupted at {existing_state.next}, "
                            "will resume with user message"
                        )
            except Exception as e:
                log.warning(f"Failed to read persisted state: {e}, using general-agent")

            # Determine input for graph invocation
            if is_interrupted:
                # Resume interrupted graph with user's response
                graph_input = Command(resume=user_content)
                log.info(f"Resuming interrupted graph with: {user_content[:100]}...")
            else:
                # Normal invocation with new message
                graph_input = {
                    "messages": [HumanMessage(content=user_content)],
                    "session_id": thread_id,
                    "current_agent": current_agent,
                    "pending_approval": None,
                    "metadata": metadata,
                }
```

#### 4. Update graph invocation to use graph_input
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Change the streaming call to use `graph_input` instead of `input_state`:

```python
            if protocol_handler:
                response_content, active_agent_id = await self._stream_response(
                    graph_input,  # Changed from input_state
                    config,
                    thread_id,
                    run_id,
                    message_id,
                    user_id,
                    protocol_handler,
                )
            else:
                response_content, active_agent_id = await self._run_blocking(
                    graph_input,  # Changed from input_state
                    config
                )
```

#### 5. Update _stream_response signature to accept Command
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

Update the method signature and handle both input types:

```python
    async def _stream_response(
        self,
        graph_input: dict[str, Any] | Command,  # Updated type
        config: dict[str, Any],
        thread_id: str,
        run_id: str,
        message_id: str,
        user_id: str,
        protocol_handler: Any,
    ) -> tuple[str, str]:
        """Stream graph response using astream_events with AG-UI Protocol."""
        full_response: list[str] = []

        # Handle both normal input and Command resume
        if isinstance(graph_input, Command):
            current_agent_id = "reporting-agent"  # Resuming interrupted reporting flow
        else:
            current_agent_id = graph_input.get("current_agent", "general-agent")

        # ... rest of method continues unchanged
```

#### 6. Update _run_blocking similarly
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`

```python
    async def _run_blocking(
        self,
        graph_input: dict[str, Any] | Command,  # Updated type
        config: dict[str, Any],
    ) -> tuple[str, str]:
        """Run graph in blocking mode without streaming."""
        result = await self.graph.ainvoke(graph_input, config=config)
        # ... rest unchanged
```

### Success Criteria:

#### Automated Verification:
- [x] Python syntax check passes: `python3 -m py_compile src/agora_langgraph/pipelines/orchestrator.py`
- [x] Type hints are valid (no mypy errors on edited lines)

#### Manual Verification:
- [ ] Server starts without errors
- [ ] Logs show "Graph interrupted" when clarification is requested
- [ ] Logs show "Resuming interrupted graph" when user responds

---

## Phase 4: Integration Testing

### Overview
Test the complete flow end-to-end to verify the interrupt pattern works correctly.

### Test Scenarios:

#### Scenario 1: Basic Clarification Flow
1. Start new session
2. Send: "Maak een inspectierapport voor Restaurant Bella Rosa, KVK 92251854"
3. Verify: reporting-agent asks clarifying questions
4. Send: "hoofdstraat 2, ja, nee"
5. Verify: reporting-agent continues and generates report
6. Verify: No recursion errors, no routing to general-agent

#### Scenario 2: Multiple Clarification Rounds
1. Start new session
2. Initiate report with minimal info
3. Answer first round of questions
4. If more questions asked, answer those too
5. Verify: Each round resumes correctly without re-routing

#### Scenario 3: Interruption During Other Agent
1. Start session, ask regulation question
2. Verify: regulation-agent answers
3. Ask follow-up question
4. Verify: Still handled appropriately (no interrupt needed)

### Success Criteria:

#### Manual Verification:
- [ ] Scenario 1 completes without errors
- [ ] Scenario 2 handles multiple rounds
- [ ] Scenario 3 doesn't interfere with non-reporting flows
- [ ] Frontend displays questions and accepts responses normally
- [ ] No changes to frontend code required

---

## Testing Strategy

### Unit Tests:
- Test `request_clarification` tool with mock interrupt
- Test orchestrator interrupt detection logic
- Test Command resume path

### Integration Tests:
- Full flow test with mock MCP server
- Verify checkpoint state contains interrupt info
- Verify resume restores correct agent context

### Manual Testing Steps:
1. Start the server-langgraph backend
2. Connect via HAI frontend
3. Initiate report creation flow
4. Verify agent asks clarifying questions
5. Respond to questions
6. Verify agent continues (check logs for "Resuming interrupted graph")
7. Verify report is generated successfully

## Performance Considerations

- `interrupt()` is lightweight - just raises an exception and checkpoints
- Resume loads checkpoint state (already happening for `current_agent`)
- No additional database queries beyond existing checkpoint reads
- No impact on non-interrupted flows

## Rollback Plan

If issues arise:
1. Remove `request_clarification` tool from reporting-agent tools list
2. Revert agent instructions to original (present questions as text)
3. The existing `route_from_start()` fix remains as fallback

## References

- LangGraph interrupt documentation: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/
- Current graph implementation: `server-langgraph/src/agora_langgraph/core/graph.py`
- Orchestrator: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
- Research: `thoughts/shared/research/2026-01-15-langgraph-deterministic-agent-flows.md`
