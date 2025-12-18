/**
 * Delete user confirmation dialog.
 */

import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAdminStore } from '@/stores/useAdminStore';
import { AlertTriangle, Loader2, Trash2, X } from 'lucide-react';

export function DeleteUserDialog() {
  const { userToDelete, isLoading, error, deleteUser, closeDeleteModal } =
    useAdminStore();

  if (!userToDelete) {
    return null;
  }

  const handleDelete = async () => {
    try {
      await deleteUser(userToDelete.id);
    } catch {
      // Error is handled by the store
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      closeDeleteModal();
    } else if (e.key === 'Enter') {
      handleDelete();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <Card
        className="w-full max-w-md shadow-xl"
        role="alertdialog"
        aria-labelledby="delete-dialog-title"
        aria-describedby="delete-dialog-description"
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle
              id="delete-dialog-title"
              className="flex items-center gap-2 text-destructive"
            >
              <AlertTriangle className="h-5 w-5" />
              Gebruiker verwijderen
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={closeDeleteModal}
              aria-label="Sluiten"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
              {error}
            </div>
          )}

          <p id="delete-dialog-description">
            Weet u zeker dat u <strong>{userToDelete.name}</strong> wilt
            verwijderen?
          </p>

          <div className="bg-destructive/10 border border-destructive/20 rounded-md p-3 text-sm">
            <p className="font-medium text-destructive mb-1">
              Let op: deze actie kan niet ongedaan worden gemaakt
            </p>
            <ul className="list-disc list-inside text-muted-foreground space-y-1">
              <li>Het gebruikersaccount wordt permanent verwijderd</li>
              <li>Alle sessies van deze gebruiker worden verwijderd</li>
              <li>Alle gesprekgeschiedenis gaat verloren</li>
            </ul>
          </div>
        </CardContent>

        <CardFooter className="flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={closeDeleteModal}
            disabled={isLoading}
          >
            Annuleren
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4 mr-2" />
            )}
            Verwijderen
          </Button>
        </CardFooter>

        <div className="px-6 pb-4 text-xs text-muted-foreground">
          Toetsenbord: <kbd>Enter</kbd> om te verwijderen, <kbd>Esc</kbd> om te annuleren
        </div>
      </Card>
    </div>
  );
}
