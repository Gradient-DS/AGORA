/**
 * AG-UI Protocol WebSocket hook for AGORA HAI.
 */

import { useEffect, useRef } from 'react';
import { AGUIWebSocketClient } from '@/lib/websocket';
import {
  useConnectionStore,
  useMessageStore,
  useSessionStore,
  useApprovalStore,
  useToolCallStore,
  useAgentStore,
} from '@/stores';
import {
  EventType,
  type AGUIEvent,
  type CustomEvent,
  isToolApprovalRequest,
  isAgoraError,
  parseToolApprovalRequest,
  parseAgoraError,
} from '@/types/schemas';
import { env } from '@/lib/env';

let globalClient: AGUIWebSocketClient | null = null;
let activeSubscriptions = 0;
let hasInitiatedConnection = false;

function getOrCreateClient(): AGUIWebSocketClient {
  if (!globalClient) {
    console.log('[AG-UI WebSocket] Creating global client instance');
    globalClient = new AGUIWebSocketClient({
      url: env.VITE_WS_URL,
      maxReconnectAttempts: 5,
      reconnectInterval: 3000,
      maxReconnectInterval: 30000,
    });
  }
  return globalClient;
}

export function useWebSocket() {
  const clientRef = useRef<AGUIWebSocketClient | null>(null);
  const currentMessageId = useRef<string | null>(null);
  const currentRunId = useRef<string | null>(null);
  const currentAgentId = useRef<string>('general-agent');

  const setStatus = useConnectionStore((state) => state.setStatus);
  const setError = useConnectionStore((state) => state.setError);
  const addMessage = useMessageStore((state) => state.addMessage);
  const updateMessageContent = useMessageStore((state) => state.updateMessageContent);
  const finalizeMessage = useMessageStore((state) => state.finalizeMessage);
  const setProcessingStatus = useMessageStore((state) => state.setProcessingStatus);
  const session = useSessionStore((state) => state.session);
  const updateActivity = useSessionStore((state) => state.updateActivity);
  const addApproval = useApprovalStore((state) => state.addApproval);
  const addToolCall = useToolCallStore((state) => state.addToolCall);
  const updateToolCall = useToolCallStore((state) => state.updateToolCall);
  const setAgentActive = useAgentStore((state) => state.setAgentActive);
  const setAgentIdle = useAgentStore((state) => state.setAgentIdle);
  const setAgentExecutingTools = useAgentStore((state) => state.setAgentExecutingTools);

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

    const unsubscribeEvent = client.onEvent((event: AGUIEvent) => {
      updateActivity();
      handleAGUIEvent(event);
    });

    function handleAGUIEvent(event: AGUIEvent) {
      switch (event.type) {
        case EventType.RUN_STARTED:
          console.log('[AG-UI] Run started:', event.runId);
          currentRunId.current = event.runId;
          setProcessingStatus('thinking');
          break;

        case EventType.RUN_FINISHED:
          console.log('[AG-UI] Run finished:', event.runId);
          currentRunId.current = null;
          setProcessingStatus(null);
          if (currentAgentId.current) {
            setAgentIdle(currentAgentId.current);
          }
          break;

        case EventType.STEP_STARTED:
          console.log('[AG-UI] Step started:', event.stepName, event.metadata);
          setProcessingStatus(event.stepName as 'thinking' | 'routing' | 'executing_tools');
          if (event.metadata?.agentId) {
            const agentId = event.metadata.agentId as string;
            currentAgentId.current = agentId;
            if (event.stepName === 'executing_tools') {
              setAgentExecutingTools(agentId);
            } else {
              setAgentActive(agentId);
            }
          }
          break;

        case EventType.STEP_FINISHED:
          console.log('[AG-UI] Step finished:', event.stepName);
          break;

        case EventType.TEXT_MESSAGE_START:
          console.log('[AG-UI] Text message start:', event.messageId, event.role);
          if (event.role === 'assistant') {
            currentMessageId.current = event.messageId;
            addMessage({
              id: event.messageId,
              role: 'assistant',
              content: '',
              isStreaming: true,
            });
          }
          break;

        case EventType.TEXT_MESSAGE_CONTENT:
          console.log('[AG-UI] Text message content:', event.messageId, event.delta.length, 'chars');
          if (currentMessageId.current === event.messageId) {
            updateMessageContent(event.messageId, event.delta, true);
          }
          break;

        case EventType.TEXT_MESSAGE_END:
          console.log('[AG-UI] Text message end:', event.messageId);
          if (currentMessageId.current === event.messageId) {
            finalizeMessage(event.messageId);
            currentMessageId.current = null;
          }
          break;

        case EventType.TOOL_CALL_START:
          console.log('[AG-UI] Tool call start:', event.toolCallName, 'agent:', currentAgentId.current);
          addToolCall({
            id: event.toolCallId,
            toolName: event.toolCallName,
            status: 'started',
            parentMessageId: event.parentMessageId ?? undefined,
            agentId: currentAgentId.current,
          });
          addMessage({
            id: event.toolCallId,
            role: 'tool',
            content: event.toolCallName,
            toolName: event.toolCallName,
            toolStatus: 'started',
            agentId: currentAgentId.current,
          });
          break;

        case EventType.TOOL_CALL_ARGS:
          console.log('[AG-UI] Tool call args:', event.toolCallId);
          try {
            const parameters = JSON.parse(event.delta);
            updateToolCall(event.toolCallId, { parameters });
          } catch {
            console.warn('[AG-UI] Failed to parse tool args:', event.delta);
          }
          break;

        case EventType.TOOL_CALL_END:
          console.log('[AG-UI] Tool call end:', event.toolCallId, event.error ? 'error' : 'success');
          updateToolCall(event.toolCallId, {
            status: event.error ? 'failed' : 'completed',
            result: event.result ?? undefined,
            error: event.error ?? undefined,
          });
          addMessage({
            id: event.toolCallId,
            role: 'tool',
            content: '',
            toolStatus: event.error ? 'failed' : 'completed',
          });
          break;

        case EventType.CUSTOM:
          handleCustomEvent(event);
          break;

        case EventType.RAW:
          console.warn('[AG-UI] Received raw event:', event.data);
          break;

        default:
          console.log('[AG-UI] Unhandled event type:', (event as AGUIEvent).type);
      }
    }

    function handleCustomEvent(event: CustomEvent) {
      if (isToolApprovalRequest(event)) {
        const payload = parseToolApprovalRequest(event);
        if (payload) {
          console.log('[AG-UI] Tool approval request:', payload.toolName);
          addApproval({
            approvalId: payload.approvalId,
            toolName: payload.toolName,
            toolDescription: payload.toolDescription,
            parameters: payload.parameters as Record<string, unknown>,
            reasoning: payload.reasoning,
            riskLevel: payload.riskLevel,
          });
        }
      } else if (isAgoraError(event)) {
        const error = parseAgoraError(event);
        if (error) {
          console.error('[AG-UI] Server error:', error.message);
          setError(new Error(error.message));
        }
      } else {
        console.log('[AG-UI] Custom event:', event.name, event.value);
      }
    }

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
      unsubscribeEvent();

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
  }, [
    setStatus,
    setError,
    addMessage,
    updateMessageContent,
    finalizeMessage,
    setProcessingStatus,
    addApproval,
    addToolCall,
    updateToolCall,
    updateActivity,
    setAgentActive,
    setAgentIdle,
    setAgentExecutingTools,
  ]);

  const sendMessage = (content: string) => {
    if (clientRef.current && session) {
      addMessage({
        id: `msg-${Date.now()}-${Math.random()}`,
        role: 'user',
        content,
      });
      clientRef.current.sendRunInput(session.id, content);
      updateActivity();
    }
  };

  const sendToolApproval = (approvalId: string, approved: boolean, feedback?: string) => {
    if (clientRef.current) {
      clientRef.current.sendToolApprovalResponse(approvalId, approved, feedback);
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
