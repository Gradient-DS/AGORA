"""Tool display name registry for AG-UI protocol.

Provides Dutch display names for tools shown in the HAI frontend.
These names are sent via the toolDisplayName field in TOOL_CALL_START events.
"""

import random

TOOL_DISPLAY_NAMES: dict[str, str] = {
    # History agent tools
    "check_company_exists": "Controleren bedrijfsgegevens",
    "get_inspection_history": "Ophalen inspectiehistorie",
    "get_company_violations": "Ophalen overtredingen",
    "check_repeat_violation": "Controleren herhaalde overtredingen",
    "get_follow_up_status": "Controleren follow-up status",
    "search_inspections_by_inspector": "Zoeken inspecties per inspecteur",
    "get_company_meldingen": "Ophalen meldingen",
    # Regulation agent tools
    "search_regulations": "Zoeken in regelgeving",
    "get_regulation_context": "Ophalen regelgeving context",
    "lookup_regulation_articles": "Opzoeken regelgeving artikelen",
    "analyze_document": "Analyseren document",
    "analyze_regulations": "Analyseren regelgeving",
    "get_database_stats": "Ophalen database statistieken",
    # Reporting agent tools
    "generate_report": "Genereren inspectierapport",
    "request_clarification": "Opvragen aanvullende informatie",
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
    "generate_inspection_report": "Genereren inspectierapport",
}


def get_tool_display_name(tool_name: str) -> str | None:
    """Get display name for a tool, or None to use default formatting."""
    return TOOL_DISPLAY_NAMES.get(tool_name)


TOOL_SPOKEN_DESCRIPTIONS: dict[str, list[str]] = {
    # Handoff tools - natural, action-oriented descriptions
    "transfer_to_reporting": [
        "Ik ga het rapport voor je voorbereiden en kom zo bij je terug.",
        "Momentje, ik begin met de rapportage. Ik ben zo terug.",
        "Ik ga de inspectiegegevens verwerken voor het rapport, een ogenblikje.",
    ],
    "transfer_to_regulation": [
        "Ik ga de regelgeving erbij pakken en kom zo bij je terug.",
        "Even de regels checken, ik ben zo terug.",
        "Ik zoek de relevante wetgeving voor je op, een momentje.",
    ],
    "transfer_to_history": [
        "Ik ga de bedrijfsgegevens opzoeken en kom zo bij je terug.",
        "Momentje, ik zoek de inspectiehistorie op. Ik ben zo terug.",
        "Ik ga kijken wat we over dit bedrijf weten, een ogenblikje.",
    ],
    # Report generation - shown in approval dialog
    "generate_report": [
        "Ik ga het eindrapport voor je opstellen.",
        "Momentje, ik genereer het inspectierapport.",
        "Ik ga de bevindingen verwerken in het rapport.",
    ],
}


def get_tool_spoken_description(tool_name: str) -> str | None:
    """Get spoken TTS description for a tool, or None for no announcement.

    Randomly selects from multiple natural-sounding options for variety.
    """
    options = TOOL_SPOKEN_DESCRIPTIONS.get(tool_name)
    if options is None:
        return None
    return random.choice(options)
