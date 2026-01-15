import { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Plus, Loader2, X } from 'lucide-react';
import { SessionListItem } from './SessionListItem';
import { useHistoryStore } from '@/stores/useHistoryStore';
import { useSessionStore, useMessageStore, useUserStore, useToolCallStore } from '@/stores';
import { generateSessionId } from '@/lib/utils';

export function ConversationSidebar() {
  const isSidebarOpen = useHistoryStore((state) => state.isSidebarOpen);
  const setSidebarOpen = useHistoryStore((state) => state.setSidebarOpen);
  const sessions = useHistoryStore((state) => state.sessions);
  const isLoading = useHistoryStore((state) => state.isLoading);
  const fetchSessions = useHistoryStore((state) => state.fetchSessions);
  const deleteSessionFromStore = useHistoryStore((state) => state.deleteSession);
  const renameSessionInStore = useHistoryStore((state) => state.renameSession);

  const currentSession = useSessionStore((state) => state.session);
  const switchToSession = useSessionStore((state) => state.switchToSession);
  const startNewSession = useSessionStore((state) => state.startNewSession);

  const clearMessages = useMessageStore((state) => state.clearMessages);
  const processingStatus = useMessageStore((state) => state.processingStatus);

  const clearToolCalls = useToolCallStore((state) => state.clearToolCalls);

  const currentUser = useUserStore((state) => state.currentUser);

  // Check if operations should be disabled (during active run)
  const isDisabled = processingStatus !== null;

  // Fetch sessions when sidebar opens or user changes
  useEffect(() => {
    if (isSidebarOpen && currentUser) {
      fetchSessions(currentUser.id);
    }
  }, [isSidebarOpen, currentUser, fetchSessions]);

  const handleSelectSession = (sessionId: string) => {
    if (isDisabled || sessionId === currentSession?.id) return;

    // Close sidebar first for better UX
    setSidebarOpen(false);

    // Clear current messages and tool calls
    clearMessages();
    clearToolCalls();

    // Switch to the selected session - App.tsx will handle loading history
    switchToSession(sessionId);
  };

  const handleNewSession = () => {
    if (isDisabled) return;

    // Same behavior as "Nieuwe Inspectie" button - clear and reload
    // Generate new session ID and store before reload
    const newSessionId = generateSessionId();
    localStorage.setItem('session_id', newSessionId);
    localStorage.setItem('session_started', new Date().toISOString());
    window.location.reload();
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (isDisabled) return;

    await deleteSessionFromStore(sessionId);

    // If we deleted the current session, start a new one
    if (sessionId === currentSession?.id) {
      clearMessages();
      startNewSession();
    }
  };

  const handleRenameSession = async (sessionId: string, newTitle: string) => {
    await renameSessionInStore(sessionId, newTitle);
  };

  const handleBackdropClick = () => {
    setSidebarOpen(false);
  };

  if (!isSidebarOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-30"
        onClick={handleBackdropClick}
        aria-hidden="true"
      />

      {/* Sidebar */}
      <aside
        className={`
          fixed top-0 left-0 h-full w-80 bg-background border-r z-40
          transform transition-transform duration-300 ease-in-out
          ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        aria-label="Conversatiegeschiedenis"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="font-semibold text-lg">Gesprekken</h2>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSidebarOpen(false)}
            aria-label="Sluit zijbalk"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* New Conversation Button */}
        <div className="p-4 border-b">
          <Button
            onClick={handleNewSession}
            disabled={isDisabled}
            className="w-full"
          >
            <Plus className="h-4 w-4 mr-2" />
            Nieuwe inspectie
          </Button>
        </div>

        {/* Sessions List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>Geen gesprekken gevonden</p>
              <p className="text-sm mt-1">Start een nieuw gesprek om te beginnen</p>
            </div>
          ) : (
            sessions.map((session) => (
              <SessionListItem
                key={session.sessionId}
                session={session}
                isActive={session.sessionId === currentSession?.id}
                isDisabled={isDisabled}
                onSelect={() => handleSelectSession(session.sessionId)}
                onDelete={() => handleDeleteSession(session.sessionId)}
                onRename={(newTitle) => handleRenameSession(session.sessionId, newTitle)}
              />
            ))
          )}
        </div>
      </aside>
    </>
  );
}
