import { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';
import { Loader2 } from 'lucide-react';
import type { Message } from '@/types';
import type { ProcessingStatus } from '@/types/schemas';

interface ChatMessageListProps {
  messages: Message[];
  status: ProcessingStatus | null;
  isTyping: boolean;
}

const statusMessages: Record<ProcessingStatus, string> = {
  thinking: 'Aan het denken...',
  routing: 'Agent wordt gekozen...',
  executing_tools: 'Tools worden uitgevoerd...',
  completed: 'Afgerond',
};

export function ChatMessageList({ messages, status, isTyping }: ChatMessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, status, isTyping]);

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Conversatie berichten"
      className="h-full overflow-y-auto p-4 space-y-4"
    >
      {messages.length === 0 && (
        <div className="flex items-center justify-center h-full text-muted-foreground">
          <p>Start een gesprek door hieronder een bericht te typen</p>
        </div>
      )}

      {messages.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}

      {status && status !== 'completed' && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span aria-live="polite">{statusMessages[status]}</span>
        </div>
      )}

      {isTyping && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span aria-live="polite">Assistent is aan het typen...</span>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}

