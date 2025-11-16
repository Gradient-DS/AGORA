import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Wrench, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ToolCallCardProps {
  toolName: string;
  status: 'started' | 'completed' | 'failed';
  parameters?: Record<string, unknown>;
  result?: string;
}

export function ToolCallCard({ toolName, status, parameters, result }: ToolCallCardProps) {
  const formatToolName = (name: string) => {
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const statusConfig = {
    started: {
      icon: Loader2,
      color: 'text-blue-500',
      bgColor: 'bg-blue-50 dark:bg-blue-950',
      borderColor: 'border-blue-200 dark:border-blue-800',
      label: 'Executing',
      labelColor: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    },
    completed: {
      icon: CheckCircle2,
      color: 'text-green-500',
      bgColor: 'bg-green-50 dark:bg-green-950',
      borderColor: 'border-green-200 dark:border-green-800',
      label: 'Completed',
      labelColor: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
    },
    failed: {
      icon: XCircle,
      color: 'text-red-500',
      bgColor: 'bg-red-50 dark:bg-red-950',
      borderColor: 'border-red-200 dark:border-red-800',
      label: 'Failed',
      labelColor: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    },
  };

  const config = statusConfig[status];
  const StatusIcon = config.icon;

  return (
    <Card
      className={cn(
        'p-3 mb-3 border animate-in fade-in slide-in-from-left-2',
        config.bgColor,
        config.borderColor
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn('mt-0.5', config.color)}>
          <StatusIcon
            className={cn('h-4 w-4', status === 'started' && 'animate-spin')}
            aria-hidden="true"
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Wrench className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
            <span className="text-sm font-medium">{formatToolName(toolName)}</span>
            <Badge variant="secondary" className={cn('text-xs', config.labelColor)}>
              {config.label}
            </Badge>
          </div>

          {parameters && Object.keys(parameters).length > 0 && (
            <div className="text-xs text-muted-foreground mt-1 font-mono">
              {Object.entries(parameters).map(([key, value]) => (
                <div key={key} className="truncate">
                  <span className="font-semibold">{key}:</span>{' '}
                  {typeof value === 'string' ? value : JSON.stringify(value)}
                </div>
              ))}
            </div>
          )}

          {status === 'completed' && result && (
            <div className="text-xs text-muted-foreground mt-1.5 pt-1.5 border-t border-current/10">
              ✓ {result}
            </div>
          )}

          {status === 'failed' && result && (
            <div className="text-xs text-red-600 dark:text-red-400 mt-1.5 pt-1.5 border-t border-current/10">
              ✗ {result}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

