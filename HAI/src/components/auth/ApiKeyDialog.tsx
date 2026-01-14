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
import { KeyRound, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/stores/useAuthStore';

interface ApiKeyDialogProps {
  open: boolean;
  onSubmit: (apiKey: string) => void;
}

export function ApiKeyDialog({ open, onSubmit }: ApiKeyDialogProps) {
  const [apiKey, setApiKey] = useState('');
  const authError = useAuthStore((state) => state.authError);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (apiKey.trim()) {
      onSubmit(apiKey.trim());
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-md" onPointerDownOutside={(e: Event) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            API-sleutel vereist
          </DialogTitle>
          <DialogDescription>
            Deze applicatie vereist authenticatie. Voer uw API-sleutel in om door te gaan.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          {authError && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{authError}</AlertDescription>
            </Alert>
          )}

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="apiKey">API-sleutel</Label>
              <Input
                id="apiKey"
                type="password"
                placeholder="Voer uw API-sleutel in..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={!apiKey.trim()}>
              Verbinden
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
