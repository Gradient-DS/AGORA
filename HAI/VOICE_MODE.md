# Voice Mode Implementation

This document describes the voice mode implementation using OpenAI's Realtime API.

## Overview

The voice mode enables real-time voice conversations between users and the AI assistant using OpenAI's Realtime API. The implementation streams audio from the user's microphone to the backend, which forwards it to OpenAI's Realtime API, and streams the audio responses back to the user.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │  useVoiceMode Hook                                  │    │
│  │  - Captures microphone audio                        │    │
│  │  - Converts to PCM16 format                         │    │
│  │  - Sends to backend via WebSocket                   │    │
│  │  - Receives & plays audio responses                 │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          │ VoiceWebSocketClient              │
│                          ▼                                   │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ WebSocket (/ws/voice)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend Server                            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  VoiceSessionHandler                                │    │
│  │  - Manages voice session lifecycle                  │    │
│  │  - Forwards audio to OpenAI                         │    │
│  │  - Streams responses back to client                 │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          │ OpenAIRealtimeClient              │
│                          ▼                                   │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ WebSocket (OpenAI Realtime API)
                           ▼
                    ┌──────────────┐
                    │   OpenAI     │
                    │ Realtime API │
                    └──────────────┘
```

## Components

### Frontend

#### VoiceWebSocketClient (`src/lib/websocket/voiceClient.ts`)
- Manages WebSocket connection to `/ws/voice` endpoint
- Sends audio data and control messages
- Receives audio responses and transcripts
- Handles connection lifecycle

#### useVoiceMode Hook (`src/hooks/useVoiceMode.ts`)
- Captures audio from user's microphone
- Converts Float32 audio to Int16 PCM format
- Encodes audio as base64 and sends to backend
- Receives audio responses and plays them
- Updates UI state (listening, speaking, volume)
- Adds transcripts to message history

#### VoiceInterface Component (`src/components/voice/VoiceInterface.tsx`)
- UI for voice mode activation
- Visual feedback (avatar, animations)
- Audio visualizer
- Status indicators

### Backend

#### OpenAIRealtimeClient (`src/agora_openai/adapters/realtime_client.py`)
- Connects to OpenAI Realtime API via WebSocket
- Sends audio data and session configuration
- Receives audio responses and events
- Handles message routing

#### VoiceSessionHandler (`src/agora_openai/api/voice_handler.py`)
- Manages individual voice sessions
- Bridges client WebSocket and OpenAI connection
- Handles audio encoding/decoding
- Manages session state and lifecycle

#### Voice WebSocket Endpoint (`src/agora_openai/api/server.py`)
- WebSocket endpoint at `/ws/voice`
- Accepts voice connections
- Creates session handlers
- Manages session lifecycle

## Message Protocol

### Client → Backend

#### Session Control
```json
{
  "type": "session.start",
  "session_id": "string",
  "instructions": "string (optional)"
}
```

```json
{
  "type": "session.stop"
}
```

#### Audio Data
```json
{
  "type": "audio.data",
  "audio": "base64-encoded PCM16 audio"
}
```

#### Control Messages
```json
{
  "type": "audio.commit"
}
```

```json
{
  "type": "response.cancel"
}
```

```json
{
  "type": "text.message",
  "text": "string"
}
```

### Backend → Client

#### Session Events
```json
{
  "type": "session.started",
  "session_id": "string"
}
```

#### Speech Events
```json
{
  "type": "speech.started"
}
```

```json
{
  "type": "speech.stopped"
}
```

#### Audio & Transcripts
```json
{
  "type": "audio.response",
  "audio": "base64-encoded PCM16 audio"
}
```

```json
{
  "type": "transcript.user",
  "text": "string"
}
```

```json
{
  "type": "transcript.assistant",
  "text": "string"
}
```

#### Response Events
```json
{
  "type": "response.completed"
}
```

```json
{
  "type": "error",
  "error_code": "string",
  "message": "string"
}
```

## Audio Format

- **Sample Rate**: 24kHz
- **Format**: PCM16 (16-bit signed integer)
- **Channels**: Mono (1 channel)
- **Encoding**: Base64

## Features

### Voice Activity Detection (VAD)
OpenAI's server-side VAD automatically detects when the user starts and stops speaking:
- **Threshold**: 0.5
- **Prefix Padding**: 300ms
- **Silence Duration**: 500ms

### Echo Cancellation & Noise Suppression
Enabled on the microphone capture for better audio quality.

### Real-time Transcription
User speech is automatically transcribed using Whisper and sent to the client.

### Audio Playback
Assistant responses are streamed as audio chunks and queued for seamless playback.

### State Management
The voice store tracks:
- `isActive`: Whether voice mode is active
- `isListening`: Whether the system is listening to the user
- `isSpeaking`: Whether the assistant is speaking
- `volume`: Current audio volume level

### Message History
Transcripts are automatically added to the message history for context.

## Usage

### Starting Voice Mode
1. Click the microphone button in the Voice Interface
2. Grant microphone permissions when prompted
3. Start speaking when you see "Listening..."

### Stopping Voice Mode
Click the microphone button again to deactivate voice mode.

## Configuration

### Frontend Environment Variables
```env
VITE_WS_URL=ws://localhost:8000/ws
```

The voice WebSocket URL is automatically derived by replacing `/ws` with `/ws/voice`.

### Backend Environment Variables
```env
APP_OPENAI_API_KEY=sk-...
```

## Error Handling

### Frontend
- Microphone access denied: Shows error message
- WebSocket disconnection: Automatically attempts reconnection
- Audio processing errors: Logged to console

### Backend
- OpenAI connection errors: Returned to client
- Audio encoding errors: Logged and returned to client
- Session errors: Gracefully closed with error message

## Testing

To test the voice mode:

1. Start the backend server:
   ```bash
   cd server-openai
   python -m agora_openai.api.server
   ```

2. Start the frontend:
   ```bash
   cd HAI
   pnpm run dev
   ```

3. Open the application in your browser
4. Click the Voice Interface tab
5. Click the microphone button
6. Grant microphone permissions
7. Start speaking and listen for responses

## Limitations

- Voice mode requires a modern browser with WebRTC support
- Microphone access must be granted
- Requires stable internet connection
- OpenAI Realtime API usage is metered separately

## Future Enhancements

- Multiple voice options (alloy, echo, fable, onyx, nova, shimmer)
- Custom instructions per session
- Voice interruption support
- Multi-language support
- Audio history playback
- Voice settings UI (volume, voice selection)

