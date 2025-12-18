/**
 * User list table component.
 */

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAdminStore } from '@/stores/useAdminStore';
import { Pencil, Trash2, Mail, Calendar, Clock } from 'lucide-react';

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('nl-NL', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function formatDateTime(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString('nl-NL', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function UserList() {
  const { users, isLoading, openEditModal, openDeleteModal } = useAdminStore();

  return (
    <div className="space-y-2">
      {users.map((user) => (
        <Card
          key={user.id}
          className="p-4 hover:bg-accent/50 transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="flex-1 min-w-0">
              <h3 className="font-medium truncate mb-1">{user.name}</h3>

              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1 truncate">
                  <Mail className="h-3 w-3 flex-shrink-0" />
                  {user.email}
                </span>

                <span className="flex items-center gap-1 flex-shrink-0">
                  <Calendar className="h-3 w-3" />
                  {formatDate(user.createdAt)}
                </span>

                <span className="flex items-center gap-1 flex-shrink-0">
                  <Clock className="h-3 w-3" />
                  {formatDateTime(user.lastActivity)}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-1 ml-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => openEditModal(user)}
                disabled={isLoading}
                aria-label={`Bewerk ${user.name}`}
              >
                <Pencil className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => openDeleteModal(user)}
                disabled={isLoading}
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                aria-label={`Verwijder ${user.name}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
