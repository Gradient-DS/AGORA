---
date: 2026-01-12T16:30:00+01:00
researcher: Claude Code
git_commit: ea075144afe772c5dd02f2860aad0643e4ceb5ae
branch: feat/parallel-spoken
repository: AGORA
topic: "Why MCP tools are called AFTER text responses in server-openai"
tags: [research, codebase, server-openai, server-langgraph, mcp, tool-execution-order, streaming]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude Code
---

# Research: Why MCP tools are called AFTER text responses in server-openai

**Date**: 2026-01-12T16:30:00+01:00
**Researcher**: Claude Code
**Git Commit**: ea075144afe772c5dd02f2860aad0643e4ceb5ae
**Branch**: feat/parallel-spoken
**Repository**: AGORA

## Research Question

In server-openai, MCP tools are being called AFTER the agent already provides an answer (using training knowledge), while in server-langgraph they're called BEFORE answering. Example:

- **server-openai**: regulation-agent provides answer about fish temperature regulations citing EU 178/2002, EU 852/2004 → THEN calls `search_regulations` tool
- **server-langgraph**: regulation-agent calls `search_regulations` tool → THEN provides answer based on actual MCP results

What causes this difference and how to fix it?

## Summary

**Root Cause**: Fundamental architectural difference in tool execution enforcement.

| Backend | Architecture | Tool Execution Order |
|---------|-------------|---------------------|
| **server-langgraph** | Explicit state machine graph | **Guaranteed** - `route_from_agent()` forces routing to ToolNode before END |
| **server-openai** | SDK event stream processing | **Not enforced** - events processed in order received from SDK/model |

**Key Finding**: The parallel spoken/written generation (commit 0d40c4d) is **NOT the cause**. The git diff shows no changes to tool execution logic - only formatting changes and isolated parallel streaming code.

**The real problem**: The OpenAI Agents SDK processes events as they arrive from the model. If the model decides to generate text first and call tools second (or in parallel), the SDK streams them in that order. There is no mechanism to enforce "tools before text" in the current server-openai implementation.

## Detailed Findings

### 1. LangGraph: Enforced Tool-First Architecture

**Critical code** (`server-langgraph/src/agora_langgraph/core/graph.py:54-92`):

```python
def route_from_agent(state: AgentState) -> Literal["tools", "end"]:
    """Route from any agent based on the last message.

    ALL tool calls (including handoffs) go to ToolNode first.
    """
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None)

    if not tool_calls:
        return "end"  # Only end when NO tool calls

    return "tools"  # Must execute tools before continuing
```

**Graph edges enforce the flow** (`graph.py:178-199`):
- Agent node → (if tool_calls) → ToolNode → back to agent
- Agent node → (if no tool_calls) → END

**Result**: The agent CANNOT produce a final text response while tool_calls exist. Tools MUST complete first.

### 2. OpenAI SDK: Event Stream Processing

**Event processing** (`server-openai/src/agora_openai/core/agent_runner.py:283-286`):

```python
async for event in result.stream_events():
    await self._process_stream_event(event, state, stream_callback, tool_callback)
```

**Event types** (`agent_runner.py:305-326`):
- `raw_response_event` with `ResponseTextDeltaEvent` → text chunks streamed immediately
- `run_item_stream_event` with `tool_called`/`tool_output` → tool events processed as they arrive

**Problem**: Events are processed in the order the SDK emits them. The SDK emits events in the order the OpenAI API returns them. If the model generates text before/during tool calls, both stream simultaneously.

### 3. Parallel Spoken/Written is Isolated

The git diff for commit 0d40c4d shows:

- **agent_runner.py**: Only formatting changes (Black autoformat), no logic changes
- **orchestrator.py**: New parallel streaming uses a SEPARATE OpenAI client call without tools:

```python
async def generate_spoken_parallel() -> None:
    """Generate spoken response in TRUE PARALLEL (summarize mode)."""
    stream = await client.chat.completions.create(
        model=settings.openai_model,
        messages=spoken_messages,
        stream=True,
        # NO tools parameter - spoken stream cannot call tools
    )
```

The spoken stream is completely isolated from the main agent runner and tool execution.

### 4. Existing Workaround Addresses Different Problem

The FunctionTool wrapper workaround (documented in `thoughts/shared/plans/2026-01-12-server-openai-mcp-tools-after-handoff.md`) addresses **tool AVAILABILITY after handoffs** - ensuring tools are bound to agents.

It does NOT address **tool EXECUTION ORDER** - when the model decides to call tools vs generate text.

### 5. Model/SDK Behavior Differences

The OpenAI model may:
1. Generate a complete text response first, then call tools for "verification"
2. Start text generation while simultaneously making tool call decisions
3. Stream text chunks before tool call chunks in the same response

This is different from LangGraph where `AIMessage.tool_calls` presence triggers routing BEFORE any text response.

## Code References

### server-langgraph (tool-first enforcement)
- `server-langgraph/src/agora_langgraph/core/graph.py:54-92` - `route_from_agent()` routing logic
- `server-langgraph/src/agora_langgraph/core/graph.py:178-199` - Graph edge definitions
- `server-langgraph/src/agora_langgraph/core/agents.py:77-83` - Runtime `llm.bind_tools()`

### server-openai (stream processing)
- `server-openai/src/agora_openai/core/agent_runner.py:283-286` - Event stream iteration
- `server-openai/src/agora_openai/core/agent_runner.py:305-326` - Event type processing
- `server-openai/src/agora_openai/core/agent_runner.py:335-342` - Tool call/output handling
- `server-openai/src/agora_openai/pipelines/orchestrator.py:347-352` - Parallel spoken task start

### Configuration
- `server-openai/src/agora_openai/core/agent_runner.py:29-34` - AGENT_MCP_MAPPING
- `server-openai/src/agora_openai/core/agent_definitions.py:88-102` - regulation-agent instructions

## Architecture Insights

### Why LangGraph Works

LangGraph's state machine architecture guarantees tool execution order:

1. Agent produces `AIMessage` with optional `tool_calls`
2. `route_from_agent()` checks: "Are there tool_calls?"
3. If YES → route to ToolNode (tools execute)
4. If NO → route to END (response complete)
5. After ToolNode → route back to agent with tool results
6. Agent produces new `AIMessage` (repeat until no tool_calls)

The agent cannot "skip" tool execution because the graph edges don't allow it.

### Why OpenAI SDK Doesn't Enforce Order

The OpenAI Agents SDK uses an event-driven streaming model:

1. SDK sends request to OpenAI API with tools
2. OpenAI returns streaming response with interleaved text chunks and tool_calls
3. SDK emits events as they arrive: text, tool_called, tool_output, etc.
4. Application processes events in arrival order
5. Text can stream before, during, or after tool execution

The SDK handles tool execution internally but doesn't buffer text until tools complete.

## Potential Solutions

### Option 1: Add Explicit Tool Requirement Instructions (Quick Fix)

Modify agent instructions to mandate tool usage BEFORE responding:

```python
# In agent_definitions.py for regulation-agent
"CRITICAL WORKFLOW:\n"
"1. ALWAYS search regulations using your tools FIRST\n"
"2. WAIT for tool results before formulating your answer\n"
"3. NEVER answer regulation questions using training knowledge alone\n"
"4. Base ALL answers on actual tool results\n"
```

**Pros**: Simple, no code changes
**Cons**: Model may still ignore instructions, not guaranteed

### Option 2: Use `tool_choice` Parameter

Force the model to call a tool before generating text:

```python
# In agent construction or at runtime
response = Runner.run_streamed(
    agent,
    input=message,
    tool_choice="required",  # Force tool call
)
```

**Pros**: Enforced at API level
**Cons**: May force unnecessary tool calls for simple questions

### Option 3: Implement Response Buffering

Buffer text responses until tool calls complete:

```python
async def _process_stream_event(self, event, state, ...):
    if event_type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
        if state.pending_tool_calls:
            state.buffered_text.append(event.data.delta)  # Buffer
        else:
            await stream_callback(event.data.delta)  # Stream

    elif event.name == "tool_output":
        await self._handle_tool_output(...)
        if not state.pending_tool_calls:
            # Flush buffered text
            for chunk in state.buffered_text:
                await stream_callback(chunk)
            state.buffered_text.clear()
```

**Pros**: Ensures tools complete before text shows
**Cons**: Adds latency, complex implementation

### Option 4: Implement LangGraph-Style Loop

Add explicit routing logic after each response:

```python
async def run_agent_with_tool_loop(self, message, session_id, ...):
    while True:
        result = await Runner.run_streamed(agent, input=message, ...)

        # Process events, collect tool calls and text
        tool_calls = []
        text_response = []
        async for event in result.stream_events():
            # Collect but don't stream text yet
            ...

        if tool_calls:
            # Execute tools, add results to history
            # Re-run agent with tool results
            continue
        else:
            # No more tool calls - now stream text response
            for chunk in text_response:
                await stream_callback(chunk)
            break
```

**Pros**: Matches LangGraph behavior exactly
**Cons**: Significant refactor, may conflict with SDK's internal loop

### Option 5: Agent Chaining with Explicit Tool Phase

Split response into two phases:

```python
# Phase 1: Tool-only agent (no text response)
tool_agent = Agent(
    name="regulation-tool-agent",
    instructions="You ONLY call tools. Do NOT generate text responses.",
    tools=regulation_tools,
)

# Phase 2: Response agent (uses tool results)
response_agent = Agent(
    name="regulation-response-agent",
    instructions="Summarize the tool results for the user.",
    tools=[],
)
```

**Pros**: Clean separation, guaranteed order
**Cons**: More complex agent setup, two API calls

## Recommended Approach

**Short-term (Option 1 + 2)**:
- Update regulation-agent instructions with explicit tool-first mandate
- Add `tool_choice="auto"` with strong instruction reinforcement

**Medium-term (Option 3)**:
- Implement response buffering to delay text until tool completion
- This provides user experience parity with LangGraph

**Long-term consideration**:
- Evaluate whether to standardize on LangGraph for both backends given its superior control over execution flow

## Related Research

- `thoughts/shared/research/2026-01-12-regulation-mcp-not-called-server-openai.md` - Tool availability after handoffs
- `thoughts/shared/plans/2026-01-12-server-openai-mcp-tools-after-handoff.md` - FunctionTool wrapper implementation

## Open Questions

1. Does OpenAI's `tool_choice` parameter work with the Agents SDK streaming?
2. Can we detect tool_calls presence BEFORE text streaming starts in the SDK event stream?
3. Is there SDK configuration to control text/tool interleaving behavior?
4. Should we migrate server-openai to use LangGraph's explicit graph pattern?
