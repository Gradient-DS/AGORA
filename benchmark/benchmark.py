#!/usr/bin/env python3
# Run with: ../server-langgraph/.venv/bin/python benchmark.py
"""AGORA Model Benchmark
========================
Benchmarks different LLM models on server-langgraph for:
  - Speed: TTFT (time to first token), response time, total time
  - Correctness: tool calls, agent routing
  - Answer quality: scored by Claude against gpt-4o baseline

Prerequisites:
  1. MCP servers running:  cd mcp-servers && docker-compose up -d
  2. ANTHROPIC_API_KEY in root .env (for Claude scoring)
  3. pip install -r benchmark/requirements.txt

Usage:
  python benchmark/benchmark.py                   # Run all models
  python benchmark/benchmark.py --models gpt-4o,gpt-4o-mini
  python benchmark/benchmark.py --skip-scoring     # Speed-only run
  python benchmark/benchmark.py --rerun-baseline   # Re-capture reference answers
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load project .env for API keys
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("benchmark")

# ─── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = PROJECT_ROOT / "server-langgraph"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ─── Server Config ────────────────────────────────────────────────────────────

SERVER_HOST = "localhost"
SERVER_PORT = 8000
WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws"
HEALTH_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/health"
USERS_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/users"

MCP_SERVERS = "regulation=http://localhost:5002,reporting=http://localhost:5003,history=http://localhost:5005"

MCP_HEALTH_URLS = {
    "regulation": "http://localhost:5002/health",
    "reporting": "http://localhost:5003/health",
    "history": "http://localhost:5005/health",
}

# ─── API Keys (read from environment / .env) ─────────────────────────────────

OPENAI_API_KEY = os.getenv("LANGGRAPH_OPENAI_API_KEY") or os.getenv(
    "OPENAI_API_KEY", ""
)
HF_API_KEY = os.getenv("HF_TOKEN") or os.getenv("LANGGRAPH_SPOKEN_API_KEY") or ""
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─── Models to Benchmark ─────────────────────────────────────────────────────
# Edit this list to add/remove models. Each entry needs:
#   id:          Short identifier (used in filenames)
#   model:       Model string sent to the API
#   base_url:    OpenAI-compatible API endpoint
#   api_key:     API key for this provider
#   is_baseline: True for the reference model (scored as 10/10)

MODELS: list[dict] = [
    # # ── Closed-source ──
    {
        "id": "gpt-4o",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "api_key": OPENAI_API_KEY,
        "is_baseline": True,
    },
    {
        "id": "gpt-4o-mini",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key": OPENAI_API_KEY,
    },
    {
        "id": "gpt-5.2",
        "model": "gpt-5.2",
        "base_url": "https://api.openai.com/v1",
        "api_key": OPENAI_API_KEY,
    },
    # ── Open-source ──
    {
        "id": "qwen-2.5-72b",
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "base_url": "https://router.huggingface.co/v1",
        "api_key": HF_API_KEY,
    },
    {
        "id": "gpt-oss-120b",
        "model": "openai/gpt-oss-120b",
        "base_url": "https://router.huggingface.co/v1",
        "api_key": HF_API_KEY,
    },
    # {
    #     "id": "gpt-oss-20b",
    #     "model": "openai/gpt-oss-20b",
    #     "base_url": "https://router.huggingface.co/v1",
    #     "api_key": HF_API_KEY,
    # },
    # ── Mistral API ──
    {
        "id": "mistral-large",
        "model": "mistral-large-latest",
        "base_url": "https://api.mistral.ai/v1",
        "api_key": MISTRAL_API_KEY,
    },
    {
        "id": "ministral-14b",
        "model": "ministral-14b-latest",
        "base_url": "https://api.mistral.ai/v1",
        "api_key": MISTRAL_API_KEY,
    },
]

# ─── Test Scenarios ───────────────────────────────────────────────────────────

SCENARIOS: list[dict] = [
    # {
    #     "id": "greeting",
    #     "prompt": "Hey, wat is de bedoeling?",
    #     "expected_agent": "general-agent",
    #     "expected_tools": [],
    #     "description": "Casual Dutch greeting — no tool calls, should stay on general-agent and explain capabilities",
    # },
    {
        "id": "inspection_start",
        "prompt": "Start inspectie bij Restaurant Bella Rosa, postcode 2511 AA nummer 123",
        "expected_agent": "history-agent",
        "expected_tools": ["check_company_exists", "get_inspection_history"],
        "description": (
            "Company inspection start — should hand off to history-agent "
            "and call check_company_exists + get_inspection_history"
        ),
    },
    {
        "id": "regulation_query",
        "prompt": (
            "Ik zie een geopende ton met rauwe vis op kamertemperatuur naast "
            "een afvoerputje vol schoonmaakmiddelresten, welke regels worden "
            "hiermee overtreden?"
        ),
        "expected_agent": "regulation-agent",
        "expected_tools": ["search_regulations"],
        "description": (
            "Real-world inspection finding — should hand off to regulation-agent "
            "and call search_regulations to find violated food safety regulations"
        ),
    },
]

# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ToolCallRecord:
    name: str
    args: str = ""
    result: str = ""


@dataclass
class ScenarioResult:
    model_id: str
    scenario_id: str
    prompt: str
    run_number: int
    # Timing (milliseconds)
    ttft_ms: float | None = None  # Time to first text token
    response_ms: float | None = None  # Time to TEXT_MESSAGE_END
    total_ms: float | None = None  # Time to RUN_FINISHED
    # Content
    response_text: str = ""
    agents_seen: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    # Status
    error: str | None = None


@dataclass
class PairwiseComparison:
    """Result of a head-to-head comparison between two models on one scenario."""

    scenario_id: str
    model_a: str
    model_b: str
    # Winner per dimension: model_a id, model_b id, or "tie"
    winner_tools: str = "tie"
    winner_routing: str = "tie"
    winner_quality: str = "tie"
    winner_language: str = "tie"
    reasoning: str = ""


# ─── Distractor Tool Scaling ────────────────────────────────────────────────

DISTRACTOR_COUNTS = [0, 2, 5, 10, 20, 50]

# All distractor tool names (must match DISTRACTOR_TEMPLATES in tools.py)
DISTRACTOR_TOOL_NAMES = {
    "search_violation_records", "search_inspection_reports", "search_audit_findings",
    "search_incident_logs", "search_complaint_records", "search_inspector_directory",
    "search_company_database", "search_supplier_directory", "search_laboratory_directory",
    "search_expert_contacts", "search_product_catalog", "search_equipment_database",
    "search_packaging_materials", "search_ingredient_database", "search_chemical_database",
    "search_internal_memos", "search_meeting_minutes", "search_training_materials",
    "search_policy_updates", "search_faq_database", "search_news_articles",
    "search_recall_notices", "search_press_releases", "search_scientific_publications",
    "search_conference_proceedings", "search_lab_results", "search_sample_database",
    "search_test_methods", "search_calibration_records", "search_reference_standards",
    "search_inspection_schedule", "search_task_assignments", "search_route_planner",
    "search_resource_availability", "search_budget_allocations", "search_facility_database",
    "search_floor_plans", "search_regional_statistics", "search_risk_maps",
    "search_zoning_permits", "search_report_templates", "search_checklist_templates",
    "search_letter_templates", "search_form_library", "search_guidance_documents",
    "search_translation_glossary", "search_photo_archive", "search_video_library",
    "search_case_studies", "search_benchmarking_data",
}

# Real MCP tools from the regulation server — these are legitimate calls, not distractors
REGULATION_MCP_TOOLS = {
    "search_regulations", "get_regulation_context", "lookup_regulation_articles",
    "analyze_document", "get_database_stats",
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


def compute_tool_metrics(
    result: ScenarioResult,
    expected_tools: set[str],
    num_distractors: int,
) -> DistractorResult:
    """Compute deterministic tool selection metrics from a scenario result.

    Only distractor tool calls count as errors. Calls to other real MCP tools
    (e.g. lookup_regulation_articles) are ignored — they're legitimate tools
    the model can reasonably use.
    """
    # Classify each tool call (exclude transfer_to_* handoff tools)
    called_names = [
        tc.name
        for tc in result.tool_calls
        if not tc.name.startswith("transfer_to_")
    ]

    expected_called = [n for n in called_names if n in expected_tools]
    distractor_called = [n for n in called_names if n in DISTRACTOR_TOOL_NAMES]
    other_called = [
        n
        for n in called_names
        if n not in expected_tools
        and n not in DISTRACTOR_TOOL_NAMES
        and n not in REGULATION_MCP_TOOLS
    ]

    # For metrics, only consider expected tools and distractor tools.
    # Real MCP tools (lookup_regulation_articles etc.) are excluded — they're
    # legitimate calls, not errors.
    called_set = set(called_names)
    relevant_called = called_set & (expected_tools | DISTRACTOR_TOOL_NAMES)

    correct = len(relevant_called & expected_tools)
    wrong = len(relevant_called & DISTRACTOR_TOOL_NAMES)
    total_relevant = len(relevant_called)

    # Precision: of tools called that are either expected or distractor,
    # what fraction were expected? (ignores real MCP tools)
    precision = correct / total_relevant if total_relevant > 0 else 1.0

    # Recall: of expected tools, what fraction were called?
    recall = correct / len(expected_tools) if expected_tools else 1.0

    # F1
    f1 = (
        (2 * precision * recall / (precision + recall))
        if (precision + recall) > 0
        else 0.0
    )

    return DistractorResult(
        model_id=result.model_id,
        num_distractors=num_distractors,
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


# ─── WebSocket Benchmark Runner ──────────────────────────────────────────────


async def run_scenario(
    scenario: dict,
    model_id: str,
    run_number: int,
    user_id: str,
    timeout: int = 180,
) -> ScenarioResult:
    """Connect to server, send a prompt, collect AG-UI events, measure timing."""
    import websockets

    result = ScenarioResult(
        model_id=model_id,
        scenario_id=scenario["id"],
        prompt=scenario["prompt"],
        run_number=run_number,
    )
    thread_id = f"bench_{uuid.uuid4().hex[:12]}"
    run_id = str(uuid.uuid4())

    message = json.dumps(
        {
            "threadId": thread_id,
            "runId": run_id,
            "userId": user_id,
            "messages": [{"role": "user", "content": scenario["prompt"]}],
        }
    )

    try:
        async with websockets.connect(WS_URL, close_timeout=10) as ws:
            start = time.monotonic()
            await ws.send(message)

            tool_calls_in_progress: dict[str, ToolCallRecord] = {}
            first_token_recorded = False
            response_end_recorded = False

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    result.error = f"Timeout after {timeout}s waiting for events"
                    result.total_ms = (time.monotonic() - start) * 1000
                    break

                event = json.loads(raw)
                etype = event.get("type", "")

                # ── Text streaming ──
                if etype == "TEXT_MESSAGE_CONTENT":
                    if not first_token_recorded:
                        result.ttft_ms = (time.monotonic() - start) * 1000
                        first_token_recorded = True
                    result.response_text += event.get("delta", "")

                elif etype == "TEXT_MESSAGE_END":
                    if not response_end_recorded:
                        result.response_ms = (time.monotonic() - start) * 1000
                        response_end_recorded = True

                # ── Agent routing ──
                elif etype == "STATE_SNAPSHOT":
                    snapshot = event.get("snapshot", {})
                    agent = snapshot.get("currentAgent") or snapshot.get(
                        "current_agent"
                    )
                    if agent and agent not in result.agents_seen:
                        result.agents_seen.append(agent)

                # ── Tool calls ──
                elif etype == "TOOL_CALL_START":
                    tc_id = event.get("toolCallId", "")
                    tool_calls_in_progress[tc_id] = ToolCallRecord(
                        name=event.get("toolCallName", "unknown"),
                    )

                elif etype == "TOOL_CALL_ARGS":
                    tc_id = event.get("toolCallId", "")
                    if tc_id in tool_calls_in_progress:
                        tool_calls_in_progress[tc_id].args += event.get("delta", "")

                elif etype == "TOOL_CALL_RESULT":
                    tc_id = event.get("toolCallId", "")
                    if tc_id in tool_calls_in_progress:
                        tool_calls_in_progress[tc_id].result = event.get("content", "")[
                            :500
                        ]
                        result.tool_calls.append(tool_calls_in_progress.pop(tc_id))

                # ── Lifecycle ──
                elif etype == "RUN_FINISHED":
                    result.total_ms = (time.monotonic() - start) * 1000
                    break

                elif etype == "RUN_ERROR":
                    result.error = event.get("message", "Unknown RUN_ERROR")
                    result.total_ms = (time.monotonic() - start) * 1000
                    # Don't break — RUN_FINISHED should follow

    except Exception as e:
        result.error = str(e)

    return result


# ─── Server Lifecycle ─────────────────────────────────────────────────────────


MCP_REGULATION_ONLY = "regulation=http://localhost:5002"


def build_server_env(
    model_config: dict,
    num_distractors: int = 0,
    regulation_only: bool = False,
) -> dict[str, str]:
    """Build environment variables for a server-langgraph subprocess."""
    env = os.environ.copy()

    # Main model
    env["LANGGRAPH_OPENAI_API_KEY"] = model_config["api_key"]
    env["LANGGRAPH_OPENAI_BASE_URL"] = model_config["base_url"]
    env["LANGGRAPH_OPENAI_MODEL"] = model_config["model"]

    # Spoken model: always use gpt-4o-mini via OpenAI for consistency
    env["LANGGRAPH_SPOKEN_MODEL"] = "gpt-4o-mini"
    env["LANGGRAPH_SPOKEN_BASE_URL"] = "https://api.openai.com/v1"
    env["LANGGRAPH_SPOKEN_API_KEY"] = OPENAI_API_KEY

    # MCP servers
    env["LANGGRAPH_MCP_SERVERS"] = MCP_REGULATION_ONLY if regulation_only else MCP_SERVERS

    # Isolated DB per model
    db_path = str(RESULTS_DIR / f"{model_config['id']}_sessions.db")
    env["LANGGRAPH_SESSIONS_DB_PATH"] = db_path

    # Disable guardrails for benchmarking
    env["LANGGRAPH_GUARDRAILS_ENABLED"] = "false"

    env["LANGGRAPH_HOST"] = SERVER_HOST
    env["LANGGRAPH_PORT"] = str(SERVER_PORT)
    env["LANGGRAPH_LOG_LEVEL"] = "WARNING"
    env["LANGGRAPH_RELOAD"] = "false"

    # Distractor tools for scaling benchmark
    if num_distractors > 0:
        env["LANGGRAPH_DISTRACTOR_TOOLS"] = str(num_distractors)

    return env


def start_server(
    model_config: dict,
    num_distractors: int = 0,
    regulation_only: bool = False,
) -> subprocess.Popen:
    """Start server-langgraph as a subprocess with the given model config."""
    env = build_server_env(
        model_config,
        num_distractors=num_distractors,
        regulation_only=regulation_only,
    )

    # Clean up any leftover DB files to avoid "database is locked"
    db_path = Path(env["LANGGRAPH_SESSIONS_DB_PATH"])
    for suffix in ["", "-wal", "-shm"]:
        p = db_path.parent / (db_path.name + suffix)
        p.unlink(missing_ok=True)

    # Use the server-langgraph venv Python to ensure source edits are picked up
    venv_python = SERVER_DIR / ".venv" / "bin" / "python"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    if num_distractors > 0:
        wrapper = str(Path(__file__).resolve().parent / "server_wrapper.py")
        cmd = [python_exe, wrapper]
    else:
        cmd = [python_exe, "-m", "agora_langgraph.api.server"]

    proc = subprocess.Popen(
        cmd,
        cwd=str(SERVER_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def stop_server(proc: subprocess.Popen, timeout: int = 10) -> None:
    """Gracefully stop the server subprocess and wait for port release."""
    if proc.poll() is not None:
        return
    # SIGINT triggers uvicorn's graceful shutdown (runs lifespan cleanup)
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

    # Wait for port to be released
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(HEALTH_URL, timeout=1)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
            return  # Port is free
        time.sleep(0.5)


def wait_for_health(timeout: int = 90, interval: float = 2.0) -> bool:
    """Poll /health until the server is ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(HEALTH_URL, timeout=5)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(interval)
    return False


def create_test_user() -> str:
    """Create a benchmark user, return the user ID."""
    try:
        resp = httpx.post(
            USERS_URL,
            json={
                "email": "benchmark@agora.test",
                "name": "Benchmark User",
                "role": "inspector",
            },
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json()["user"]["id"]
        # 409 = already exists, try listing
        if resp.status_code == 409:
            resp = httpx.get(USERS_URL, timeout=10)
            for u in resp.json().get("users", []):
                if u.get("email") == "benchmark@agora.test":
                    return u["id"]
    except Exception as e:
        logger.warning(f"Could not create test user: {e}")
    return str(uuid.uuid4())


# ─── Pre-flight Checks ───────────────────────────────────────────────────────


def preflight_checks(skip_scoring: bool) -> None:
    """Verify prerequisites before running the benchmark."""
    print("\n=== Pre-flight Checks ===\n")

    # API keys
    if not OPENAI_API_KEY:
        print(
            "  FAIL  No OpenAI API key found (LANGGRAPH_OPENAI_API_KEY or OPENAI_API_KEY)"
        )
        sys.exit(1)
    print("  OK    OpenAI API key found")

    if not HF_API_KEY:
        print("  WARN  No HuggingFace API key (HF_TOKEN or LANGGRAPH_SPOKEN_API_KEY)")
        print("        Open-source models via HF Router will be skipped")
    else:
        print("  OK    HuggingFace API key found")

    if not skip_scoring:
        if not ANTHROPIC_API_KEY:
            print("  FAIL  No ANTHROPIC_API_KEY set (needed for scoring)")
            print(
                "        Run with --skip-scoring to skip, or export ANTHROPIC_API_KEY"
            )
            sys.exit(1)
        print("  OK    Anthropic API key found")
    else:
        print("  SKIP  Scoring disabled (--skip-scoring)")

    # MCP servers
    all_ok = True
    for name, url in MCP_HEALTH_URLS.items():
        try:
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                print(f"  OK    MCP {name} server")
            else:
                print(f"  FAIL  MCP {name} returned {resp.status_code}")
                all_ok = False
        except Exception:
            print(f"  FAIL  MCP {name} not reachable at {url}")
            all_ok = False

    if not all_ok:
        print("\n  Start MCP servers: cd mcp-servers && docker-compose up -d")
        sys.exit(1)

    print()


# ─── Pairwise Claude Scoring ─────────────────────────────────────────────────

PAIRWISE_PROMPT = """\
You are a strict judge comparing two AI agent responses in the AGORA system — \
a Dutch food inspection compliance platform for NVWA inspectors.

You MUST pick a winner for each dimension. Only use "TIE" if the responses are \
truly indistinguishable on that dimension. Avoid ties — find the difference.

## Important formatting rules
- Responses should be natural, flowing prose — NOT tables or markdown grids. \
Penalize responses that use ASCII/markdown tables instead of well-written paragraphs.
- Emojis are acceptable if used sparingly and appropriately.
- Prefer clear, readable text over heavy formatting (bold, headers, bullet lists are fine).

## Scenario
{description}

## User Prompt
{prompt}

## Expected Behavior
- Expected specialist agent: {expected_agent}
- Expected tool calls: {expected_tools}

## Response A
- Agents activated: {agents_a}
- Tool calls made: {tools_a}
- Response text:
{text_a}

## Response B
- Agents activated: {agents_b}
- Tool calls made: {tools_b}
- Response text:
{text_b}

For each dimension, pick "A", "B", or "TIE":

1. **tool_usage**: Which called the correct tools with better arguments? Penalize redundant/duplicate tool calls — calling a tool more times than needed is worse, not better.
2. **agent_routing**: Which routed to the correct specialist more efficiently?
3. **answer_quality**: Which is more complete, accurate, and actionable for an NVWA inspector? Penalize table-heavy responses.
4. **language_quality**: Which has better professional Dutch suitable for government compliance?

Respond with ONLY this JSON:
{{"tool_usage": "<A|B|TIE>", "agent_routing": "<A|B|TIE>", "answer_quality": "<A|B|TIE>", "language_quality": "<A|B|TIE>", "reasoning": "<brief explanation>"}}
"""


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from text."""
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    brace_depth = 0
    json_end = len(text)
    for i, ch in enumerate(text):
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0:
                json_end = i + 1
                break
    return json.loads(text[:json_end])


def compare_pair_with_claude(
    result_a: ScenarioResult,
    result_b: ScenarioResult,
    scenario: dict,
) -> PairwiseComparison:
    """Compare two model responses head-to-head using Claude."""
    import random

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Randomize presentation order to avoid position bias
    swap = random.random() > 0.5
    first, second = (result_b, result_a) if swap else (result_a, result_b)

    prompt = PAIRWISE_PROMPT.format(
        description=scenario["description"],
        prompt=scenario["prompt"],
        expected_agent=scenario["expected_agent"],
        expected_tools=", ".join(scenario["expected_tools"]) or "(none)",
        agents_a=", ".join(first.agents_seen) or "(none)",
        tools_a=", ".join(tc.name for tc in first.tool_calls) or "(none)",
        text_a=first.response_text or "(empty)",
        agents_b=", ".join(second.agents_seen) or "(none)",
        tools_b=", ".join(tc.name for tc in second.tool_calls) or "(none)",
        text_b=second.response_text or "(empty)",
    )

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "{"},
            ],
        )
        result = _extract_json("{" + resp.content[0].text.strip())
    except Exception as e:
        logger.warning(f"Pairwise scoring failed: {e}")
        return PairwiseComparison(
            scenario_id=result_a.scenario_id,
            model_a=result_a.model_id,
            model_b=result_b.model_id,
            reasoning=f"Error: {e}",
        )

    def map_winner(val: str) -> str:
        v = val.strip().upper()
        if v == "A":
            return first.model_id
        elif v == "B":
            return second.model_id
        return "tie"

    return PairwiseComparison(
        scenario_id=result_a.scenario_id,
        model_a=result_a.model_id,
        model_b=result_b.model_id,
        winner_tools=map_winner(result.get("tool_usage", "TIE")),
        winner_routing=map_winner(result.get("agent_routing", "TIE")),
        winner_quality=map_winner(result.get("answer_quality", "TIE")),
        winner_language=map_winner(result.get("language_quality", "TIE")),
        reasoning=result.get("reasoning", ""),
    )


def tally_comparisons(
    comparisons: list[PairwiseComparison],
    model_ids: list[str],
) -> dict[str, dict[str, int]]:
    """Tally pairwise wins into per-model scores."""
    scores: dict[str, dict[str, int]] = {}
    for mid in model_ids:
        scores[mid] = {
            "wins": 0,
            "ties": 0,
            "losses": 0,
            "tools_w": 0,
            "routing_w": 0,
            "quality_w": 0,
            "language_w": 0,
        }

    dim_map = [
        ("winner_tools", "tools_w"),
        ("winner_routing", "routing_w"),
        ("winner_quality", "quality_w"),
        ("winner_language", "language_w"),
    ]
    for c in comparisons:
        for attr, key in dim_map:
            winner = getattr(c, attr)
            if winner == c.model_a:
                scores[c.model_a][key] += 1
                scores[c.model_a]["wins"] += 1
                scores[c.model_b]["losses"] += 1
            elif winner == c.model_b:
                scores[c.model_b][key] += 1
                scores[c.model_b]["wins"] += 1
                scores[c.model_a]["losses"] += 1
            else:
                scores[c.model_a]["ties"] += 1
                scores[c.model_b]["ties"] += 1

    return scores


# ─── Results Output ──────────────────────────────────────────────────────────


def save_raw_results(all_results: dict[str, list[ScenarioResult]]) -> Path:
    """Save raw results as JSON."""
    path = RESULTS_DIR / "raw_results.json"
    data = {}
    for model_id, results in all_results.items():
        data[model_id] = [_result_to_dict(r) for r in results]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def save_pairwise_results(comparisons: list[PairwiseComparison]) -> Path:
    """Save pairwise comparison results as JSON."""
    path = RESULTS_DIR / "pairwise_results.json"
    data = [asdict(c) for c in comparisons]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def _result_to_dict(r: ScenarioResult) -> dict:
    d = asdict(r)
    d["tool_calls"] = [asdict(tc) for tc in r.tool_calls]
    return d


def print_timing_table(all_results: dict[str, list[ScenarioResult]]) -> None:
    """Print per-scenario timing and tool/agent results."""
    from tabulate import tabulate

    print("\n" + "=" * 100)
    print("TIMING & TOOL RESULTS")
    print("=" * 100)

    headers = [
        "Model",
        "Scenario",
        "TTFT (ms)",
        "Response (ms)",
        "Total (ms)",
        "Tools Called",
        "Final Agent",
        "Error?",
    ]
    rows = []

    for model_id, results in all_results.items():
        for r in results:
            tools_str = ", ".join(tc.name for tc in r.tool_calls) or "-"
            agent_str = r.agents_seen[-1] if r.agents_seen else "-"
            rows.append(
                [
                    model_id,
                    r.scenario_id,
                    f"{r.ttft_ms:.0f}" if r.ttft_ms else "-",
                    f"{r.response_ms:.0f}" if r.response_ms else "-",
                    f"{r.total_ms:.0f}" if r.total_ms else "-",
                    tools_str,
                    agent_str,
                    r.error[:30] if r.error else "",
                ]
            )

    print(tabulate(rows, headers=headers, tablefmt="grid"))


def print_ranking_table(
    tally: dict[str, dict[str, int]],
    all_results: dict[str, list[ScenarioResult]],
) -> None:
    """Print model rankings based on pairwise wins."""
    from tabulate import tabulate

    print("\n" + "=" * 100)
    print("RANKINGS (pairwise head-to-head)")
    print("=" * 100)

    headers = [
        "Rank",
        "Model",
        "Win%",
        "W",
        "T",
        "L",
        "Avg TTFT",
        "Avg Total",
        "Tools W",
        "Route W",
        "Quality W",
        "Lang W",
    ]
    rows = []

    ranked = sorted(
        tally.items(),
        key=lambda x: (x[1]["wins"], x[1]["ties"]),
        reverse=True,
    )

    for rank, (model_id, s) in enumerate(ranked, 1):
        total = s["wins"] + s["ties"] + s["losses"]
        win_rate = (s["wins"] + 0.5 * s["ties"]) / total * 100 if total else 0

        results = all_results.get(model_id, [])
        successful = [r for r in results if not r.error]
        ttft_vals = [r.ttft_ms for r in successful if r.ttft_ms is not None]
        total_vals = [r.total_ms for r in successful if r.total_ms is not None]
        avg_ttft = f"{sum(ttft_vals)/len(ttft_vals):.0f}" if ttft_vals else "-"
        avg_total = f"{sum(total_vals)/len(total_vals):.0f}" if total_vals else "-"

        rows.append(
            [
                rank,
                model_id,
                f"{win_rate:.0f}%",
                s["wins"],
                s["ties"],
                s["losses"],
                avg_ttft,
                avg_total,
                s["tools_w"],
                s["routing_w"],
                s["quality_w"],
                s["language_w"],
            ]
        )

    print(tabulate(rows, headers=headers, tablefmt="grid"))


def print_h2h_matrix(
    comparisons: list[PairwiseComparison],
    model_ids: list[str],
) -> None:
    """Print head-to-head win matrix (total dimension wins across all scenarios)."""
    from tabulate import tabulate

    print("\n" + "=" * 100)
    print("HEAD-TO-HEAD (dimension wins: row vs column)")
    print("=" * 100)

    matrix: dict[str, dict[str, int]] = {
        a: {b: 0 for b in model_ids} for a in model_ids
    }

    for c in comparisons:
        for attr in [
            "winner_tools",
            "winner_routing",
            "winner_quality",
            "winner_language",
        ]:
            winner = getattr(c, attr)
            if winner == c.model_a:
                matrix[c.model_a][c.model_b] += 1
            elif winner == c.model_b:
                matrix[c.model_b][c.model_a] += 1

    headers = ["Model"] + model_ids
    rows = []
    for mid in model_ids:
        row: list[str] = [mid]
        for other in model_ids:
            if mid == other:
                row.append("-")
            else:
                row.append(str(matrix[mid][other]))
        rows.append(row)

    print(tabulate(rows, headers=headers, tablefmt="grid"))


def save_markdown_report(
    all_results: dict[str, list[ScenarioResult]],
    comparisons: list[PairwiseComparison] | None = None,
    tally: dict[str, dict[str, int]] | None = None,
) -> Path:
    """Save results as a markdown file."""
    from tabulate import tabulate

    path = RESULTS_DIR / "benchmark_report.md"
    lines = [
        "# AGORA Model Benchmark Report",
        f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Server**: server-langgraph",
        f"**Scoring**: Pairwise head-to-head (Claude judge)",
        f"**Scenarios**: {len(SCENARIOS)}",
        f"**Models**: {len(all_results)}",
        "",
    ]

    # Rankings
    if tally:
        lines.append("## Rankings\n")
        ranked = sorted(
            tally.items(), key=lambda x: (x[1]["wins"], x[1]["ties"]), reverse=True
        )
        headers = [
            "Rank",
            "Model",
            "Win%",
            "W",
            "T",
            "L",
            "Tools W",
            "Route W",
            "Quality W",
            "Lang W",
        ]
        rows = []
        for rank, (model_id, s) in enumerate(ranked, 1):
            total = s["wins"] + s["ties"] + s["losses"]
            win_rate = (s["wins"] + 0.5 * s["ties"]) / total * 100 if total else 0
            rows.append(
                [
                    rank,
                    model_id,
                    f"{win_rate:.0f}%",
                    s["wins"],
                    s["ties"],
                    s["losses"],
                    s["tools_w"],
                    s["routing_w"],
                    s["quality_w"],
                    s["language_w"],
                ]
            )
        lines.append(tabulate(rows, headers=headers, tablefmt="github"))

    # Timing
    lines.append("\n\n## Timing\n")
    headers = ["Model", "Avg TTFT (ms)", "Avg Response (ms)", "Avg Total (ms)"]
    rows = []
    for model_id, results in all_results.items():
        successful = [r for r in results if not r.error]

        def avg(vals):
            nums = [v for v in vals if v is not None]
            return f"{sum(nums)/len(nums):.0f}" if nums else "-"

        rows.append(
            [
                model_id,
                avg([r.ttft_ms for r in successful]),
                avg([r.response_ms for r in successful]),
                avg([r.total_ms for r in successful]),
            ]
        )
    lines.append(tabulate(rows, headers=headers, tablefmt="github"))

    # Head-to-head details
    if comparisons:
        lines.append("\n\n## Head-to-Head Results\n")
        for scenario in SCENARIOS:
            lines.append(f"\n### {scenario['id']}\n")
            lines.append(f"**Prompt**: {scenario['prompt']}\n")
            for c in comparisons:
                if c.scenario_id != scenario["id"]:
                    continue
                lines.append(
                    f"**{c.model_a} vs {c.model_b}**: "
                    f"tools={c.winner_tools}, routing={c.winner_routing}, "
                    f"quality={c.winner_quality}, language={c.winner_language} "
                    f"— {c.reasoning}"
                )

    # Response samples
    lines.append("\n\n## Response Samples\n")
    for model_id, results in all_results.items():
        lines.append(f"\n### {model_id}\n")
        for r in results:
            lines.append(f"**{r.scenario_id}**:")
            text = r.response_text[:500]
            if len(r.response_text) > 500:
                text += "..."
            lines.append(f"```\n{text}\n```\n")

    path.write_text("\n".join(lines))
    return path


# ─── Distractor Benchmark Runner ─────────────────────────────────────────────


async def run_distractor_benchmark(
    models_to_run: list[dict],
    distractor_counts: list[int],
    timeout: int = 180,
) -> dict[str, list[DistractorResult]]:
    """Run the regulation_query scenario at each distractor level for each model."""
    scenario = next(s for s in SCENARIOS if s["id"] == "regulation_query")
    expected_tools = set(scenario["expected_tools"])

    all_results: dict[str, list[DistractorResult]] = {}

    for model_config in models_to_run:
        model_id = model_config["id"]
        model_results: list[DistractorResult] = []

        print(f"\n{'─' * 60}")
        print(f"  Model: {model_id} ({model_config['model']})")
        print(f"  Provider: {model_config['base_url']}")
        print(f"{'─' * 60}")

        for n_distractors in distractor_counts:
            print(f"\n  Distractors: {n_distractors}")
            print(f"  Starting server...", end="", flush=True)

            proc = start_server(
                model_config,
                num_distractors=n_distractors,
                regulation_only=True,
            )

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
                {
                    "id": "warmup",
                    "prompt": "Hallo",
                    "expected_agent": "general-agent",
                    "expected_tools": [],
                },
                model_id,
                0,
                user_id,
                timeout=timeout,
            )
            if warmup.error:
                print(f" WARN: {warmup.error}")
            else:
                print(f" OK ({warmup.total_ms:.0f}ms)")

            # Run regulation_query
            print(
                f"    regulation_query (N={n_distractors})...", end="", flush=True
            )
            result = await run_scenario(
                scenario, model_id, 1, user_id, timeout=timeout
            )

            if result.error:
                print(f" ERROR: {result.error[:60]}")
            else:
                tools = [
                    tc.name
                    for tc in result.tool_calls
                    if not tc.name.startswith("transfer_to_")
                ]
                print(f" tools={tools}")

            # Compute metrics
            dr = compute_tool_metrics(result, expected_tools, n_distractors)
            model_results.append(dr)

            print(
                f"    P={dr.precision:.2f}  R={dr.recall:.2f}  F1={dr.f1:.2f}  "
                f"distractors_called={dr.distractor_tools_called}"
            )

            # Stop server
            print(f"  Stopping server...", end="", flush=True)
            stop_server(proc)
            print(" done")
            await asyncio.sleep(2)

        all_results[model_id] = model_results

    return all_results


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

    headers = [
        "Model",
        "N Distractors",
        "Precision",
        "Recall",
        "F1",
        "Distractors Called",
        "Total Time (ms)",
        "Error?",
    ]
    rows = []

    for model_id, dr_list in results.items():
        for dr in dr_list:
            rows.append(
                [
                    model_id,
                    dr.num_distractors,
                    f"{dr.precision:.2f}" if not dr.error else "-",
                    f"{dr.recall:.2f}" if not dr.error else "-",
                    f"{dr.f1:.2f}" if not dr.error else "-",
                    ", ".join(dr.distractor_tools_called) or "-",
                    f"{dr.total_ms:.0f}" if dr.total_ms else "-",
                    dr.error[:30] if dr.error else "",
                ]
            )

    print(tabulate(rows, headers=headers, tablefmt="grid"))


# ─── Main ────────────────────────────────────────────────────────────────────


async def run_model_benchmark(
    model_config: dict,
    user_id: str,
    num_runs: int = 1,
    timeout: int = 180,
) -> list[ScenarioResult]:
    """Run all scenarios for a single model (server already running)."""
    results = []

    # Warm-up: one quick request to prime the model / connection
    print(f"    Warming up...", end="", flush=True)
    warmup = await run_scenario(
        {
            "id": "warmup",
            "prompt": "Hallo",
            "expected_agent": "general-agent",
            "expected_tools": [],
        },
        model_config["id"],
        0,
        user_id,
        timeout=timeout,
    )
    if warmup.error:
        print(f" WARN: warmup error: {warmup.error}")
    else:
        print(f" OK ({warmup.total_ms:.0f}ms)")

    for scenario in SCENARIOS:
        for run in range(1, num_runs + 1):
            label = f"    {scenario['id']} (run {run}/{num_runs})..."
            print(label, end="", flush=True)

            result = await run_scenario(
                scenario, model_config["id"], run, user_id, timeout=timeout
            )

            if result.error:
                print(f" ERROR: {result.error[:60]}")
            else:
                tools = [tc.name for tc in result.tool_calls]
                ttft = f"{result.ttft_ms:.0f}ms" if result.ttft_ms else "-"
                resp = f"{result.response_ms:.0f}ms" if result.response_ms else "-"
                total = f"{result.total_ms:.0f}ms" if result.total_ms else "-"
                agent = result.agents_seen[-1] if result.agents_seen else "?"
                print(
                    f" TTFT={ttft}  resp={resp}  total={total}  tools={tools}  agent={agent}"
                )

            results.append(result)

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="AGORA Model Benchmark")
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated model IDs to benchmark",
    )
    parser.add_argument(
        "--scenarios", type=str, default=None, help="Comma-separated scenario IDs"
    )
    parser.add_argument(
        "--runs", type=int, default=1, help="Runs per scenario (default: 1)"
    )
    parser.add_argument(
        "--timeout", type=int, default=180, help="Per-scenario timeout in seconds"
    )
    parser.add_argument(
        "--skip-scoring", action="store_true", help="Skip Claude-based quality scoring"
    )
    parser.add_argument(
        "--rerun-baseline", action="store_true", help="Force re-run of baseline"
    )
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="Re-run only pairwise scoring from existing raw_results.json (no server runs)",
    )
    parser.add_argument(
        "--drop-models",
        type=str,
        default=None,
        help="Comma-separated model IDs to exclude from rescore comparison",
    )
    parser.add_argument(
        "--distractor-benchmark",
        action="store_true",
        help="Run distractor tool scaling benchmark (regulation_query only)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    # ── Rescore mode: load existing results and skip to scoring ──
    if args.rescore:
        raw_path = RESULTS_DIR / "raw_results.json"
        if not raw_path.exists():
            print(f"No raw_results.json found at {raw_path}")
            sys.exit(1)
        if not ANTHROPIC_API_KEY:
            print("ANTHROPIC_API_KEY required for scoring")
            sys.exit(1)

        print("\n=== Rescore Mode ===")
        print(f"  Loading results from {raw_path}")

        raw_data = json.loads(raw_path.read_text())
        all_results: dict[str, list[ScenarioResult]] = {}
        for model_id, entries in raw_data.items():
            results = []
            for r_data in entries:
                r = ScenarioResult(
                    **{k: v for k, v in r_data.items() if k not in ("tool_calls",)}
                )
                r.tool_calls = [
                    ToolCallRecord(**tc) for tc in r_data.get("tool_calls", [])
                ]
                results.append(r)
            all_results[model_id] = results

        # Drop models if requested
        if args.drop_models:
            drop_ids = [m.strip() for m in args.drop_models.split(",")]
            dropped = [m for m in drop_ids if m in all_results]
            unknown = [m for m in drop_ids if m not in all_results]
            for mid in dropped:
                del all_results[mid]
            if dropped:
                print(f"  Dropped: {dropped}")
            if unknown:
                print(f"  Unknown (ignored): {unknown}")
            if not all_results:
                print("No models left after dropping. Exiting.")
                sys.exit(1)

        print(f"  Models: {list(all_results.keys())}")
        print(f"  Scenarios: {sorted({r.scenario_id for rs in all_results.values() for r in rs})}")

        # Jump straight to scoring
        from itertools import combinations

        comparisons: list[PairwiseComparison] = []
        model_ids = list(all_results.keys())
        scenario_ids = sorted({r.scenario_id for rs in all_results.values() for r in rs})

        # Rebuild SCENARIOS list from what's in the data
        global SCENARIOS
        active_scenarios = [s for s in SCENARIOS if s["id"] in scenario_ids]

        print(f"\n{'=' * 60}")
        print("  Pairwise scoring with Claude...")
        print(f"{'=' * 60}")

        for scenario in active_scenarios:
            scenario_results: dict[str, ScenarioResult] = {}
            for mid, results in all_results.items():
                for r in results:
                    if r.scenario_id == scenario["id"] and not r.error:
                        scenario_results[mid] = r
                        break

            for mid_a, mid_b in combinations(scenario_results.keys(), 2):
                print(
                    f"    {scenario['id']}: {mid_a} vs {mid_b}...", end="", flush=True
                )
                comp = compare_pair_with_claude(
                    scenario_results[mid_a],
                    scenario_results[mid_b],
                    scenario,
                )
                comparisons.append(comp)
                qw = comp.winner_quality
                label = "TIE" if qw == "tie" else qw
                print(f" quality→{label}")

        tally = tally_comparisons(comparisons, model_ids)

        # Output
        print_timing_table(all_results)
        print_ranking_table(tally, all_results)
        print_h2h_matrix(comparisons, model_ids)

        md_path = save_markdown_report(all_results, comparisons, tally)
        pw_path = save_pairwise_results(comparisons)

        print(f"\n  Results saved:")
        print(f"    Pairwise JSON: {pw_path}")
        print(f"    Report:       {md_path}")
        print()
        return

    # ── Distractor benchmark mode ──
    if args.distractor_benchmark:
        # Filter models
        models_to_run = MODELS
        if args.models:
            selected = [m.strip() for m in args.models.split(",")]
            models_to_run = [m for m in MODELS if m["id"] in selected]
            if not models_to_run:
                print(f"No matching models. Available: {[m['id'] for m in MODELS]}")
                sys.exit(1)

        # Drop models if requested
        if args.drop_models:
            drop_ids = {m.strip() for m in args.drop_models.split(",")}
            models_to_run = [m for m in models_to_run if m["id"] not in drop_ids]

        # Skip models without API keys
        models_to_run = [m for m in models_to_run if m["api_key"]]

        # Preflight: only check regulation MCP (only server needed for this benchmark)
        print("\n=== Pre-flight Checks ===\n")
        if not OPENAI_API_KEY:
            print("  FAIL  No OpenAI API key found")
            sys.exit(1)
        print("  OK    OpenAI API key found")
        try:
            resp = httpx.get(MCP_HEALTH_URLS["regulation"], timeout=5)
            if resp.status_code == 200:
                print("  OK    MCP regulation server")
            else:
                print(f"  FAIL  MCP regulation returned {resp.status_code}")
                sys.exit(1)
        except Exception:
            print(f"  FAIL  MCP regulation not reachable at {MCP_HEALTH_URLS['regulation']}")
            print("        Start it: cd mcp-servers && docker-compose up -d regulation-analysis")
            sys.exit(1)
        print()

        print(f"=== Distractor Tool Scaling Benchmark ===")
        print(f"  Models:    {[m['id'] for m in models_to_run]}")
        print(f"  Scenario:  regulation_query")
        print(f"  Distractor counts: {DISTRACTOR_COUNTS}")
        print()

        distractor_results = await run_distractor_benchmark(
            models_to_run,
            DISTRACTOR_COUNTS,
            timeout=args.timeout,
        )

        print_distractor_table(distractor_results)

        path = save_distractor_results(distractor_results)
        print(f"\n  Results saved: {path}")

        # Generate plot
        try:
            from plot_results import plot_tool_scaling

            distractor_data = json.loads(path.read_text())
            plot_tool_scaling(distractor_data)
        except Exception as e:
            print(f"  Plot generation failed: {e}")
            print("  Run manually: python benchmark/plot_results.py")

        print()
        return

    # ── Normal mode ──

    # Filter models
    models_to_run = MODELS
    if args.models:
        selected = [m.strip() for m in args.models.split(",")]
        models_to_run = [m for m in MODELS if m["id"] in selected]
        if not models_to_run:
            print(f"No matching models. Available: {[m['id'] for m in MODELS]}")
            sys.exit(1)

    # Filter scenarios
    if args.scenarios:
        selected_s = [s.strip() for s in args.scenarios.split(",")]
        SCENARIOS = [s for s in SCENARIOS if s["id"] in selected_s]

    # Skip models without API keys
    models_to_run = [
        m
        for m in models_to_run
        if m["api_key"]
        or print(f"  SKIP  {m['id']} — no API key for provider") is not None
    ]
    models_to_run = [m for m in models_to_run if m["api_key"]]

    # Ensure baseline is first
    baseline_models = [m for m in models_to_run if m.get("is_baseline")]
    other_models = [m for m in models_to_run if not m.get("is_baseline")]
    models_to_run = baseline_models + other_models

    preflight_checks(args.skip_scoring)

    # Check for existing baseline
    baseline_path = RESULTS_DIR / "baseline.json"
    baseline_results: dict[str, ScenarioResult] | None = None

    if baseline_path.exists() and not args.rerun_baseline:
        print("Loading existing baseline from", baseline_path)
        baseline_data = json.loads(baseline_path.read_text())
        baseline_results = {}
        for r_data in baseline_data:
            r = ScenarioResult(**{k: v for k, v in r_data.items() if k != "tool_calls"})
            r.tool_calls = [ToolCallRecord(**tc) for tc in r_data.get("tool_calls", [])]
            baseline_results[r.scenario_id] = r
        # Remove baseline model from run list if not rerunning
        if not args.rerun_baseline:
            models_to_run = [m for m in models_to_run if not m.get("is_baseline")]

    print(f"\n=== Benchmark Plan ===")
    print(f"  Models:    {[m['id'] for m in models_to_run]}")
    print(f"  Scenarios: {[s['id'] for s in SCENARIOS]}")
    print(f"  Runs/scenario: {args.runs}")
    print(f"  Scoring: {'Claude' if not args.skip_scoring else 'disabled'}")
    print()

    # ── Run benchmarks ──
    all_results: dict[str, list[ScenarioResult]] = {}  # noqa: F811

    for model_config in models_to_run:
        model_id = model_config["id"]
        print(f"\n{'─' * 60}")
        print(f"  Model: {model_id} ({model_config['model']})")
        print(f"  Provider: {model_config['base_url']}")
        print(f"{'─' * 60}")

        # Start server
        print(f"  Starting server...", end="", flush=True)
        proc = start_server(model_config)

        if not wait_for_health(timeout=90):
            print(f" FAILED (server did not become healthy)")
            stop_server(proc)
            # Record errors for all scenarios
            all_results[model_id] = [
                ScenarioResult(
                    model_id=model_id,
                    scenario_id=s["id"],
                    prompt=s["prompt"],
                    run_number=1,
                    error="Server failed to start",
                )
                for s in SCENARIOS
            ]
            continue

        print(f" OK (healthy)")

        # Create test user
        user_id = create_test_user()

        # Run scenarios
        results = await run_model_benchmark(
            model_config, user_id, num_runs=args.runs, timeout=args.timeout
        )
        all_results[model_id] = results

        # Save baseline
        if model_config.get("is_baseline"):
            baseline_results = {}
            for r in results:
                if r.scenario_id not in baseline_results or not r.error:
                    baseline_results[r.scenario_id] = r
            baseline_data = [_result_to_dict(r) for r in baseline_results.values()]
            baseline_path.write_text(
                json.dumps(baseline_data, indent=2, ensure_ascii=False)
            )
            print(f"\n  Baseline saved to {baseline_path}")

        # Stop server
        print(f"  Stopping server...", end="", flush=True)
        stop_server(proc)
        print(" done")

        # Brief pause for port release
        await asyncio.sleep(2)

    # ── Add baseline to results for display (if loaded from file) ──
    if baseline_results and not any(
        m.get("is_baseline") and m["id"] in all_results for m in MODELS
    ):
        baseline_model_id = next(
            (m["id"] for m in MODELS if m.get("is_baseline")), "gpt-4o"
        )
        all_results = {
            baseline_model_id: list(baseline_results.values()),
            **all_results,
        }

    # ── Pairwise scoring with Claude ──
    comparisons: list[PairwiseComparison] = []
    tally: dict[str, dict[str, int]] = {}

    if not args.skip_scoring and len(all_results) >= 2:
        from itertools import combinations

        print(f"\n{'=' * 60}")
        print("  Pairwise scoring with Claude...")
        print(f"{'=' * 60}")

        model_ids = list(all_results.keys())

        for scenario in SCENARIOS:
            # Collect best result per model for this scenario
            scenario_results: dict[str, ScenarioResult] = {}
            for model_id, results in all_results.items():
                for r in results:
                    if r.scenario_id == scenario["id"] and not r.error:
                        scenario_results[model_id] = r
                        break

            for mid_a, mid_b in combinations(scenario_results.keys(), 2):
                print(
                    f"    {scenario['id']}: {mid_a} vs {mid_b}...", end="", flush=True
                )
                comp = compare_pair_with_claude(
                    scenario_results[mid_a],
                    scenario_results[mid_b],
                    scenario,
                )
                comparisons.append(comp)
                # Show quality winner
                qw = comp.winner_quality
                label = "TIE" if qw == "tie" else qw
                print(f" quality→{label}")

        tally = tally_comparisons(comparisons, model_ids)

    # ── Output ──
    print_timing_table(all_results)
    if tally:
        print_ranking_table(tally, all_results)
        print_h2h_matrix(comparisons, list(all_results.keys()))

    raw_path = save_raw_results(all_results)
    md_path = save_markdown_report(all_results, comparisons, tally)
    if comparisons:
        pw_path = save_pairwise_results(comparisons)

    print(f"\n  Results saved:")
    print(f"    Raw JSON:     {raw_path}")
    if comparisons:
        print(f"    Pairwise JSON: {pw_path}")
    print(f"    Report:       {md_path}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
