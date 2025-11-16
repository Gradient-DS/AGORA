import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useConnectionStore, useSessionStore } from '@/stores';
import { Wifi, WifiOff, Loader2, RefreshCw } from 'lucide-react';
import { env } from '@/lib/env';

export function Header({ onReconnect }: { onReconnect?: () => void }) {
  const status = useConnectionStore((state) => state.status);
  const error = useConnectionStore((state) => state.error);
  const session = useSessionStore((state) => state.session);

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
            <Badge 
              variant={getStatusVariant()}
              className="flex items-center gap-1"
              role="status"
              aria-label={`Connection status: ${status}`}
            >
              {getStatusIcon()}
              <span className="capitalize">{status}</span>
            </Badge>
            
            {(status === 'error' || status === 'disconnected') && onReconnect && (
              <Button
                size="sm"
                variant="outline"
                onClick={onReconnect}
                className="flex items-center gap-1"
                aria-label="Retry connection"
              >
                <RefreshCw className="h-3 w-3" />
                Retry
              </Button>
            )}
          </div>
        </div>

        {error && status === 'error' && (
          <div className="text-xs text-destructive bg-destructive/10 p-2 rounded">
            <strong>Connection Error:</strong> {error.message}
          </div>
        )}
      </header>
    </Card>
  );
}

