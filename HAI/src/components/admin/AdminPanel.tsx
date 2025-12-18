/**
 * Admin panel for user management.
 */

import { useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useAdminStore } from '@/stores/useAdminStore';
import { UserList } from './UserList';
import { UserForm } from './UserForm';
import { DeleteUserDialog } from './DeleteUserDialog';
import { X, Plus, Users, AlertCircle, Loader2 } from 'lucide-react';

export function AdminPanel() {
  const {
    users,
    isLoading,
    error,
    totalCount,
    closeAdminPanel,
    openCreateModal,
    isCreateModalOpen,
    isEditModalOpen,
    isDeleteModalOpen,
    clearError,
  } = useAdminStore();

  // Clear error after 5 seconds
  useEffect(() => {
    if (!error) {
      return;
    }
    const timer = setTimeout(() => clearError(), 5000);
    return () => clearTimeout(timer);
  }, [error, clearError]);

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <Card className="rounded-none border-x-0 border-t-0">
        <CardHeader className="py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Users className="h-6 w-6 text-muted-foreground" />
              <div>
                <CardTitle className="text-xl">Gebruikersbeheer</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Beheer gebruikers en hun rechten
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="font-normal">
                {totalCount} gebruiker{totalCount !== 1 ? 's' : ''}
              </Badge>

              <Button
                variant="default"
                size="sm"
                onClick={openCreateModal}
                disabled={isLoading}
                aria-label="Nieuwe gebruiker toevoegen"
              >
                <Plus className="h-4 w-4 mr-1" />
                Nieuwe gebruiker
              </Button>

              <Button
                variant="ghost"
                size="sm"
                onClick={closeAdminPanel}
                aria-label="Sluit admin paneel"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Error alert */}
      {error && (
        <Alert variant="destructive" className="mx-4 mt-4">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Content */}
      <CardContent className="flex-1 overflow-auto p-4">
        {isLoading && users.length === 0 ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : users.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center">
            <Users className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">Geen gebruikers gevonden</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Voeg een nieuwe gebruiker toe om te beginnen.
            </p>
            <Button onClick={openCreateModal}>
              <Plus className="h-4 w-4 mr-1" />
              Nieuwe gebruiker
            </Button>
          </div>
        ) : (
          <UserList />
        )}
      </CardContent>

      {/* Modals */}
      {isCreateModalOpen && <UserForm mode="create" />}
      {isEditModalOpen && <UserForm mode="edit" />}
      {isDeleteModalOpen && <DeleteUserDialog />}
    </div>
  );
}
