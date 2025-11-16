import { useEffect, useState } from 'react';
import { useAgentStore, useToolCallStore } from '@/stores';
import type { ProcessingStatus } from '@/types/schemas';

interface LoadingIndicatorProps {
  status: ProcessingStatus | null;
}

const TOOL_NAME_TRANSLATIONS: Record<string, string> = {
  // Inspection History Tools
  'check_company_exists': 'Controleren bedrijfsgegevens',
  'get_inspection_history': 'Ophalen inspectiehistorie',
  'get_company_violations': 'Ophalen overtredingen',
  'check_repeat_violation': 'Controleren herhaalde overtredingen',
  'get_follow_up_status': 'Controleren follow-up status',
  'search_inspections_by_inspector': 'Zoeken inspecties per inspecteur',
  
  // Regulation Analysis Tools
  'search_regulations': 'Zoeken in regelgeving',
  'get_regulation_context': 'Ophalen regelgeving context',
  'lookup_regulation_articles': 'Opzoeken regelgeving artikelen',
  'analyze_document': 'Analyseren document',
  'get_database_stats': 'Ophalen database statistieken',
  
  // Reporting Tools
  'start_inspection_report': 'Starten inspectie rapport',
  'extract_inspection_data': 'Verwerken inspectiegegevens',
  'verify_inspection_data': 'Verifiëren inspectiegegevens',
  'submit_verification_answers': 'Verwerken antwoorden',
  'generate_final_report': 'Genereren eindrapport',
  'get_report_status': 'Ophalen rapport status',
  
  // Legacy/Generic
  'search_kvk': 'Zoeken in het KVK',
  'analyze_regulations': 'Analyseren regelgeving',
  'generate_report': 'Genereren rapportage',
  'search_documents': 'Zoeken in documenten',
  'query_knowledge_base': 'Zoeken in kennisbank',
};

export function LoadingIndicator({ status }: LoadingIndicatorProps) {
  const activeAgents = useAgentStore((state) => state.getActiveAgents());
  const toolCalls = useToolCallStore((state) => state.toolCalls);
  const [displayText, setDisplayText] = useState('');
  const [showIndicator, setShowIndicator] = useState(false);

  useEffect(() => {
    const activeToolCall = toolCalls
      .filter(tc => tc.status === 'started')
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())[0];
    
    if (activeToolCall) {
      const toolDisplayName = TOOL_NAME_TRANSLATIONS[activeToolCall.toolName] || activeToolCall.toolName;
      setDisplayText(toolDisplayName);
      setShowIndicator(true);
    } else if (status === 'routing') {
      setDisplayText('Agent wordt uitgekozen...');
      setShowIndicator(true);
    } else if (status === 'thinking') {
      const activeAgent = activeAgents.find(agent => agent.status === 'active');
      if (activeAgent) {
        setDisplayText(`${activeAgent.name} aan het denken...`);
      } else {
        setDisplayText('Aan het denken...');
      }
      setShowIndicator(true);
    } else if (status === 'executing_tools') {
      const executingAgent = activeAgents.find(agent => agent.status === 'executing_tools');
      if (executingAgent) {
        setDisplayText('Tools uitvoeren...');
      } else {
        setDisplayText('Bezig met uitvoeren...');
      }
      setShowIndicator(true);
    } else {
      setShowIndicator(false);
    }
  }, [status, activeAgents, toolCalls]);

  if (!showIndicator || status === 'completed') {
    return null;
  }

  return (
    <div className="flex items-start gap-3 mb-4 animate-in fade-in slide-in-from-bottom-2">
      <div className="h-8 w-8 shrink-0" />
      <div className="flex flex-col max-w-[80%] gap-2">
        <span className="text-xs text-muted-foreground px-1 animate-wave-opacity">
          {displayText}
        </span>
      </div>
    </div>
  );
}

