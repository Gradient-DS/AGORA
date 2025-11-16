import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useConnectionStore, useSessionStore, useMessageStore } from '@/stores';
import { Wifi, WifiOff, Loader2, RefreshCw, Plus } from 'lucide-react';
import { env } from '@/lib/env';

export function Header({ onReconnect }: { onReconnect?: () => void }) {
  const status = useConnectionStore((state) => state.status);
  const error = useConnectionStore((state) => state.error);
  const session = useSessionStore((state) => state.session);
  const clearSession = useSessionStore((state) => state.clearSession);
  const initializeSession = useSessionStore((state) => state.initializeSession);
  const clearMessages = useMessageStore((state) => state.clearMessages);

  const handleNewConversation = () => {
    // Clear session and messages
    clearSession();
    clearMessages();
    // Reinitialize with new session
    initializeSession();
    // Force page reload to reconnect with new session
    window.location.reload();
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'connected':
        return <Wifi className="h-4 w-4" aria-hidden="true" />;
      case 'connecting':
      case 'reconnecting':
        return <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />;
      default:
        return <WifiOff className="h-4 w-4" aria-hidden="true" />;
    }
  };

  const getStatusVariant = () => {
    switch (status) {
      case 'connected':
        return 'default';
      case 'connecting':
      case 'reconnecting':
        return 'secondary';
      default:
        return 'destructive';
    }
  };

  const getStatusLabel = () => {
    switch (status) {
      case 'connected':
        return 'verbonden';
      case 'connecting':
        return 'verbinden';
      case 'reconnecting':
        return 'opnieuw verbinden';
      case 'disconnected':
        return 'verbroken';
      case 'error':
        return 'fout';
      default:
        return status;
    }
  };

  return (
    <Card className="rounded-none border-x-0 border-t-0">
      <header className="flex flex-col gap-2 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">{env.VITE_APP_NAME}</h1>
            {session && (
              <p className="text-xs text-muted-foreground">
                Session: {session.id.slice(0, 12)}...
              </p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleNewConversation}
              className="flex items-center gap-1"
              aria-label="Start nieuwe inspectie"
            >
              <Plus className="h-3 w-3" />
              Nieuwe Inspectie
            </Button>
            
            <Badge 
              variant={getStatusVariant()}
              className="flex items-center gap-1"
              role="status"
              aria-label={`Verbindingsstatus: ${getStatusLabel()}`}
            >
              {getStatusIcon()}
              <span className="capitalize">{getStatusLabel()}</span>
            </Badge>
            
            {(status === 'error' || status === 'disconnected') && onReconnect && (
              <Button
                size="sm"
                variant="outline"
                onClick={onReconnect}
                className="flex items-center gap-1"
                aria-label="Probeer opnieuw verbinding te maken"
              >
                <RefreshCw className="h-3 w-3" />
                Opnieuw
              </Button>
            )}
          </div>
        </div>

        {error && status === 'error' && (
          <div className="text-xs text-destructive bg-destructive/10 p-2 rounded">
            <strong>Verbindingsfout:</strong> {error.message}
          </div>
        )}
      </header>
    </Card>
  );
}

