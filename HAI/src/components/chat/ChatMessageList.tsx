/**
 * Chat message list component for AG-UI Protocol messages.
 */

import { useRef, useState, useLayoutEffect } from 'react';
import { ChatMessage } from './ChatMessage';
import { LoadingIndicator } from './LoadingIndicator';
import type { ChatMessage as ChatMessageType } from '@/types';

type ProcessingStatus = 'thinking' | 'routing' | 'executing_tools' | null;

interface ChatMessageListProps {
  messages: ChatMessageType[];
  status: ProcessingStatus;
  isTyping: boolean;
}

export function ChatMessageList({ messages, status }: ChatMessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const prevMessagesLength = useRef(messages.length);

  const handleScroll = () => {
    const element = containerRef.current;
    if (!element) return;

    const { scrollTop, scrollHeight, clientHeight } = element;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
    setShouldAutoScroll(isAtBottom);
  };

  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element || !shouldAutoScroll) return;

    const isNewMessage = messages.length > prevMessagesLength.current;
    prevMessagesLength.current = messages.length;

    if (isNewMessage) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, shouldAutoScroll, status]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
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
