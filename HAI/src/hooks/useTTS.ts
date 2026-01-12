/**
 * TTS (Text-to-Speech) hook for AGORA HAI.
 *
 * Integrates with WebSocket events to speak:
 * - agora:spoken_text_* events (TTS-optimized assistant responses)
 * - toolDescription from TOOL_CALL_START events (agent handoffs only)
 */

import { useEffect, useRef, useCallback } from 'react';
import { useTTSStore } from '@/stores';
import { getElevenLabsClient } from '@/lib/elevenlabs';

// Event types for TTS
export type TTSEventType =
  | 'spoken_text_start'
  | 'spoken_text_content'
  | 'spoken_text_end'
  | 'tool_description';

export interface TTSEvent {
  type: TTSEventType;
  messageId?: string;
  content?: string;
}

// Global event emitter for TTS events
type TTSEventCallback = (event: TTSEvent) => void;
const ttsEventCallbacks: Set<TTSEventCallback> = new Set();

/**
 * Emit a TTS event to all subscribers.
 */
export function emitTTSEvent(event: TTSEvent): void {
  ttsEventCallbacks.forEach(callback => callback(event));
}

/**
 * Subscribe to TTS events.
 */
function subscribeTTSEvents(callback: TTSEventCallback): () => void {
  ttsEventCallbacks.add(callback);
  return () => ttsEventCallbacks.delete(callback);
}

/**
 * Hook that handles TTS playback based on WebSocket events.
 */
export function useTTS() {
  const isEnabled = useTTSStore((state) => state.isEnabled);
  const setIsSpeaking = useTTSStore((state) => state.setIsSpeaking);

  // Buffer for accumulating spoken text chunks
  const textBuffer = useRef<Map<string, string>>(new Map());

  const handleTTSEvent = useCallback(
    async (event: TTSEvent) => {
      if (!isEnabled) {
        return;
      }

      const client = getElevenLabsClient();
      if (!client.isConfigured()) {
        return;
      }

      switch (event.type) {
        case 'spoken_text_start':
          // Start accumulating text for this message
          if (event.messageId) {
            textBuffer.current.set(event.messageId, '');
          }
          break;

        case 'spoken_text_content':
          // Append content to buffer
          if (event.messageId && event.content) {
            const current = textBuffer.current.get(event.messageId) || '';
            textBuffer.current.set(event.messageId, current + event.content);
          }
          break;

        case 'spoken_text_end':
          // Flush buffer and speak
          if (event.messageId) {
            const text = textBuffer.current.get(event.messageId);
            textBuffer.current.delete(event.messageId);

            if (text && text.trim().length > 0) {
              setIsSpeaking(true);
              try {
                await client.speak(text);
              } finally {
                setIsSpeaking(false);
              }
            }
          }
          break;

        case 'tool_description':
          // Immediately queue tool description (for handoffs)
          if (event.content && event.content.trim().length > 0) {
            setIsSpeaking(true);
            try {
              await client.speak(event.content);
            } finally {
              setIsSpeaking(false);
            }
          }
          break;
      }
    },
    [isEnabled, setIsSpeaking]
  );

  useEffect(() => {
    const unsubscribe = subscribeTTSEvents(handleTTSEvent);
    const buffer = textBuffer.current;
    return () => {
      unsubscribe();
      // Clear any pending buffers
      buffer.clear();
    };
  }, [handleTTSEvent]);

  // Return control functions
  const stop = useCallback(() => {
    const client = getElevenLabsClient();
    client.stop();
    setIsSpeaking(false);
    textBuffer.current.clear();
  }, [setIsSpeaking]);

  return { stop };
}
