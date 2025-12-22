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
  useUserStore,
  useHistoryStore,
} from '@/stores';
import {
  EventType,
  type AGUIEvent,
  type CustomEvent,
  type StateSnapshotEvent,
  type ToolCallStartEvent,
  isToolApprovalRequest,
  isAgoraError,
  parseToolApprovalRequest,
  parseAgoraError,
} from '@/types/schemas';
import { env } from '@/lib/env';
import { emitTTSEvent } from './useTTS';

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

        case EventType.RUN_FINISHED: {
          console.log('[AG-UI] Run finished:', event.runId);
          currentRunId.current = null;
          setProcessingStatus(null);
          if (currentAgentId.current) {
            setAgentIdle(currentAgentId.current);
          }
          // Refresh session list to capture new/updated sessions
          const userId = useUserStore.getState().currentUser?.id;
          if (userId) {
            useHistoryStore.getState().fetchSessions(userId);
          }
          break;
        }

        case EventType.RUN_ERROR:
          console.error('[AG-UI] Run error:', event.message, event.code);
          setError(new Error(event.message));
          setProcessingStatus(null);
          break;

        case EventType.STEP_STARTED:
          console.log('[AG-UI] Step started:', event.stepName);
          setProcessingStatus(event.stepName as 'thinking' | 'routing' | 'executing_tools');
          if (event.stepName === 'executing_tools') {
            if (currentAgentId.current) {
              setAgentExecutingTools(currentAgentId.current);
            }
          } else if (currentAgentId.current) {
            setAgentActive(currentAgentId.current);
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

        case EventType.TOOL_CALL_START: {
          const toolEvent = event as ToolCallStartEvent;
          console.log('[AG-UI] Tool call start:', toolEvent.toolCallName, 'agent:', currentAgentId.current);
          addToolCall({
            id: toolEvent.toolCallId,
            toolName: toolEvent.toolCallName,
            status: 'started',
            parentMessageId: toolEvent.parentMessageId ?? undefined,
            agentId: currentAgentId.current,
          });
          addMessage({
            id: toolEvent.toolCallId,
            role: 'tool',
            content: toolEvent.toolCallName,
            toolName: toolEvent.toolCallName,
            toolStatus: 'started',
            agentId: currentAgentId.current,
          });
          // Emit TTS event for tool description (only handoffs have this)
          if (toolEvent.toolDescription) {
            emitTTSEvent({
              type: 'tool_description',
              content: toolEvent.toolDescription,
            });
          }
          break;
        }

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
          console.log('[AG-UI] Tool call end:', event.toolCallId);
          // TOOL_CALL_END now just signals end of streaming, result comes via TOOL_CALL_RESULT
          break;

        case EventType.TOOL_CALL_RESULT:
          console.log('[AG-UI] Tool call result:', event.toolCallId);
          updateToolCall(event.toolCallId, {
            status: 'completed',
            result: event.content,
          });
          addMessage({
            id: event.toolCallId,
            role: 'tool',
            content: '',
            toolStatus: 'completed',
          });
          break;

        case EventType.STATE_SNAPSHOT:
          handleStateSnapshot(event);
          break;

        case EventType.STATE_DELTA:
          console.log('[AG-UI] State delta received');
          break;

        case EventType.CUSTOM:
          handleCustomEvent(event);
          break;

        case EventType.RAW:
          console.warn('[AG-UI] Received raw event:', event.event);
          break;

        default:
          console.log('[AG-UI] Unhandled event type:', (event as AGUIEvent).type);
      }
    }

    function handleStateSnapshot(event: StateSnapshotEvent) {
      console.log('[AG-UI] State snapshot:', event.snapshot);
      const snapshot = event.snapshot;
      
      // Update current agent from state snapshot
      if (snapshot.current_agent || snapshot.currentAgent) {
        const newAgentId = (snapshot.current_agent || snapshot.currentAgent) as string;
        if (newAgentId !== currentAgentId.current) {
          console.log('[AG-UI] Agent changed via state snapshot:', currentAgentId.current, '→', newAgentId);
          currentAgentId.current = newAgentId;
          setAgentActive(newAgentId);
        }
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
      } else if (event.name === 'agora:spoken_text_start') {
        // TTS: Start of spoken text stream
        const value = event.value as { messageId?: string };
        emitTTSEvent({
          type: 'spoken_text_start',
          messageId: value.messageId,
        });
      } else if (event.name === 'agora:spoken_text_content') {
        // TTS: Spoken text content chunk
        const value = event.value as { messageId?: string; delta?: string };
        emitTTSEvent({
          type: 'spoken_text_content',
          messageId: value.messageId,
          content: value.delta,
        });
      } else if (event.name === 'agora:spoken_text_end') {
        // TTS: End of spoken text stream
        const value = event.value as { messageId?: string };
        emitTTSEvent({
          type: 'spoken_text_end',
          messageId: value.messageId,
        });
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
    const userId = useUserStore.getState().currentUser?.id;
    if (!userId) {
      console.warn('[useWebSocket] Cannot send message: no user selected');
      return;
    }
    if (clientRef.current && session) {
      addMessage({
        id: `msg-${Date.now()}-${Math.random()}`,
        role: 'user',
        content,
      });
      clientRef.current.sendRunInput(session.id, userId, content);
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
