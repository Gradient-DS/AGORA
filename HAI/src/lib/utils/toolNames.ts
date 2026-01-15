/**
 * Dutch translations for MCP tool names displayed in the UI.
 */

const TOOL_NAME_TRANSLATIONS: Record<string, string> = {
  // History agent tools
  check_company_exists: 'Controleren bedrijfsgegevens',
  get_inspection_history: 'Ophalen inspectiehistorie',
  get_company_violations: 'Ophalen overtredingen',
  check_repeat_violation: 'Controleren herhaalde overtredingen',
  get_follow_up_status: 'Controleren follow-up status',
  search_inspections_by_inspector: 'Zoeken inspecties per inspecteur',
  search_kvk: 'Zoeken in het KVK',

  // Regulation agent tools
  search_regulations: 'Zoeken in regelgeving',
  get_regulation_context: 'Ophalen regelgeving context',
  lookup_regulation_articles: 'Opzoeken regelgeving artikelen',
  analyze_document: 'Analyseren document',
  analyze_regulations: 'Analyseren regelgeving',
  get_database_stats: 'Ophalen database statistieken',

  // Reporting agent tools
  start_inspection_report: 'Starten inspectie rapport',
  extract_inspection_data: 'Verwerken inspectiegegevens',
  verify_inspection_data: 'Verifiëren inspectiegegevens',
  submit_verification_answers: 'Verwerken antwoorden',
  request_clarification: 'Opvragen aanvullende informatie',
  generate_final_report: 'Genereren eindrapport',
  get_report_status: 'Ophalen rapport status',
  generate_report: 'Genereren rapportage',

  // General tools
  search_documents: 'Zoeken in documenten',
  query_knowledge_base: 'Zoeken in kennisbank',

  // Handoff tools (transfer between agents)
  transfer_to_reporting: 'Overdracht naar rapportage',
  transfer_to_regulation: 'Overdracht naar regelgeving',
  transfer_to_history: 'Overdracht naar inspectiehistorie',
  transfer_to_general: 'Overdracht naar algemeen',
  transfer_to_triage: 'Overdracht naar triage',
};

/**
 * Formats a tool name for display in the UI.
 * Returns the Dutch translation if available, otherwise converts snake_case to Title Case.
 */
export function formatToolName(name: string): string {
  // Check for Dutch translation first
  if (TOOL_NAME_TRANSLATIONS[name]) {
    return TOOL_NAME_TRANSLATIONS[name];
  }

  // Fallback: convert snake_case to Title Case
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
