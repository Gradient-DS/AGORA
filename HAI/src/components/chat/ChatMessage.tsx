/**
 * Chat message component for AG-UI Protocol messages.
 */

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import type { ChatMessage as ChatMessageType } from '@/types';
import { Bot, User } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { DownloadLinks } from './DownloadLinks';
import { ToolCallReference } from './ToolCallReference';
import { useAgentStore } from '@/stores';

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const getAgent = useAgentStore((state) => state.getAgent);

  if (message.role === 'tool') {
    return (
      <div className="flex justify-center mb-2">
        <ToolCallReference
          toolName={message.toolName || message.content}
          status={message.toolStatus || 'started'}
          toolCallId={message.id}
        />
      </div>
    );
  }

  const isUser = message.role === 'user';
  const timestamp = message.timestamp.toLocaleTimeString('nl-NL', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const agentName = message.agentId ? getAgent(message.agentId)?.name || message.agentId : null;

  const downloadUrls = message.metadata?.download_urls as
    | { json?: string; pdf?: string }
    | undefined;
  const reportId = message.metadata?.report_id as string | undefined;
  const hasDownloadLinks = downloadUrls && (downloadUrls.json || downloadUrls.pdf);

  return (
    <article
      aria-label={`Bericht van ${message.role}`}
      className={cn(
        'flex gap-3 mb-4 animate-in fade-in slide-in-from-bottom-2',
        isUser && 'flex-row-reverse'
      )}
    >
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className={cn(isUser ? 'bg-primary' : 'bg-secondary')}>
          {isUser ? (
            <User className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Bot className="h-4 w-4" aria-hidden="true" />
          )}
        </AvatarFallback>
      </Avatar>

      <div className={cn('flex flex-col max-w-[80%] gap-2', isUser && 'items-end')}>
        <div
          className={cn(
            'rounded-lg px-4 py-2 break-words',
            isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
          )}
        >
          <div className="text-sm prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-black/5 dark:prose-pre:bg-white/5 prose-pre:p-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            {message.isStreaming && (
              <span
                className="inline-block w-2 h-4 ml-1 bg-current animate-pulse"
                aria-label="Streaming indicatie"
              />
            )}
          </div>
        </div>

        {hasDownloadLinks && !isUser && (
          <DownloadLinks jsonUrl={downloadUrls?.json} pdfUrl={downloadUrls?.pdf} reportId={reportId} />
        )}

        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1 px-1">
          <span aria-label={`Verzonden om ${timestamp}`}>{timestamp}</span>
          {agentName && (
            <>
              <span>-</span>
              <span className="font-medium">{agentName}</span>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
