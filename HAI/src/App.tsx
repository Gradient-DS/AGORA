/**
 * Main application component for AGORA HAI using AG-UI Protocol.
 */

import { useEffect, useRef } from 'react';
import { MainLayout } from '@/components/layout/MainLayout';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { DebugPanel } from '@/components/debug/DebugPanel';
import { ApprovalDialog } from '@/components/approval/ApprovalDialog';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useVoiceMode } from '@/hooks/useVoiceMode';
import {
  useSessionStore,
  useApprovalStore,
  useConnectionStore,
  useVoiceStore,
  useAgentStore,
  useUserStore,
  useMessageStore,
  useToolCallStore,
} from '@/stores';
import { useHistoryStore } from '@/stores/useHistoryStore';
import { fetchSessionHistory } from '@/lib/api/sessions';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';

export default function App() {
  const initializeSession = useSessionStore((state) => state.initializeSession);
  const session = useSessionStore((state) => state.session);
  const initializeUser = useUserStore((state) => state.initializeUser);
  const currentUser = useUserStore((state) => state.currentUser);
  const loadAgentsFromAPI = useAgentStore((state) => state.loadAgentsFromAPI);
  const fetchSessions = useHistoryStore((state) => state.fetchSessions);
  const messages = useMessageStore((state) => state.messages);
  const replaceMessages = useMessageStore((state) => state.replaceMessages);
  const replaceToolCalls = useToolCallStore((state) => state.replaceToolCalls);
  const { sendMessage, sendToolApproval, reconnect } = useWebSocket();
  const { toggleVoice } = useVoiceMode();
  const connectionStatus = useConnectionStore((state) => state.status);
  const connectionError = useConnectionStore((state) => state.error);

  const currentApproval = useApprovalStore((state) => state.currentApproval);
  const pendingApprovals = useApprovalStore((state) => state.pendingApprovals);
  const removeApproval = useApprovalStore((state) => state.removeApproval);
  const setCurrentApproval = useApprovalStore((state) => state.setCurrentApproval);

  const isVoiceActive = useVoiceStore((state) => state.isActive);

  useEffect(() => {
    initializeSession();
    initializeUser();
    loadAgentsFromAPI();
  }, [initializeSession, initializeUser, loadAgentsFromAPI]);

  // Track which session we've loaded history for to avoid duplicate loads
  const loadedHistoryForSession = useRef<string | null>(null);

  // Load history for restored session on page refresh
  useEffect(() => {
    const loadSessionHistory = async () => {
      // Skip if we've already loaded history for this session
      if (!session?.id || loadedHistoryForSession.current === session.id) {
        return;
      }

      // Only load if messages are empty (page was refreshed or session switched)
      if (messages.length > 0) {
        // Mark as loaded since there's already content
        loadedHistoryForSession.current = session.id;
        return;
      }

      // Mark as loading to prevent duplicate requests
      loadedHistoryForSession.current = session.id;

      try {
        console.log('[App] Loading history for session:', session.id);
        const { messages: historyMessages, toolCalls } = await fetchSessionHistory(session.id);
        if (historyMessages.length > 0) {
          replaceMessages(historyMessages);
          replaceToolCalls(toolCalls);
          console.log('[App] Loaded', historyMessages.length, 'messages and', toolCalls.length, 'tool calls');
        }
      } catch (error) {
        // Session might not have history yet (new session), that's ok
        console.log('[App] No history found for session (may be new):', error);
      }
    };

    loadSessionHistory();
  }, [session?.id, messages.length, replaceMessages, replaceToolCalls]);

  // Fetch sessions when user changes
  useEffect(() => {
    if (currentUser) {
      fetchSessions(currentUser.id);
    }
  }, [currentUser, fetchSessions]);

  const handleSendMessage = (message: string) => {
    sendMessage(message);
  };

  const handleApprove = (approvalId: string, feedback?: string) => {
    sendToolApproval(approvalId, true, feedback);
    removeApproval(approvalId);
  };

  const handleReject = (approvalId: string, feedback?: string) => {
    sendToolApproval(approvalId, false, feedback);
    removeApproval(approvalId);
  };

  const currentIndex = currentApproval
    ? pendingApprovals.findIndex((a) => a.approvalId === currentApproval.approvalId)
    : -1;

  const handleNavigate = (direction: 'prev' | 'next') => {
    if (currentIndex === -1) return;
    const newIndex = direction === 'prev' ? currentIndex - 1 : currentIndex + 1;
    if (newIndex >= 0 && newIndex < pendingApprovals.length) {
      setCurrentApproval(pendingApprovals[newIndex] ?? null);
    }
  };

  const isDisabled = connectionStatus !== 'connected';

  return (
    <MainLayout onReconnect={reconnect}>
      <div className="h-full flex flex-col p-4 gap-4 overflow-hidden">
        {connectionError && (
          <Alert variant="destructive" className="flex-shrink-0">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Verbindingsfout</AlertTitle>
            <AlertDescription>{connectionError.message}</AlertDescription>
          </Alert>
        )}

        {currentApproval && (
          <ApprovalDialog
            approval={currentApproval}
            onApprove={handleApprove}
            onReject={handleReject}
            currentIndex={currentIndex}
            totalCount={pendingApprovals.length}
            onNavigate={handleNavigate}
          />
        )}

        <div className="flex-1 flex gap-4 min-h-0">
          <div className="w-1/2 h-full">
            <ChatInterface
              onSendMessage={handleSendMessage}
              disabled={isDisabled}
              onToggleVoice={toggleVoice}
              isVoiceActive={isVoiceActive}
            />
          </div>

          <div className="w-1/2 h-full">
            <DebugPanel />
          </div>
        </div>
      </div>
    </MainLayout>
  );
}
