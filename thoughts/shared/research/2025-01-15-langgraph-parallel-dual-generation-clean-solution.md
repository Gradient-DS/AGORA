---
date: 2025-01-15T12:00:00+01:00
researcher: Claude
git_commit: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
branch: main
repository: Gradient-DS/AGORA
topic: "LangGraph Parallel Dual Generation Without Wasted LLM Call"
tags: [research, langgraph, parallel-generation, spoken-text, fan-out, send-api]
status: complete
last_updated: 2025-01-15
last_updated_by: Claude
---

# Research: LangGraph Parallel Dual Generation Without Wasted LLM Call

**Date**: 2025-01-15T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
**Branch**: main
**Repository**: Gradient-DS/AGORA

## Research Question

How to achieve true parallel spoken and written text generation in LangGraph without the "wasted LLM call" proposed in `thoughts/shared/plans/2025-01-15-parallel-dual-text-generation.md`?

## Summary

LangGraph provides native support for **parallel branching (fan-out)** that allows running multiple nodes simultaneously with shared context. The clean solution is to **modify the ReAct graph architecture** to route to a fork node instead of generating a final response, then use the **Send API** to spawn two parallel generation streams with different system prompts but identical message context.

This approach:
- **No wasted LLM call** - The graph stops before final generation; we generate ourselves
- **True parallel execution** - Both streams start at exactly the same time
- **Shared context** - Both have full access to tool results

## Detailed Findings

### Current Problem Analysis

**Location**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:352-392`

The current bug occurs because:
1. `generate_spoken_parallel()` captures `input_state` which only contains the original user message
2. Tool results exist in the graph checkpoint but aren't passed to spoken generation
3. The graph runs to completion (including final LLM response generation), then spoken runs separately

**Current Flow**:
```
User Message → Agent → Tool Calls → Tools → Agent (generates response) → END
                                                    ↓
                                            Spoken generation starts
                                            (with only original message!)
```

### The Clean Solution: Modified Graph with Send API

LangGraph supports three patterns for parallel execution:

#### 1. Static Fan-Out (Multiple Edges)
```python
# Multiple edges from same source = parallel execution
builder.add_edge("tools_complete", "spoken_generator")
builder.add_edge("tools_complete", "written_generator")
builder.add_edge(["spoken_generator", "written_generator"], "merge")
```

#### 2. Conditional Fan-Out (Return List)
```python
def route_after_tools(state) -> list[str]:
    if state["messages"][-1].tool_calls:
        return ["agent"]  # Continue tool loop
    return ["spoken_generator", "written_generator"]  # Fan out
```

#### 3. Send API (Recommended - Different State Per Branch)
```python
from langgraph.types import Send

def fork_to_generators(state):
    """After ReAct loop, fork with different system prompts."""
    return [
        Send("generate", {
            "messages": state["messages"],  # Same context
            "system_prompt": spoken_prompt,
            "output_type": "spoken"
        }),
        Send("generate", {
            "messages": state["messages"],  # Same context
            "system_prompt": written_prompt,
            "output_type": "written"
        })
    ]
```

### Recommended Architecture

```
                    ┌─────────┐
                    │  agent  │◄────────────┐
                    └────┬────┘             │
                         │                  │
              ┌──────────▼──────────┐       │
              │   should_continue   │       │
              └──────────┬──────────┘       │
                    ┌────┴────┐             │
              tool_calls?     no_tools      │
                    │              │        │
              ┌─────▼─────┐  ┌─────▼─────┐  │
              │   tools   │  │   fork    │  │
              └─────┬─────┘  └─────┬─────┘  │
                    │              │        │
                    └──────────────┤ Send() │
                         ┌─────────┴─────────┐
                         │                   │
                   ┌─────▼─────┐       ┌─────▼─────┐
                   │  spoken   │       │  written  │
                   │ generator │       │ generator │
                   └─────┬─────┘       └─────┬─────┘
                         │                   │
                         └─────────┬─────────┘
                                   │
                            ┌──────▼──────┐
                            │    merge    │
                            └──────┬──────┘
                                   │
                                  END
```

**Key insight**: The `agent` node no longer generates a final response. When no tool calls remain, we route to `fork` which dispatches parallel generators.

### Implementation Approach

#### Step 1: Modify Routing Logic

**File**: `server-langgraph/src/agora_langgraph/core/graph.py`

Change `route_from_agent()` to route to a fork node instead of END:

```python
def route_from_agent(state: AgentState) -> str:
    """Route based on last message."""
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # Instead of END, go to fork for dual generation
    return "fork_generation"
```

#### Step 2: Add Fork Node with Send API

```python
from langgraph.types import Send
from agora_langgraph.core.spoken_prompts import get_spoken_prompt
from agora_langgraph.core.agent_definitions import get_agent_by_id

def fork_to_parallel_generation(state: AgentState) -> list[Send]:
    """Fork into parallel spoken and written generation."""
    agent_id = state.get("current_agent", "general-agent")

    # Get prompts
    agent_config = get_agent_by_id(agent_id)
    written_prompt = agent_config["instructions"] if agent_config else ""
    spoken_prompt = get_spoken_prompt(agent_id) or ""

    # Get messages WITHOUT system messages (we add our own)
    messages = [m for m in state["messages"] if not isinstance(m, SystemMessage)]

    return [
        Send("generate_stream", {
            "messages": messages,
            "system_prompt": written_prompt,
            "stream_type": "written",
            "agent_id": agent_id,
        }),
        Send("generate_stream", {
            "messages": messages,
            "system_prompt": spoken_prompt,
            "stream_type": "spoken",
            "agent_id": agent_id,
        })
    ]
```

#### Step 3: Add Generator Node

```python
async def generate_stream_node(state: dict) -> dict:
    """Generate a single stream (called twice in parallel)."""
    llm = get_llm_for_agent(state["agent_id"])

    messages = [
        SystemMessage(content=state["system_prompt"])
    ] + state["messages"]

    response = await llm.ainvoke(messages)

    return {
        state["stream_type"]: response.content
    }
```

#### Step 4: Update State Schema

```python
from typing import Annotated
import operator

class AgentState(TypedDict):
    messages: list[BaseMessage]
    current_agent: str
    session_id: str
    pending_approval: dict | None
    metadata: dict
    # New: Parallel output accumulators
    written: Annotated[list[str], operator.add]
    spoken: Annotated[list[str], operator.add]
```

#### Step 5: Add Merge Node

```python
def merge_parallel_outputs(state: AgentState) -> dict:
    """Combine parallel generation outputs."""
    written_content = "".join(state.get("written", []))
    spoken_content = "".join(state.get("spoken", []))

    # Add written response as AI message to conversation
    return {
        "messages": [AIMessage(content=written_content)],
        "final_written": written_content,
        "final_spoken": spoken_content,
    }
```

#### Step 6: Build the Graph

```python
def create_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # Agent nodes (existing)
    builder.add_node("general-agent", create_agent_node("general-agent"))
    # ... other agents

    # Tools node (existing)
    builder.add_node("tools", tool_node)

    # NEW: Fork and generation nodes
    builder.add_node("fork_generation", fork_to_parallel_generation)
    builder.add_node("generate_stream", generate_stream_node)
    builder.add_node("merge", merge_parallel_outputs)

    # Routing
    builder.add_conditional_edges(
        "general-agent",
        route_from_agent,
        {"tools": "tools", "fork_generation": "fork_generation"}
    )
    # ... edges for other agents

    builder.add_conditional_edges("tools", route_after_tools)

    # Parallel generation edges
    builder.add_conditional_edges("fork_generation", fork_to_parallel_generation)
    builder.add_edge("generate_stream", "merge")
    builder.add_edge("merge", END)

    return builder.compile(checkpointer=checkpointer)
```

### Streaming the Parallel Generation

The orchestrator needs to handle streaming from both parallel nodes. Options:

#### Option A: Use `stream_mode=["custom"]`

```python
from langgraph.config import get_stream_writer

async def generate_stream_node(state: dict) -> dict:
    """Stream chunks via custom writer."""
    writer = get_stream_writer()
    llm = get_llm_for_agent(state["agent_id"])

    messages = [SystemMessage(content=state["system_prompt"])] + state["messages"]

    full_content = []
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_content.append(chunk.content)
            writer({
                "type": state["stream_type"],
                "content": chunk.content
            })

    return {state["stream_type"]: ["".join(full_content)]}

# In orchestrator:
async for mode, chunk in graph.astream(input_state, stream_mode=["updates", "custom"], config=config):
    if mode == "custom":
        if chunk["type"] == "written":
            await protocol_handler.send_text_message_content(message_id, chunk["content"])
        else:
            await protocol_handler.send_spoken_text_content(message_id, chunk["content"])
```

#### Option B: Use `astream_events` with Node Filtering

```python
async for event in graph.astream_events(input_state, config=config, version="v2"):
    metadata = event.get("metadata", {})
    node_name = metadata.get("langgraph_node", "")

    if event["event"] == "on_chat_model_stream" and node_name == "generate_stream":
        chunk = event["data"].get("chunk")
        if chunk and chunk.content:
            # Determine stream type from run context
            stream_type = determine_stream_type(event)
            if stream_type == "written":
                await protocol_handler.send_text_message_content(message_id, chunk.content)
            else:
                await protocol_handler.send_spoken_text_content(message_id, chunk.content)
```

### State Management for Parallel Nodes

**Critical**: When parallel nodes write to the same state key, use a reducer:

```python
from typing import Annotated
import operator

class AgentState(TypedDict):
    # Use operator.add to concatenate results from parallel branches
    written: Annotated[list[str], operator.add]
    spoken: Annotated[list[str], operator.add]
```

Without a reducer: `"At key 'written': Can receive only one value per step."`

## Code References

- Current graph structure: `server-langgraph/src/agora_langgraph/core/graph.py:123-202`
- Current routing: `server-langgraph/src/agora_langgraph/core/graph.py:70-91`
- Broken spoken generation: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:352-392`
- Existing parallel streaming util (unused): `server-langgraph/src/agora_langgraph/core/parallel_streaming.py:45-158`
- Agent definitions: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
- Spoken prompts: `server-langgraph/src/agora_langgraph/core/spoken_prompts.py`

## Architecture Insights

### Why Send API is Preferred

1. **Different state per branch**: Each `Send()` creates an independent execution with custom state
2. **Same context, different prompts**: Both generators see identical `messages` but different `system_prompt`
3. **Dynamic dispatch**: Could conditionally skip spoken generation based on settings
4. **Future extensibility**: Easy to add third stream (e.g., "bullet points" format)

### Why Not Use Checkpoints + Time Travel

The time-travel approach (fork checkpoint, run twice with different configs) would:
- Require two separate graph invocations
- Make streaming coordination more complex
- Add overhead from checkpoint serialization

The Send API handles parallelism natively within a single graph execution.

## Comparison: Old Plan vs Clean Solution

| Aspect | Old Plan (Wasted Call) | Clean Solution (Send API) |
|--------|------------------------|---------------------------|
| LLM calls | 3 (tool-calling + written + spoken) | 2 (tool-calling loop only, then parallel) |
| Parallel start | After graph completes | Native graph parallelism |
| Context sharing | Manual accumulation | Automatic via state |
| Code complexity | Intercept events, manual parallel | Graph structure change |
| Streaming | Custom event handling | Native `stream_mode` or `astream_events` |

## Open Questions

1. **Tool events during generation**: With the new architecture, tool events stream during the ReAct loop, then text generation starts. This is the same UX as the old plan but cleaner.

2. **Dictate mode**: When `spoken_mode == "dictate"`, skip the fork and just generate written (or duplicate to spoken).

3. **Error handling**: If one parallel branch fails, the whole superstep fails atomically. May need retry logic.

4. **Message ID correlation**: Both streams need to share the same `message_id` for frontend coordination.

## Related Research

- `thoughts/shared/plans/2025-01-15-parallel-dual-text-generation.md` - Original plan with wasted LLM call
- `thoughts/shared/research/2025-01-15-spoken-written-shared-context-design.md` - Context on the problem

## Sources

- [LangGraph Graph API - Fan-out patterns](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [LangGraph Send API for Parallel Execution](https://dev.to/sreeni5018/leveraging-langgraphs-send-api-for-dynamic-and-parallel-workflow-execution-4pgd)
- [LangGraph Types Reference (Send class)](https://reference.langchain.com/python/langgraph/types/)
- [How to create a ReAct agent from scratch](https://langchain-ai.github.io/langgraph/how-tos/react-agent-from-scratch/)
- [LangGraph Streaming Modes](https://dev.to/sreeni5018/langgraph-streaming-101-5-modes-to-build-responsive-ai-applications-4p3f)
- [Structured Output for ReAct Agents](https://langchain-ai.github.io/langgraph/how-tos/react-agent-structured-output/)
- [LangGraph Branching How-To](https://langchain-ai.lang.chat/langgraphjs/how-tos/branching/)
