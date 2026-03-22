---
date: 2026-03-08T12:00:00+01:00
researcher: claude
git_commit: 62f1cf1a249818bb130f9d17ea90827619147b47
branch: feat/tool-description
repository: AGORA
topic: "Reporting Agent Overview: Data Flow, Clarification Questions, and Brittleness"
tags: [research, codebase, reporting-agent, mcp-reporting, verification, hap-report]
status: complete
last_updated: 2026-03-08
last_updated_by: claude
---

# Research: Reporting Agent Overview

**Date**: 2026-03-08
**Git Commit**: 62f1cf1
**Branch**: feat/tool-description

## Research Questions
1. How does information from the session get reused in the report generation step?
2. How are clarification questions generated/determined?
3. What are brittle mechanisms that could pose bugs?

Known issues: (a) clarification questions that duplicate already-answered info, (b) unreliable tool calls and agent confusion.

## Summary

The reporting pipeline follows a 3-step MCP tool workflow: `extract_inspection_data` -> `submit_verification_answers` -> `generate_final_report`. The core brittleness comes from **session context being passed as a single LLM-constructed text string** (`inspection_summary`), **double LLM interpretation** (orchestrator LLM constructs the summary, MCP server LLM re-extracts from it), and **verification questions generated without awareness of what was already discussed** in the conversation.

---

## 1. How Session Information Gets Reused in Report Generation

### The Bottleneck: `inspection_summary` Parameter

All conversation context enters the reporting MCP server through a **single string parameter** on `extract_inspection_data`:

```
Orchestrator LLM (has full conversation)
  → constructs `inspection_summary` string (agent prompt says: "ONLY user/assistant messages, not tool results")
    → MCP server wraps it as synthetic messages
      → GPT-4o re-extracts structured data from it
```

**Key files:**
- Agent instructions: `server-openai/.../agent_definitions.py:146-191` -- tells agent what to include
- MCP tool: `mcp-servers/reporting/server.py:34-173` -- receives the summary
- Re-wrapping: `mcp-servers/reporting/analyzers/conversation_extractor.py:60-74` -- wraps summary as 2 synthetic messages

### What Gets Lost

The agent is instructed to pass "ONLY user/assistant messages about the inspection" with a 5000-char limit. This means:
- **Tool results from regulation/history agents are excluded** by design
- **System context, metadata, and structured findings are discarded**
- The summary is subject to **LLM summarization quality** -- the orchestrator's LLM decides what to include/exclude

### Additional Context Paths

- **Company info**: Passed as separate params (`company_name`, `company_address`) -- but only if the LLM remembers to include them
- **Inspector info**: In server-langgraph, injected into agent instructions from metadata (`agents.py:271-294`). In server-openai, no explicit injection -- relies on LLM memory
- **Evidence images**: Forwarded directly to MCP server via HTTP POST (`orchestrator.py:151-158`), bypassing the tool protocol entirely

---

## 2. How Clarification Questions Are Generated

### Three Generation Paths

**Path A -- Inline with extraction (primary):**
The `EXTRACTION_SYSTEM_PROMPT` (`prompts.py:1-139`) instructs GPT-4o to include `verification_questions` in its extraction output. Questions target missing critical fields or low-confidence extractions. Popped from extraction result at `server.py:135`.

**Path B -- Fallback programmatic generation:**
If the LLM returns no questions, `Verifier._identify_missing_critical_fields()` at `verifier.py:88-114` checks six critical fields and `_generate_fallback_questions()` at `verifier.py:232-284` produces hardcoded Dutch questions.

**Path C -- LLM-based standalone (currently unused):**
`Verifier.generate_verification_questions()` at `verifier.py:16-86` can call GPT-4o with `VERIFICATION_PROMPT` for more nuanced questions. This method exists but is **not called** by any tool.

### Why Questions Duplicate Already-Answered Info

The root cause: **questions are generated from the extraction result, not from the conversation**. The GPT-4o extraction sees the `inspection_summary` text but may:
1. Fail to extract information that was clearly stated (low confidence → asks again)
2. Not have access to information from tool results (regulation analysis, history lookups) which the inspector already discussed
3. Generate questions about fields that were covered in parts of the conversation the LLM didn't include in the summary

The verification system has **no mechanism to cross-reference questions against the original conversation history**.

---

## 3. Brittle Mechanisms

### 3a. Double LLM Interpretation (Most Critical)

The same information is processed by **two separate LLM calls**:
1. The orchestrator's reporting-agent LLM constructs `inspection_summary` from conversation
2. The MCP server's GPT-4o extracts structured data from that summary

Each step can lose, misinterpret, or hallucinate information. The second LLM has no access to the original conversation, only the first LLM's summary.

### 3b. LLM-Dependent Tool Call Construction

The reporting agent must construct correct tool calls with specific parameters. The agent prompt at `agent_definitions.py:146-191` describes a rigid 3-step workflow, but:
- The LLM may call tools out of order or skip steps
- The `inspection_summary` parameter is free-form text the LLM must compose -- quality varies
- If the LLM gets confused about which step it's on, it may re-call `extract_inspection_data` instead of `submit_verification_answers`
- No server-side enforcement of workflow order (any tool can be called at any time)

### 3c. Synthetic Message Wrapping

At `conversation_extractor.py:116-119`, the summary is wrapped into synthetic messages:
```python
messages = [
    {"role": "user", "content": "Genereer een HAP rapport op basis van de volgende inspectie:"},
    {"role": "assistant", "content": inspection_summary}
]
```
This loses the multi-turn structure of the original conversation and presents everything as a single assistant message.

### 3d. Answer Parsing Fragility

`ResponseParser.parse_simple_response()` at `response_parser.py:73-92` uses simple string matching:
- Matches options by substring (e.g., "ja" anywhere in the answer)
- For yes/no, checks against hardcoded word lists
- No LLM-based parsing fallback for ambiguous answers
- If the agent passes answers as a string instead of a dict, parsing depends on matching against stored question options

### 3e. Field Mapping Substring Matching

`FieldMapper` at `field_mapper.py` maps extracted strings to enums via bidirectional substring matching (lines 262-269). E.g., violation type "temperatuur" matches `ViolationType` by checking if either contains the other. This can produce incorrect matches for similar terms.

### 3f. No Retry or Recovery Logic

- MCP tool call failures return error JSON to the LLM (`mcp_tools.py:52-54`) with no retry
- If `extract_inspection_data` fails, the agent must decide to retry -- but its instructions don't cover error recovery
- The MCP timeout is 120s (`mcp_tools.py:118-126`) -- if GPT-4o extraction is slow, timeout kills the request

### 3g. State Consistency Risks

- `SessionManager` uses in-memory cache + file storage with no locking
- If the agent calls `submit_verification_answers` before `extract_inspection_data` completes writing, the draft may not exist yet
- The `session_id` must match between all three tool calls -- if the LLM uses different IDs, state is fragmented

### 3h. Divergent Orchestrator Implementations

Key differences between server-openai and server-langgraph that could cause inconsistent behavior:
- server-langgraph injects `session_id`, `inspector_name`, `inspector_email` into agent instructions; server-openai does not
- server-langgraph has `request_clarification` tool with `interrupt()` for multi-turn verification; server-openai relies on natural conversation
- server-langgraph reporting agent has `handoffs: []` (no hand-back); server-openai has `handoffs: ["general-agent"]`

---

## Architecture Insights

### Simplification Opportunities

1. **Eliminate double LLM interpretation**: Pass structured conversation data directly to MCP tools instead of having the agent construct a text summary. The MCP server could receive the raw message array.

2. **Context-aware verification**: Pass the full conversation (or at minimum a structured summary) to the verification question generator so it can avoid asking about already-discussed topics.

3. **Server-side workflow enforcement**: The MCP server could enforce the 3-step sequence (reject `submit_verification_answers` if no extraction exists, reject `generate_final_report` if not verified).

4. **Reduce tool count**: Consider merging the 3-step workflow into fewer calls. E.g., extraction + verification could be one tool that returns questions, and the agent just needs to pass answers + generate.

5. **Structured answer passing**: Always pass verification answers as a dict, never as free-form text, to avoid parsing ambiguity.

---

## Code References

- `mcp-servers/reporting/server.py:34-173` -- `extract_inspection_data` tool definition
- `mcp-servers/reporting/server.py:176-242` -- `submit_verification_answers` tool definition
- `mcp-servers/reporting/server.py:245-361` -- `generate_final_report` tool definition
- `mcp-servers/reporting/analyzers/prompts.py:1-139` -- EXTRACTION_SYSTEM_PROMPT
- `mcp-servers/reporting/analyzers/conversation_extractor.py:15-58` -- extraction flow
- `mcp-servers/reporting/analyzers/conversation_extractor.py:116-119` -- synthetic message wrapping
- `mcp-servers/reporting/verification/verifier.py:88-114` -- critical field identification
- `mcp-servers/reporting/verification/verifier.py:232-284` -- fallback question generation
- `mcp-servers/reporting/verification/response_parser.py:73-92` -- answer parsing
- `mcp-servers/reporting/analyzers/field_mapper.py:262-269` -- enum substring matching
- `server-openai/src/agora_openai/core/agent_definitions.py:131-197` -- reporting agent definition
- `server-openai/src/agora_openai/adapters/mcp_tools.py:52-54` -- error handling (no retry)
- `server-openai/src/agora_openai/pipelines/orchestrator.py:151-158` -- image forwarding
- `server-langgraph/src/agora_langgraph/core/agents.py:271-294` -- dynamic context injection

## Related Research
- `thoughts/shared/research/2026-02-04-report-cross-conversation-leakage.md` -- message accumulation in LangGraph state
- `thoughts/shared/research/2026-03-06-nvwa-rapport-van-bevindingen-styling.md` -- NVWA PDF styling

## Open Questions
- Should the MCP reporting server receive raw message arrays instead of text summaries?
- Can the 3-tool workflow be simplified to 2 or even 1 tool?
- Should verification questions be generated orchestrator-side with full conversation access?
