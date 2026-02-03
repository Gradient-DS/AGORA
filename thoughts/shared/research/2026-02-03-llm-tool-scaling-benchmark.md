---
date: 2026-02-03T10:00:00+01:00
researcher: Claude
git_commit: c91b74f3eed61364ee042ff2581c5370c6e9721f
branch: feat/benchmark
repository: AGORA
topic: "Comparing LLMs on the number of tools they can handle — tool scaling benchmark approaches"
tags: [research, benchmark, tool-scaling, mcp, llm-evaluation, distractor-tools]
status: complete
last_updated: 2026-02-03
last_updated_by: Claude
---

# Research: Comparing LLMs on Tool-Count Scaling

**Date**: 2026-02-03T10:00:00+01:00
**Researcher**: Claude
**Git Commit**: c91b74f
**Branch**: feat/benchmark
**Repository**: AGORA

## Research Question

Given AGORA's existing benchmark (`benchmark/benchmark.py`) that tests LLMs on speed, tool correctness, agent routing, and answer quality across a multi-agent system with ~16 tools — what would be an easy and interesting way to add a "tool scaling" dimension that compares how well models handle increasing numbers of available tools?

## Summary

The most practical approach for AGORA is **distractor tool injection**: keep your real scenarios and ground-truth tools fixed, but progressively add plausible-but-fake tools to the agent's tool set, then measure whether models still pick the correct tools. This is the dominant methodology in the literature (RAG-MCP, MCP-Bench, MCP-Atlas, FuncBenchGen all use it). For AGORA specifically, the easiest implementation injects distractors at the `get_tools_for_agent()` level via a `--distractors N` flag in the benchmark harness, requiring minimal server changes.

## Current Tool Landscape

### Active Tools (16 total across 4 agents)

| Agent | Built-in Tools | MCP Server | MCP Tools | Total |
|-------|---------------|------------|-----------|-------|
| `general-agent` | `transfer_to_history`, `transfer_to_regulation`, `transfer_to_reporting`, `update_user_settings` | (none) | 0 | **4** |
| `regulation-agent` | (none) | `regulation` (port 5002) | `search_regulations`, `get_regulation_context`, `lookup_regulation_articles`, `analyze_document`, `get_database_stats` | **5** |
| `reporting-agent` | `request_clarification` | `reporting` (port 5003) | `extract_inspection_data`, `submit_verification_answers`, `generate_final_report`, `get_report_status` | **5** |
| `history-agent` | (none) | `history` (port 5005) | `check_company_exists`, `get_inspection_history` | **2** |

### Disabled Tools (4 in inspection-history server)

`get_company_violations`, `check_repeat_violation`, `get_follow_up_status`, `search_inspections_by_inspector` — all commented out in `mcp-servers/inspection-history/server.py`.

### Key Integration Points

- Agent-to-MCP mapping: `server-langgraph/src/agora_langgraph/core/tools.py:203-208` (`AGENT_MCP_MAPPING`)
- Tool assembly: `get_tools_for_agent()` at `tools.py:211-253`
- Tool binding to LLM: `agents.py:142` (`llm.bind_tools(tools)`)
- Graph wiring: `graph.py:564-597` (`build_agent_graph()`)

## Detailed Findings

### Existing Benchmarks for Tool-Count Scaling

#### Tier 1: Directly measure scaling with N tools

| Benchmark | Year | Approach | Scale | Key Finding |
|-----------|------|----------|-------|-------------|
| **RAG-MCP** | 2025 | Needle-in-haystack: 1 real tool among N-1 distractors | N = 1 to 11,100 | Accuracy >90% for N<30, degrades at 31-70, collapses >100 |
| **MCP-Bench** (Accenture) | 2025 | 10 distractor MCP servers per task | 28 servers, 250 tools | Strong models (o3, gpt-5) stable; weak models degrade sharply |
| **MCP-Atlas** | 2026 | 36 real MCP servers, distractors from similar domains | 220 tools, 1000 tasks | 10-25 tools per task (3-7 target, 5-10 distractors) |
| **FuncBenchGen** | 2025 | Synthetic DAGs with type-compatible distractors | Controllable N | Domain-plausible distractors cause steepest accuracy decline |

#### Tier 2: Large catalogs (not specifically varying N)

- **BFCL** (Berkeley): ~3 function choices per test case, best for single-call correctness
- **ToolBench/ToolLLM**: 3,451 tools, 16,464 APIs — massive but stability issues
- **Seal-Tools**: 4,076 auto-generated APIs with nested calling
- **MCPToolBench++**: 4,000+ MCP servers, found prompt-size degradation

### Key Metrics for Tool Scaling

**Selection accuracy:**
- Exact Match (EM): Did the model call exactly the right tools?
- Tool Precision/Recall/F1: Correct calls vs. total calls vs. expected calls
- Distractor call rate: How often does the model call a fake tool?

**Scaling-specific:**
- Accuracy-at-N curve: Plot accuracy vs. number of available tools
- Distractor resistance: Accuracy specifically with domain-plausible distractors
- Context overhead: Tokens consumed by tool schemas as N grows

**Already measured in AGORA benchmark:**
- TTFT, response time, total time
- Tool calls made (names + args)
- Agent routing (agents_seen)
- Pairwise quality scoring via Claude judge

### Recommended Approach: Distractor Injection

#### Why This Is the Easiest Path

1. Your benchmark already measures tool calls per scenario (`ScenarioResult.tool_calls`)
2. Your scenarios already define `expected_tools` — you can directly compute precision/recall
3. The `get_tools_for_agent()` function is a clean injection point
4. No MCP server changes required for the simplest version

#### Implementation Options (Easiest to Most Thorough)

**Option A: Env-var controlled distractor injection in server (Recommended)**

Add a `LANGGRAPH_DISTRACTOR_TOOLS=N` environment variable. In `get_tools_for_agent()`, append N `StructuredTool` instances with plausible NVWA food-inspection names and schemas. These tools return a fixed error if called.

Changes needed:
1. `benchmark.py`: Add `--distractors N` flag, set env var in `build_server_env()`
2. `tools.py`: Read env var, generate and append distractor tools in `get_tools_for_agent()`
3. `benchmark.py`: Add new fields to `ScenarioResult` for tracking distractor calls

**Option B: Dummy MCP server**

Create `mcp-servers/distractor/server.py` — a FastMCP server that exposes a configurable number of dummy tools. Add to `LANGGRAPH_MCP_SERVERS` during benchmark runs. Tests the full MCP discovery stack.

**Option C: Per-agent targeted distractors**

Most informative for AGORA's multi-agent architecture:
- Add distractor handoff tools to `general-agent` (e.g., `transfer_to_quality_assurance`, `transfer_to_laboratory`)
- Add domain-similar distractors to specialist agents (e.g., `search_eu_directives` alongside `search_regulations`)

#### Distractor Tool Examples (NVWA Food Inspection Domain)

Plausible distractors that would be hard for models to reject:

```python
DISTRACTOR_TEMPLATES = [
    ("verify_temperature_logs", "Verify cold chain temperature logs for a facility", {"facility_id": "str", "date_range": "str"}),
    ("check_allergen_labeling", "Check allergen labeling compliance for products", {"product_id": "str", "kvk_number": "str"}),
    ("search_eu_directives", "Search EU food safety directives by topic", {"query": "str", "directive_type": "str"}),
    ("lookup_haccp_certificate", "Look up HACCP certification status for a company", {"kvk_number": "str"}),
    ("query_import_permits", "Query food import permits and documentation", {"kvk_number": "str", "product_category": "str"}),
    ("get_pest_control_records", "Retrieve pest control inspection records", {"kvk_number": "str", "limit": "int"}),
    ("check_water_quality_reports", "Check water quality test results for food facilities", {"facility_id": "str"}),
    ("search_food_recalls", "Search recent food product recall notices", {"query": "str", "severity": "str"}),
    ("verify_staff_certifications", "Verify food handler certifications for staff", {"kvk_number": "str"}),
    ("get_lab_test_results", "Retrieve laboratory test results for food samples", {"sample_id": "str", "test_type": "str"}),
    ("check_transport_conditions", "Check transport temperature and condition logs", {"shipment_id": "str"}),
    ("lookup_supplier_compliance", "Look up supplier compliance history", {"supplier_kvk": "str"}),
    ("get_traceability_records", "Get product traceability chain records", {"batch_number": "str", "kvk_number": "str"}),
    ("search_enforcement_actions", "Search historical enforcement actions and fines", {"kvk_number": "str", "action_type": "str"}),
    ("verify_waste_disposal", "Verify waste disposal procedures and records", {"kvk_number": "str", "waste_type": "str"}),
    # ... extend to 50 for full scaling range
]
```

#### Suggested Benchmark Matrix

Run each model with:
- N = 0 (baseline, current behavior)
- N = 5 (minor noise)
- N = 10 (moderate — roughly doubles available tools)
- N = 20 (significant — ~3x current tools)
- N = 50 (stress test — most models start degrading around 30+)

#### New Metrics to Add to ScenarioResult

```python
@dataclass
class ScenarioResult:
    # ... existing fields ...
    num_available_tools: int = 0
    num_distractor_tools: int = 0
    distractor_tools_called: list[str] = field(default_factory=list)
    tool_precision: float = 0.0   # correct_calls / total_calls
    tool_recall: float = 0.0      # correct_calls / expected_calls
```

#### New Visualization: Accuracy-at-N Curve

Add to `plot_results.py`:
- X-axis: Number of distractor tools (0, 5, 10, 20, 50)
- Y-axis: Tool selection F1 score
- One line per model
- This is the signature plot from RAG-MCP and is visually compelling

### What the Literature Tells Us to Expect

1. **Threshold around N=30**: RAG-MCP found accuracy >90% below 30 tools, sharp degradation at 31-70
2. **Domain-plausible distractors are much harder**: FuncBenchGen found type-compatible distractors cause 2-3x more errors than random ones
3. **Strong vs. weak model separation**: MCP-Bench found o3/gpt-5 maintain stable scores while weaker models collapse — this is exactly the kind of model differentiation useful for benchmarking
4. **Context window pressure**: Each tool schema consumes ~500-1000 tokens; at N=50 distractors, you add ~25-50k tokens of schema

## Code References

- `benchmark/benchmark.py:140-174` — Current test scenarios with `expected_tools`
- `benchmark/benchmark.py:179-202` — `ScenarioResult` dataclass (extend with new metrics)
- `benchmark/benchmark.py:330-359` — `build_server_env()` (add `LANGGRAPH_DISTRACTOR_TOOLS` env var)
- `server-langgraph/src/agora_langgraph/core/tools.py:203-208` — `AGENT_MCP_MAPPING`
- `server-langgraph/src/agora_langgraph/core/tools.py:211-253` — `get_tools_for_agent()` (injection point)
- `server-langgraph/src/agora_langgraph/core/agents.py:142` — `llm.bind_tools(tools)` (where tools hit the LLM)
- `mcp-servers/inspection-history/server.py:284-482` — 4 disabled tools (could re-enable as "easy" distractors)

## Architecture Insights

- The `AGENT_MCP_MAPPING` + `get_tools_for_agent()` pattern makes AGORA unusually well-suited for distractor injection — tools are assembled per agent at startup, providing a clean hook
- The single shared `ToolNode` (graph.py:614) means distractor tools must be registered there too, but this happens automatically via `get_tools_for_agent()`
- AGORA's multi-agent handoff pattern provides a second interesting scaling dimension: can `general-agent` still route correctly when given extra handoff tool options?

## Related Research

- [RAG-MCP paper (arXiv:2505.03275)](https://arxiv.org/abs/2505.03275) — Most directly relevant methodology
- [FuncBenchGen (arXiv:2509.26553)](https://arxiv.org/abs/2509.26553) — Controllable distractor generation
- [MCP-Bench (arXiv:2508.20453)](https://arxiv.org/abs/2508.20453) — Live MCP server distractor approach
- [MCP-Atlas (arXiv:2602.00933)](https://arxiv.org/html/2602.00933) — Latest comprehensive MCP benchmark
- [Anthropic: Writing Effective Tools for AI Agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — Practical tool design guidance
- [MCP "too many tools" problem](https://demiliani.com/2025/09/04/model-context-protocol-and-the-too-many-tools-problem/) — Context window cost analysis

## Open Questions

1. **Should distractors be per-agent or global?** Per-agent is more realistic for AGORA's architecture but requires more implementation. Global (all agents get all distractors) is simpler but less realistic.
2. **How to handle the 4 disabled history tools?** Re-enabling them as "real" distractors (they have implementations) could be an easy first step before synthetic generation.
3. **Should the pairwise Claude judge scoring be adapted?** The current PAIRWISE_PROMPT evaluates tool usage but doesn't specifically penalize distractor calls — may need an update.
4. **Token budget tracking**: Should the benchmark measure prompt token counts to quantify context overhead at each distractor level?
