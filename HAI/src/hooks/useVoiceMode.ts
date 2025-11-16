import { useEffect, useRef, useState } from 'react';
import { useVoiceStore } from '@/stores';
import { useSessionStore, useMessageStore } from '@/stores';
import { VoiceWebSocketClient } from '@/lib/websocket/voiceClient';
import { getEnvVariable } from '@/lib/env';

export function useVoiceMode() {
  const { isActive, setActive, setListening, setSpeaking, setVolume, reset } = useVoiceStore();
  const { session } = useSessionStore();
  const { addMessage, messages } = useMessageStore();
  const sessionId = session?.id || 'default';
  const [error, setError] = useState<Error | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const voiceClientRef = useRef<VoiceWebSocketClient | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const audioQueueRef = useRef<Int16Array[]>([]);
  const isPlayingRef = useRef(false);

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, []);

  const startVoice = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 24000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const audioContext = new AudioContext({ sampleRate: 24000 });
      audioContextRef.current = audioContext;

      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      audioProcessorRef.current = processor;
      source.connect(processor);
      processor.connect(audioContext.destination);

      processor.onaudioprocess = (e) => {
        if (!voiceClientRef.current || voiceClientRef.current.getStatus() !== 'connected') {
          return;
        }

        const inputData = e.inputBuffer.getChannelData(0);
        const pcm16 = floatTo16BitPCM(inputData);
        const base64Audio = arrayBufferToBase64(pcm16.buffer);
        voiceClientRef.current.sendAudioData(base64Audio);
      };

      const wsUrl = getEnvVariable('VITE_WS_URL').replace('/ws', '/ws/voice');
      const client = new VoiceWebSocketClient({ url: wsUrl, sessionId });
      voiceClientRef.current = client;

      client.onMessage((message) => {
        handleVoiceMessage(message);
      });

      client.onError((err) => {
        setError(err);
        console.error('Voice WebSocket error:', err);
      });

      client.onStatusChange((status) => {
        if (status === 'connected') {
          const conversationHistory = messages.map((msg) => ({
            role: msg.type === 'user' ? 'user' : 'assistant',
            content: msg.content,
          }));
          
          if (conversationHistory.length > 0) {
            console.log(`[Voice] Loading ${conversationHistory.length} previous messages into context`);
          }
          
          client.startSession(undefined, conversationHistory);
        }
      });

      client.connect();

      setActive(true);
      setListening(true);
      setError(null);

      monitorAudio();
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to start voice mode');
      setError(error);
      console.error('Voice mode error:', error);
    }
  };

  const stopVoice = () => {
    cleanup();
  };

  const cleanup = () => {
    if (voiceClientRef.current) {
      voiceClientRef.current.disconnect();
      voiceClientRef.current = null;
    }

    if (audioProcessorRef.current) {
      audioProcessorRef.current.disconnect();
      audioProcessorRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    analyserRef.current = null;
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    reset();
  };

  const monitorAudio = () => {
    if (!analyserRef.current || !isActive) return;

    const bufferLength = analyserRef.current.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const update = () => {
      if (!analyserRef.current || !isActive) return;

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

  const handleVoiceMessage = (message: { type: string; [key: string]: unknown }) => {
    switch (message.type) {
      case 'session.started':
        console.log('Voice session started');
        break;

      case 'speech.started':
        setListening(false);
        console.log('User started speaking');
        break;

      case 'speech.stopped':
        console.log('User stopped speaking');
        break;

      case 'audio.committed':
        setListening(false);
        setSpeaking(true);
        break;

      case 'transcript.user':
        addMessage({
          type: 'user',
          content: message.text as string,
          metadata: { source: 'voice' },
        });
        break;

      case 'audio.response':
        playAudioChunk(message.audio as string);
        break;

      case 'transcript.assistant':
        addMessage({
          type: 'assistant',
          content: message.text as string,
          agent_id: 'voice-assistant',
          metadata: { source: 'voice' },
        });
        break;

      case 'tool.executing':
        console.log(`Executing tool: ${message.tool_name}`);
        addMessage({
          type: 'assistant',
          content: `🔧 Executing ${message.tool_name}...`,
          agent_id: 'voice-assistant',
          metadata: { source: 'voice', tool_execution: true },
        });
        break;

      case 'tool.completed':
        console.log(`Tool completed: ${message.tool_name}`);
        addMessage({
          type: 'assistant',
          content: `✅ ${message.tool_name} completed`,
          agent_id: 'voice-assistant',
          metadata: { source: 'voice', tool_execution: true },
        });
        break;

      case 'tool.failed':
        console.error(`Tool failed: ${message.tool_name}`, message.error);
        addMessage({
          type: 'assistant',
          content: `❌ ${message.tool_name} failed: ${message.error}`,
          agent_id: 'voice-assistant',
          metadata: { source: 'voice', tool_execution: true },
        });
        break;

      case 'response.completed':
        setSpeaking(false);
        setListening(true);
        break;

      case 'error':
        console.error('Voice error:', message.message);
        setError(new Error(message.message as string));
        break;

      default:
        console.log('Unhandled voice message:', message.type);
    }
  };

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

  const base64ToArrayBuffer = (base64: string): ArrayBuffer => {
    const binaryString = atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  };

  const playAudioChunk = (base64Audio: string) => {
    const arrayBuffer = base64ToArrayBuffer(base64Audio);
    const int16Array = new Int16Array(arrayBuffer);
    audioQueueRef.current.push(int16Array);

    if (!isPlayingRef.current) {
      playNextChunk();
    }
  };

  const playNextChunk = async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }

    isPlayingRef.current = true;
    const chunk = audioQueueRef.current.shift()!;

    if (!audioContextRef.current) {
      return;
    }

    const audioContext = audioContextRef.current;
    const audioBuffer = audioContext.createBuffer(1, chunk.length, 24000);
    const channelData = audioBuffer.getChannelData(0);

    for (let i = 0; i < chunk.length; i++) {
      const sample = chunk[i];
      if (sample !== undefined) {
        channelData[i] = sample / 32768;
      }
    }

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = () => {
      playNextChunk();
    };
    source.start();
  };

  return {
    isActive,
    startVoice,
    stopVoice,
    toggleVoice,
    error,
  };
}

