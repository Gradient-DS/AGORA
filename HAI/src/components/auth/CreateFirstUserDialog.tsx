import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { UserPlus, AlertCircle, Loader2 } from 'lucide-react';
import { createUser } from '@/lib/api/users';
import { useUserStore } from '@/stores/useUserStore';

interface CreateFirstUserDialogProps {
  open: boolean;
}

export function CreateFirstUserDialog({ open }: CreateFirstUserDialogProps) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const loadUsers = useUserStore((state) => state.loadUsers);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Naam is verplicht');
      return;
    }

    if (!email.trim()) {
      setError('E-mail is verplicht');
      return;
    }

    if (!email.includes('@')) {
      setError('Voer een geldig e-mailadres in');
      return;
    }

    setIsLoading(true);
    try {
      await createUser({
        name: name.trim(),
        email: email.trim(),
      });
      // Reload users - this will auto-select the first user
      await loadUsers();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Kon gebruiker niet aanmaken';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-md" hideCloseButton onPointerDownOutside={(e: Event) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            Welkom bij AGORA
          </DialogTitle>
          <DialogDescription>
            Er zijn nog geen gebruikers aangemaakt. Maak uw eerste gebruikersaccount aan om te beginnen.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Naam</Label>
              <Input
                id="name"
                type="text"
                placeholder="Voer uw naam in..."
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="email">E-mail</Label>
              <Input
                id="email"
                type="email"
                placeholder="naam@voorbeeld.nl"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={isLoading || !name.trim() || !email.trim()}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Aanmaken...
                </>
              ) : (
                <>
                  <UserPlus className="h-4 w-4 mr-2" />
                  Account aanmaken
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
