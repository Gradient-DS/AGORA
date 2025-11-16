import { Card } from '@/components/ui/card';
import { ChatMessageList } from './ChatMessageList';
import { ChatInput } from './ChatInput';
import { useMessageStore } from '@/stores';

interface ChatInterfaceProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
  onToggleVoice?: () => void;
  isVoiceActive?: boolean;
}

export function ChatInterface({ onSendMessage, disabled = false, onToggleVoice, isVoiceActive }: ChatInterfaceProps) {
  const messages = useMessageStore((state) => state.messages);
  const currentStatus = useMessageStore((state) => state.currentStatus);
  const isTyping = useMessageStore((state) => state.isTyping);

  return (
    <Card className="flex flex-col h-full overflow-hidden">
      <div className="border-b p-4 flex-shrink-0">
        <h2 className="text-lg font-semibold">Chat</h2>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        <ChatMessageList 
          messages={messages} 
          status={currentStatus}
          isTyping={isTyping}
        />
      </div>

      <div className="border-t p-4 flex-shrink-0">
        <ChatInput 
          onSend={onSendMessage} 
          disabled={disabled}
          onToggleVoice={onToggleVoice}
          isVoiceActive={isVoiceActive}
        />
      </div>
    </Card>
  );
}

