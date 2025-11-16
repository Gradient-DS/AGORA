import { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';
import { LoadingIndicator } from './LoadingIndicator';
import type { Message } from '@/types';
import type { ProcessingStatus } from '@/types/schemas';

interface ChatMessageListProps {
  messages: Message[];
  status: ProcessingStatus | null;
  isTyping: boolean;
}

export function ChatMessageList({ messages, status }: ChatMessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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

      <LoadingIndicator status={status} />

      <div ref={messagesEndRef} />
    </div>
  );
}

