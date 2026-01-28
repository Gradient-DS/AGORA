import { Wrench, CheckCircle2, XCircle, Loader2, ExternalLink } from 'lucide-react';
import { cn, formatToolNameFallback } from '@/lib/utils';

interface ToolCallReferenceProps {
  toolName: string;
  displayName?: string;
  status: 'started' | 'completed' | 'failed';
  toolCallId: string;
}

export function ToolCallReference({
  toolName,
  displayName,
  status,
  toolCallId,
}: ToolCallReferenceProps) {
  const statusConfig = {
    started: {
      icon: Loader2,
      color: 'text-blue-500',
      bgColor: 'bg-blue-50 dark:bg-blue-900/30',
      label: 'Uitvoeren',
    },
    completed: {
      icon: CheckCircle2,
      color: 'text-green-500',
      bgColor: 'bg-green-50 dark:bg-green-900/30',
      label: 'Afgerond',
    },
    failed: {
      icon: XCircle,
      color: 'text-red-500',
      bgColor: 'bg-red-50 dark:bg-red-900/30',
      label: 'Mislukt',
    },
  };

  const config = statusConfig[status];
  const StatusIcon = config.icon;

  const scrollToToolCall = () => {
    const element = document.getElementById(`tool-call-${toolCallId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      element.classList.add('ring-2', 'ring-blue-500', 'ring-offset-2');
      setTimeout(() => {
        element.classList.remove('ring-2', 'ring-blue-500', 'ring-offset-2');
      }, 2000);
    }
  };

  return (
    <button
      id={`chat-tool-${toolCallId}`}
      onClick={scrollToToolCall}
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-all hover:scale-105 cursor-pointer',
        config.bgColor
      )}
      title="Klik om details te bekijken in het Onder de Motorkap paneel"
    >
      <Wrench className="h-3 w-3" aria-hidden="true" />
      <span>{displayName ?? formatToolNameFallback(toolName)}</span>
      <StatusIcon
        className={cn('h-3 w-3', config.color, status === 'started' && 'animate-spin')}
        aria-hidden="true"
      />
      <ExternalLink className="h-2.5 w-2.5 opacity-50" aria-hidden="true" />
    </button>
  );
}

