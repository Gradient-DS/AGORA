# Distractor Tool Scaling Benchmark — Implementation Plan

## Overview

Add a benchmark mode that measures how well each LLM handles increasing numbers of plausible-but-fake "distractor" tools. The `regulation-agent` receives N distractor tools alongside its real `search_regulations` tool, and we measure whether models still pick the correct tool. Distractor counts: 0 (baseline), 2, 5, 10, 20, 50. Evaluation is fully deterministic — no LLM judge needed.

## Current State Analysis

- **Benchmark** (`benchmark/benchmark.py`) already tests 7 models on 2 scenarios with timing, tool call tracking, and pairwise Claude scoring
- **Tool assembly** (`tools.py:211-253`) cleanly separates per-agent tools via `AGENT_MCP_MAPPING` — ideal injection point
- **`regulation-agent`** currently gets only MCP tools from the `regulation` server (5 tools: `search_regulations`, `get_regulation_context`, `lookup_regulation_articles`, `analyze_document`, `get_database_stats`)
- **`regulation_query` scenario** expects exactly `["search_regulations"]` — single expected tool makes precision/recall measurement clean
- **Server env var pattern** (`LANGGRAPH_` prefix, Pydantic Settings) is established and trivial to extend

### Key Discoveries:
- `get_tools_for_agent()` at `tools.py:211-253` is the injection point — distractor `StructuredTool` instances append to the tools list
- `build_server_env()` at `benchmark.py:330-359` sets all `LANGGRAPH_*` env vars — add `LANGGRAPH_DISTRACTOR_TOOLS` here
- `ScenarioResult` at `benchmark.py:186-201` tracks `tool_calls: list[ToolCallRecord]` — we can compute metrics from this
- Server restarts per model already happen (`benchmark.py:1210-1266`) — we extend this to restart per model × distractor_count
- `StructuredTool.from_function()` pattern is already used at `tools.py:182-192` for `update_user_settings`

## Desired End State

A new `--distractor-benchmark` CLI mode that:
1. Runs the `regulation_query` scenario for each model × distractor count (0, 2, 5, 10, 20, 50)
2. Computes tool precision, recall, and F1 deterministically
3. Saves results to `benchmark/results/distractor_results.json`
4. Generates an accuracy-at-N line plot (`tool_scaling.png`) with one line per model

### How to Verify:
```bash
# Run distractor benchmark for 2 models
python benchmark/benchmark.py --distractor-benchmark --models gpt-4o,gpt-4o-mini

# Check output
cat benchmark/results/distractor_results.json | python -m json.tool
ls benchmark/results/plots/tool_scaling.png

# Plot from existing results
python benchmark/plot_results.py --distractor
```

## What We're NOT Doing

- No changes to the pairwise Claude judge scoring — the existing benchmark mode stays as-is
- No distractor injection for other agents (history-agent, reporting-agent, general-agent)
- No dummy MCP server (Option B from research) — using in-process `StructuredTool` injection (Option A)
- No per-agent targeted distractors (Option C) — all distractors go to regulation-agent
- No changes to the frontend, MCP servers, or AG-UI protocol
- No token budget tracking (mentioned as open question in research — defer to future work)

## Implementation Approach

**Option A from the research document**: Env-var controlled distractor injection in the server process. Distractors are `StructuredTool` instances added in `get_tools_for_agent()`. They have plausible NVWA food-inspection names and schemas but return a fixed error string if called. The benchmark harness sets the env var and restarts the server for each distractor count.

Evaluation is deterministic: we know which tool names are distractors (they all start with a known prefix or are in a known list), so we can compute precision/recall/F1 without an LLM judge.

---

## Phase 1: Server-Side Distractor Tool Injection

### Overview
Add a `distractor_tools` setting and generate N plausible `StructuredTool` instances that get appended to the regulation-agent's tool list.

### Changes Required:

#### 1. Add `distractor_tools` setting
**File**: `server-langgraph/src/agora_langgraph/config.py`
**Changes**: Add one field to the `Settings` class

```python
# After line 50 (guardrails_enabled)
distractor_tools: int = Field(
    default=0,
    description="Number of distractor tools to inject for benchmarking (0 = disabled)",
)
```

This is automatically read from `LANGGRAPH_DISTRACTOR_TOOLS` env var (via the `LANGGRAPH_` prefix).

#### 2. Add distractor tool generation to tools.py
**File**: `server-langgraph/src/agora_langgraph/core/tools.py`
**Changes**: Add distractor templates list, generator function, and inject in `get_tools_for_agent()`

Add after the `AGENT_MCP_MAPPING` dict (after line 208):

```python
# ─── Distractor Tools (for benchmarking) ─────────────────────────────────────

DISTRACTOR_TEMPLATES: list[tuple[str, str, dict[str, str]]] = [
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
    ("lookup_supplier_compliance", "Look up supplier compliance history and audit results", {"supplier_kvk": "str"}),
    ("get_traceability_records", "Get product traceability chain records for a batch", {"batch_number": "str", "kvk_number": "str"}),
    ("search_enforcement_actions", "Search historical enforcement actions and fines", {"kvk_number": "str", "action_type": "str"}),
    ("verify_waste_disposal", "Verify waste disposal procedures and compliance records", {"kvk_number": "str", "waste_type": "str"}),
    ("check_packaging_compliance", "Check food packaging material compliance with EU standards", {"product_id": "str"}),
    ("get_hygiene_audit_results", "Retrieve hygiene audit scores and findings", {"kvk_number": "str", "audit_year": "str"}),
    ("search_product_specifications", "Search product specification documents and standards", {"product_name": "str", "category": "str"}),
    ("verify_organic_certification", "Verify organic certification status and history", {"kvk_number": "str", "product_type": "str"}),
    ("check_animal_welfare_records", "Check animal welfare inspection records for livestock facilities", {"facility_id": "str"}),
    ("get_sampling_schedule", "Get the inspection sampling schedule for a facility", {"kvk_number": "str", "quarter": "str"}),
    ("lookup_food_contact_materials", "Look up food contact material safety assessments", {"material_type": "str"}),
    ("search_incident_reports", "Search food safety incident and outbreak reports", {"query": "str", "region": "str"}),
    ("verify_export_certificates", "Verify export health certificates for food products", {"certificate_id": "str"}),
    ("check_gmo_labeling", "Check GMO labeling compliance for food products", {"product_id": "str", "kvk_number": "str"}),
    ("get_veterinary_records", "Retrieve veterinary inspection records for meat processing", {"facility_id": "str", "species": "str"}),
    ("search_nutrition_claims", "Search and verify nutrition and health claims on products", {"product_name": "str"}),
    ("check_cold_chain_integrity", "Check cold chain integrity logs from producer to retailer", {"batch_number": "str"}),
    ("lookup_pesticide_residues", "Look up pesticide residue test results for produce", {"product_id": "str", "harvest_date": "str"}),
    ("verify_halal_certification", "Verify halal certification status for food establishments", {"kvk_number": "str"}),
    ("get_cross_contamination_risk", "Assess cross-contamination risk based on facility layout", {"facility_id": "str"}),
    ("search_additive_approvals", "Search food additive approval status and usage limits", {"additive_code": "str"}),
    ("check_shelf_life_compliance", "Check shelf life labeling and date marking compliance", {"product_id": "str"}),
    ("lookup_training_records", "Look up food safety training records for facility staff", {"kvk_number": "str", "year": "str"}),
    ("get_complaint_history", "Get consumer complaint history for a food business", {"kvk_number": "str", "category": "str"}),
    ("verify_label_accuracy", "Verify ingredient list and nutritional label accuracy", {"product_id": "str"}),
    ("check_microbiological_limits", "Check microbiological test results against legal limits", {"sample_id": "str", "organism": "str"}),
    ("search_rapid_alerts", "Search RASFF rapid alert notifications for food safety", {"query": "str", "country": "str"}),
    ("get_facility_floor_plan", "Retrieve facility floor plan and production flow layout", {"facility_id": "str"}),
    ("lookup_water_source_permits", "Look up water source permits for food production facilities", {"facility_id": "str"}),
    ("check_heavy_metal_levels", "Check heavy metal contamination levels in food products", {"sample_id": "str", "metal_type": "str"}),
    ("verify_cold_storage_temps", "Verify cold storage temperature monitoring compliance", {"facility_id": "str", "zone": "str"}),
    ("search_novel_food_approvals", "Search novel food authorization status in the EU", {"product_name": "str"}),
    ("get_process_validation_data", "Get HACCP process validation and critical control point data", {"kvk_number": "str", "process": "str"}),
    ("check_irradiation_compliance", "Check food irradiation treatment compliance and labeling", {"product_id": "str"}),
    ("lookup_geographic_indications", "Look up protected geographic indication status", {"product_name": "str", "region": "str"}),
    ("verify_supply_chain_docs", "Verify supply chain documentation and traceability papers", {"kvk_number": "str", "supplier_id": "str"}),
    ("get_allergen_management_plan", "Get facility allergen management plan and procedures", {"kvk_number": "str"}),
    ("search_contaminant_limits", "Search maximum contaminant levels for food categories", {"contaminant": "str", "food_category": "str"}),
    ("check_biofilm_testing", "Check biofilm testing results for food processing equipment", {"facility_id": "str", "equipment_id": "str"}),
]


def generate_distractor_tools(n: int) -> list[StructuredTool]:
    """Generate N distractor StructuredTools for benchmarking.

    Each tool has a plausible NVWA food-inspection name and schema
    but returns a fixed error if called.
    """
    if n <= 0:
        return []

    tools = []
    for i in range(min(n, len(DISTRACTOR_TEMPLATES))):
        name, description, params = DISTRACTOR_TEMPLATES[i]

        def _make_distractor_fn(tool_name: str):
            def _distractor(**kwargs: Any) -> str:
                return f"Error: {tool_name} is not available in this environment."
            _distractor.__name__ = tool_name
            _distractor.__doc__ = description
            return _distractor

        tool = StructuredTool.from_function(
            func=_make_distractor_fn(name),
            name=name,
            description=description,
        )
        tools.append(tool)

    if n > len(DISTRACTOR_TEMPLATES):
        log.warning(
            f"Requested {n} distractors but only {len(DISTRACTOR_TEMPLATES)} "
            f"templates available. Using {len(DISTRACTOR_TEMPLATES)}."
        )

    return tools
```

Then modify `get_tools_for_agent()` to inject distractors at the end (after line 252, before `return tools`):

```python
    # Inject distractor tools for benchmarking (regulation-agent only)
    if agent_id == "regulation-agent":
        from agora_langgraph.config import get_settings
        settings = get_settings()
        if settings.distractor_tools > 0:
            distractors = generate_distractor_tools(settings.distractor_tools)
            tools.extend(distractors)
            distractor_names = [t.name for t in distractors]
            log.info(
                f"{agent_id} injected {len(distractors)} distractor tools: "
                f"{distractor_names}"
            )

    log.info(f"{agent_id} total tools: {len(tools)}")
    return tools
```

Note: The existing `log.info(f"{agent_id} total tools: {len(tools)}")` at line 252 is moved after the distractor injection so it reports the final count.

### Success Criteria:

#### Automated Verification:
- [ ] Server starts with `LANGGRAPH_DISTRACTOR_TOOLS=5`: verify in logs that regulation-agent gets 5+5=10 tools
- [ ] Server starts with `LANGGRAPH_DISTRACTOR_TOOLS=0` (default): no distractors, regulation-agent gets normal 5 tools
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] If a distractor tool is called, it returns the error string (not a crash)

#### Manual Verification:
- [ ] Start server with `LANGGRAPH_DISTRACTOR_TOOLS=10` and send the regulation_query prompt via WebSocket — confirm the model still calls `search_regulations`

**Implementation Note**: After completing this phase, pause for manual verification before proceeding.

---

## Phase 2: Benchmark Distractor Mode

### Overview
Add `--distractor-benchmark` mode to `benchmark.py` that runs `regulation_query` for each model × distractor count, computes deterministic tool selection metrics, and saves structured results.

### Changes Required:

#### 1. New data classes
**File**: `benchmark/benchmark.py`
**Changes**: Add after `PairwiseComparison` class (after line 216)

```python
DISTRACTOR_COUNTS = [0, 2, 5, 10, 20, 50]

# All distractor tool names (must match DISTRACTOR_TEMPLATES in tools.py)
DISTRACTOR_TOOL_NAMES = {
    "verify_temperature_logs", "check_allergen_labeling", "search_eu_directives",
    "lookup_haccp_certificate", "query_import_permits", "get_pest_control_records",
    "check_water_quality_reports", "search_food_recalls", "verify_staff_certifications",
    "get_lab_test_results", "check_transport_conditions", "lookup_supplier_compliance",
    "get_traceability_records", "search_enforcement_actions", "verify_waste_disposal",
    "check_packaging_compliance", "get_hygiene_audit_results", "search_product_specifications",
    "verify_organic_certification", "check_animal_welfare_records", "get_sampling_schedule",
    "lookup_food_contact_materials", "search_incident_reports", "verify_export_certificates",
    "check_gmo_labeling", "get_veterinary_records", "search_nutrition_claims",
    "check_cold_chain_integrity", "lookup_pesticide_residues", "verify_halal_certification",
    "get_cross_contamination_risk", "search_additive_approvals", "check_shelf_life_compliance",
    "lookup_training_records", "get_complaint_history", "verify_label_accuracy",
    "check_microbiological_limits", "search_rapid_alerts", "get_facility_floor_plan",
    "lookup_water_source_permits", "check_heavy_metal_levels", "verify_cold_storage_temps",
    "search_novel_food_approvals", "get_process_validation_data", "check_irradiation_compliance",
    "lookup_geographic_indications", "verify_supply_chain_docs", "get_allergen_management_plan",
    "search_contaminant_limits", "check_biofilm_testing",
}


@dataclass
class DistractorResult:
    """Result of one model run at one distractor level."""
    model_id: str
    num_distractors: int
    # From the ScenarioResult
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    error: str | None = None
    total_ms: float | None = None
    # Computed metrics
    expected_tools_called: list[str] = field(default_factory=list)
    distractor_tools_called: list[str] = field(default_factory=list)
    other_tools_called: list[str] = field(default_factory=list)
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
```

#### 2. Metric computation function
**File**: `benchmark/benchmark.py`
**Changes**: Add after `DistractorResult` class

```python
def compute_tool_metrics(
    result: ScenarioResult,
    expected_tools: set[str],
    distractor_names: set[str],
) -> DistractorResult:
    """Compute deterministic tool selection metrics from a scenario result."""
    # Classify each tool call (exclude transfer_to_* handoff tools)
    called_names = [
        tc.name for tc in result.tool_calls
        if not tc.name.startswith("transfer_to_")
    ]

    expected_called = [n for n in called_names if n in expected_tools]
    distractor_called = [n for n in called_names if n in distractor_names]
    other_called = [n for n in called_names if n not in expected_tools and n not in distractor_names]

    # Precision: of all non-handoff tools called, how many were expected?
    total_calls = len(called_names)
    correct_calls = len(expected_called)
    precision = correct_calls / total_calls if total_calls > 0 else 1.0

    # Recall: of all expected tools, how many were called?
    recall = correct_calls / len(expected_tools) if expected_tools else 1.0

    # F1
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return DistractorResult(
        model_id=result.model_id,
        num_distractors=0,  # Set by caller
        tool_calls=result.tool_calls,
        error=result.error,
        total_ms=result.total_ms,
        expected_tools_called=expected_called,
        distractor_tools_called=distractor_called,
        other_tools_called=other_called,
        precision=precision,
        recall=recall,
        f1=f1,
    )
```

#### 3. `build_server_env()` update
**File**: `benchmark/benchmark.py`
**Changes**: Add distractor env var support (in `build_server_env`, after line 352)

Add a `num_distractors: int = 0` parameter to the function signature, and add:

```python
    # Distractor tools for scaling benchmark
    if num_distractors > 0:
        env["LANGGRAPH_DISTRACTOR_TOOLS"] = str(num_distractors)
```

Also update `start_server()` to accept and pass through `num_distractors`.

#### 4. Distractor benchmark runner
**File**: `benchmark/benchmark.py`
**Changes**: Add new async function before `main()`

```python
async def run_distractor_benchmark(
    models_to_run: list[dict],
    distractor_counts: list[int],
    timeout: int = 180,
) -> dict[str, list[DistractorResult]]:
    """Run the regulation_query scenario at each distractor level for each model."""
    scenario = next(s for s in SCENARIOS if s["id"] == "regulation_query")
    expected_tools = set(scenario["expected_tools"])

    # Results keyed by model_id
    all_results: dict[str, list[DistractorResult]] = {}

    for model_config in models_to_run:
        model_id = model_config["id"]
        model_results: list[DistractorResult] = []

        print(f"\n{'─' * 60}")
        print(f"  Model: {model_id} ({model_config['model']})")
        print(f"{'─' * 60}")

        for n_distractors in distractor_counts:
            print(f"\n  Distractors: {n_distractors}")
            print(f"  Starting server...", end="", flush=True)

            proc = start_server(model_config, num_distractors=n_distractors)

            if not wait_for_health(timeout=90):
                print(f" FAILED (server did not become healthy)")
                stop_server(proc)
                dr = DistractorResult(
                    model_id=model_id,
                    num_distractors=n_distractors,
                    error="Server failed to start",
                )
                model_results.append(dr)
                continue

            print(f" OK")

            user_id = create_test_user()

            # Warm-up
            print(f"    Warming up...", end="", flush=True)
            warmup = await run_scenario(
                {"id": "warmup", "prompt": "Hallo", "expected_agent": "general-agent", "expected_tools": []},
                model_id, 0, user_id, timeout=timeout,
            )
            print(f" {'OK' if not warmup.error else 'WARN: ' + str(warmup.error)}")

            # Run regulation_query
            print(f"    regulation_query (N={n_distractors})...", end="", flush=True)
            result = await run_scenario(scenario, model_id, 1, user_id, timeout=timeout)

            if result.error:
                print(f" ERROR: {result.error[:60]}")
            else:
                tools = [tc.name for tc in result.tool_calls if not tc.name.startswith("transfer_to_")]
                print(f" tools={tools}")

            # Compute metrics
            active_distractor_names = set(
                name for name, _, _ in DISTRACTOR_TEMPLATES_NAMES[:n_distractors]
            )
            dr = compute_tool_metrics(result, expected_tools, DISTRACTOR_TOOL_NAMES)
            dr.num_distractors = n_distractors
            model_results.append(dr)

            print(f"    P={dr.precision:.2f}  R={dr.recall:.2f}  F1={dr.f1:.2f}  "
                  f"distractors_called={dr.distractor_tools_called}")

            # Stop server
            print(f"  Stopping server...", end="", flush=True)
            stop_server(proc)
            print(" done")
            await asyncio.sleep(2)

        all_results[model_id] = model_results

    return all_results
```

**Note**: The above uses `DISTRACTOR_TOOL_NAMES` (the full set of all 50 names) for classification. Even though only N are injected, any name in the set is classified as a distractor if called. This is safe because non-injected distractor names can never appear in tool calls.

#### 5. Save and print distractor results
**File**: `benchmark/benchmark.py`

```python
def save_distractor_results(results: dict[str, list[DistractorResult]]) -> Path:
    """Save distractor benchmark results as JSON."""
    path = RESULTS_DIR / "distractor_results.json"
    data = {}
    for model_id, dr_list in results.items():
        data[model_id] = [asdict(dr) for dr in dr_list]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def print_distractor_table(results: dict[str, list[DistractorResult]]) -> None:
    """Print distractor benchmark results table."""
    from tabulate import tabulate

    print("\n" + "=" * 100)
    print("DISTRACTOR TOOL SCALING RESULTS")
    print("=" * 100)

    headers = ["Model", "N Distractors", "Precision", "Recall", "F1",
               "Distractors Called", "Total Time (ms)", "Error?"]
    rows = []

    for model_id, dr_list in results.items():
        for dr in dr_list:
            rows.append([
                model_id,
                dr.num_distractors,
                f"{dr.precision:.2f}" if not dr.error else "-",
                f"{dr.recall:.2f}" if not dr.error else "-",
                f"{dr.f1:.2f}" if not dr.error else "-",
                ", ".join(dr.distractor_tools_called) or "-",
                f"{dr.total_ms:.0f}" if dr.total_ms else "-",
                dr.error[:30] if dr.error else "",
            ])

    print(tabulate(rows, headers=headers, tablefmt="grid"))
```

#### 6. CLI integration in `main()`
**File**: `benchmark/benchmark.py`
**Changes**: Add `--distractor-benchmark` arg and branch

In the argparse section (after line 1049):
```python
    parser.add_argument(
        "--distractor-benchmark",
        action="store_true",
        help="Run distractor tool scaling benchmark (regulation_query only)",
    )
```

Add a new branch after the rescore branch (after line 1150) and before the normal mode:

```python
    # ── Distractor benchmark mode ──
    if args.distractor_benchmark:
        # Filter models
        models_to_run = MODELS
        if args.models:
            selected = [m.strip() for m in args.models.split(",")]
            models_to_run = [m for m in MODELS if m["id"] in selected]

        # Skip models without API keys
        models_to_run = [m for m in models_to_run if m["api_key"]]

        preflight_checks(skip_scoring=True)

        print(f"\n=== Distractor Tool Scaling Benchmark ===")
        print(f"  Models:    {[m['id'] for m in models_to_run]}")
        print(f"  Scenario:  regulation_query")
        print(f"  Distractor counts: {DISTRACTOR_COUNTS}")
        print()

        distractor_results = await run_distractor_benchmark(
            models_to_run, DISTRACTOR_COUNTS, timeout=args.timeout,
        )

        print_distractor_table(distractor_results)

        path = save_distractor_results(distractor_results)
        print(f"\n  Results saved: {path}")
        print()
        return
```

### Success Criteria:

#### Automated Verification:
- [ ] `python benchmark/benchmark.py --distractor-benchmark --models gpt-4o` runs successfully for 6 distractor counts
- [ ] `distractor_results.json` is written with correct structure: `{model_id: [{num_distractors, precision, recall, f1, ...}]}`
- [ ] At `num_distractors=0`, precision and recall are both 1.0 (assuming gpt-4o calls the right tool)
- [ ] The table prints correctly showing all model × distractor count combinations

#### Manual Verification:
- [ ] Run with 2+ models and verify the results look reasonable
- [ ] Check that at high distractor counts (20, 50), weaker models show degradation

**Implementation Note**: After completing this phase, pause for manual verification.

---

## Phase 3: Accuracy-at-N Visualization

### Overview
Add a tool scaling plot to `plot_results.py` that shows F1 score vs number of distractor tools, with one line per model.

### Changes Required:

#### 1. Load distractor results
**File**: `benchmark/plot_results.py`
**Changes**: Add path constant and loader function

```python
DISTRACTOR_PATH = RESULTS_DIR / "distractor_results.json"

def load_distractor_results() -> dict | None:
    if not DISTRACTOR_PATH.exists():
        return None
    return json.loads(DISTRACTOR_PATH.read_text())
```

#### 2. Accuracy-at-N line plot
**File**: `benchmark/plot_results.py`
**Changes**: Add new plot function

```python
def plot_tool_scaling(distractor_data: dict) -> None:
    """Line plot: F1 score vs number of distractor tools, one line per model."""
    models = list(distractor_data.keys())

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.suptitle(
        "Tool Selectie bij Toenemend Aantal Afleidingstools",
        fontsize=16, fontweight="bold",
    )

    for i, model_id in enumerate(models):
        entries = distractor_data[model_id]
        # Sort by num_distractors
        entries.sort(key=lambda e: e["num_distractors"])

        xs = [e["num_distractors"] for e in entries if not e.get("error")]
        ys = [e["f1"] for e in entries if not e.get("error")]

        if not xs:
            continue

        ax.plot(
            xs, ys,
            marker="o", linewidth=2, markersize=8,
            label=model_id, color=get_model_color(i),
        )

        # Annotate last point
        if ys:
            ax.annotate(
                f"{ys[-1]:.2f}",
                (xs[-1], ys[-1]),
                textcoords="offset points",
                xytext=(10, 0),
                fontsize=9,
            )

    ax.set_xlabel("Aantal afleidingstools", fontsize=12)
    ax.set_ylabel("Tool Selectie F1-score", fontsize=12)
    ax.set_ylim(-0.05, 1.10)
    ax.set_xticks([0, 2, 5, 10, 20, 50])
    ax.legend(fontsize=10, loc="lower left")
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    path = PLOTS_DIR / "tool_scaling.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")
```

#### 3. Integrate into main
**File**: `benchmark/plot_results.py`
**Changes**: Add `--distractor` flag and call the plot

In argparse (after line 803):
```python
    parser.add_argument(
        "--distractor",
        action="store_true",
        help="Also generate distractor tool scaling plots",
    )
```

In main(), after the existing plots (after line 858):
```python
    # Distractor scaling plot
    distractor_data = load_distractor_results()
    if distractor_data:
        if args.drop_models:
            for mid in drop_ids:
                distractor_data.pop(mid, None)
        plot_tool_scaling(distractor_data)
    elif args.distractor:
        print("  SKIP  Distractor plot (geen distractor_results.json)")
```

### Success Criteria:

#### Automated Verification:
- [ ] `python benchmark/plot_results.py` generates `tool_scaling.png` when `distractor_results.json` exists
- [ ] `--drop-models` correctly filters distractor plot
- [ ] Plot has correct axis labels, one line per model, markers at each distractor count

#### Manual Verification:
- [ ] The plot is visually clear and readable
- [ ] Lines show expected pattern: high F1 at low N, potential degradation at high N
- [ ] Legend identifies each model correctly

---

## Testing Strategy

### Automated Tests:
- Start server with `LANGGRAPH_DISTRACTOR_TOOLS=5`, call `/mcp/tools` or inspect logs to confirm 10 tools on regulation-agent (5 real + 5 distractor)
- Run `--distractor-benchmark --models gpt-4o` with a single distractor count to verify the full pipeline

### Manual Testing:
1. Run full distractor benchmark with 2-3 models
2. Verify `distractor_results.json` structure
3. Run `plot_results.py` and inspect `tool_scaling.png`
4. Verify the plot matches the JSON data

## Implementation Notes

- The distractor tools intentionally have **no parameters of type that match `search_regulations`'s query parameter** — but they have plausible food-inspection domain names that make them semantically similar to the real tools. This makes them effective distractors (harder than random-domain tools).
- At N=50 distractors, the regulation-agent will have 55 tools bound to the LLM. Each tool schema is ~500-1000 tokens, adding ~25-50k tokens to the prompt. Models with smaller context windows may hit limits.
- The `StructuredTool.from_function()` approach (not async) is intentional — distractor tools should never actually be called, and if they are, a sync error return is fine.
- The `get_settings()` call inside `get_tools_for_agent()` uses the `@lru_cache` cached settings, so there's no performance concern from reading it on every call.

## References

- Research document: `thoughts/shared/research/2026-02-03-llm-tool-scaling-benchmark.md`
- RAG-MCP paper methodology (arXiv:2505.03275) — distractor injection approach
- Current benchmark: `benchmark/benchmark.py`
- Tool injection point: `server-langgraph/src/agora_langgraph/core/tools.py:211-253`
- Server config: `server-langgraph/src/agora_langgraph/config.py:18-71`
