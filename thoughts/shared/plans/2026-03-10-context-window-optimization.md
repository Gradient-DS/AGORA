# Context Window Optimization — Implementation Plan

## Overview

The LangGraph orchestrator sends far too much context to the LLM at each step. Context grows from 2.8K chars (first call) to 86K chars (reporting-agent generation) because:

1. **Duplicate AIMessages**: Each turn produces TWO AI responses — the agent's raw output AND a regenerated "written" version. Both persist in state.
2. **Cross-agent pollution**: Tool results from history-agent (2.2K) and regulation-agent (56K of raw search results) carry over to reporting-agent, even though their final AI answers already summarize them.
3. **Redundant written regeneration**: The agent already produced the answer; we then make a second LLM call to "regenerate" it with the same prompt — adding 44-63 seconds of latency.

## Current State Analysis

### Message flow (from context_window.log)

```
Turn 1: User → general-agent → history-agent → tools → history-agent → generate_written + generate_spoken → merge
Turn 2: User → general-agent → update_user_settings → generate_written + generate_spoken → merge
Turn 3: User → general-agent → regulation-agent → search_regulations ×2 → generate_written + generate_spoken → merge
Turn 4: User → general-agent → reporting-agent → request_clarification → generate_report → generate_written + generate_spoken → merge
```

### Context window growth

| Step | Agent | Total Chars | Key Waste |
|------|-------|------------|-----------|
| Initial | general-agent | **2,841** | Clean |
| After history tools | history-agent | **5,011** | — |
| After regulation search ×2 | regulation-agent | **67,513** | 56K regulation results |
| Reporting-agent generation | reporting-agent (spoken) | **83,184** | 56K regulation + 2K history tools + 6K duplicates |

### Key files

- `core/agents.py:297-300` — `_run_agent_node`: passes ALL `state["messages"]` to every agent
- `core/graph.py:324-456` — `_create_parallel_sends`: converts ALL tool results to text, dispatches both written+spoken
- `core/graph.py:459-526` — `_generate_stream`: the LLM call for written/spoken generation
- `core/graph.py:547-596` — `merge_parallel_outputs`: creates AIMessage #2 (the duplicate)
- `core/state.py:33` — `messages: Annotated[list[BaseMessage], add_messages]` — append-only accumulator
- `pipelines/orchestrator.py:679-739` — streaming handler: skips agent nodes, streams from generate_written/generate_spoken

### The duplicate AIMessage problem (detailed)

Each agent turn produces TWO AIMessages in state:

1. **AIMessage #1** — from `_run_agent_node` (`agents.py:407`): the agent's actual LLM response. Has `agent_id` in `additional_kwargs`.
2. **AIMessage #2** — from `merge_parallel_outputs` (`graph.py:596`): regenerated written content from a SECOND LLM call. Has `spoken_text` in `additional_kwargs`.

The written regeneration uses the **same system prompt** as the agent (`graph.py:344`), just without tools bound. It's redundant — the agent already answered. From the logs:
- AIMessage #1 (history-agent): 3,501 chars (the real answer)
- AIMessage #2 (written regen): 2,448 chars (shorter, lost detail)
- Written regen took 48.29 seconds of additional latency

## Desired End State

Each LLM call receives **only the context it needs**:

- **Agent invocations**: system prompt + conversation summary (HumanMessages + final AI responses from prior turns) + current turn's own tool interactions
- **Spoken generation**: system prompt + user's question + agent's response (to summarize)
- **No written regeneration**: the agent's response IS the written output

### Expected results

| Step | Before | After | Reduction |
|------|--------|-------|-----------|
| regulation-agent (2nd search) | 67,513 | ~35K | 48% |
| reporting-agent invoke | 82,646 | ~19K | 77% |
| reporting spoken gen | 83,184 | ~5K | 94% |
| Latency per turn | +44-63s (written regen) | 0s | eliminated |

### How to verify

1. Run the demo scenario (postcode lookup → listen mode → regulation question → report)
2. Inspect `context_window.log` — each entry shows total chars and per-message breakdown
3. Verify no duplicate AIMessages (each turn should have exactly ONE AIMessage)
4. Verify agent responses are identical quality (no regression from removing written regen)
5. Verify spoken responses still generate correctly

## What We're NOT Doing

- Not changing the spoken generation architecture (separate model, separate prompt — still needed)
- Not truncating or summarizing tool results within a turn (the agent needs its own tool results)
- Not changing MCP server response sizes (that's a separate optimization)
- Not changing the server-openai implementation (focusing on server-langgraph only)
- Not removing the context_window.log instrumentation (keeping it for ongoing monitoring)

## Implementation Approach

Three phases, each independently deployable:

1. **Eliminate written regeneration** — removes the redundant LLM call, fixes duplicate AIMessages, biggest latency win
2. **Filter agent invocation context** — strip cross-agent tool results, biggest context window win
3. **Filter spoken generation context** — spoken model only needs user question + agent answer

---

## Phase 1: Eliminate Written Regeneration

### Overview

Remove the separate `generate_written` LLM call. The agent's response IS the written output. Only generate spoken text separately. This eliminates one full LLM call per turn and the duplicate AIMessage.

### Changes Required

#### 1. Simplify `route_from_agent` return — only spoken Send

**File**: `core/graph.py` — `_create_parallel_sends` → rename to `_create_spoken_send`

The function currently builds two `Send` commands (written + spoken). Change to only build spoken. Also apply message filtering (Phase 3 prep — for now, keep existing message building but only create one Send).

```python
def _create_spoken_send(state: AgentState) -> list[Send]:
    """Create Send command for spoken generation only.

    The agent's response is used directly as the written output.
    Only spoken text needs a separate LLM call (different prompt, potentially different model).
    """
    agent_id = state.get("current_agent", "general-agent")
    spoken_prompt = get_spoken_prompt(agent_id) or ""

    raw_messages = state.get("messages", [])

    # Build messages for spoken model:
    # Keep HumanMessages and the agent's final response (so spoken model can summarize it)
    # Convert tool results to plain text context
    # NOTE: Do NOT filter out the agent's final response — spoken model needs it to summarize
    messages: list[BaseMessage] = []
    tool_context_parts: list[str] = []

    for m in raw_messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                name = tc.get("name", "unknown")
                if is_handoff_tool(name):
                    continue
                args = tc.get("args", {})
                args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if args else ""
                tool_context_parts.append(f"[Tool aanroep: {name}({args_str})]")
            continue  # Don't include tool-calling AIMessages
        elif isinstance(m, ToolMessage):
            content = extract_text(m.content)
            if "Transferring to" in content:
                continue
            tool_context_parts.append(f"[Resultaat: {content}]")
            continue  # Don't include ToolMessages
        elif isinstance(m, SystemMessage):
            continue
        messages.append(m)

    # Inject tool context before last HumanMessage
    if tool_context_parts:
        tool_context = "\n".join(tool_context_parts)
        tool_context_msg = HumanMessage(
            content=f"[Uitgevoerde tools en resultaten]\n{tool_context}"
        )
        last_human_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_idx = i
                break
        if last_human_idx is not None:
            messages.insert(last_human_idx, tool_context_msg)
        else:
            messages.append(tool_context_msg)

    session_id = state.get("session_id", "")
    metadata = state.get("metadata", {})

    return [
        Send(
            "generate_spoken",
            GeneratorState(
                messages=messages,
                system_prompt=spoken_prompt,
                stream_type="spoken",
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
            ),
        ),
    ]
```

Update `route_from_agent` to call the renamed function:

```python
def route_from_agent(state: AgentState) -> Literal["tools"] | list[Send]:
    # ... existing tool call detection ...
    if not tool_calls:
        log.info("route_from_agent: No tool calls, dispatching spoken generation")
        return _create_spoken_send(state)
    return "tools"
```

#### 2. Simplify `merge_parallel_outputs` — use agent's response as written

**File**: `core/graph.py` — `merge_parallel_outputs`

Instead of creating a NEW AIMessage, update the agent's existing response in-place (via ID-based replacement in `add_messages` reducer) to add the `is_final_response` marker and `spoken_text`.

```python
def merge_parallel_outputs(state: AgentState) -> dict[str, Any]:
    """Merge spoken output with the agent's existing response.

    The agent's AIMessage is already in state as the written response.
    We update it with is_final_response marker and spoken_text,
    then set final_written/final_spoken for the orchestrator.
    """
    spoken_parts = state.get("spoken", [])
    spoken_content = spoken_parts[-1] if spoken_parts else ""

    # Find the agent's final response (last AIMessage without tool_calls)
    messages = state.get("messages", [])
    written_content = ""
    agent_msg = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            written_content = extract_text(msg.content)
            agent_msg = msg
            break

    log.info(
        f"merge_parallel_outputs: written={len(written_content)} chars, "
        f"spoken={len(spoken_content)} chars"
    )

    result: dict[str, Any] = {
        "final_written": written_content,
        "final_spoken": spoken_content,
    }

    # Update the agent's AIMessage with spoken text and final_response marker
    # Using the same ID triggers add_messages reducer to REPLACE (not append)
    if agent_msg:
        updated_kwargs = {**agent_msg.additional_kwargs}
        updated_kwargs["is_final_response"] = True
        if spoken_content:
            updated_kwargs["spoken_text"] = spoken_content

        updated_msg = AIMessage(
            content=agent_msg.content,
            id=agent_msg.id,
            additional_kwargs=updated_kwargs,
        )
        result["messages"] = [updated_msg]

    return result
```

#### 3. Remove `generate_written` node from graph

**File**: `core/graph.py` — `build_agent_graph`

```python
# REMOVE these lines:
graph.add_node("generate_written", generate_written_node)
graph.add_edge("generate_written", "merge")

# UPDATE conditional edges for agents — remove "generate_written" from targets:
graph.add_conditional_edges(
    agent_id,
    route_from_agent,
    ["tools", "generate_spoken"],  # was: ["tools", "generate_written", "generate_spoken"]
)
```

Also remove `generate_written_node` function (or keep as dead code if preferred).

#### 4. Remove `written` accumulator from AgentState

**File**: `core/state.py`

```python
# REMOVE this line from AgentState:
written: Annotated[list[str], operator.add]
```

The `spoken` accumulator stays (generate_spoken still uses it).

#### 5. Orchestrator — emit agent's response directly

**File**: `pipelines/orchestrator.py` — `_stream_response`

Currently, the orchestrator skips all agent node streaming (`if node_name in agent_nodes: continue`) and only streams from `generate_written`. Since we're removing `generate_written`, emit the agent's final response when the agent node completes.

In the `on_chain_end` handler (around line 872), add response emission:

```python
elif kind == "on_chain_end":
    output = event.get("data", {}).get("output", {})
    if isinstance(output, dict):
        # Existing: detect agent changes
        if "current_agent" in output:
            new_agent = output["current_agent"]
            if new_agent != current_agent_id:
                # ... existing agent change handling ...

        # NEW: Emit agent's final response as written text
        if node_name in agent_nodes:
            output_messages = output.get("messages", [])
            if output_messages:
                last_msg = output_messages[-1]
                if (
                    isinstance(last_msg, AIMessage)
                    and not getattr(last_msg, "tool_calls", None)
                    and last_msg.content
                ):
                    content = extract_text(last_msg.content)
                    if content and protocol_handler.is_connected:
                        if not message_started:
                            await protocol_handler.send_text_message_start(
                                message_id, "assistant"
                            )
                            message_started = True
                            if not spoken_message_started:
                                await protocol_handler.send_spoken_text_start(
                                    message_id, "assistant"
                                )
                                spoken_message_started = True
                        await protocol_handler.send_text_message_content(
                            message_id, content
                        )
                        full_response.append(content)

                        # In dictate mode, also send to spoken channel
                        if spoken_mode == "dictate":
                            await protocol_handler.send_spoken_text_content(
                                message_id, content
                            )
```

Remove the `generate_written` streaming handler (lines 692-722) since the node no longer exists.

### Success Criteria

#### Automated Verification:
- [x] Server starts without errors: `.venv/bin/python -m agora_langgraph.api.server`
- [x] No import errors for removed functions
- [ ] `context_window.log` shows NO `generate_written` entries
- [ ] `context_window.log` shows exactly ONE AIMessage per completed turn (no duplicates)

#### Manual Verification:
- [ ] Written response appears in chat immediately when agent finishes (no 44s+ delay)
- [ ] Spoken audio summary still generates and plays correctly
- [ ] Dictate mode still works (written text sent to both channels)
- [ ] Listen mode → wake word → feedback mode transition still works
- [ ] Tool approval flow (reporting-agent) still works
- [ ] Clarification request flow still works

**Implementation Note**: After completing this phase, pause for manual testing before proceeding to Phase 2.

---

## Phase 2: Filter Agent Invocation Context

### Overview

When an agent runs, it currently receives ALL messages from ALL prior agents. After Phase 1, each completed turn has exactly one AIMessage (marked with `is_final_response`). Use this marker to split messages into "prior history" (filtered) and "current turn" (full).

### Changes Required

#### 1. Create `_build_agent_messages` filtering function

**File**: `core/agents.py`

```python
def _build_agent_messages(state: AgentState) -> list[BaseMessage]:
    """Build filtered message list for agent LLM invocation.

    Prior completed turns: only HumanMessages + final AI responses
    Current turn: everything (own tool calls, results, handoffs)

    This prevents cross-agent pollution — an agent doesn't need to see
    another agent's raw tool results when it already has the final answer.
    """
    raw = list(state["messages"])

    # Find the last completed turn boundary (last is_final_response AIMessage)
    last_final_idx = -1
    for i in range(len(raw) - 1, -1, -1):
        if (
            isinstance(raw[i], AIMessage)
            and raw[i].additional_kwargs.get("is_final_response")
        ):
            last_final_idx = i
            break

    if last_final_idx == -1:
        # No prior completed turns — this is the first turn, keep everything
        return raw

    # Prior history: only HumanMessages + final response AIMessages
    history: list[BaseMessage] = []
    for msg in raw[: last_final_idx + 1]:
        if isinstance(msg, HumanMessage):
            history.append(msg)
        elif (
            isinstance(msg, AIMessage)
            and msg.additional_kwargs.get("is_final_response")
        ):
            history.append(msg)
        # Skip: ToolMessages, AIMessages with tool_calls, raw agent responses

    # Current turn: everything after the last completed turn
    current_turn = raw[last_final_idx + 1 :]

    return history + current_turn
```

#### 2. Use filtered messages in `_run_agent_node`

**File**: `core/agents.py` — `_run_agent_node`

```python
# BEFORE (line 297):
messages_with_system = [system_message] + list(state["messages"])

# AFTER:
filtered_messages = _build_agent_messages(state)
messages_with_system = [system_message] + filtered_messages
```

Update the `_log_context_window` call to log the filtered messages:

```python
_log_context_window(
    call_site="agent_invoke",
    agent_id=agent_id,
    messages=filtered_messages,
    system_prompt_chars=len(instructions),
)
```

### Success Criteria

#### Automated Verification:
- [x] Server starts without errors
- [ ] `context_window.log` shows regulation-agent receiving ~35K chars (was 67K)
- [ ] `context_window.log` shows reporting-agent receiving ~19K chars (was 83K)
- [ ] No ToolMessages from history-agent visible in regulation-agent's context
- [ ] No ToolMessages from regulation-agent visible in reporting-agent's context

#### Manual Verification:
- [ ] regulation-agent still produces correct regulatory analysis (it has its own search results)
- [ ] reporting-agent still produces complete reports (it has the final AI answers from prior agents)
- [ ] Multi-turn conversations maintain coherent context

**Implementation Note**: After completing this phase, pause for manual testing before proceeding to Phase 3.

---

## Phase 3: Filter Spoken Generation Context

### Overview

The spoken model currently receives the full tool context (59K+ chars) just to produce a 1-2 sentence summary. It only needs the user's question and the agent's response.

### Changes Required

#### 1. Simplify spoken message building in `_create_spoken_send`

**File**: `core/graph.py` — `_create_spoken_send`

Replace the full message building with minimal context:

```python
def _create_spoken_send(state: AgentState) -> list[Send]:
    """Create Send command for spoken generation with minimal context.

    The spoken model only needs:
    - Conversation summary (HumanMessages + final AI responses from prior turns)
    - The agent's current response (to summarize for TTS)
    No tool results needed — the agent's response already incorporates them.
    """
    agent_id = state.get("current_agent", "general-agent")
    spoken_prompt = get_spoken_prompt(agent_id) or ""
    raw_messages = state.get("messages", [])

    # Find the last completed turn boundary
    last_final_idx = -1
    for i in range(len(raw_messages) - 1, -1, -1):
        if (
            isinstance(raw_messages[i], AIMessage)
            and raw_messages[i].additional_kwargs.get("is_final_response")
        ):
            last_final_idx = i
            break

    messages: list[BaseMessage] = []

    # Prior turns: only HumanMessages + final responses
    if last_final_idx >= 0:
        for msg in raw_messages[: last_final_idx + 1]:
            if isinstance(msg, HumanMessage):
                messages.append(msg)
            elif (
                isinstance(msg, AIMessage)
                and msg.additional_kwargs.get("is_final_response")
            ):
                messages.append(msg)

    # Current turn: only HumanMessages + agent's final AIMessage
    for msg in raw_messages[last_final_idx + 1 :]:
        if isinstance(msg, HumanMessage):
            messages.append(msg)
        elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            messages.append(msg)

    log.info(
        f"_create_spoken_send: {len(messages)} messages for spoken generation "
        f"(was {len(raw_messages)} raw)"
    )

    session_id = state.get("session_id", "")
    metadata = state.get("metadata", {})

    return [
        Send(
            "generate_spoken",
            GeneratorState(
                messages=messages,
                system_prompt=spoken_prompt,
                stream_type="spoken",
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
            ),
        ),
    ]
```

### Success Criteria

#### Automated Verification:
- [x] Server starts without errors, all tests pass
- [ ] `context_window.log` shows `generate_spoken` receiving ~5K chars (was 83K)
- [ ] No ToolMessages or tool context in spoken generation entries

#### Manual Verification:
- [ ] Spoken summaries are still accurate and natural
- [ ] Spoken text correctly summarizes the agent's response, not prior turns
- [ ] Spoken generation latency is noticeably faster (smaller context = faster inference)

---

## Testing Strategy

### Full scenario test (DEMO_SCENARIOS.md):
1. Start inspection: "Ik ga op inspectie bij postcode 2521 DJ huisnummer 45"
2. Listen mode: "luister modus"
3. Buffer messages during listen mode
4. Wake word: "Agora, welke regelgeving wordt hier overtreden?"
5. Report: "genereer rapport"

### Verify at each step via `context_window.log`:
- Each agent_invoke entry should only contain relevant context
- No ToolMessages from other agents in filtered context
- No duplicate AIMessages
- Spoken generation context should be minimal

### Edge cases:
- First message in new session (no prior turns)
- Listen mode → wake word transition
- Clarification request interrupt (reporting-agent)
- Tool approval interrupt (generate_report)
- Dictate mode (written duplicated to spoken channel)
- Empty spoken response

## Code Cleanup After All Phases

- Remove `generate_written_node` function from `graph.py`
- Remove `_create_parallel_sends` function (replaced by `_create_spoken_send`)
- Remove `written` field from `AgentState` in `state.py`
- Remove `import operator` from `state.py` if unused
- Update comments referencing "parallel written/spoken generation" to reflect spoken-only
- Keep `context_window.log` instrumentation for ongoing monitoring

## References

- Context window log: `server-langgraph/context_window.log`
- Research: `thoughts/shared/research/2026-03-01-spoken-written-divergence.md`
