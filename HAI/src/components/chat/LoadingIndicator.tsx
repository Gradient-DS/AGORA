/**
 * Loading indicator component for AG-UI Protocol processing states.
 */

import { useMemo } from 'react';
import { useAgentStore, useToolCallStore } from '@/stores';

type ProcessingStatus = 'thinking' | 'routing' | 'executing_tools' | null;

interface LoadingIndicatorProps {
  status: ProcessingStatus;
}

const TOOL_NAME_TRANSLATIONS: Record<string, string> = {
  check_company_exists: 'Controleren bedrijfsgegevens',
  get_inspection_history: 'Ophalen inspectiehistorie',
  get_company_violations: 'Ophalen overtredingen',
  check_repeat_violation: 'Controleren herhaalde overtredingen',
  get_follow_up_status: 'Controleren follow-up status',
  search_inspections_by_inspector: 'Zoeken inspecties per inspecteur',
  search_regulations: 'Zoeken in regelgeving',
  get_regulation_context: 'Ophalen regelgeving context',
  lookup_regulation_articles: 'Opzoeken regelgeving artikelen',
  analyze_document: 'Analyseren document',
  get_database_stats: 'Ophalen database statistieken',
  start_inspection_report: 'Starten inspectie rapport',
  extract_inspection_data: 'Verwerken inspectiegegevens',
  verify_inspection_data: 'Verifiëren inspectiegegevens',
  submit_verification_answers: 'Verwerken antwoorden',
  generate_final_report: 'Genereren eindrapport',
  get_report_status: 'Ophalen rapport status',
  search_kvk: 'Zoeken in het KVK',
  analyze_regulations: 'Analyseren regelgeving',
  generate_report: 'Genereren rapportage',
  search_documents: 'Zoeken in documenten',
  query_knowledge_base: 'Zoeken in kennisbank',
};

export function LoadingIndicator({ status }: LoadingIndicatorProps) {
  const activeAgents = useAgentStore((state) => state.getActiveAgents());
  const toolCalls = useToolCallStore((state) => state.toolCalls);

  const displayState = useMemo(() => {
    const activeToolCall = toolCalls
      .filter((tc) => tc.status === 'started')
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())[0];

    if (activeToolCall) {
      const toolDisplayName =
        TOOL_NAME_TRANSLATIONS[activeToolCall.toolName] || activeToolCall.toolName;
      return { showIndicator: true, displayText: toolDisplayName };
    }

    if (status === 'routing') {
      return { showIndicator: true, displayText: 'Agent wordt uitgekozen...' };
    }

    if (status === 'thinking') {
      const activeAgent = activeAgents.find((agent) => agent.status === 'active');
      if (activeAgent) {
        return { showIndicator: true, displayText: `${activeAgent.name} aan het denken...` };
      }
      return { showIndicator: true, displayText: 'Aan het denken...' };
    }

    if (status === 'executing_tools') {
      const executingAgent = activeAgents.find((agent) => agent.status === 'executing_tools');
      if (executingAgent) {
        return { showIndicator: true, displayText: 'Tools uitvoeren...' };
      }
      return { showIndicator: true, displayText: 'Bezig met uitvoeren...' };
    }

    return { showIndicator: false, displayText: '' };
  }, [status, activeAgents, toolCalls]);

  if (!displayState.showIndicator) {
    return null;
  }

  return (
    <div className="flex items-start gap-3 mb-4 animate-in fade-in slide-in-from-bottom-2">
      <div className="h-8 w-8 shrink-0" />
      <div className="flex flex-col max-w-[80%] gap-2">
        <span className="text-xs text-muted-foreground px-1 animate-wave-opacity">
          {displayState.displayText}
        </span>
      </div>
    </div>
  );
}
