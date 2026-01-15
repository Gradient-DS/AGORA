/**
 * Loading indicator component for AG-UI Protocol processing states.
 */

import { useMemo } from 'react';
import { useAgentStore, useToolCallStore } from '@/stores';
import { formatToolName } from '@/lib/utils';

type ProcessingStatus = 'thinking' | 'routing' | 'executing_tools' | null;

interface LoadingIndicatorProps {
  status: ProcessingStatus;
}

export function LoadingIndicator({ status }: LoadingIndicatorProps) {
  const activeAgents = useAgentStore((state) => state.getActiveAgents());
  const toolCalls = useToolCallStore((state) => state.toolCalls);

  const displayState = useMemo(() => {
    const activeToolCall = toolCalls
      .filter((tc) => tc.status === 'started')
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())[0];

    if (activeToolCall) {
      const toolDisplayName = formatToolName(activeToolCall.toolName);
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
