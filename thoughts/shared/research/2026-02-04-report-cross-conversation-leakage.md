---
date: 2026-02-04T12:00:00+01:00
researcher: claude
git_commit: b8bf6cb5e94acde612b1b6815c52b7c0898a1a03
branch: main
repository: AGORA
topic: "Report generation uses context from all conversations instead of only the current one"
tags: [research, codebase, reporting, server-langgraph, mcp-servers, state-management, bug]
status: complete
last_updated: 2026-02-04
last_updated_by: claude
---

# Research: Report Generation Cross-Conversation Context Leakage

**Date**: 2026-02-04T12:00:00+01:00
**Researcher**: claude
**Git Commit**: b8bf6cb5e94acde612b1b6815c52b7c0898a1a03
**Branch**: main
**Repository**: AGORA

## Research Question

Report generation takes longer as more conversations accumulate, and answers from previous conversations appear in reports of later conversations. Is the reporting MCP server fetching all conversations, or is conversation context not being cleared?

## Summary

**The reporting MCP server is NOT at fault.** It is a stateless tool server that only processes the `inspection_summary` string it receives as a parameter — it never fetches conversation history from any database.

**The root cause is in the server-langgraph orchestrator's state management.** The reporting-agent LLM constructs the `inspection_summary` argument from `state["messages"]`, which contains the **entire message history** for the current thread. LangGraph's `add_messages` reducer only appends messages — it never trims, summarizes, or clears them. Within a single thread (same `thread_id`), every message from every turn accumulates indefinitely.

This means:
1. **If the frontend reuses the same `threadId` across what the user considers "separate conversations"**, all messages from all those interactions accumulate in a single LangGraph state, and the reporting-agent sees everything.
2. **Even within a legitimately single thread**, a long conversation generates an ever-growing message list. Each report generation cycle adds extraction results, verification Q&A, and report outputs as `ToolMessage` and `AIMessage` objects to the same state. Subsequent reports see all prior content.

## Detailed Findings

### 1. Reporting MCP Server — Stateless Tool (NOT the cause)

The reporting MCP server at `mcp-servers/reporting/server.py` is a pure tool server. It receives discrete parameters and never queries any conversation database.

**`extract_inspection_data` tool** (`mcp-servers/reporting/server.py:34-42`):
```python
async def extract_inspection_data(
    session_id: str,
    inspection_summary: str,  # <-- This is the ONLY source of conversation context
    company_name: str | None = None,
    ...
)
```

The `inspection_summary` parameter is wrapped into a synthetic 2-message conversation (`server.py:115-118`) and passed to `ConversationExtractor.extract_from_conversation()` for GPT-4o structured extraction. The MCP server has no back-channel to the orchestrator's conversation storage.

**File storage exists but doesn't cause cross-contamination**: The reporting server writes `draft_data.json`, `final_report.json`, and `final_report.pdf` per `session_id` under `./storage/reports/{session_id}/`. These files persist across sessions (no cleanup mechanism exists), but they are keyed by `session_id` and the extraction is always performed fresh from the `inspection_summary` parameter, not from stored data.

### 2. Server-langgraph State Accumulation (ROOT CAUSE)

#### Message accumulation is unbounded

The `AgentState` in `server-langgraph/src/agora_langgraph/core/state.py:33`:
```python
messages: Annotated[list[BaseMessage], add_messages]
```

The `add_messages` reducer only appends. There is no trimming, windowing, or summarization anywhere in the codebase.

#### Messages grow with every graph turn

Each user message adds a `HumanMessage`. Each agent response adds an `AIMessage`. Each tool call adds `AIMessage` (with tool_calls) + `ToolMessage` (result). The `merge_parallel_outputs` node (`graph.py:553-558`) adds another `AIMessage` with the final written content.

For a single report generation cycle, approximately **8-12 messages** are added (handoff tool call + result, extract_inspection_data call + result, request_clarification interrupt + resume, submit_verification_answers call + result, generate_final_report call + result, plus written/spoken outputs).

#### The reporting-agent sees ALL accumulated messages

In `server-langgraph/src/agora_langgraph/core/agents.py:189`:
```python
messages_with_system = [system_message] + list(state["messages"])
response = await llm_with_tools.ainvoke(messages_with_system)
```

The LLM receives the **full** `state["messages"]` list — every message from the entire thread history. While the system prompt instructs it to include "ONLY user/assistant messages about the inspection" in `inspection_summary` (`agent_definitions.py:154-159`), the LLM sees everything and may include content from prior interactions in its summary.

#### State persistence via AsyncSqliteSaver

The `AsyncSqliteSaver` checkpointer (`server-langgraph/src/agora_langgraph/adapters/checkpointer.py:14-37`) persists the full graph state per `thread_id`. On each new message for an existing thread, the orchestrator loads the checkpoint (`orchestrator.py:221`), appends the new message, and saves the updated state.

There is no state expiration, TTL, or cleanup. The `delete_session` endpoint (`server.py:223-240`) only deletes from the `session_metadata` table — it does NOT delete LangGraph checkpoint data.

#### Thread ID is the only isolation boundary

All state isolation depends on `thread_id` at `orchestrator.py:197`:
```python
config = {"configurable": {"thread_id": thread_id}}
```

If the frontend sends the same `thread_id` for what the user considers separate conversations, all messages accumulate in one state.

### 3. What the Reporting-Agent LLM Actually Sees

When generating a report, the reporting-agent receives:

1. **System prompt** with 3-step workflow instructions (`agent_definitions.py:134-181`)
2. **ALL messages** from the thread: every `HumanMessage`, `AIMessage`, and `ToolMessage` ever added
3. **User metadata** injected into the system prompt (inspector name, email, email preferences)

The LLM then constructs the `inspection_summary` argument for `extract_inspection_data`. Despite instructions to keep it "concise - max 5000 characters" and include "ONLY user/assistant messages about the inspection", the LLM has the full history and may inadvertently include content from earlier in the thread.

### 4. Why It Gets Slower

Each turn adds messages to `state["messages"]`. The entire list is serialized/deserialized from SQLite on every graph invocation. More importantly, the full list is sent as LLM context in every agent call. As the thread grows:
- SQLite checkpoint read/write time increases
- LLM inference time increases (more input tokens)
- Token costs increase

## Code References

- `server-langgraph/src/agora_langgraph/core/state.py:33` — `messages` field with `add_messages` reducer (append-only)
- `server-langgraph/src/agora_langgraph/core/agents.py:189` — Full `state["messages"]` passed to LLM
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:197` — `thread_id` as sole state isolation key
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:221` — Existing state loaded from checkpointer
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:256-262` — Existing thread: only new message appended
- `server-langgraph/src/agora_langgraph/adapters/checkpointer.py:28` — `AsyncSqliteSaver` persistence
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:152-159` — Reporting-agent instructions for `inspection_summary`
- `mcp-servers/reporting/server.py:34-42` — `extract_inspection_data` tool definition
- `mcp-servers/reporting/server.py:115-118` — Summary wrapped as synthetic messages

## Architecture Insights

1. **LLM-as-data-constructor pattern**: The `inspection_summary` argument is not built programmatically — the LLM composes it from conversation history. This means the quality and scope of the summary depends entirely on the LLM's judgment, and giving it a huge message history makes it more likely to include irrelevant prior context.

2. **No message windowing**: LangGraph's `add_messages` reducer supports message deduplication (by ID) but not pruning. The codebase has no `trim_messages`, `RemoveMessage`, or summarization step — standard techniques for managing conversation length in LangGraph.

3. **Checkpoint data is never cleaned up**: The `delete_session` endpoint removes session metadata but not LangGraph checkpoints, leading to unbounded SQLite growth.

4. **Reporting MCP server has unused storage methods**: `SessionManager.store_conversation()` and `FileStorage.save_conversation_history()` exist but are never called. They appear to be dead code from an earlier design.

## Potential Fix Approaches

### Approach A: Message trimming before reporting-agent invocation
Add a message trimming step in `_run_agent_node` (or a dedicated pre-processing node) that limits the messages passed to the LLM. LangGraph provides `trim_messages` utility for this.

### Approach B: Programmatic summary construction
Instead of relying on the LLM to construct `inspection_summary`, build it programmatically from `state["messages"]` in the reporting-agent node — filtering to only `HumanMessage` and non-tool `AIMessage` types from the current "conversation segment" (e.g., messages after the last report generation).

### Approach C: Conversation segmentation
Track "conversation boundaries" in state (e.g., a `last_report_index` field). When generating a new report, only pass messages after the last boundary to the reporting-agent.

### Approach D: Frontend-side thread management
Ensure the HAI frontend generates a new `threadId` when starting a new conversation, so LangGraph state isolation naturally separates interactions.

## Open Questions

1. **Does the HAI frontend reuse `threadId` across what the user considers separate conversations?** If yes, this is the primary driver. If no, the issue is unbounded message accumulation within a single long thread.
2. **How large do message lists typically get?** Logging `len(state["messages"])` in `_run_agent_node` would quantify the problem.
3. **Should old checkpoints be cleaned up?** The SQLite database grows indefinitely. A TTL or cleanup mechanism may be needed.
