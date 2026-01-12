---
date: 2026-01-12T14:30:00+01:00
researcher: Claude
git_commit: 8e824d28ccfcec5186ad10f79c5540896c1caac6
branch: feat/parallel-spoken
repository: AGORA
topic: "Frontend-Only Voice Transcription with ElevenLabs STT"
tags: [research, voice, elevenlabs, stt, frontend, transcription]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Frontend-Only Voice Transcription with ElevenLabs STT

**Date**: 2026-01-12T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 8e824d28ccfcec5186ad10f79c5540896c1caac6
**Branch**: feat/parallel-spoken
**Repository**: AGORA

## Research Question

Can we implement frontend-only speech-to-text (STT) using ElevenLabs, similar to the existing TTS implementation, and remove the backend voice WebSocket endpoint?

## Summary

**Yes, this is very feasible.** ElevenLabs offers a real-time WebSocket-based STT API (Scribe v2 Realtime) that can run entirely in the frontend. The implementation would:

1. Create a new ElevenLabs STT client (mirroring the existing TTS client pattern)
2. Modify the voice mode hook to use ElevenLabs STT instead of backend WebSocket
3. Submit transcribed text as normal user messages via the existing AG-UI WebSocket
4. Remove the placeholder backend voice code (which isn't even active)

This results in a **simpler architecture** - no special voice backend needed.

## Detailed Findings

### Current State

#### TTS (Text-to-Speech) - Already Frontend-Only

| Component | Location | Status |
|-----------|----------|--------|
| ElevenLabs Client | `HAI/src/lib/elevenlabs/client.ts` | Fully implemented |
| TTS Store | `HAI/src/stores/useTTSStore.ts` | Fully implemented |
| TTS Hook | `HAI/src/hooks/useTTS.ts` | Fully implemented |
| TTS Toggle | `HAI/src/components/chat/TTSToggle.tsx` | Fully implemented |

**API Pattern:**
- Endpoint: `https://api.elevenlabs.io/v1/text-to-speech/{voiceId}/stream`
- Auth: `xi-api-key` header
- Uses same API key from `VITE_ELEVENLABS_API_KEY`

#### STT (Speech-to-Text) - Current Backend-Dependent Architecture

| Component | Location | Status |
|-----------|----------|--------|
| Voice WebSocket Client | `HAI/src/lib/websocket/voiceClient.ts` | Implemented but targets backend |
| Voice Mode Hook | `HAI/src/hooks/useVoiceMode.ts` | Captures audio, sends to `/ws/voice` |
| Voice Store | `HAI/src/stores/useVoiceStore.ts` | Fully implemented |
| Backend Voice Handler | `server-openai/src/agora_openai/api/unified_voice_handler.py` | **Placeholder only - NOT ACTIVE** |

**Critical Finding:** The backend `/ws/voice` endpoint is **not registered**. The `unified_voice_handler.py` file explicitly states:
```python
# NOTE: This file is not used yet, but is a placeholder for future voice handling.
# TODO: Implement voice handling using STT and TTS with async text gen for both.
```

### ElevenLabs STT API Capabilities

ElevenLabs offers **two STT options**:

#### 1. REST API (File Upload)
- Endpoint: `POST https://api.elevenlabs.io/v1/speech-to-text`
- Model: `scribe_v1` or `scribe_v1_experimental`
- **Not suitable** for real-time transcription (requires complete audio file)

#### 2. Realtime WebSocket API (Streaming) - **Recommended**
- Endpoint: `wss://api.elevenlabs.io/v1/speech-to-text/realtime`
- Model: Scribe v2 Realtime
- Latency: ~150ms
- Languages: 90+

**Authentication:**
- API Key: `xi-api-key` header (same key as TTS!)
- Or token via query parameter (for client-side use)

**Audio Format:**
- PCM 16-bit at 8000, 16000, 22050, 24000, 44100, or 48000 Hz
- Current voice mode already uses **24000 Hz PCM 16-bit** - compatible!

**Message Protocol:**
```typescript
// Client sends:
{ type: 'input_audio_chunk', audio: 'base64-encoded-pcm' }

// Server responds:
{ type: 'partial_transcript', text: '...' }      // Real-time updates
{ type: 'committed_transcript', text: '...' }   // Final text
```

**Voice Activity Detection (VAD):**
- Automatic silence detection for commit
- Configurable thresholds

### Files to Create/Modify

#### New Files
| File | Purpose |
|------|---------|
| `HAI/src/lib/elevenlabs/sttClient.ts` | ElevenLabs STT WebSocket client |

#### Files to Modify
| File | Changes |
|------|---------|
| `HAI/src/hooks/useVoiceMode.ts` | Replace backend WS with ElevenLabs STT client |
| `HAI/src/lib/websocket/voiceClient.ts` | Can be **deleted** (replaced by sttClient.ts) |
| `HAI/src/lib/env.ts` | Already has `VITE_ELEVENLABS_API_KEY` |

#### Files to Remove (Backend Cleanup)
| File | Reason |
|------|--------|
| `server-openai/src/agora_openai/api/unified_voice_handler.py` | Placeholder, never used |
| Voice dependencies in `server-openai/pyproject.toml` | `sounddevice`, possibly `numpy` if unused elsewhere |

### Proposed Architecture

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

This is **simpler** than the current planned architecture because:
1. No backend voice endpoint needed
2. Same API key for both TTS and STT
3. Existing audio capture code can be reused
4. Transcription is just text - feeds into normal chat flow

## Code References

### Existing Audio Capture (Reusable)
- `HAI/src/hooks/useVoiceMode.ts:30-37` - Microphone capture with 24kHz PCM
- `HAI/src/hooks/useVoiceMode.ts:50-64` - Audio processing to base64 PCM
- `HAI/src/hooks/useVoiceMode.ts:259-269` - Float32 to 16-bit PCM conversion
- `HAI/src/hooks/useVoiceMode.ts:271-282` - ArrayBuffer to base64 encoding

### ElevenLabs TTS Pattern (Model for STT)
- `HAI/src/lib/elevenlabs/client.ts:30-37` - Configuration pattern
- `HAI/src/lib/elevenlabs/client.ts:157-171` - Singleton pattern

### Environment Configuration
- `HAI/src/lib/env.ts:8-9` - `VITE_ELEVENLABS_API_KEY` already defined
- `HAI/.env.example:14-17` - Example configuration

## Implementation Approach

### Phase 1: ElevenLabs STT Client

Create `HAI/src/lib/elevenlabs/sttClient.ts`:

```typescript
interface ElevenLabsSTTConfig {
  apiKey: string;
  sampleRate?: number;  // Default 24000
  enableVAD?: boolean;  // Default true
}

class ElevenLabsSTTClient {
  private ws: WebSocket | null = null;
  private onTranscriptCallbacks: ((text: string, isFinal: boolean) => void)[] = [];

  connect(): void {
    this.ws = new WebSocket('wss://api.elevenlabs.io/v1/speech-to-text/realtime', {
      headers: { 'xi-api-key': this.config.apiKey }
    });
    // Handle messages...
  }

  sendAudioChunk(base64Audio: string): void {
    this.ws?.send(JSON.stringify({
      type: 'input_audio_chunk',
      audio: base64Audio,
    }));
  }

  onTranscript(callback: (text: string, isFinal: boolean) => void): () => void {
    // Subscribe to transcripts
  }
}
```

### Phase 2: Modify useVoiceMode Hook

Replace `VoiceWebSocketClient` with `ElevenLabsSTTClient`:

```typescript
// In useVoiceMode.ts
import { ElevenLabsSTTClient } from '@/lib/elevenlabs/sttClient';

// When transcription is received:
sttClient.onTranscript((text, isFinal) => {
  if (isFinal) {
    // Submit as normal user message via existing WebSocket
    useMessageStore.getState().sendMessage({ content: text });
  }
});
```

### Phase 3: Backend Cleanup

1. Delete `server-openai/src/agora_openai/api/unified_voice_handler.py`
2. Remove voice-specific dependencies if unused:
   - `sounddevice>=0.4.6`
   - `openai-agents[voice]` voice extra (keep base package)
3. Update `server-openai/README.md` to remove `/ws/voice` documentation

## Effort Estimate

| Task | Complexity |
|------|------------|
| Create ElevenLabs STT client | Low - mirrors TTS pattern |
| Modify useVoiceMode hook | Low - replace WS client |
| Remove backend placeholder | Trivial |
| Testing | Medium |

**Total**: 1-2 days of work

## Open Questions

1. **Token vs API Key**: Should we use token-based auth for better security? Tokens can be generated server-side with limited scope.

2. **Partial Transcripts**: Should we show partial transcripts in the UI as the user speaks, or wait for final?

3. **Error Handling**: What happens if ElevenLabs STT fails mid-transcription? Fallback to Web Speech API?

4. **Concurrent TTS/STT**: Can both TTS and STT connections be active simultaneously with the same API key?

## Related Research

- `thoughts/shared/plans/2026-01-12-parallel-llm-spoken-text-generation.md` - Parallel TTS generation plan

## Conclusion

Frontend-only voice transcription with ElevenLabs is not only feasible but results in a **simpler architecture**:

- Same API key for TTS and STT
- No backend voice handling needed
- Existing audio capture code is compatible
- Transcriptions become normal text messages
- The backend `/ws/voice` endpoint was never implemented anyway

The implementation is straightforward and can be modeled after the existing TTS client pattern.
