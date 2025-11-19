import { useRef, useState, useLayoutEffect } from 'react';
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
  const containerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const prevMessagesLength = useRef(messages.length);

  // Determine if we should stick to bottom based on user scroll position
  const handleScroll = () => {
    const element = containerRef.current;
    if (!element) return;

    const { scrollTop, scrollHeight, clientHeight } = element;
    // If user is within 100px of bottom, enable auto-scroll
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
    setShouldAutoScroll(isAtBottom);
  };

  // Handle scrolling logic
  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element || !shouldAutoScroll) return;

    const isNewMessage = messages.length > prevMessagesLength.current;
    prevMessagesLength.current = messages.length;

    if (isNewMessage) {
      // New message: smooth scroll to bottom
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else {
      // Existing message update (streaming): instant scroll to prevent jitter
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, shouldAutoScroll, status]); // Added status to dependencies in case loading indicator appears

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

