import { useEffect, useRef } from 'react';
import { HAIWebSocketClient } from '@/lib/websocket';
import { 
  useConnectionStore, 
  useMessageStore, 
  useSessionStore, 
  useApprovalStore 
} from '@/stores';
import type { HAIMessage } from '@/types/schemas';
import { env } from '@/lib/env';

function getOrCreateClient(): HAIWebSocketClient {
  if (!globalClient) {
    console.log('[WebSocket Singleton] Creating global client instance');
    globalClient = new HAIWebSocketClient({
      url: env.VITE_WS_URL,
      maxReconnectAttempts: 5,
      reconnectInterval: 3000,
      maxReconnectInterval: 30000,
    });
  }
  return globalClient;
}

let globalClient: HAIWebSocketClient | null = null;
let activeSubscriptions = 0;
let hasInitiatedConnection = false;

export function useWebSocket() {
  const clientRef = useRef<HAIWebSocketClient | null>(null);
  const setStatus = useConnectionStore((state) => state.setStatus);
  const setError = useConnectionStore((state) => state.setError);
  const addMessage = useMessageStore((state) => state.addMessage);
  const updateMessageContent = useMessageStore((state) => state.updateMessageContent);
  const finalizeMessage = useMessageStore((state) => state.finalizeMessage);
  const updateStatus = useMessageStore((state) => state.updateStatus);
  const session = useSessionStore((state) => state.session);
  const updateActivity = useSessionStore((state) => state.updateActivity);
  const addApproval = useApprovalStore((state) => state.addApproval);

  useEffect(() => {
    const client = getOrCreateClient();
    clientRef.current = client;
    
    activeSubscriptions++;
    console.log('[useWebSocket] Subscribing (active: %d)', activeSubscriptions);

    const unsubscribeStatus = client.onStatusChange((status) => {
      setStatus(status);
    });

    const unsubscribeError = client.onError((error) => {
      setError(error);
      console.error('[useWebSocket] WebSocket error:', error);
    });

    const unsubscribeMessage = client.onMessage((message: HAIMessage) => {
      updateActivity();

      switch (message.type) {
        case 'assistant_message':
          addMessage({
            id: `msg-${Date.now()}-${Math.random()}`,
            type: 'assistant',
            content: message.content,
            agent_id: message.agent_id ?? undefined,
            metadata: message.metadata,
          });
          break;

        case 'assistant_message_chunk':
          {
            const existingMessage = useMessageStore.getState().messages.find(
              (msg) => msg.id === message.message_id
            );

            if (!existingMessage) {
              if (message.content) {
                addMessage({
                  id: message.message_id,
                  type: 'assistant',
                  content: message.content,
                  agent_id: message.agent_id ?? undefined,
                  isStreaming: !message.is_final,
                });
              }
            } else {
              if (message.content) {
                updateMessageContent(message.message_id, message.content, true);
              }
              if (message.is_final) {
                finalizeMessage(message.message_id);
              }
            }
          }
          break;

        case 'status':
          updateStatus(message.status);
          break;

        case 'tool_call':
          // Add tool call as a special message in the chat
          addMessage({
            id: message.tool_call_id,
            type: 'tool_call',
            content: message.tool_name,
            tool_name: message.tool_name,
            tool_status: message.status,
            agent_id: message.agent_id ?? undefined,
            metadata: {
              parameters: message.parameters,
              result: message.result,
            },
          });
          break;

        case 'tool_approval_request':
          addApproval(message);
          break;

        case 'error':
          console.error('[useWebSocket] Server error:', message.message);
          setError(new Error(message.message));
          break;
      }
    });

    if (!hasInitiatedConnection) {
      const status = client.getStatus();
      console.log('[useWebSocket] First subscription, client status: %s', status);
      
      if (status === 'disconnected' || status === 'error') {
        console.log('[useWebSocket] Initiating connection');
        hasInitiatedConnection = true;
        setTimeout(() => client.connect(), 0);
      }
    }

    return () => {
      activeSubscriptions--;
      console.log('[useWebSocket] Unsubscribing (active: %d)', activeSubscriptions);
      
      unsubscribeStatus();
      unsubscribeError();
      unsubscribeMessage();

      if (activeSubscriptions === 0) {
        console.log('[useWebSocket] No active subscriptions, scheduling cleanup check');
        setTimeout(() => {
          if (activeSubscriptions === 0 && globalClient) {
            console.log('[useWebSocket] Disconnecting idle client');
            globalClient.disconnect();
            globalClient = null;
            hasInitiatedConnection = false;
          }
        }, 100);
      }
    };
  }, [setStatus, setError, addMessage, updateMessageContent, finalizeMessage, updateStatus, addApproval, updateActivity]);

  const sendMessage = (content: string) => {
    if (clientRef.current && session) {
      addMessage({
        id: `msg-${Date.now()}-${Math.random()}`,
        type: 'user',
        content,
      });
      clientRef.current.sendUserMessage(content, session.id);
      updateActivity();
    }
  };

  const sendToolApproval = (approvalId: string, approved: boolean, feedback?: string) => {
    if (clientRef.current) {
      clientRef.current.sendToolApproval(approvalId, approved, feedback);
      updateActivity();
    }
  };

  const reconnect = () => {
    const client = clientRef.current || globalClient;
    if (client) {
      console.log('[useWebSocket] Manual reconnect requested');
      hasInitiatedConnection = false;
      client.reset();
      client.connect();
      hasInitiatedConnection = true;
    }
  };

  return {
    sendMessage,
    sendToolApproval,
    reconnect,
    client: clientRef.current,
  };
}

