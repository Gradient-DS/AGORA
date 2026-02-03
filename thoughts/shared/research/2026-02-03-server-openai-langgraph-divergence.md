---
date: "2026-02-03T21:45:00+01:00"
researcher: Claude
git_commit: 7e07592a065e7652f6f84fcf8122bc38342e0809
branch: feat/benchmark
repository: AGORA
topic: "Why server-openai could not keep up with server-langgraph"
tags: [research, codebase, server-openai, server-langgraph, streaming, dual-streaming, divergence, openai-agents-sdk, langgraph]
status: complete
last_updated: "2026-02-03"
last_updated_by: Claude
---

# Research: Why server-openai could not keep up with server-langgraph

**Date**: 2026-02-03T21:45:00+01:00
**Researcher**: Claude
**Git Commit**: 7e07592a065e7652f6f84fcf8122bc38342e0809
**Branch**: feat/benchmark
**Repository**: AGORA

## Research Question

Was "dual streaming" the reason server-openai fell behind server-langgraph and could no longer be kept in line?

## Summary

**Dual streaming was not the primary cause.** Both servers successfully implemented dual-channel streaming (written + spoken text in parallel). The divergence was caused by a broader set of OpenAI Agents SDK limitations that surfaced as the project's requirements grew. The key inflection point was around mid-January 2026, when features like listen mode, the clarification tool (interrupt/resume), configurable spoken models, and distractor tool benchmarking were needed — none of which the SDK could support. Dual streaming was implementable in both (via different mechanisms), but the SDK's lack of graph-level primitives, interrupt support, and vendor flexibility made it increasingly impractical to maintain feature parity.

## Detailed Findings

### 1. Dual streaming was implemented in both servers

Both servers successfully implement parallel written + spoken text generation, but via fundamentally different mechanisms:

**server-openai** (`orchestrator.py:214-368`):
- The agent's SDK stream IS the written text (streamed directly via `ResponseTextDeltaEvent`)
- On the first written chunk, an `asyncio.create_task()` spawns a separate `AsyncOpenAI` client call for spoken text (`orchestrator.py:238-255`)
- An `asyncio.Queue` bridges spoken chunks to the frontend (`orchestrator.py:290-304`)
- Both streams are serialized at the WebSocket level via `asyncio.Lock` (`ag_ui_handler.py:63`)

**server-langgraph** (`graph.py:323-509`):
- The agent's final text response is **discarded** (`graph.py:386-390`)
- LangGraph's `Send` API dispatches to two parallel graph nodes: `generate_written` and `generate_spoken` (`graph.py:411-434`)
- Both nodes regenerate the response with dedicated prompts via `llm.astream()` (`graph.py:471`)
- `astream_events` naturally interleaves chunks from both branches (`orchestrator.py:459-517`)
- The spoken stream can use an entirely different model/provider via `LANGGRAPH_SPOKEN_*` env vars (`agents.py:64-96`)

The dual streaming approach in server-openai works, but has a structural limitation: the spoken stream always uses the same OpenAI model (hardcoded provider), while server-langgraph can use any OpenAI-compatible provider for spoken.

### 2. The real causes of divergence

The git history shows a clear timeline. Both servers were developed in parallel from November 2025 through January 12, 2026. After that, server-langgraph received 10+ unique feature commits that never touched server-openai:

| Date | Feature | Why impossible/impractical in server-openai |
|------|---------|----------------------------------------------|
| 2026-01-15 | Bug fixes for edge cases | SDK internal state is opaque, harder to debug |
| 2026-01-25 | Separate spoken model config (`LANGGRAPH_SPOKEN_*`) | server-openai's spoken generation already bypasses the SDK via raw `AsyncOpenAI`, but can't use non-OpenAI providers |
| 2026-01-27 | Listen mode (wake word, message buffering) | Requires graph-level conditional routing, custom state reducers, and `Send` API — no SDK equivalent |
| 2026-01-27 | Interrupt/resume for clarification tool | Uses LangGraph's `interrupt()` primitive (`tools.py:101`) — SDK has no pause/resume mechanism |
| 2026-01-28 | Disconnect handling | Tightly coupled to graph state management |
| 2026-01-28 | Chitchat routing improvements | Required graph edge modifications not possible in SDK's agent loop |
| 2026-02-03 | Distractor tool scaling benchmark | Required runtime tool injection (`tools.py:211-315`) tied to graph construction |

### 3. Specific OpenAI Agents SDK limitations

The following SDK constraints are documented in the codebase:

1. **No interrupt/resume** — LangGraph's `interrupt()` pauses graph execution mid-tool-call and resumes with `Command(resume=...)`. The SDK's `Runner.run_streamed()` runs to completion with no equivalent (`tools.py:78-107` vs no counterpart in server-openai).

2. **Turn-based tool execution** — The SDK executes tools only AFTER the LLM finishes streaming for a turn (`_run_impl.py:297-341`). Text and tool results cannot truly interleave within a single turn.

3. **Opaque internal state** — The SDK's internal `_run_impl_task` manages the agent loop. LangGraph exposes full state via `aget_state()` and `aupdate_state()`, enabling runtime inspection and modification.

4. **Vendor lock-in** — The SDK only works with OpenAI's API. LangGraph wraps any OpenAI-compatible endpoint via `ChatOpenAI(base_url=...)`, which was critical for the benchmark testing 7 different models.

5. **MCP tool workaround (SDK issue #617)** — MCP tools must be wrapped in `FunctionTool` instances rather than using native `mcp_servers=` parameter, because tools are lost after agent handoffs (`agent_runner.py:84`, `mcp_tools.py:16-67`).

6. **No graph-level primitives** — Features like conditional routing based on wake words, message buffering with custom reducers, and `Send`-based fan-out have no SDK counterpart. server-openai would need to reimplement these patterns from scratch using raw asyncio.

### 4. Timeline summary

| Phase | Period | State |
|-------|--------|-------|
| server-openai only | Oct-Nov 2025 | Original and sole backend |
| server-langgraph introduced | Nov 28, 2025 | Clean-room LangGraph reimplementation |
| Parallel development | Dec 2025 – Jan 12, 2026 | Both servers receive same features (AG-UI, sessions, spoken text, parallel generation) |
| Divergence begins | Jan 15, 2026 | server-langgraph gets bug fixes not ported to server-openai |
| Full divergence | Jan 25–28, 2026 | Listen mode, interrupt, spoken model config, disconnect — all LangGraph-only |
| Shared features continue | Jan 28 – Feb 2, 2026 | Some features still applied to both (tool display names, report acceptance) |

The last unique feature commit to server-openai was `0d40c4d` on January 12, 2026 (parallel spoken/written generation). After that, only shared commits touched server-openai.

## Code References

- `server-openai/src/agora_openai/pipelines/orchestrator.py:214-368` — Dual-channel streaming in server-openai
- `server-openai/src/agora_openai/core/agent_runner.py:211-236` — SDK streaming session
- `server-openai/src/agora_openai/api/ag_ui_handler.py:63` — asyncio.Lock for concurrent sends
- `server-langgraph/src/agora_langgraph/core/graph.py:251-509` — Send-based parallel generation
- `server-langgraph/src/agora_langgraph/core/graph.py:59-174` — Listen mode nodes
- `server-langgraph/src/agora_langgraph/core/tools.py:78-107` — Clarification interrupt
- `server-langgraph/src/agora_langgraph/core/agents.py:64-96` — Configurable spoken LLM
- `server-langgraph/src/agora_langgraph/config.py:29-40` — LANGGRAPH_SPOKEN_* settings
- `server-openai/src/agora_openai/core/agent_runner.py:84` — FunctionTool MCP workaround

## Architecture Insights

1. **Dual streaming was a solved problem in both servers** — The architectural difference (asyncio.Queue vs LangGraph Send) is an implementation detail, not a blocking limitation. Both approaches work.

2. **The SDK's closed-loop agent execution model was the real constraint** — `Runner.run_streamed()` runs the full ReAct loop internally. You can observe events but cannot inject custom logic (like wake word detection, message buffering, or interrupt/resume) into the execution flow.

3. **The divergence validates the project's thesis** — AGORA's purpose is comparing closed-source vs open-source multi-agent architectures. The fact that server-openai fell behind is itself evidence supporting the vendor-flexibility thesis documented in the comparison report.

4. **Maintenance burden, not impossibility** — Some features (like listen mode) could theoretically be reimplemented from scratch using raw asyncio outside the SDK. But this would mean duplicating what LangGraph provides natively, defeating the purpose of using the SDK in the first place.

## Historical Context (from thoughts/)

- `thoughts/shared/research/2026-02-03-technisch-ontwerp-rapport-vergelijking.md` — Comprehensive comparison noting features only in server-langgraph (listen mode, clarification tool, configurable spoken model)
- `thoughts/shared/research/2026-01-28-chitchat-handling-divergence.md` — Exclusively references server-langgraph code paths, confirming it was the sole development target by late January
- `thoughts/shared/research/2026-01-15-listen-mode-message-buffering.md` — Extensive analysis of LangGraph patterns not available in the OpenAI SDK
- `thoughts/shared/research/2026-01-28-dual-text-comparison-ui-setting.md` — Documents the dual-channel architecture across both servers

## Open Questions

1. Should server-openai be formally deprecated or kept as a reference implementation for the comparison thesis?
2. Were there any attempts to implement listen mode or interrupt patterns in server-openai that were abandoned?
