/**
 * Voice mode hook using ElevenLabs STT.
 *
 * Captures microphone audio, sends to ElevenLabs for transcription,
 * and submits transcribed text as regular user messages via AG-UI WebSocket.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useVoiceStore, useSessionStore, useMessageStore, useUserStore } from '@/stores';
import { getElevenLabsSTTClient, resetElevenLabsSTTClient } from '@/lib/elevenlabs';
import { getWebSocketClient } from './useWebSocket';
import { generateMessageId } from '@/lib/utils';

export function useVoiceMode() {
  const { isActive, setActive, setListening, setVolume, setPartialTranscript, reset } = useVoiceStore();
  const { session } = useSessionStore();
  const { addMessage } = useMessageStore();
  const [error, setError] = useState<Error | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const isActiveRef = useRef(false);

  const cleanup = useCallback(() => {
    // Disconnect STT client
    resetElevenLabsSTTClient();

    // Clean up audio processor
    if (audioProcessorRef.current) {
      audioProcessorRef.current.disconnect();
      audioProcessorRef.current = null;
    }

    // Stop microphone stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    analyserRef.current = null;
    reset();
  }, [reset]);

  // Keep isActiveRef in sync with isActive for use in callbacks
  useEffect(() => {
    isActiveRef.current = isActive;
  }, [isActive]);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  const startVoice = async () => {
    try {
      const sttClient = getElevenLabsSTTClient();

      if (!sttClient.isConfigured()) {
        throw new Error('ElevenLabs API key not configured');
      }

      // Request microphone access
      // Note: browsers often ignore sampleRate constraint, so we'll use whatever we get
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // Set up audio context for processing
      // Don't force sample rate - use the device's native rate for best quality
      // ElevenLabs supports various sample rates (8000, 16000, 22050, 24000, 44100)
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;

      // Log actual sample rate (browsers may use 44100 or 48000)
      const actualSampleRate = audioContext.sampleRate;
      console.log(`[VoiceMode] AudioContext sample rate: ${actualSampleRate}`);

      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      // Create audio processor for sending audio chunks
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      audioProcessorRef.current = processor;
      source.connect(processor);
      processor.connect(audioContext.destination);

      processor.onaudioprocess = (e) => {
        if (sttClient.getStatus() !== 'connected') {
          return;
        }

        const inputData = e.inputBuffer.getChannelData(0);
        const pcm16 = floatTo16BitPCM(inputData);
        const base64Audio = arrayBufferToBase64(pcm16.buffer);
        sttClient.sendAudioChunk(base64Audio);
      };

      // Handle transcription results
      sttClient.onTranscript((text, isFinal) => {
        if (isFinal && text.trim()) {
          // Clear partial transcript
          setPartialTranscript('');

          // Submit as regular user message
          const messageId = generateMessageId();
          const userId = useUserStore.getState().currentUser?.id;

          // Add to local message store for immediate display
          addMessage({
            id: messageId,
            role: 'user',
            content: text.trim(),
            metadata: { source: 'voice' },
          });

          // Send via AG-UI WebSocket if session and user exist
          if (session && userId) {
            const client = getWebSocketClient();
            client.sendRunInput(session.id, userId, text.trim());
          }
        } else if (text) {
          // Update partial transcript for display
          setPartialTranscript(text);
        }
      });

      sttClient.onError((err) => {
        setError(err);
        console.error('[VoiceMode] STT error:', err);
      });

      sttClient.onStatusChange((status) => {
        console.log('[VoiceMode] STT status:', status);
        if (status === 'error') {
          setListening(false);
        }
      });

      // Connect to STT service with actual sample rate
      await sttClient.connect(actualSampleRate);

      setActive(true);
      setListening(true);
      setError(null);

      // Start audio level monitoring
      monitorAudio();
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to start voice mode');
      setError(error);
      console.error('[VoiceMode] Error:', error);
    }
  };

  const stopVoice = () => {
    cleanup();
  };

  const monitorAudio = () => {
    if (!analyserRef.current) return;

    const bufferLength = analyserRef.current.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const update = () => {
      if (!analyserRef.current || !isActiveRef.current) return;

      analyserRef.current.getByteFrequencyData(dataArray);
      const average = dataArray.reduce((a, b) => a + b) / bufferLength;
      const normalizedVolume = average / 255;

      setVolume(normalizedVolume);

      requestAnimationFrame(update);
    };

    update();
  };

  const toggleVoice = () => {
    if (isActive) {
      stopVoice();
    } else {
      startVoice();
    }
  };

  // Convert Float32Array to Int16Array (PCM 16-bit)
  const floatTo16BitPCM = (float32Array: Float32Array): Int16Array => {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const value = float32Array[i];
      if (value !== undefined) {
        const s = Math.max(-1, Math.min(1, value));
        int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
    }
    return int16Array;
  };

  // Convert ArrayBuffer to Base64 string
  const arrayBufferToBase64 = (buffer: ArrayBufferLike): string => {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      const byte = bytes[i];
      if (byte !== undefined) {
        binary += String.fromCharCode(byte);
      }
    }
    return btoa(binary);
  };

  return {
    isActive,
    startVoice,
    stopVoice,
    toggleVoice,
    error,
  };
}
