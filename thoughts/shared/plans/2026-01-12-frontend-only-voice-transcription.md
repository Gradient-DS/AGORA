# Frontend-Only Voice Transcription Implementation Plan

## Overview

Replace the planned backend-dependent voice transcription architecture with a frontend-only solution using ElevenLabs STT WebSocket API. This simplifies the architecture by eliminating backend voice endpoints entirely - transcribed speech becomes regular text messages flowing through the existing AG-UI WebSocket.

## Current State Analysis

### What Exists Now

**Frontend Voice Infrastructure (Targets Non-Existent Backend):**
| File | Purpose | Status |
|------|---------|--------|
| `HAI/src/lib/websocket/voiceClient.ts` | WebSocket client for `/ws/voice` | **Targets backend that doesn't exist** |
| `HAI/src/hooks/useVoiceMode.ts` | Audio capture, sends to backend | **Working audio capture, wrong target** |
| `HAI/src/stores/useVoiceStore.ts` | Voice state management | **Keep as-is** |
| `HAI/src/components/voice/*` | Voice UI components | **Keep as-is** |

**Frontend TTS (Already Working):**
| File | Purpose | Status |
|------|---------|--------|
| `HAI/src/lib/elevenlabs/client.ts` | ElevenLabs TTS client | **Model for STT client** |
| `HAI/src/hooks/useTTS.ts` | TTS event handling | **Working** |
| `HAI/src/stores/useTTSStore.ts` | TTS state | **Working** |

**Backend Voice Code (Never Used):**
| File | Purpose | Status |
|------|---------|--------|
| `server-openai/src/agora_openai/api/unified_voice_handler.py` | Placeholder voice handler | **Never registered, DELETE** |
| `server-openai/pyproject.toml` lines 16, 27 | Voice dependencies | **Remove** |
| `server-openai/README.md` | Documents `/ws/voice` | **Update** |

**Documentation:**
| File | Section | Status |
|------|---------|--------|
| `docs/hai-contract/HAI_API_CONTRACT.md` | "Future: Voice Support" (lines 1053-1204) | **Never implemented, UPDATE** |

### Key Discovery

The backend `/ws/voice` endpoint was **never registered** in `server.py`. The `unified_voice_handler.py` file explicitly states:
```python
# NOTE: This file is not used yet, but is a placeholder for future voice handling.
```

## Desired End State

**Architecture:**
```
User speaks → Microphone (getUserMedia)
    ↓
Audio processing (existing code in useVoiceMode.ts)
    ↓ PCM 16-bit @ 24kHz
ElevenLabs STT WebSocket (wss://api.elevenlabs.io/v1/speech-to-text/realtime)
    ↓ transcript
Submit as user message → AG-UI WebSocket (/ws) → Backend orchestrator
    ↓
LLM response
    ↓ agora:spoken_text_* events
ElevenLabs TTS (existing) → Audio playback
```

**Verification:**
1. Voice mode toggle activates microphone capture
2. Speech is transcribed in real-time via ElevenLabs STT
3. Transcription appears as a user message in the chat
4. Backend processes the message like any text input
5. Response is spoken via existing TTS infrastructure
6. All backend voice placeholder code is removed
7. Dependencies are cleaned up

## What We're NOT Doing

- NOT implementing backend voice WebSocket endpoints
- NOT using OpenAI's VoicePipeline (was placeholder code)
- NOT adding new backend dependencies
- NOT changing the mock server's `agora:spoken_text_*` events (these are for TTS, kept as-is)
- NOT implementing partial transcript display in UI (can be added later)

## Implementation Approach

1. Create ElevenLabs STT client following the existing TTS client pattern
2. Modify `useVoiceMode` to use STT client instead of backend WebSocket
3. Submit transcriptions as regular user messages through existing infrastructure
4. Clean up all backend voice placeholder code
5. Update documentation

---

## Phase 1: Create ElevenLabs STT Client

### Overview
Create a new STT client that mirrors the structure of the existing TTS client for consistency.

### Changes Required:

#### 1. Create STT Client
**File**: `HAI/src/lib/elevenlabs/sttClient.ts` (new file)

```typescript
/**
 * ElevenLabs STT client for AGORA HAI.
 *
 * Real-time speech-to-text using ElevenLabs WebSocket API.
 * Follows the same patterns as the TTS client.
 */

import { env } from '@/lib/env';

interface ElevenLabsSTTConfig {
  apiKey: string;
  sampleRate?: number;
  languageCode?: string;
}

type TranscriptCallback = (text: string, isFinal: boolean) => void;
type StatusCallback = (status: 'disconnected' | 'connecting' | 'connected' | 'error') => void;
type ErrorCallback = (error: Error) => void;

class ElevenLabsSTTClient {
  private config: ElevenLabsSTTConfig;
  private ws: WebSocket | null = null;
  private transcriptCallbacks: TranscriptCallback[] = [];
  private statusCallbacks: StatusCallback[] = [];
  private errorCallbacks: ErrorCallback[] = [];
  private currentStatus: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';

  constructor(config: Partial<ElevenLabsSTTConfig> = {}) {
    this.config = {
      apiKey: config.apiKey || env.VITE_ELEVENLABS_API_KEY || '',
      sampleRate: config.sampleRate || 24000,
      languageCode: config.languageCode || 'nl', // Dutch default for NVWA
    };
  }

  /**
   * Check if ElevenLabs STT is configured with a valid API key.
   */
  isConfigured(): boolean {
    return Boolean(this.config.apiKey && this.config.apiKey.length > 0);
  }

  /**
   * Connect to ElevenLabs STT WebSocket.
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      console.log('[ElevenLabsSTT] Already connected or connecting');
      return;
    }

    if (!this.isConfigured()) {
      console.warn('[ElevenLabsSTT] Not configured - cannot connect');
      this.handleError(new Error('ElevenLabs API key not configured'));
      return;
    }

    this.updateStatus('connecting');

    const url = new URL('wss://api.elevenlabs.io/v1/speech-to-text/realtime');
    url.searchParams.set('model_id', 'scribe_v1');
    url.searchParams.set('language_code', this.config.languageCode || 'nl');
    url.searchParams.set('sample_rate', String(this.config.sampleRate));

    try {
      this.ws = new WebSocket(url.toString(), {
        // Note: Browser WebSocket doesn't support custom headers directly
        // ElevenLabs accepts API key via query parameter for client-side use
      });

      // Send API key in initial message after connection
      this.setupEventHandlers();
    } catch (error) {
      console.error('[ElevenLabsSTT] Failed to create WebSocket:', error);
      this.handleError(new Error(`Failed to create WebSocket: ${error}`));
      this.updateStatus('error');
    }
  }

  /**
   * Disconnect from ElevenLabs STT WebSocket.
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus('disconnected');
  }

  /**
   * Send audio chunk to STT service.
   * @param base64Audio - Base64-encoded PCM 16-bit audio
   */
  sendAudioChunk(base64Audio: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        audio: base64Audio,
      }));
    }
  }

  /**
   * Signal end of audio stream for final transcription.
   */
  endStream(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        eos: true,
      }));
    }
  }

  /**
   * Subscribe to transcript events.
   */
  onTranscript(callback: TranscriptCallback): () => void {
    this.transcriptCallbacks.push(callback);
    return () => {
      this.transcriptCallbacks = this.transcriptCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * Subscribe to status changes.
   */
  onStatusChange(callback: StatusCallback): () => void {
    this.statusCallbacks.push(callback);
    callback(this.currentStatus);
    return () => {
      this.statusCallbacks = this.statusCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * Subscribe to errors.
   */
  onError(callback: ErrorCallback): () => void {
    this.errorCallbacks.push(callback);
    return () => {
      this.errorCallbacks = this.errorCallbacks.filter((cb) => cb !== callback);
    };
  }

  getStatus(): 'disconnected' | 'connecting' | 'connected' | 'error' {
    return this.currentStatus;
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[ElevenLabsSTT] Connection established');
      // Send initial configuration with API key
      this.ws?.send(JSON.stringify({
        type: 'start',
        api_key: this.config.apiKey,
        sample_rate: this.config.sampleRate,
        language_code: this.config.languageCode,
      }));
      this.updateStatus('connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        if (message.type === 'transcript') {
          const isFinal = message.is_final === true;
          const text = message.text || '';

          if (text) {
            this.transcriptCallbacks.forEach((callback) => callback(text, isFinal));
          }
        } else if (message.type === 'error') {
          this.handleError(new Error(message.message || 'STT error'));
        }
      } catch (error) {
        console.error('[ElevenLabsSTT] Invalid message received:', error);
      }
    };

    this.ws.onerror = () => {
      console.error('[ElevenLabsSTT] Connection error');
      this.handleError(new Error('WebSocket connection error'));
    };

    this.ws.onclose = (event) => {
      console.log(`[ElevenLabsSTT] Connection closed (code: ${event.code})`);
      if (this.currentStatus === 'connected') {
        this.updateStatus('disconnected');
      }
    };
  }

  private updateStatus(status: typeof this.currentStatus): void {
    this.currentStatus = status;
    this.statusCallbacks.forEach((callback) => callback(status));
  }

  private handleError(error: Error): void {
    this.updateStatus('error');
    this.errorCallbacks.forEach((callback) => callback(error));
  }
}

// Singleton instance
let sttClient: ElevenLabsSTTClient | null = null;

export function getElevenLabsSTTClient(): ElevenLabsSTTClient {
  if (!sttClient) {
    sttClient = new ElevenLabsSTTClient();
  }
  return sttClient;
}

export function resetElevenLabsSTTClient(): void {
  if (sttClient) {
    sttClient.disconnect();
    sttClient = null;
  }
}

export { ElevenLabsSTTClient };
```

#### 2. Update Module Exports
**File**: `HAI/src/lib/elevenlabs/index.ts`
**Changes**: Add STT client exports

```typescript
export { getElevenLabsClient, resetElevenLabsClient, ElevenLabsClient } from './client';
export { getElevenLabsSTTClient, resetElevenLabsSTTClient, ElevenLabsSTTClient } from './sttClient';
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles without errors: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] New file exists: `HAI/src/lib/elevenlabs/sttClient.ts`

#### Manual Verification:
- [ ] STT client can be imported and instantiated
- [ ] `isConfigured()` returns true when API key is set

---

## Phase 2: Modify useVoiceMode Hook

### Overview
Replace the backend WebSocket client with the ElevenLabs STT client. Transcriptions are submitted as regular user messages.

### Changes Required:

#### 1. Update useVoiceMode Hook
**File**: `HAI/src/hooks/useVoiceMode.ts`
**Changes**: Replace `VoiceWebSocketClient` with `ElevenLabsSTTClient`, submit transcriptions as messages

```typescript
import { useEffect, useRef, useState } from 'react';
import { useVoiceStore } from '@/stores';
import { useSessionStore, useMessageStore, useWebSocketStore } from '@/stores';
import { getElevenLabsSTTClient, resetElevenLabsSTTClient } from '@/lib/elevenlabs';
import { generateMessageId } from '@/lib/utils';

export function useVoiceMode() {
  const { isActive, setActive, setListening, setSpeaking, setVolume, reset } = useVoiceStore();
  const { session } = useSessionStore();
  const { addMessage } = useMessageStore();
  const { sendMessage } = useWebSocketStore();
  const sessionId = session?.id || 'default';
  const [error, setError] = useState<Error | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const transcriptRef = useRef<string>('');

  useEffect(() => {
    return () => {
      cleanup();
    };
  }, []);

  const startVoice = async () => {
    try {
      const sttClient = getElevenLabsSTTClient();

      if (!sttClient.isConfigured()) {
        throw new Error('ElevenLabs API key not configured');
      }

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
          // Submit as regular user message via AG-UI WebSocket
          const messageId = generateMessageId();

          // Add to local message store for immediate display
          addMessage({
            id: messageId,
            type: 'user',
            content: text.trim(),
            metadata: { source: 'voice' },
          });

          // Send via AG-UI WebSocket
          sendMessage({
            role: 'user',
            content: text.trim(),
          });

          transcriptRef.current = '';
        } else {
          // Partial transcript - could display in UI if desired
          transcriptRef.current = text;
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

      sttClient.connect();

      setActive(true);
      setListening(true);
      setError(null);

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

  const cleanup = () => {
    resetElevenLabsSTTClient();

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
    transcriptRef.current = '';
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

  return {
    isActive,
    startVoice,
    stopVoice,
    toggleVoice,
    error,
  };
}
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles without errors: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`

#### Manual Verification:
- [ ] Clicking voice button activates microphone
- [ ] Speaking results in transcription being sent as user message
- [ ] Transcribed message appears in chat
- [ ] Backend responds to the transcribed message
- [ ] TTS speaks the response

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that voice transcription is working end-to-end before proceeding to cleanup phases.

---

## Phase 3: Frontend Cleanup

### Overview
Remove the now-unused backend voice WebSocket client.

### Changes Required:

#### 1. Delete Voice WebSocket Client
**File**: `HAI/src/lib/websocket/voiceClient.ts`
**Action**: DELETE entire file

#### 2. Update WebSocket Index Exports
**File**: `HAI/src/lib/websocket/index.ts`
**Changes**: Remove voiceClient export

```typescript
export { AGUIWebSocketClient } from './client';
// Removed: export { VoiceWebSocketClient } from './voiceClient';
```

### Success Criteria:

#### Automated Verification:
- [x] File deleted: `HAI/src/lib/websocket/voiceClient.ts` does not exist
- [x] TypeScript compiles without errors: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Build succeeds: `cd HAI && pnpm run build`

#### Manual Verification:
- [ ] Voice mode still works after cleanup

---

## Phase 4: Backend Cleanup (server-openai)

### Overview
Remove the placeholder voice handler and voice-specific dependencies.

### Changes Required:

#### 1. Delete Voice Handler
**File**: `server-openai/src/agora_openai/api/unified_voice_handler.py`
**Action**: DELETE entire file

#### 2. Delete Orphaned Cache Files
**Files to delete**:
- `server-openai/src/agora_openai/api/__pycache__/voice_handler.cpython-311.pyc`
- `server-openai/src/agora_openai/api/__pycache__/unified_voice_handler.cpython-311.pyc`

**Action**: DELETE these files (or let them be regenerated correctly by Python)

#### 3. Remove Voice Dependencies
**File**: `server-openai/pyproject.toml`
**Changes**:

Line 16 - Change:
```toml
# FROM:
"openai-agents[voice]>=0.1.0",
# TO:
"openai-agents>=0.1.0",
```

Line 27 - Remove entirely:
```toml
# REMOVE:
"sounddevice>=0.4.6",
```

Note: Keep `numpy>=1.24.0` as it may be used by other dependencies.

#### 4. Update README
**File**: `server-openai/README.md`
**Changes**: Remove the `/ws/voice` documentation section (lines mentioning voice mode, VoicePipeline, and `/ws/voice` endpoint)

Find and remove sections referencing:
- "Verenigde Spraak & Tekst"
- "Spraak I/O (STT & TTS via VoicePipeline)"
- "Verenigde spraakafhandelaar met VoicePipeline"
- "voice_handler.py"
- "/ws/voice" endpoint documentation
- "Spraakmodus" section

### Success Criteria:

#### Automated Verification:
- [x] File deleted: `server-openai/src/agora_openai/api/unified_voice_handler.py` does not exist
- [ ] Dependencies install cleanly: `cd server-openai && pip install -e .`
- [x] Python syntax check passes: `python3 -m py_compile server-openai/src/agora_openai/api/server.py`
- [x] No references to deleted voice files: `grep -r "unified_voice_handler\|voice_handler" server-openai/src/`

#### Manual Verification:
- [ ] Backend starts without errors
- [ ] AG-UI WebSocket still works for text messages

---

## Phase 5: Documentation Cleanup

### Overview
Update HAI_API_CONTRACT.md to reflect the new architecture.

### Changes Required:

#### 1. Update API Contract
**File**: `docs/hai-contract/HAI_API_CONTRACT.md`
**Changes**:

Replace the "Future: Voice Support" section (lines 1053-1204) with:

```markdown
## Voice Support

### Overview

AGORA supports voice interactions through a frontend-only architecture:

- **Speech-to-Text (STT)**: ElevenLabs Realtime STT API (frontend)
- **Text-to-Speech (TTS)**: ElevenLabs TTS API (frontend)

Voice transcriptions are submitted as regular user messages via the AG-UI WebSocket. No special voice endpoints or events are required on the backend.

### Architecture

```
User speaks → Microphone
    ↓
ElevenLabs STT WebSocket (frontend)
    ↓ transcript
User message → AG-UI WebSocket → Backend
    ↓
LLM response
    ↓ agora:spoken_text_* events
ElevenLabs TTS (frontend) → Audio playback
```

### Spoken Text Events

When TTS is enabled, the backend streams spoken-friendly text alongside regular message content:

| Event | Direction | Purpose |
|-------|-----------|---------|
| `agora:spoken_text_start` | Server → Client | Begin spoken text for a message |
| `agora:spoken_text_content` | Server → Client | Spoken text delta (streaming) |
| `agora:spoken_text_end` | Server → Client | End spoken text for a message |

These events are sent via the AG-UI `CUSTOM` event type and are documented in the [Custom Events](#custom-events-hitl) section.

### Configuration

Voice support requires ElevenLabs API credentials:

```env
VITE_ELEVENLABS_API_KEY=your_api_key
VITE_ELEVENLABS_VOICE_ID=optional_voice_id
```
```

Also update the table of contents (line 23) from:
```markdown
9. [Future: Voice Support](#future-voice-support)
```
to:
```markdown
9. [Voice Support](#voice-support)
```

And update the changelog to add:

```markdown
### v2.5.0 (January 2026)
- Implemented frontend-only voice architecture using ElevenLabs STT/TTS
- Removed planned backend voice endpoints (never implemented)
- Updated Voice Support documentation to reflect actual implementation
```

### Success Criteria:

#### Automated Verification:
- [x] Documentation file updated: `docs/hai-contract/HAI_API_CONTRACT.md`
- [x] No broken markdown links in documentation

#### Manual Verification:
- [ ] Documentation accurately describes the implemented voice architecture
- [ ] No references to removed backend voice endpoints

---

## Testing Strategy

### Unit Tests:
- STT client connection/disconnection lifecycle
- Audio chunk encoding/sending
- Transcript callback handling
- Error handling for missing API key

### Integration Tests:
- End-to-end voice mode activation
- Transcription submission via AG-UI WebSocket
- TTS response playback

### Manual Testing Steps:
1. Enable voice mode with valid ElevenLabs API key
2. Speak a sentence in Dutch
3. Verify transcription appears as user message
4. Verify backend responds to the message
5. Verify TTS speaks the response (if enabled)
6. Disable voice mode
7. Verify microphone access is released

## Performance Considerations

- ElevenLabs STT has ~150ms latency
- Audio is captured at 24kHz PCM 16-bit (matches ElevenLabs requirements)
- Existing audio capture code is reused (no changes to audio processing)
- Same API key works for both TTS and STT

## Migration Notes

No data migration required - the backend voice endpoint was never implemented or used.

## References

- Research document: `thoughts/shared/research/2026-01-12-frontend-only-voice-transcription.md`
- ElevenLabs STT API: https://elevenlabs.io/docs/api-reference/speech-to-text
- ElevenLabs TTS pattern: `HAI/src/lib/elevenlabs/client.ts`
- Existing audio capture: `HAI/src/hooks/useVoiceMode.ts:30-64`
