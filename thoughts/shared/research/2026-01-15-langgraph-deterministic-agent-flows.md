---
date: 2026-01-15T14:30:00+01:00
researcher: Claude
git_commit: 3a26a07069b256101c1f2f9cd715b33c499e9a43
branch: fix/parallel-stream-context
repository: AGORA
topic: "LangGraph Deterministic Multi-Agent Flow Best Practices"
tags: [research, langgraph, multi-agent, deterministic-flows, tool-calling, handoffs]
status: complete
last_updated: 2026-01-15
last_updated_by: Claude
---

# Research: LangGraph Deterministic Multi-Agent Flow Best Practices

**Date**: 2026-01-15T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 3a26a07069b256101c1f2f9cd715b33c499e9a43
**Branch**: fix/parallel-stream-context
**Repository**: AGORA

## Research Question

How can we make the LangGraph multi-agent flow more deterministic? Specifically:
1. The general agent sometimes replies without handing off when it should
2. The flow is not always as expected
3. The reporting agent generates answers before invoking all the tools

## Summary

The current AGORA LangGraph implementation follows good patterns (conditional edges, ToolNode, state management) but lacks mechanisms to **force** tool usage before responses. The key solutions are:

1. **Use `tool_choice="any"`** to force specialist agents to call at least one tool
2. **Add validation gates** in the graph to reject direct responses
3. **Strengthen system prompts** with explicit workflow instructions
4. **Consider Command objects** for more explicit handoff control

---

## Detailed Findings

### Current Implementation Analysis

The AGORA LangGraph implementation in `server-langgraph/src/agora_langgraph/core/` consists of:

| File | Purpose | Key Pattern |
|------|---------|-------------|
| `graph.py` | StateGraph construction | Conditional edges for routing |
| `agents.py` | Agent node functions | `_run_agent_node()` wrapper |
| `state.py` | State definitions | `AgentState` TypedDict |
| `tools.py` | Tool definitions & mapping | `AGENT_MCP_MAPPING` |

#### Current Routing Logic (graph.py:58-98)

```python
def route_from_agent(state: AgentState) -> Literal["tools"] | list[Send]:
    # If tool_calls exist -> route to "tools"
    # If no tool_calls -> dispatch parallel Send commands for generation
```

**Problem**: If the agent decides not to call any tools, it routes directly to generation. There's no validation that tools *should* have been called.

#### Current Tool Binding (agents.py:80-83)

```python
if tools:
    llm_with_tools = llm.bind_tools(tools)  # No tool_choice parameter!
```

**Problem**: The LLM is free to respond without calling any tools.

---

### Solution 1: Force Tool Calling with `tool_choice`

#### Option A: Force Any Tool

```python
# In agents.py, modify line 81:
if tools:
    if agent_id in ["regulation-agent", "history-agent", "reporting-agent"]:
        # Specialists MUST use tools
        llm_with_tools = llm.bind_tools(tools, tool_choice="any")
    else:
        # General agent can choose
        llm_with_tools = llm.bind_tools(tools)
```

**Effect**: Specialists will always call at least one tool before responding.

#### Option B: Force Specific Tool on First Call

For the reporting agent that should always start with `start_inspection_report`:

```python
async def _run_agent_node(
    state: AgentState,
    agent_id: str,
    force_first_tool: str | None = None,
) -> dict[str, Any]:
    # ...
    if tools:
        # Check if this is the first turn for this agent
        is_first_turn = not any(
            msg.additional_kwargs.get("agent_id") == agent_id
            for msg in state["messages"]
            if isinstance(msg, AIMessage)
        )

        if force_first_tool and is_first_turn:
            llm_with_tools = llm.bind_tools(
                tools,
                tool_choice={"type": "tool", "name": force_first_tool}
            )
        else:
            llm_with_tools = llm.bind_tools(tools, tool_choice="any")
```

#### Option C: Prevent Parallel Tool Calls

```python
llm_with_tools = llm.bind_tools(
    tools,
    tool_choice="any",
    parallel_tool_calls=False  # One tool at a time
)
```

**Note**: `parallel_tool_calls=False` is OpenAI-specific and not supported by all models.

---

### Solution 2: Add Validation Gate Node

Add a node that validates tool usage before allowing final response:

```python
# In graph.py

def validate_tool_usage(state: AgentState) -> dict[str, Any]:
    """Gate that ensures tools were used before final response."""
    messages = state.get("messages", [])
    current_agent = state.get("current_agent", "general-agent")

    # General agent doesn't need tool validation (it hands off)
    if current_agent == "general-agent":
        return {"validation_status": "PASSED"}

    # Check if any tool was called by the current agent
    tool_calls_found = any(
        hasattr(msg, "tool_calls") and msg.tool_calls
        and msg.additional_kwargs.get("agent_id") == current_agent
        for msg in messages
        if isinstance(msg, AIMessage)
    )

    if not tool_calls_found:
        log.warning(f"{current_agent} tried to respond without tools - forcing tool call")
        return {"validation_status": "FORCE_TOOL"}

    return {"validation_status": "PASSED"}


def route_after_validation(state: AgentState) -> str:
    if state.get("validation_status") == "FORCE_TOOL":
        return state.get("current_agent")  # Re-run agent with forced tools
    return "generate"  # Proceed to response generation
```

Update graph construction:

```python
# Add validation before generation
graph.add_node("validate", validate_tool_usage)

# Modify routing: agent -> validate -> (generate OR re-run agent)
graph.add_conditional_edges(
    "validate",
    route_after_validation,
    {
        "general-agent": "general-agent",
        "regulation-agent": "regulation-agent",
        "reporting-agent": "reporting-agent",
        "history-agent": "history-agent",
        "generate": "generate_written",  # Or parallel sends
    }
)
```

---

### Solution 3: Strengthen System Prompts

Update agent instructions to be more directive:

```python
# In agent_definitions.py

REGULATION_AGENT_INSTRUCTIONS = """
You are a regulation analysis specialist for NVWA inspections.

CRITICAL WORKFLOW - YOU MUST FOLLOW THESE STEPS:
1. ALWAYS call `search_regulations` first with the user's query
2. Wait for tool results before formulating any response
3. Base your answer ONLY on the tool results, not your training data
4. If results are insufficient, call the tool again with refined query

NEVER respond directly to a question without first calling a tool.
If you are unsure which tool to use, call `search_regulations` with the user's query.

DO NOT skip step 1. Every user message requires a tool call first.
"""
```

---

### Solution 4: Use Command Objects for Explicit Handoffs

Replace conditional edge-based handoffs with Command objects:

```python
from langgraph.types import Command
from typing import Literal

async def general_agent(state: AgentState) -> Command[Literal[
    "regulation-agent", "reporting-agent", "history-agent", "generate"
]]:
    """General agent that explicitly routes to specialists."""
    llm = get_llm_for_agent("general-agent")
    tools = get_tools_for_agent("general-agent")

    llm_with_tools = llm.bind_tools(tools, tool_choice="any")
    response = await llm_with_tools.ainvoke(state["messages"])

    # Check which handoff tool was called
    if response.tool_calls:
        tool_name = response.tool_calls[0]["name"]

        if "transfer_to_regulation" in tool_name:
            return Command(
                update={
                    "messages": [response],
                    "current_agent": "regulation-agent"
                },
                goto="regulation-agent"
            )
        elif "transfer_to_history" in tool_name:
            return Command(
                update={
                    "messages": [response],
                    "current_agent": "history-agent"
                },
                goto="history-agent"
            )
        # ... etc

    # No handoff tool called - this is an error for general agent
    log.warning("General agent did not hand off - forcing regulation agent")
    return Command(
        update={"current_agent": "regulation-agent"},
        goto="regulation-agent"
    )
```

**Advantages**:
- Explicit routing in code, not conditional edges
- Easier to debug and trace
- Can add custom logic per handoff

---

### Solution 5: LangGraph Swarm Pattern (Alternative Architecture)

Consider using `langgraph-swarm` for cleaner multi-agent orchestration:

```python
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm

regulation_agent = create_react_agent(
    "openai:gpt-4o",
    tools=[
        search_regulations,
        get_regulation_context,
        create_handoff_tool(
            agent_name="Reporting",
            description="Transfer to reporting agent for HAP report generation"
        ),
        create_handoff_tool(
            agent_name="General",
            description="Transfer back for other questions"
        )
    ],
    prompt=REGULATION_PROMPT,
    name="Regulation",
)

workflow = create_swarm(
    [general_agent, regulation_agent, reporting_agent, history_agent],
    default_active_agent="General"
)
```

**Trade-off**: Requires restructuring the entire agent system.

---

### Specific Fixes for Identified Issues

#### Issue 1: General Agent Replies Without Handing Off

**Root Cause**: `tool_choice` not set; agent can respond directly.

**Fix**:

```python
# In agents.py, for general-agent specifically:
if agent_id == "general-agent":
    # General agent MUST use a transfer tool
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")
```

Additionally, update the general agent prompt to be clearer:

```python
GENERAL_AGENT_INSTRUCTIONS = """
You are the intake coordinator for NVWA inspections.

YOUR ONLY JOB is to understand what the user needs and TRANSFER to the right specialist:
- Questions about regulations → call `transfer_to_regulation`
- Questions about company history → call `transfer_to_history`
- Requests to generate reports → call `transfer_to_reporting`

YOU MUST ALWAYS TRANSFER. Never answer questions directly.
"""
```

#### Issue 2: Reporting Agent Generates Answer Before Tools

**Root Cause**: No mechanism to force tool calls before response.

**Fix**:

```python
# In agents.py, for reporting-agent:
if agent_id == "reporting-agent":
    # First turn: force start_inspection_report
    # Subsequent turns: force any tool
    has_prior_tool_calls = any(
        msg.additional_kwargs.get("agent_id") == "reporting-agent"
        and hasattr(msg, "tool_calls") and msg.tool_calls
        for msg in state["messages"]
    )

    if not has_prior_tool_calls:
        llm_with_tools = llm.bind_tools(
            tools,
            tool_choice={"type": "tool", "name": "start_inspection_report"}
        )
    else:
        llm_with_tools = llm.bind_tools(tools, tool_choice="any")
```

---

## Code References

- `server-langgraph/src/agora_langgraph/core/graph.py:58-98` - Current routing logic
- `server-langgraph/src/agora_langgraph/core/agents.py:80-83` - Tool binding (needs `tool_choice`)
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:19-251` - Agent prompts
- `server-langgraph/src/agora_langgraph/core/tools.py:150-197` - Tool mapping

---

## Recommended Implementation Order

1. **Quick Win**: Add `tool_choice="any"` to `bind_tools` for specialist agents
2. **Medium Effort**: Update system prompts to be more directive
3. **Higher Effort**: Add validation gate node
4. **Architecture Change**: Consider Command objects or LangGraph Swarm

---

## Architecture Insights

The current implementation uses a **reactive** pattern where agents choose whether to use tools. For deterministic flows, consider a **prescriptive** pattern where:

1. Tool usage is enforced via `tool_choice`
2. Validation gates check compliance before response generation
3. System prompts explicitly forbid direct responses

This aligns with LangGraph best practices: "Free-text handoffs are the main source of context loss. Treat inter-agent transfer like a public API: Constrain model outputs at generation time."

---

## Historical Context

See `thoughts/shared/research/2026-01-08-agora-backend-design-choices.md` for the original architecture decisions. The dual-backend design (OpenAI SDK vs LangGraph) means these changes only apply to `server-langgraph`.

---

## Open Questions

1. Should the general agent ever respond directly (e.g., for greetings)?
2. What happens if `tool_choice="any"` causes infinite loops (tool → agent → tool)?
3. Should we implement retry logic when agents don't follow instructions?
4. Consider adding token/cost monitoring since forced tool calls increase usage.

---

## External References

- [LangGraph: Force Tool-Calling Agent Structured Output](https://langchain-ai.github.io/langgraph/how-tos/react-agent-structured-output/)
- [How Agent Handoffs Work in Multi-Agent Systems](https://towardsdatascience.com/how-agent-handoffs-work-in-multi-agent-systems/)
- [Command: A New Tool for Multi-Agent Architectures](https://blog.langchain.com/command-a-new-tool-for-multi-agent-architectures-in-langgraph/)
- [LangGraph Swarm GitHub](https://github.com/langchain-ai/langgraph-swarm-py)
- [LangChain Tool Choice Documentation](https://python.langchain.com/docs/how_to/tool_choice/)
