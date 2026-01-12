import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel
} from '@/components/ui/dropdown-menu';
import { useConnectionStore, useSessionStore, useMessageStore, useUserStore, useAdminStore } from '@/stores';
import { useHistoryStore } from '@/stores/useHistoryStore';
import { Wifi, WifiOff, Loader2, RefreshCw, Plus, ChevronDown, User, Menu, Settings, Mic, FileText } from 'lucide-react';
import { env } from '@/lib/env';

export function Header({ onReconnect }: { onReconnect?: () => void }) {
  const status = useConnectionStore((state) => state.status);
  const error = useConnectionStore((state) => state.error);
  const session = useSessionStore((state) => state.session);
  const clearSession = useSessionStore((state) => state.clearSession);
  const initializeSession = useSessionStore((state) => state.initializeSession);
  const clearMessages = useMessageStore((state) => state.clearMessages);
  const currentUser = useUserStore((state) => state.currentUser);
  const users = useUserStore((state) => state.users);
  const usersLoading = useUserStore((state) => state.isLoading);
  const setUser = useUserStore((state) => state.setUser);
  const preferences = useUserStore((state) => state.preferences);
  const toggleSidebar = useHistoryStore((state) => state.toggleSidebar);
  const fetchSessions = useHistoryStore((state) => state.fetchSessions);
  const openAdminPanel = useAdminStore((state) => state.openAdminPanel);

  const handleNewConversation = (userId?: string) => {
    if (userId) {
      setUser(userId);
      // Refresh sessions for the new user (sidebar stays open per design decision)
      fetchSessions(userId);
    }
    clearSession();
    clearMessages();
    initializeSession();
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
          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={toggleSidebar}
              aria-label="Open conversatiegeschiedenis"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-2xl font-bold">{env.VITE_APP_NAME}</h1>
              <div className="flex items-center gap-2">
                {session && (
                  <p className="text-xs text-muted-foreground">
                    Session: {session.id.slice(0, 12)}...
                  </p>
                )}
                {currentUser && (
                  <Badge variant="secondary" className="text-xs">
                    <User className="h-3 w-3 mr-1" />
                    {currentUser.name}
                  </Badge>
                )}
                {preferences?.spoken_text_type && (
                  <Badge variant="outline" className="text-xs">
                    {preferences.spoken_text_type === 'dictate' ? (
                      <>
                        <Mic className="h-3 w-3 mr-1" />
                        Dicteer
                      </>
                    ) : (
                      <>
                        <FileText className="h-3 w-3 mr-1" />
                        Samenvatten
                      </>
                    )}
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleNewConversation()}
                className="flex items-center gap-1 rounded-r-none border-r-0"
                aria-label="Start nieuwe inspectie"
              >
                <Plus className="h-3 w-3" />
                Nieuwe inspectie
              </Button>
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    size="sm"
                    variant="outline"
                    className="rounded-l-none px-2"
                    aria-label="Selecteer inspecteur"
                    disabled={usersLoading}
                  >
                    {usersLoading ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <ChevronDown className="h-3 w-3" />
                    )}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuLabel>Selecteer inspecteur</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {users.length === 0 ? (
                    <DropdownMenuItem disabled>
                      <span className="text-muted-foreground">Geen gebruikers beschikbaar</span>
                    </DropdownMenuItem>
                  ) : (
                    users.map((user) => (
                      <DropdownMenuItem
                        key={user.id}
                        onClick={() => handleNewConversation(user.id)}
                        className="flex flex-col items-start py-2 cursor-pointer"
                      >
                        <div className="font-medium">{user.name}</div>
                        <div className="text-xs text-muted-foreground">{user.email}</div>
                      </DropdownMenuItem>
                    ))
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <Button
              size="sm"
              variant="ghost"
              onClick={openAdminPanel}
              aria-label="Open beheerdersinstellingen"
            >
              <Settings className="h-4 w-4" />
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

