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
import { fetchUserPreferences, updateUserPreferences } from '@/lib/api/users';
import { X, Loader2, Save, UserPlus, Mic, FileText, MessageSquare, Headphones, Mail, MailX } from 'lucide-react';
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
  const [spokenTextType, setSpokenTextType] = useState<'dictate' | 'summarize'>('summarize');
  const [interactionMode, setInteractionMode] = useState<'feedback' | 'listen'>('feedback');
  const [emailReports, setEmailReports] = useState<boolean>(true);
  const [localError, setLocalError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Populate form for edit mode
  useEffect(() => {
    if (mode === 'edit' && selectedUser) {
      setName(selectedUser.name);
      setEmail(selectedUser.email);
      // Load preferences
      fetchUserPreferences(selectedUser.id)
        .then((prefs) => {
          if (prefs.spoken_text_type) {
            setSpokenTextType(prefs.spoken_text_type);
          }
          if (prefs.interaction_mode) {
            setInteractionMode(prefs.interaction_mode);
          }
          if (prefs.email_reports !== undefined) {
            setEmailReports(prefs.email_reports);
          }
        })
        .catch((err) => {
          console.warn('Failed to load preferences:', err);
        });
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

    setIsSaving(true);
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
        // Update preferences separately
        await updateUserPreferences(selectedUser.id, {
          spoken_text_type: spokenTextType,
          interaction_mode: interactionMode,
          email_reports: emailReports,
        });
      }
    } catch {
      // Error is handled by the store
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleClose();
    }
  };

  const title = mode === 'create' ? 'Nieuwe gebruiker' : 'Gebruiker bewerken';
  const displayError = localError || error;
  const isFormLoading = isLoading || isSaving;

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
                disabled={isFormLoading}
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
                disabled={isFormLoading || mode === 'edit'}
                className={mode === 'edit' ? 'bg-muted' : ''}
              />
              {mode === 'edit' && (
                <p className="text-xs text-muted-foreground">
                  E-mailadres kan niet worden gewijzigd
                </p>
              )}
            </div>

            {mode === 'edit' && (
              <>
                <div className="space-y-2">
                  <label htmlFor="spokenTextType" className="text-sm font-medium">
                    Spraakweergave
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setSpokenTextType('summarize')}
                      disabled={isFormLoading}
                      className={`flex items-center justify-center gap-2 p-3 rounded-md border transition-colors ${
                        spokenTextType === 'summarize'
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
                      }`}
                    >
                      <FileText className="h-4 w-4" />
                      <span className="text-sm font-medium">Samenvatten</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setSpokenTextType('dictate')}
                      disabled={isFormLoading}
                      className={`flex items-center justify-center gap-2 p-3 rounded-md border transition-colors ${
                        spokenTextType === 'dictate'
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
                      }`}
                    >
                      <Mic className="h-4 w-4" />
                      <span className="text-sm font-medium">Dicteer</span>
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {spokenTextType === 'summarize'
                      ? 'AI vat antwoorden samen voor spraak'
                      : 'AI leest antwoorden volledig voor'}
                  </p>
                </div>

                <div className="space-y-2">
                  <label htmlFor="interactionMode" className="text-sm font-medium">
                    Interactiemodus
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setInteractionMode('feedback')}
                      disabled={isFormLoading}
                      className={`flex items-center justify-center gap-2 p-3 rounded-md border transition-colors ${
                        interactionMode === 'feedback'
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
                      }`}
                    >
                      <MessageSquare className="h-4 w-4" />
                      <span className="text-sm font-medium">Feedback</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setInteractionMode('listen')}
                      disabled={isFormLoading}
                      className={`flex items-center justify-center gap-2 p-3 rounded-md border transition-colors ${
                        interactionMode === 'listen'
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
                      }`}
                    >
                      <Headphones className="h-4 w-4" />
                      <span className="text-sm font-medium">Luisteren</span>
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {interactionMode === 'feedback'
                      ? 'AI denkt actief mee en geeft suggesties'
                      : 'AI noteert alleen zonder tussenkomst'}
                  </p>
                </div>

                <div className="space-y-2">
                  <label htmlFor="emailReports" className="text-sm font-medium">
                    Rapporten per e-mail
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setEmailReports(true)}
                      disabled={isFormLoading}
                      className={`flex items-center justify-center gap-2 p-3 rounded-md border transition-colors ${
                        emailReports
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
                      }`}
                    >
                      <Mail className="h-4 w-4" />
                      <span className="text-sm font-medium">Aan</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setEmailReports(false)}
                      disabled={isFormLoading}
                      className={`flex items-center justify-center gap-2 p-3 rounded-md border transition-colors ${
                        !emailReports
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
                      }`}
                    >
                      <MailX className="h-4 w-4" />
                      <span className="text-sm font-medium">Uit</span>
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {emailReports
                      ? 'Rapporten worden automatisch per e-mail verzonden'
                      : 'Rapporten worden niet per e-mail verzonden'}
                  </p>
                </div>
              </>
            )}
          </CardContent>

          <CardFooter className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isFormLoading}
            >
              Annuleren
            </Button>
            <Button type="submit" disabled={isFormLoading}>
              {isFormLoading ? (
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
