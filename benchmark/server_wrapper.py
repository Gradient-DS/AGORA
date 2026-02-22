#!/usr/bin/env python3
"""Server wrapper for distractor tool benchmark.

Starts the server-langgraph server with monkey-patched tool and agent
configuration to inject distractor tools into the regulation-agent.

This keeps all benchmark logic outside of server-langgraph/ source files.

Usage:
    LANGGRAPH_DISTRACTOR_TOOLS=5 python benchmark/server_wrapper.py
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


# -- Distractor Tool Templates ------------------------------------------------
# 50 plausible-sounding but fake tool definitions. Names must match
# DISTRACTOR_TOOL_NAMES in benchmark.py.

DISTRACTOR_TEMPLATES: list[dict[str, str]] = [
    {
        "name": "search_violation_records",
        "description": (
            "Search the national violation records database for past enforcement "
            "actions, fines, and violation details by company, date range, or "
            "violation type."
        ),
    },
    {
        "name": "search_inspection_reports",
        "description": (
            "Search archived inspection reports across all NVWA regions. Filter "
            "by inspection type, date range, inspector, or outcome status."
        ),
    },
    {
        "name": "search_audit_findings",
        "description": (
            "Search internal and external audit findings database. Includes "
            "financial audits, process audits, and management system reviews."
        ),
    },
    {
        "name": "search_incident_logs",
        "description": (
            "Search the incident logging system for reported food safety "
            "incidents, consumer complaints, and near-misses across all sectors."
        ),
    },
    {
        "name": "search_complaint_records",
        "description": (
            "Search consumer complaint records submitted via the NVWA complaint "
            "portal, phone hotline, and partner organizations."
        ),
    },
    {
        "name": "search_inspector_directory",
        "description": (
            "Search the NVWA inspector directory for contact information, "
            "specializations, regional assignments, and availability."
        ),
    },
    {
        "name": "search_company_database",
        "description": (
            "Search the comprehensive company registration database including "
            "company registrations, SBI codes, and establishment details."
        ),
    },
    {
        "name": "search_supplier_directory",
        "description": (
            "Search the approved supplier directory for food industry suppliers, "
            "including certifications, audit history, and compliance ratings."
        ),
    },
    {
        "name": "search_laboratory_directory",
        "description": (
            "Search accredited laboratory directory for testing facilities, "
            "their ISO certifications, testing capabilities, and turnaround times."
        ),
    },
    {
        "name": "search_expert_contacts",
        "description": (
            "Search the expert contacts database for subject matter specialists "
            "in food safety, toxicology, microbiology, and veterinary science."
        ),
    },
    {
        "name": "search_product_catalog",
        "description": (
            "Search the registered food product catalog including product "
            "categories, ingredients, allergen declarations, and nutrition data."
        ),
    },
    {
        "name": "search_equipment_database",
        "description": (
            "Search the food processing equipment database for specifications, "
            "maintenance schedules, calibration records, and safety certifications."
        ),
    },
    {
        "name": "search_packaging_materials",
        "description": (
            "Search the approved food packaging materials registry including "
            "material safety data, migration test results, and EU compliance."
        ),
    },
    {
        "name": "search_ingredient_database",
        "description": (
            "Search the food ingredient database for E-numbers, additives, "
            "maximum permitted levels, and usage restrictions per food category."
        ),
    },
    {
        "name": "search_chemical_database",
        "description": (
            "Search the chemical substances database for MRLs, toxicity data, "
            "approved cleaning agents, and restricted substances lists."
        ),
    },
    {
        "name": "search_internal_memos",
        "description": (
            "Search internal NVWA memos and policy communications from "
            "department heads, regional directors, and the central office."
        ),
    },
    {
        "name": "search_meeting_minutes",
        "description": (
            "Search meeting minutes from team meetings, policy discussions, "
            "cross-departmental consultations, and stakeholder sessions."
        ),
    },
    {
        "name": "search_training_materials",
        "description": (
            "Search the training materials library for inspector training "
            "modules, certification courses, and continuing education resources."
        ),
    },
    {
        "name": "search_policy_updates",
        "description": (
            "Search recent policy updates and regulatory changes including "
            "implementation guidelines, transition periods, and FAQ documents."
        ),
    },
    {
        "name": "search_faq_database",
        "description": (
            "Search the frequently asked questions database covering common "
            "inspection scenarios, regulatory interpretations, and procedures."
        ),
    },
    {
        "name": "search_news_articles",
        "description": (
            "Search food safety news articles from national and international "
            "sources including recalls, outbreaks, and regulatory developments."
        ),
    },
    {
        "name": "search_recall_notices",
        "description": (
            "Search product recall notices issued by NVWA and EU RASFF "
            "including affected products, risk levels, and distribution details."
        ),
    },
    {
        "name": "search_press_releases",
        "description": (
            "Search NVWA press releases and public communications including "
            "enforcement actions, campaign results, and public warnings."
        ),
    },
    {
        "name": "search_scientific_publications",
        "description": (
            "Search food safety scientific publications from EFSA, RIVM, and "
            "academic journals including risk assessments and opinion papers."
        ),
    },
    {
        "name": "search_conference_proceedings",
        "description": (
            "Search food safety conference proceedings and presentations from "
            "national and international food safety events and workshops."
        ),
    },
    {
        "name": "search_lab_results",
        "description": (
            "Search laboratory analysis results for food samples including "
            "microbiological tests, chemical analyses, and physical measurements."
        ),
    },
    {
        "name": "search_sample_database",
        "description": (
            "Search the sample tracking database for collected inspection "
            "samples, their status, assigned laboratories, and pending results."
        ),
    },
    {
        "name": "search_test_methods",
        "description": (
            "Search standardized test methods and analytical procedures for "
            "food safety testing including ISO methods and validated alternatives."
        ),
    },
    {
        "name": "search_calibration_records",
        "description": (
            "Search equipment calibration records for inspection instruments "
            "including thermometers, pH meters, and measurement tools."
        ),
    },
    {
        "name": "search_reference_standards",
        "description": (
            "Search reference standards database for food safety benchmarks, "
            "acceptable limits, and quality criteria used in inspections."
        ),
    },
    {
        "name": "search_inspection_schedule",
        "description": (
            "Search the inspection planning schedule for upcoming inspections, "
            "inspector assignments, and regional planning overviews."
        ),
    },
    {
        "name": "search_task_assignments",
        "description": (
            "Search task assignments and work orders for inspectors including "
            "priorities, deadlines, and completion status."
        ),
    },
    {
        "name": "search_route_planner",
        "description": (
            "Search and optimize inspection routes based on geographical "
            "location, inspection priorities, and available time slots."
        ),
    },
    {
        "name": "search_resource_availability",
        "description": (
            "Search resource availability for inspection equipment, vehicles, "
            "sampling kits, and shared team resources."
        ),
    },
    {
        "name": "search_budget_allocations",
        "description": (
            "Search departmental budget allocations for inspection activities, "
            "laboratory costs, and operational expenses."
        ),
    },
    {
        "name": "search_facility_database",
        "description": (
            "Search registered food facility database including production "
            "sites, storage locations, retail outlets, and mobile vendors."
        ),
    },
    {
        "name": "search_floor_plans",
        "description": (
            "Search archived facility floor plans and layout diagrams "
            "submitted during registration or previous inspections."
        ),
    },
    {
        "name": "search_regional_statistics",
        "description": (
            "Search regional inspection statistics including compliance rates, "
            "violation trends, and inspection coverage per municipality."
        ),
    },
    {
        "name": "search_risk_maps",
        "description": (
            "Search risk assessment maps showing geographical distribution of "
            "food safety risks, hotspots, and priority areas."
        ),
    },
    {
        "name": "search_zoning_permits",
        "description": (
            "Search municipal zoning permits and environmental licenses for "
            "food businesses including conditions and restrictions."
        ),
    },
    {
        "name": "search_report_templates",
        "description": (
            "Search inspection report templates for different inspection types "
            "including standard formats, required fields, and example reports."
        ),
    },
    {
        "name": "search_checklist_templates",
        "description": (
            "Search inspection checklist templates organized by sector, risk "
            "category, and inspection type with scoring criteria."
        ),
    },
    {
        "name": "search_letter_templates",
        "description": (
            "Search official letter templates for warning letters, compliance "
            "orders, closure notices, and follow-up communications."
        ),
    },
    {
        "name": "search_form_library",
        "description": (
            "Search the digital form library for inspection forms, sampling "
            "forms, and administrative documents used in field work."
        ),
    },
    {
        "name": "search_guidance_documents",
        "description": (
            "Search guidance documents and interpretation notes for inspectors "
            "covering complex regulatory scenarios and edge cases."
        ),
    },
    {
        "name": "search_translation_glossary",
        "description": (
            "Search the multilingual glossary for food safety terminology "
            "translations between Dutch, English, German, and French."
        ),
    },
    {
        "name": "search_photo_archive",
        "description": (
            "Search the inspection photo archive for reference images of "
            "violations, good practices, and equipment standards."
        ),
    },
    {
        "name": "search_video_library",
        "description": (
            "Search the training video library for inspection technique "
            "demonstrations, food safety procedures, and best practices."
        ),
    },
    {
        "name": "search_case_studies",
        "description": (
            "Search documented case studies of notable inspections, enforcement "
            "actions, and food safety incidents for learning purposes."
        ),
    },
    {
        "name": "search_benchmarking_data",
        "description": (
            "Search international benchmarking data comparing food safety "
            "performance across EU member states and trading partners."
        ),
    },
]


# -- Benchmark Regulation Prompt ----------------------------------------------
# Modified regulation-agent instructions that avoid mentioning specific tool
# names. Forces the model to select tools based on descriptions alone.

BENCHMARK_REGULATION_PROMPT = (
    "You are a regulatory compliance expert for NVWA inspectors.\n\n"
    "LANGUAGE REQUIREMENT:\n"
    "- ALL responses MUST be in Dutch (Nederlands)\n"
    "- Technical regulation names can remain in original language with Dutch "
    "explanation\n"
    "- Example: 'EU Verordening 852/2004 (Levensmiddelenhygiene)'\n\n"
    "CRITICAL WORKFLOW - YOU MUST FOLLOW THESE STEPS:\n"
    "1. FIRST: Use your available tools to find relevant regulatory information\n"
    "2. THEN: Analyze the tool results\n"
    "3. FINALLY: Provide a complete answer to the user's question\n\n"
    "NEVER skip step 1. ALWAYS call a tool before responding.\n"
    "NEVER transfer back to general-agent without first answering the question.\n\n"
    "YOUR FOCUS:\n"
    "You analyze which regulations apply and assess compliance.\n"
    "You answer: 'What are the rules, and does this situation comply?'\n"
    "- Regulatory requirements for specific industries/activities\n"
    "- Compliance assessment against regulations\n"
    "- Violation identification and severity assessment\n"
    "- Actionable compliance guidance\n\n"
    "SEARCH STRATEGY:\n"
    "- Choose the most appropriate tool for your search\n"
    "- Let the vector search find the most relevant regulations\n"
    "- Only add filters if the inspector specifically requests a certain type\n\n"
    "COMPLETING YOUR TASK:\n"
    "- You provide the final answer to the user\n"
    "- Stay focused on regulation questions until they are fully answered\n"
    "- If the user asks about something outside your expertise, explain that "
    "they should ask about regulations\n\n"
    "ALWAYS:\n"
    "- Call a tool FIRST before any response\n"
    "- Cite specific regulations with Dutch summaries\n"
    "- Provide actionable compliance guidance in Dutch\n"
    "- Flag high-risk areas clearly: 'WAARSCHUWING', 'HOOG RISICO'\n\n"
    "FORMAT:\n"
    "Structure responses with: Samenvatting, Details, Aanbevelingen, Bronnen"
)


# -- Tool Generation ----------------------------------------------------------


def generate_distractor_tools(n: int) -> list[Any]:
    """Create N StructuredTool instances from DISTRACTOR_TEMPLATES.

    Each tool accepts a ``query: str`` parameter and returns a stub response.
    """
    from langchain_core.tools import StructuredTool

    templates = DISTRACTOR_TEMPLATES[:n]
    tools = []

    for tmpl in templates:
        name = tmpl["name"]
        desc = tmpl["description"]

        # Default-arg capture avoids the loop-closure variable bug
        async def _stub(query: str, _name: str = name) -> str:
            return f"[{_name}] No results found for: {query}"

        tool = StructuredTool.from_function(
            coroutine=_stub,
            name=name,
            description=desc,
        )
        tools.append(tool)

    return tools


# -- Monkey-Patching ----------------------------------------------------------


def apply_patches(n: int) -> None:
    """Monkey-patch server modules to inject distractor tools.

    Must be called after imports but before ``uvicorn.run()`` starts the app.

    Patches two functions across five module-level bindings:

    * ``get_tools_for_agent`` on ``tools`` and ``graph``
    * ``get_agent_by_id`` on ``agent_definitions``, ``agents``, and ``graph``

    Python's ``from X import Y`` creates independent name bindings, so each
    module that imported the name needs its own patch.
    """
    import agora_langgraph.core.agent_definitions as agent_defs_mod
    import agora_langgraph.core.agents as agents_mod
    import agora_langgraph.core.graph as graph_mod
    import agora_langgraph.core.tools as tools_mod

    distractor_tools = generate_distractor_tools(n)
    distractor_names = [t.name for t in distractor_tools]
    log.info(
        "Generated %d distractor tools: %s", len(distractor_tools), distractor_names
    )

    # -- Patch get_tools_for_agent ---------------------------------------------
    original_get_tools = tools_mod.get_tools_for_agent

    def patched_get_tools_for_agent(
        agent_id: str,
        mcp_tools_by_server: dict[str, list[Any]],
    ) -> list[Any]:
        tools = original_get_tools(agent_id, mcp_tools_by_server)
        if agent_id == "regulation-agent":
            tools.extend(distractor_tools)
            log.info(
                "Injected %d distractor tools into %s (total: %d)",
                len(distractor_tools),
                agent_id,
                len(tools),
            )
        return tools

    tools_mod.get_tools_for_agent = patched_get_tools_for_agent
    graph_mod.get_tools_for_agent = patched_get_tools_for_agent

    # -- Patch get_agent_by_id -------------------------------------------------
    original_get_agent = agent_defs_mod.get_agent_by_id

    def patched_get_agent_by_id(agent_id: str):
        config = original_get_agent(agent_id)
        if config is not None and agent_id == "regulation-agent":
            # Return a copy with the benchmark prompt (no explicit tool names)
            config = dict(config)
            config["instructions"] = BENCHMARK_REGULATION_PROMPT
        return config

    agent_defs_mod.get_agent_by_id = patched_get_agent_by_id
    agents_mod.get_agent_by_id = patched_get_agent_by_id
    graph_mod.get_agent_by_id = patched_get_agent_by_id

    log.info("Monkey-patches applied for distractor benchmark")


# -- Entry Point ---------------------------------------------------------------

if __name__ == "__main__":
    n_distractors = int(os.environ.get("LANGGRAPH_DISTRACTOR_TOOLS", "0"))

    if n_distractors > 0:
        logging.basicConfig(level=logging.INFO)
        log.info("Distractor benchmark mode: %d distractor tools", n_distractors)
        apply_patches(n_distractors)

    from agora_langgraph.api.server import main as server_main

    server_main()
