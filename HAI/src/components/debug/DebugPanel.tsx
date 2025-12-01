import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Settings, Bot, Circle, ChevronDown, ChevronRight, Lock, Wrench } from 'lucide-react';
import { useToolCallStore, useAgentStore } from '@/stores';
import { ToolCallCard } from '@/components/chat/ToolCallCard';
import { cn } from '@/lib/utils';
import { useState } from 'react';

export function DebugPanel() {
  const toolCalls = useToolCallStore((state) => state.toolCalls);
  const getToolCallsByAgent = useToolCallStore((state) => state.getToolCallsByAgent);
  const agents = useAgentStore((state) => state.getAllAgents());
  const inactiveAgents = useAgentStore((state) => state.inactiveAgents);
  const [collapsedAgents, setCollapsedAgents] = useState<Set<string>>(new Set());
  const [inactiveCollapsed, setInactiveCollapsed] = useState(true);
  const [unassignedCollapsed, setUnassignedCollapsed] = useState(false);

  const unassignedToolCalls = toolCalls.filter((tc) => !tc.agentId);

  console.log('[DebugPanel] All tool calls:', toolCalls.length, toolCalls);

  const toggleAgentCollapse = (agentId: string) => {
    setCollapsedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const statusColors = {
    idle: 'text-gray-400',
    active: 'text-green-500',
    executing_tools: 'text-blue-500 animate-pulse',
  };

  const statusLabels = {
    idle: 'Inactief',
    active: 'Actief',
    executing_tools: 'Tools Uitvoeren',
  };

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardHeader className="flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Onder de Motorkap
          </CardTitle>
          <Badge variant="outline" className="gap-1">
            {toolCalls.length} {toolCalls.length === 1 ? 'call' : 'calls'}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto space-y-4">
        {/* Agents Section */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
            <Bot className="h-4 w-4" />
            Agents ({agents.length})
          </h3>
          
          {agents.map((agent) => {
            const agentToolCalls = getToolCallsByAgent(agent.id);
            const hasToolCalls = agentToolCalls.length > 0;
            const isCollapsed = collapsedAgents.has(agent.id);
            const ChevronIcon = isCollapsed ? ChevronRight : ChevronDown;
            
            return (
              <div key={agent.id} className="space-y-2">
                <button
                  onClick={() => hasToolCalls && toggleAgentCollapse(agent.id)}
                  className={cn(
                    "w-full flex items-center justify-between p-2 rounded-lg bg-muted/50 transition-colors",
                    hasToolCalls && "hover:bg-muted cursor-pointer"
                  )}
                >
                  <div className="flex items-center gap-2">
                    {hasToolCalls && (
                      <ChevronIcon className="h-4 w-4 text-muted-foreground transition-transform" />
                    )}
                    {!hasToolCalls && (
                      <div className="w-4" />
                    )}
                    <Circle
                      className={cn('h-2 w-2 fill-current', statusColors[agent.status])}
                    />
                    <span className="text-sm font-medium">{agent.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {agentToolCalls.length > 0 && (
                      <Badge variant="secondary" className="text-xs">
                        {agentToolCalls.length} {agentToolCalls.length === 1 ? 'aanroep' : 'aanroepen'}
                      </Badge>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {statusLabels[agent.status]}
                    </span>
                  </div>
                </button>
                
                {/* Agent's Tool Calls */}
                {hasToolCalls && !isCollapsed && (
                  <div className="ml-4 space-y-2 border-l-2 border-muted pl-3 animate-in fade-in slide-in-from-top-2">
                    {agentToolCalls.map((toolCall) => (
                      <div key={toolCall.id} id={`tool-call-${toolCall.id}`} className="transition-all">
                        <ToolCallCard
                          toolName={toolCall.toolName}
                          status={toolCall.status}
                          parameters={toolCall.parameters}
                          result={toolCall.result}
                          toolCallId={toolCall.id}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Unassigned Tool Calls Section */}
        {unassignedToolCalls.length > 0 && (
          <>
            <Separator className="my-4" />
            <div className="space-y-2">
              <button
                onClick={() => setUnassignedCollapsed(!unassignedCollapsed)}
                className="w-full flex items-center justify-between p-2 rounded-lg bg-muted/50 hover:bg-muted transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  {unassignedCollapsed ? (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  )}
                  <Wrench className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Tool Aanroepen</span>
                </div>
                <Badge variant="secondary" className="text-xs">
                  {unassignedToolCalls.length} {unassignedToolCalls.length === 1 ? 'aanroep' : 'aanroepen'}
                </Badge>
              </button>

              {!unassignedCollapsed && (
                <div className="ml-4 space-y-2 border-l-2 border-muted pl-3 animate-in fade-in slide-in-from-top-2">
                  {unassignedToolCalls.map((toolCall) => (
                    <div key={toolCall.id} id={`tool-call-${toolCall.id}`} className="transition-all">
                      <ToolCallCard
                        toolName={toolCall.toolName}
                        status={toolCall.status}
                        parameters={toolCall.parameters}
                        result={toolCall.result}
                        toolCallId={toolCall.id}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* Inactive Agents Section */}
        {inactiveAgents.length > 0 && (
          <>
            <Separator className="my-4" />
            <div className="space-y-2">
              <button
                onClick={() => setInactiveCollapsed(!inactiveCollapsed)}
                className="w-full flex items-center justify-between p-2 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  {inactiveCollapsed ? (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  )}
                  <Lock className="h-3 w-3 text-muted-foreground" />
                  <span className="text-sm font-medium text-muted-foreground">
                    Inactieve Agents
                  </span>
                </div>
                <Badge variant="secondary" className="text-xs">
                  {inactiveAgents.length}
                </Badge>
              </button>

              {!inactiveCollapsed && (
                <div className="ml-6 space-y-2 animate-in fade-in slide-in-from-top-2">
                  {inactiveAgents.map((agent) => (
                    <div
                      key={agent.id}
                      className="p-2 rounded-lg bg-muted/20 border border-dashed opacity-60"
                    >
                      <div className="flex items-start gap-2">
                        <Lock className="h-3 w-3 text-muted-foreground mt-0.5 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-muted-foreground">
                              {agent.name}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {agent.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {toolCalls.length === 0 && (
          <>
            <Separator />
            <div className="p-4 rounded-lg bg-muted/50 text-sm">
              <p className="text-muted-foreground">
                Nog geen tool uitvoeringen. Tool aanroepen verschijnen hier zodra ze worden uitgevoerd.
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

