import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Trash2, MessageSquare } from 'lucide-react';
import type { SessionMetadata } from '@/types';

interface SessionListItemProps {
  session: SessionMetadata;
  isActive: boolean;
  isDisabled: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

/**
 * Format a date string as relative time in Dutch.
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) {
    return 'zojuist';
  } else if (diffMinutes < 60) {
    return `${diffMinutes} min geleden`;
  } else if (diffHours < 24) {
    return `${diffHours} uur geleden`;
  } else if (diffDays === 1) {
    return 'gisteren';
  } else if (diffDays < 7) {
    return `${diffDays} dagen geleden`;
  } else {
    return date.toLocaleDateString('nl-NL', {
      day: 'numeric',
      month: 'short',
    });
  }
}

/**
 * Truncate a string to a maximum length with ellipsis.
 */
function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + '...';
}

export function SessionListItem({
  session,
  isActive,
  isDisabled,
  onSelect,
  onDelete,
}: SessionListItemProps) {
  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete();
  };

  return (
    <button
      onClick={onSelect}
      disabled={isDisabled}
      className={`
        w-full text-left p-3 rounded-lg border transition-colors
        ${isActive
          ? 'bg-primary/10 border-primary'
          : 'bg-card border-border hover:bg-accent/50'
        }
        ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      `}
      aria-label={`Gesprek: ${session.title}`}
      aria-current={isActive ? 'true' : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-sm truncate">
            {truncate(session.title, 50)}
          </h4>
          <p className="text-xs text-muted-foreground mt-1">
            {formatRelativeTime(session.lastActivity)}
          </p>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          <Badge variant="secondary" className="text-xs px-1.5 py-0">
            <MessageSquare className="h-3 w-3 mr-0.5" />
            {session.messageCount}
          </Badge>

          <Button
            size="sm"
            variant="ghost"
            onClick={handleDelete}
            disabled={isDisabled}
            className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
            aria-label="Verwijder gesprek"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </button>
  );
}
