/**
 * User create/edit form dialog.
 */

import { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAdminStore } from '@/stores/useAdminStore';
import { X, Loader2, Save, UserPlus } from 'lucide-react';
import type { CreateUserRequest, UpdateUserRequest } from '@/types/user';

interface UserFormProps {
  mode: 'create' | 'edit';
}

export function UserForm({ mode }: UserFormProps) {
  const {
    selectedUser,
    isLoading,
    error,
    createUser,
    updateUser,
    closeCreateModal,
    closeEditModal,
  } = useAdminStore();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  // Populate form for edit mode
  useEffect(() => {
    if (mode === 'edit' && selectedUser) {
      setName(selectedUser.name);
      setEmail(selectedUser.email);
    }
  }, [mode, selectedUser]);

  const handleClose = () => {
    if (mode === 'create') {
      closeCreateModal();
    } else {
      closeEditModal();
    }
  };

  const validateForm = (): boolean => {
    if (!name.trim()) {
      setLocalError('Naam is verplicht');
      return false;
    }
    if (mode === 'create' && !email.trim()) {
      setLocalError('E-mail is verplicht');
      return false;
    }
    if (mode === 'create' && !email.includes('@')) {
      setLocalError('Voer een geldig e-mailadres in');
      return false;
    }
    setLocalError(null);
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      if (mode === 'create') {
        const data: CreateUserRequest = {
          name: name.trim(),
          email: email.trim(),
        };
        await createUser(data);
      } else if (selectedUser) {
        const data: UpdateUserRequest = {
          name: name.trim(),
        };
        await updateUser(selectedUser.id, data);
      }
    } catch {
      // Error is handled by the store
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleClose();
    }
  };

  const title = mode === 'create' ? 'Nieuwe gebruiker' : 'Gebruiker bewerken';
  const displayError = localError || error;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <Card
        className="w-full max-w-md shadow-xl"
        role="dialog"
        aria-labelledby="user-form-title"
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        <form onSubmit={handleSubmit}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle id="user-form-title">{title}</CardTitle>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleClose}
                aria-label="Sluiten"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {displayError && (
              <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
                {displayError}
              </div>
            )}

            <div className="space-y-2">
              <label htmlFor="name" className="text-sm font-medium">
                Naam <span className="text-destructive">*</span>
              </label>
              <Input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Voer naam in"
                disabled={isLoading}
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                E-mail {mode === 'create' && <span className="text-destructive">*</span>}
              </label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="naam@voorbeeld.nl"
                disabled={isLoading || mode === 'edit'}
                className={mode === 'edit' ? 'bg-muted' : ''}
              />
              {mode === 'edit' && (
                <p className="text-xs text-muted-foreground">
                  E-mailadres kan niet worden gewijzigd
                </p>
              )}
            </div>
          </CardContent>

          <CardFooter className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isLoading}
            >
              Annuleren
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : mode === 'create' ? (
                <UserPlus className="h-4 w-4 mr-2" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              {mode === 'create' ? 'Toevoegen' : 'Opslaan'}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
