import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import type { Message } from '@/types';
import { Bot, User } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ToolCallReference } from './ToolCallReference';
import { DownloadLinks } from './DownloadLinks';
import { useEffect } from 'react';
import { useToolCallStore, useAgentStore } from '@/stores';

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const addToolCall = useToolCallStore((state) => state.addToolCall);
  const updateToolCall = useToolCallStore((state) => state.updateToolCall);
  const setAgentActive = useAgentStore((state) => state.setAgentActive);
  const setAgentIdle = useAgentStore((state) => state.setAgentIdle);
  const setAgentExecutingTools = useAgentStore((state) => state.setAgentExecutingTools);

  // Track agent status based on message chunks
  useEffect(() => {
    if (message.agent_id) {
      if (message.isStreaming) {
        setAgentActive(message.agent_id);
      } else if (message.type === 'assistant') {
        // Delay setting to idle to account for tool calls
        const timer = setTimeout(() => {
          if (message.agent_id) {
            setAgentIdle(message.agent_id);
          }
        }, 1000);
        return () => clearTimeout(timer);
      }
    }
    return undefined;
  }, [message.agent_id, message.isStreaming, message.type, setAgentActive, setAgentIdle]);

  // Handle tool call messages - add to tool call store and show compact reference
  useEffect(() => {
    if (message.type === 'tool_call') {
      const toolCallId = message.id || `tool-${Date.now()}`;
      const agentId = message.agent_id;
      const toolStatus = message.tool_status;
      
      console.log('[ChatMessage] Processing tool call:', {
        id: toolCallId,
        toolName: message.tool_name,
        status: toolStatus,
        agentId,
      });
      
      if (toolStatus === 'started') {
        if (agentId) {
          setAgentExecutingTools(agentId);
        }
        addToolCall({
          id: toolCallId,
          toolName: message.tool_name || message.content,
          status: 'started',
          parameters: message.metadata?.parameters as Record<string, unknown> | undefined,
          messageId: message.id,
          agentId,
        });
      } else if (toolStatus === 'completed' || toolStatus === 'failed') {
        updateToolCall(toolCallId, {
          status: toolStatus,
          result: message.metadata?.result as string | undefined,
        });
        // Set agent back to active after tool execution
        if (agentId) {
          setAgentActive(agentId);
        }
      }
    }
  }, [message.id, message.type, message.tool_status, message.agent_id, addToolCall, updateToolCall, setAgentExecutingTools, setAgentActive]);

  if (message.type === 'tool_call') {
    return (
      <div className="flex justify-center mb-2">
        <ToolCallReference
          toolName={message.tool_name || message.content}
          status={message.tool_status || 'started'}
          toolCallId={message.id || `tool-${Date.now()}`}
        />
      </div>
    );
  }

  const isUser = message.type === 'user';
  const timestamp = message.timestamp.toLocaleTimeString('nl-NL', { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: false
  });

  // Get agent display name
  const getAgent = useAgentStore((state) => state.getAgent);
  const agentName = message.agent_id ? getAgent(message.agent_id)?.name || message.agent_id : null;

  // Check if message contains download URLs
  const downloadUrls = message.metadata?.download_urls as { json?: string; pdf?: string } | undefined;
  const reportId = message.metadata?.report_id as string | undefined;
  const hasDownloadLinks = downloadUrls && (downloadUrls.json || downloadUrls.pdf);

  return (
    <article
      aria-label={`Bericht van ${message.type}`}
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
            isUser 
              ? 'bg-primary text-primary-foreground' 
              : 'bg-muted text-foreground'
          )}
        >
          <div className="text-sm prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-black/5 dark:prose-pre:bg-white/5 prose-pre:p-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
            {message.isStreaming && (
              <span className="inline-block w-2 h-4 ml-1 bg-current animate-pulse" aria-label="Streaming indicatie" />
            )}
          </div>
        </div>

        {hasDownloadLinks && !isUser && (
          <DownloadLinks
            jsonUrl={downloadUrls?.json}
            pdfUrl={downloadUrls?.pdf}
            reportId={reportId}
          />
        )}
        
        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1 px-1">
          <span aria-label={`Verzonden om ${timestamp}`}>
            {timestamp}
          </span>
          {agentName && (
            <>
              <span>-</span>
              <span className="font-medium">
                {agentName}
              </span>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

