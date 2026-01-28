/**
 * Chat interface component for AG-UI Protocol communication.
 */

import { Card } from '@/components/ui/card';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';
import { useMessageStore, useUserStore } from '@/stores';
import { useTTS } from '@/hooks/useTTS';

interface ChatInterfaceProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
  onToggleVoice?: () => void;
  isVoiceActive?: boolean;
  /** Separate disabled state for voice mode (requires active connection) */
  voiceDisabled?: boolean;
}

export function ChatInterface({
  onSendMessage,
  disabled = false,
  onToggleVoice,
  isVoiceActive,
  voiceDisabled = false,
}: ChatInterfaceProps) {
  const messages = useMessageStore((state) => state.messages);
  const processingStatus = useMessageStore((state) => state.processingStatus);
  const isTyping = useMessageStore((state) => state.isTyping);
  const currentUser = useUserStore((state) => state.currentUser);

  // Initialize TTS hook to handle spoken text events
  useTTS();

  return (
    <Card className="flex flex-col h-full overflow-hidden">
      <div className="border-b p-4 flex-shrink-0">
        <h2 className="text-lg font-semibold">Chat</h2>
        {currentUser && messages.length === 0 && (
          <p className="text-sm text-muted-foreground mt-1">
            Welkom {currentUser.name}! Hoe kan ik je vandaag helpen met je inspectie?
          </p>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        <ChatMessageList messages={messages} status={processingStatus} isTyping={isTyping} />
      </div>

      <div className="border-t p-4 flex-shrink-0">
        <ChatInput
          onSend={onSendMessage}
          disabled={disabled}
          onToggleVoice={onToggleVoice}
          isVoiceActive={isVoiceActive}
          voiceDisabled={voiceDisabled}
        />
      </div>
    </Card>
  );
}
