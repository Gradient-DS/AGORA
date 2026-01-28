"""Tool display name registry for AG-UI protocol.

Provides Dutch display names for tools shown in the HAI frontend.
These names are sent via the toolDisplayName field in TOOL_CALL_START events.
"""

TOOL_DISPLAY_NAMES: dict[str, str] = {
    # History agent tools
    "check_company_exists": "Controleren bedrijfsgegevens",
    "get_inspection_history": "Ophalen inspectiehistorie",
    "get_company_violations": "Ophalen overtredingen",
    "check_repeat_violation": "Controleren herhaalde overtredingen",
    "get_follow_up_status": "Controleren follow-up status",
    "search_inspections_by_inspector": "Zoeken inspecties per inspecteur",
    "search_kvk": "Zoeken in het KVK",
    # Regulation agent tools
    "search_regulations": "Zoeken in regelgeving",
    "get_regulation_context": "Ophalen regelgeving context",
    "lookup_regulation_articles": "Opzoeken regelgeving artikelen",
    "analyze_document": "Analyseren document",
    "analyze_regulations": "Analyseren regelgeving",
    "get_database_stats": "Ophalen database statistieken",
    # Reporting agent tools
    "start_inspection_report": "Starten inspectie rapport",
    "extract_inspection_data": "Verwerken inspectiegegevens",
    "verify_inspection_data": "Verifiëren inspectiegegevens",
    "submit_verification_answers": "Verwerken antwoorden",
    "request_clarification": "Opvragen aanvullende informatie",
    "generate_final_report": "Genereren eindrapport",
    "get_report_status": "Ophalen rapport status",
    "generate_report": "Genereren rapportage",
    # General tools
    "search_documents": "Zoeken in documenten",
    "query_knowledge_base": "Zoeken in kennisbank",
    "update_user_settings": "Bijwerken instellingen",
    # Handoff tools
    "transfer_to_reporting": "Overdracht naar rapportage",
    "transfer_to_regulation": "Overdracht naar regelgeving",
    "transfer_to_history": "Overdracht naar inspectiehistorie",
    "transfer_to_general": "Overdracht naar algemeen",
    "transfer_to_triage": "Overdracht naar triage",
    "transfer_to_agent": "Overdracht naar specialist",
    # Mock server tools
    "get_company_info": "Ophalen bedrijfsgegevens",
    "generate_inspection_report": "Genereren inspectierapport",
}


def get_tool_display_name(tool_name: str) -> str | None:
    """Get display name for a tool, or None to use default formatting."""
    return TOOL_DISPLAY_NAMES.get(tool_name)
