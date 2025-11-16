# Voice Mode Setup Guide

Quick guide to get voice mode working in your AGORA system with full tool access.

## 🎉 What's New: Unified System

Voice mode now has **full access to all your MCP tools**! Both voice and chat go through the same backend system:
- ✅ Voice can execute compliance checks, risk analysis, reporting, etc.
- ✅ Shared conversation context between voice and chat
- ✅ Same capabilities, different interfaces
- ✅ Tool execution visible in chat interface

See [UNIFIED_SYSTEM.md](../UNIFIED_SYSTEM.md) for complete details.

## Prerequisites

1. OpenAI API key with access to Realtime API
2. Python 3.11+ with FastAPI
3. Node.js 18+ with pnpm
4. Modern browser with microphone access

## Backend Setup

### 1. Install Dependencies

Make sure `websockets` package is installed (it should already be in `pyproject.toml`):

```bash
cd server-openai
pip install -e ".[dev]"
```

### 2. Set Environment Variables

Create or update your `.env` file:

```env
APP_OPENAI_API_KEY=sk-proj-your-api-key-here
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
```

### 3. Start the Server

```bash
cd server-openai
python -m agora_openai.api.server
```

The server will start on `http://localhost:8000` with:
- Main WebSocket endpoint: `ws://localhost:8000/ws`
- Voice WebSocket endpoint: `ws://localhost:8000/ws/voice`

## Frontend Setup

### 1. Install Dependencies

```bash
cd HAI
pnpm install
```

### 2. Set Environment Variables

Create `.env.local`:

```env
VITE_WS_URL=ws://localhost:8000/ws
VITE_OPENAI_API_KEY=dummy
VITE_APP_NAME=AGORA HAI
VITE_SESSION_TIMEOUT=3600000
```

Note: The frontend derives the voice WebSocket URL automatically.

### 3. Start the Frontend

```bash
pnpm run dev
```

The app will start on `http://localhost:5173`

## Testing Voice Mode

1. Open the application in your browser
2. Click on the "Voice Interface" tab
3. Click the microphone button
4. Allow microphone access when prompted
5. Wait for "Listening..." status
6. Start speaking
7. The assistant will respond with voice

## Troubleshooting

### TypeError: create_connection() got an unexpected keyword argument 'extra_headers'

This is a websockets library version issue. Fixed in the latest code by using `additional_headers` instead of `extra_headers`.

If you still see this error:
```bash
cd server-openai
pip install --upgrade websockets
```

### "Cannot send event, not connected" Errors

If you see repeated "Cannot send event, not connected" errors in the backend logs:

1. **Check API Key**: Ensure `APP_OPENAI_API_KEY` is set correctly
   ```bash
   # Your API key should start with 'sk-proj-' or 'sk-'
   echo $APP_OPENAI_API_KEY
   ```

2. **Test Connection**: Run the diagnostic script
   ```bash
   cd server-openai
   python test_realtime_connection.py
   ```

3. **Verify Realtime API Access**: 
   - Check if your OpenAI account has access to the Realtime API
   - Visit https://platform.openai.com/settings/organization/limits
   - The Realtime API may require a paid account or special access

4. **Check Model Name**: Ensure using the correct model
   - Default: `gpt-4o-realtime-preview-2024-10-01`
   - Check OpenAI docs for latest model name

5. **Review Backend Logs**: Look for more specific error messages
   ```bash
   # Look for:
   # - "Invalid status code from Realtime API"
   # - "Failed to connect to Realtime API"
   # - "Authentication failed"
   ```

### Microphone Not Working

- Ensure browser has microphone permissions
- Check if microphone is selected in system settings
- Try a different browser (Chrome/Edge recommended)

### WebSocket Connection Failed

- Verify backend server is running
- Check `VITE_WS_URL` in frontend `.env.local`
- Ensure no firewall is blocking WebSocket connections
- Check browser console for detailed errors

### No Audio Playback

- Check browser audio permissions
- Verify system volume is not muted
- Check browser console for audio errors
- Try refreshing the page

### OpenAI API Errors

- Verify API key is valid and has Realtime API access
- Check OpenAI API status: https://status.openai.com
- Review backend logs for detailed error messages
- Ensure you have sufficient API credits

### Audio Quality Issues

- Check internet connection stability
- Ensure microphone is working properly
- Try reducing background noise
- Check if echo cancellation is enabled

## Verifying the Setup

### Backend Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "agora-openai"
}
```

### Backend Info

```bash
curl http://localhost:8000/
```

Expected response:
```json
{
  "service": "AGORA OpenAI Orchestration",
  "version": "1.0.0",
  "docs": "/docs",
  "websocket": "/ws",
  "voice_websocket": "/ws/voice"
}
```

### Frontend Console

Open browser DevTools and check for:
- `[VoiceWS] Connecting to ws://localhost:8000/ws/voice`
- `[VoiceWS] Connection established`
- `[VoiceWS] Received: session.started`

### Backend Logs

Check server logs for:
- `Voice WebSocket connection ESTABLISHED`
- `Connected to OpenAI Realtime API`
- `Voice session started: <session_id>`

## Advanced Configuration

### Custom Voice Instructions

Modify the instructions in `voice_handler.py` to customize the assistant's behavior:

```python
default_instructions = """Your custom instructions here"""
```

### Audio Quality Settings

Adjust in `useVoiceMode.ts`:
- Sample rate (default: 24000)
- Buffer size (default: 4096)
- Echo cancellation settings

### VAD Sensitivity

Adjust in `voice_handler.py`:
```python
"turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,  # Adjust 0.0-1.0
    "prefix_padding_ms": 300,
    "silence_duration_ms": 500,
}
```

## Docker Deployment

### Backend
```bash
cd server-openai
docker build -t agora-backend .
docker run -p 8000:8000 --env-file .env agora-backend
```

### Frontend
```bash
cd HAI
docker build -t agora-hai .
docker run -p 3000:80 agora-hai
```

## Security Considerations

- Never expose API keys in frontend code
- Use HTTPS/WSS in production
- Implement rate limiting on voice endpoints
- Add authentication for production use
- Monitor API usage and costs

## Cost Considerations

OpenAI Realtime API pricing:
- Audio input: $0.06 / minute
- Audio output: $0.24 / minute
- Cached input: $0.06 / minute

Monitor usage in your OpenAI dashboard.

## Support

For issues or questions:
1. Check the logs (both frontend and backend)
2. Review the VOICE_MODE.md documentation
3. Check OpenAI API status
4. Ensure all dependencies are up to date

