---
date: 2026-01-27T22:30:00+01:00
researcher: Claude
git_commit: 9ba31c308b7273adea8cbacbe444afc45dc03a3e
branch: feat/buffer
repository: AGORA
topic: "Specialist agents not returning control to general-agent after completing"
tags: [research, codebase, langgraph, routing, multi-agent]
status: complete
last_updated: 2026-01-27
last_updated_by: Claude
---

# Research: Specialist Agents Not Returning to General-Agent

**Date**: 2026-01-27T22:30:00+01:00
**Researcher**: Claude
**Git Commit**: 9ba31c308b7273adea8cbacbe444afc45dc03a3e
**Branch**: feat/buffer
**Repository**: AGORA

## Research Question

After implementing listen mode, specialist agents (like `history-agent`) don't transfer control back to `general-agent` after completing their task. Subsequent messages route directly to the specialist instead of going through general-agent for proper triage. This breaks the multi-agent handoff pattern.

## Summary

**Root Cause**: The `route_from_start` function was changed from a hardcoded `START → general-agent` edge to dynamic routing based on the **persisted `current_agent`** state. When a specialist completes, `current_agent` remains set to that specialist, causing subsequent messages to bypass `general-agent`.

**Solution**: In feedback mode, always route to `general-agent` first, regardless of the persisted `current_agent` value. This restores the original triage pattern deterministically without requiring a `transfer_to_general` tool.

## Detailed Findings

### 1. Original Routing (pre-listen-mode)

From git history (commit `5cb1ed7`), the entry point was hardcoded:

```python
graph.add_edge(START, "general-agent")  # Always start here
```

This guaranteed `general-agent` triaged every new message.

### 2. Current Routing (broken)

In `server-langgraph/src/agora_langgraph/core/graph.py:210-219`:

```python
def route_from_start(state: AgentState) -> str:
    # ...listen mode checks...

    # Normal routing to persisted agent (THE BUG)
    current = state.get("current_agent", "general-agent")
    if current not in VALID_AGENTS:
        return "general-agent"

    log.info(f"route_from_start: Routing to persisted agent '{current}'")
    return current  # <-- Routes to history-agent if that was last!
```

### 3. How current_agent Gets Stuck

Each agent node stamps itself into state (`agents.py:198-201`):

```python
return {
    "messages": [response],
    "current_agent": agent_id,  # history-agent sets this to "history-agent"
}
```

The checkpointer persists this value. For existing threads, the orchestrator doesn't override it (`orchestrator.py:245-250`):

```python
# Existing thread - only send new message, don't override persisted state
graph_input = {
    "messages": [HumanMessage(content=user_content)],
    "metadata": metadata,
}  # No current_agent override!
```

### 4. Execution Flow That Causes the Bug

```
Turn 1:
├── route_from_start → general-agent (default, new session)
├── general-agent calls transfer_to_history
├── route_after_tools → history-agent (handoff detected)
├── history-agent runs, sets current_agent="history-agent"
├── Parallel generation → merge → END
└── State persisted: current_agent="history-agent"

Turn 2: (BROKEN)
├── route_from_start reads current_agent="history-agent"
├── Routes DIRECTLY to history-agent (bypasses general!)
├── history-agent processes even non-history questions
└── No way to get back to general-agent
```

## Code References

- `server-langgraph/src/agora_langgraph/core/graph.py:171-219` - `route_from_start` function with the bug
- `server-langgraph/src/agora_langgraph/core/graph.py:210-219` - Specific lines that route to persisted agent
- `server-langgraph/src/agora_langgraph/core/agents.py:198-201` - Agents stamp their ID into state
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:245-250` - Existing thread input doesn't override current_agent
- `server-langgraph/src/agora_langgraph/core/tools.py:237-238` - Comment noting specialists don't have transfer_to_general

## Proposed Solution

Change `route_from_start` (lines 210-219) to always route to `general-agent` in feedback mode:

**Before** (broken):
```python
# Normal routing to persisted agent
current = state.get("current_agent", "general-agent")
if current not in VALID_AGENTS:
    log.info(f"route_from_start: Unknown agent '{current}', defaulting to general-agent")
    return "general-agent"

log.info(f"route_from_start: Routing to persisted agent '{current}'")
return current
```

**After** (fixed):
```python
# Feedback mode - always route to general-agent for triage
# general-agent will hand off to specialists as needed based on message content
log.info("route_from_start: Feedback mode, routing to general-agent for triage")
return "general-agent"
```

### Why This Works

1. **Deterministic**: No tool or LLM decision required
2. **Matches original design**: Restores the hardcoded `START → general-agent` behavior
3. **Preserves handoffs**: `general-agent` can still call `transfer_to_*` tools
4. **current_agent still useful**: Used in `route_after_tools` to return to current agent after non-handoff tools

### Alternative Considered (rejected)

Adding `transfer_to_general` tool to specialists - rejected because:
- Requires LLM to decide when to hand back (non-deterministic)
- Adds latency and cost
- User explicitly requested deterministic solution

## Architecture Insights

The multi-agent handoff pattern in AGORA is designed as:

```
                  ┌──────────────────┐
                  │  general-agent   │  <-- Triage agent
                  │  (entry point)   │
                  └────────┬─────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  history    │   │ regulation  │   │  reporting  │
│   agent     │   │   agent     │   │    agent    │
└─────────────┘   └─────────────┘   └─────────────┘
```

- `general-agent` is the **router/triage** agent
- Specialists are **one-way handoffs** that complete their task
- Control should return to `general-agent` for the **next** user message

## Related Research

- `thoughts/shared/plans/2026-01-27-listen-mode-ambient-agents.md` - Implementation plan that introduced the routing change

## Open Questions

None - the fix is straightforward.
