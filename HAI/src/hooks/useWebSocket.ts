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
  useAuthStore,
  useListenModeStore,
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
import { getWebSocketUrl } from '@/lib/env';
import { emitTTSEvent } from './useTTS';

let globalClient: AGUIWebSocketClient | null = null;
let activeSubscriptions = 0;
let hasInitiatedConnection = false;

function getOrCreateClient(): AGUIWebSocketClient {
  if (!globalClient) {
    globalClient = new AGUIWebSocketClient({
      url: getWebSocketUrl(),
      maxReconnectAttempts: 5,
      reconnectInterval: 3000,
      maxReconnectInterval: 30000,
    });
  }
  return globalClient;
}

/**
 * Get the global WebSocket client instance.
 * Used by voice mode to send transcribed messages.
 */
export function getWebSocketClient(): AGUIWebSocketClient {
  return getOrCreateClient();
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
  const setAuthRequired = useAuthStore((state) => state.setAuthRequired);
  const setAuthError = useAuthStore((state) => state.setAuthError);

  useEffect(() => {
    const client = getOrCreateClient();
    clientRef.current = client;

    activeSubscriptions++;

    const unsubscribeStatus = client.onStatusChange((status) => {
      setStatus(status);
    });

    const unsubscribeError = client.onError((error) => {
      if (error.message === 'AUTH_REQUIRED') {
        setAuthRequired(true);
        setAuthError('Authenticatie vereist. Voer uw API-sleutel in.');
      } else {
        setError(error);
      }
    });

    const unsubscribeEvent = client.onEvent((event: AGUIEvent) => {
      updateActivity();
      handleAGUIEvent(event);
    });

    function handleAGUIEvent(event: AGUIEvent) {
      switch (event.type) {
        case EventType.RUN_STARTED:
          currentRunId.current = event.runId;
          setProcessingStatus('thinking');
          break;

        case EventType.RUN_FINISHED: {
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
          setError(new Error(event.message));
          setProcessingStatus(null);
          break;

        case EventType.STEP_STARTED:
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
          break;

        case EventType.TEXT_MESSAGE_START:
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

        case EventType.TEXT_MESSAGE_CONTENT: {
          const delta = event.delta ?? '';
          if (currentMessageId.current === event.messageId) {
            updateMessageContent(event.messageId, delta, true);

            // Update listen mode store based on message content
            if (delta.startsWith('[Luistermodus actief')) {
              const match = delta.match(/bericht (\d+)/);
              if (match?.[1]) {
                useListenModeStore.getState().setBufferedCount(parseInt(match[1], 10));
              }
            } else if (delta.includes('Feedback modus geactiveerd')) {
              useListenModeStore.getState().resetBufferedCount();
            }
          }
          break;
        }

        case EventType.TEXT_MESSAGE_END:
          if (currentMessageId.current === event.messageId) {
            finalizeMessage(event.messageId);
            currentMessageId.current = null;
          }
          break;

        case EventType.TOOL_CALL_START: {
          const toolEvent = event as ToolCallStartEvent;
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
          try {
            const parameters = JSON.parse(event.delta);
            updateToolCall(event.toolCallId, { parameters });
          } catch {
            // Failed to parse tool args
          }
          break;

        case EventType.TOOL_CALL_END:
          // TOOL_CALL_END now just signals end of streaming, result comes via TOOL_CALL_RESULT
          break;

        case EventType.TOOL_CALL_RESULT:
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
          break;

        case EventType.CUSTOM:
          handleCustomEvent(event);
          break;

        case EventType.RAW:
          break;

        default:
          break;
      }
    }

    function handleStateSnapshot(event: StateSnapshotEvent) {
      const snapshot = event.snapshot;

      // Update current agent from state snapshot
      if (snapshot.current_agent || snapshot.currentAgent) {
        const newAgentId = (snapshot.current_agent || snapshot.currentAgent) as string;
        if (newAgentId !== currentAgentId.current) {
          currentAgentId.current = newAgentId;
          setAgentActive(newAgentId);
        }
      }
    }

    function handleCustomEvent(event: CustomEvent) {
      if (isToolApprovalRequest(event)) {
        const payload = parseToolApprovalRequest(event);
        if (payload) {
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
      }
    }

    if (!hasInitiatedConnection) {
      const status = client.getStatus();

      if (status === 'disconnected' || status === 'error') {
        hasInitiatedConnection = true;
        setTimeout(() => client.connect(), 0);
      }
    }

    return () => {
      activeSubscriptions--;

      unsubscribeStatus();
      unsubscribeError();
      unsubscribeEvent();

      if (activeSubscriptions === 0) {
        setTimeout(() => {
          if (activeSubscriptions === 0 && globalClient) {
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
    setAuthRequired,
    setAuthError,
  ]);

  const sendMessage = (content: string) => {
    const userId = useUserStore.getState().currentUser?.id;
    if (!userId) {
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
