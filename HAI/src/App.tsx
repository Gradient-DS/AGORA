import { useEffect } from 'react';
import { MainLayout } from '@/components/layout/MainLayout';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { DebugPanel } from '@/components/debug/DebugPanel';
import { ApprovalDialog } from '@/components/approval/ApprovalDialog';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useVoiceMode } from '@/hooks/useVoiceMode';
import { useSessionStore, useApprovalStore, useConnectionStore, useVoiceStore, useAgentStore, useUserStore } from '@/stores';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';

export default function App() {
  const initializeSession = useSessionStore((state) => state.initializeSession);
  const initializeUser = useUserStore((state) => state.initializeUser);
  const loadAgentsFromAPI = useAgentStore((state) => state.loadAgentsFromAPI);
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
    ? pendingApprovals.findIndex(a => a.approval_id === currentApproval.approval_id)
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

