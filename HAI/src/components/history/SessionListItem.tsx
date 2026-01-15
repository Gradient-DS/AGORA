import { useState, useRef, useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Trash2, MessageSquare, Pencil, Check, X } from 'lucide-react';
import type { SessionMetadata } from '@/types';

interface SessionListItemProps {
  session: SessionMetadata;
  isActive: boolean;
  isDisabled: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (newTitle: string) => Promise<void>;
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
  onRename,
}: SessionListItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(session.title);
  const [isSaving, setIsSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete();
  };

  const handleStartEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditTitle(session.title);
    setIsEditing(true);
  };

  const handleCancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsEditing(false);
    setEditTitle(session.title);
  };

  const handleSaveEdit = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const trimmedTitle = editTitle.trim();
    if (!trimmedTitle || trimmedTitle === session.title) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    try {
      await onRename(trimmedTitle);
      setIsEditing(false);
    } catch {
      // Error is handled in the store, keep editing mode open
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === 'Enter') {
      handleSaveEdit(e as unknown as React.MouseEvent);
    } else if (e.key === 'Escape') {
      setIsEditing(false);
      setEditTitle(session.title);
    }
  };

  return (
    <button
      onClick={isEditing ? undefined : onSelect}
      disabled={isDisabled || isEditing}
      className={`
        w-full text-left p-3 rounded-lg border transition-colors
        ${isActive
          ? 'bg-primary/10 border-primary'
          : 'bg-card border-border hover:bg-accent/50'
        }
        ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        ${isEditing ? 'cursor-default' : ''}
      `}
      aria-label={`Gesprek: ${session.title}`}
      aria-current={isActive ? 'true' : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <Input
              ref={inputRef}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={handleKeyDown}
              onClick={(e) => e.stopPropagation()}
              disabled={isSaving}
              className="h-7 text-sm"
              maxLength={200}
            />
          ) : (
            <h4 className="font-medium text-sm truncate">
              {truncate(session.title, 50)}
            </h4>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            {formatRelativeTime(session.lastActivity)}
          </p>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          {isEditing ? (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={handleSaveEdit}
                disabled={isSaving}
                className="h-6 w-6 p-0 text-muted-foreground hover:text-primary"
                aria-label="Opslaan"
              >
                <Check className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={handleCancelEdit}
                disabled={isSaving}
                className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                aria-label="Annuleren"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </>
          ) : (
            <>
              <Badge variant="secondary" className="text-xs px-1.5 py-0">
                <MessageSquare className="h-3 w-3 mr-0.5" />
                {session.messageCount}
              </Badge>

              <Button
                size="sm"
                variant="ghost"
                onClick={handleStartEdit}
                disabled={isDisabled}
                className="h-6 w-6 p-0 text-muted-foreground hover:text-primary"
                aria-label="Hernoem gesprek"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>

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
            </>
          )}
        </div>
      </div>
    </button>
  );
}
