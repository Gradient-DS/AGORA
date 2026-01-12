# AGORA API Guide

This guide explains how to use the AGORA API with your API key.

## Quick Start

### Base URL

```
https://agora.gradient-testing.nl
```

Replace with the URL provided to you.

### Authentication

Include your API key in **every request** using one of these methods:

**Option 1: HTTP Header (Recommended)**
```
X-API-Key: your-api-key-here
```

**Option 2: Query Parameter (for WebSocket connections)**
```
wss://agora.gradient-testing.nl/ws?token=your-api-key-here
```

---

## Endpoints

### Health Check

Verify the API is running:

```bash
curl -H "X-API-Key: your-api-key" https://agora.gradient-testing.nl/health
```

Response:
```json
{
  "status": "healthy",
  "service": "api-gateway"
}
```

### List Available Backends

```bash
curl -H "X-API-Key: your-api-key" https://agora.gradient-testing.nl/gateway/backends
```

Response:
```json
{
  "backends": ["openai", "langgraph", "mock"],
  "default": "langgraph",
  "routes": {
    "openai": "/api/openai/*",
    "langgraph": "/api/langgraph/*",
    "mock": "/api/mock/*"
  }
}
```

### List Available Agents

```bash
curl -H "X-API-Key: your-api-key" https://agora.gradient-testing.nl/agents
```

Response:
```json
{
  "success": true,
  "agents": [
    {"id": "general-agent", "name": "Algemene Assistent", "description": "Algemene vraag- en routeringagent"},
    {"id": "history-agent", "name": "Bedrijfsinformatie Specialist", "description": "KVK-gegevens en inspectiehistorie"},
    {"id": "regulation-agent", "name": "Regelgeving Specialist", "description": "Wet- en regelgevingsanalyse"},
    {"id": "reporting-agent", "name": "Rapportage Specialist", "description": "Inspectierapport genereren"}
  ]
}
```

---

## WebSocket Chat API

AGORA uses WebSocket for real-time chat with AI agents. The protocol is based on the [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui).

### Connect

```
wss://agora.gradient-testing.nl/ws?token=your-api-key
```

Or use a specific backend:
```
wss://agora.gradient-testing.nl/api/langgraph/ws?token=your-api-key
```

### Send a Message

After connecting, send a JSON message:

```json
{
  "threadId": "unique-conversation-id",
  "runId": "unique-run-id",
  "userId": "your-user-id",
  "messages": [
    {"role": "user", "content": "What are the food safety regulations for restaurants?"}
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `threadId` | Yes | Unique conversation ID (UUID). Use the same ID to continue a conversation. |
| `runId` | No | Unique ID for this request. Auto-generated if not provided. |
| `userId` | Yes | Your user identifier (UUID) |
| `messages` | Yes | Array of messages with `role` and `content` |

### Receive Events

The server streams events back. Key event types:

| Event Type | Description |
|------------|-------------|
| `RUN_STARTED` | Processing has begun |
| `TEXT_MESSAGE_START` | Agent is starting to respond |
| `TEXT_MESSAGE_CONTENT` | Chunk of response text (`delta` field) |
| `TEXT_MESSAGE_END` | Response complete |
| `TOOL_CALL_START` | Agent is calling a tool |
| `TOOL_CALL_RESULT` | Tool execution result |
| `RUN_FINISHED` | Processing complete |
| `RUN_ERROR` | An error occurred |

Example response stream:
```json
{"type": "RUN_STARTED", "threadId": "abc123", "runId": "run-456"}
{"type": "TEXT_MESSAGE_START", "messageId": "msg-789", "role": "assistant"}
{"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg-789", "delta": "Based on the "}
{"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg-789", "delta": "regulations..."}
{"type": "TEXT_MESSAGE_END", "messageId": "msg-789"}
{"type": "RUN_FINISHED", "threadId": "abc123", "runId": "run-456"}
```

### Example: Using wscat

```bash
# Install wscat
npm install -g wscat

# Connect
wscat -c "wss://agora.gradient-testing.nl/ws?token=your-api-key"

# Send a message (paste this after connecting)
{"threadId":"550e8400-e29b-41d4-a716-446655440000","userId":"550e8400-e29b-41d4-a716-446655440001","messages":[{"role":"user","content":"Hello, what can you help me with?"}]}
```

### Example: Python Client

```python
import asyncio
import json
import uuid
import websockets

API_KEY = "your-api-key"
WS_URL = "wss://agora.gradient-testing.nl/ws"

async def chat():
    url = f"{WS_URL}?token={API_KEY}"

    async with websockets.connect(url) as ws:
        # Send message
        request = {
            "threadId": str(uuid.uuid4()),
            "userId": str(uuid.uuid4()),
            "messages": [
                {"role": "user", "content": "What are the food safety regulations?"}
            ]
        }
        await ws.send(json.dumps(request))

        # Receive events
        full_response = ""
        async for message in ws:
            event = json.loads(message)

            if event["type"] == "TEXT_MESSAGE_CONTENT":
                full_response += event["delta"]
                print(event["delta"], end="", flush=True)

            elif event["type"] == "RUN_FINISHED":
                print("\n--- Done ---")
                break

            elif event["type"] == "RUN_ERROR":
                print(f"\nError: {event['message']}")
                break

asyncio.run(chat())
```

### Example: JavaScript/TypeScript Client

```typescript
const API_KEY = "your-api-key";
const WS_URL = "wss://agora.gradient-testing.nl/ws";

function connect() {
  const ws = new WebSocket(`${WS_URL}?token=${API_KEY}`);

  ws.onopen = () => {
    // Send message
    const request = {
      threadId: crypto.randomUUID(),
      userId: crypto.randomUUID(),
      messages: [
        { role: "user", content: "What are the food safety regulations?" }
      ]
    };
    ws.send(JSON.stringify(request));
  };

  let fullResponse = "";

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case "TEXT_MESSAGE_CONTENT":
        fullResponse += data.delta;
        console.log(data.delta);
        break;

      case "RUN_FINISHED":
        console.log("--- Complete response:", fullResponse);
        ws.close();
        break;

      case "RUN_ERROR":
        console.error("Error:", data.message);
        ws.close();
        break;
    }
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
  };
}

connect();
```

---

## REST API

### Session Management

#### List Sessions
```bash
curl -H "X-API-Key: your-api-key" \
  "https://agora.gradient-testing.nl/sessions?user_id=your-user-id"
```

#### Get Session History
```bash
curl -H "X-API-Key: your-api-key" \
  "https://agora.gradient-testing.nl/sessions/{session_id}/history?include_tools=true"
```

#### Delete Session
```bash
curl -X DELETE -H "X-API-Key: your-api-key" \
  "https://agora.gradient-testing.nl/sessions/{session_id}"
```

---

## Error Handling

### HTTP Errors

| Status Code | Meaning |
|-------------|---------|
| 401 | Missing or invalid API key |
| 404 | Resource not found |
| 500 | Server error |

### WebSocket Errors

Errors are sent as `RUN_ERROR` events:
```json
{
  "type": "RUN_ERROR",
  "message": "Error description",
  "code": "error_code"
}
```

---

## Rate Limits

Contact your administrator for rate limit details specific to your API key.

---

## Automated Testing

A comprehensive test script is available to verify your API setup:

```bash
# Install dependencies
pip install httpx websockets

# Run tests against production
python scripts/test_api.py --api-key YOUR_API_KEY

# Run tests against a custom URL
python scripts/test_api.py --api-key YOUR_API_KEY --base-url https://your-domain.com
```

The test script validates:
- HTTP endpoint authentication (no auth, valid key, wrong key)
- Gateway backends listing
- All backend health endpoints (langgraph, openai, mock)
- WebSocket authentication rejection
- WebSocket streaming with actual message delivery

Example output:
```
============================================================
AGORA API Test Suite
============================================================
Base URL: https://agora.gradient-testing.nl
API Key:  cabf0b2b...2844
============================================================

HTTP Endpoint Tests
----------------------------------------
  [PASS] Health (no auth): Returns 401 as expected (156ms)
  [PASS] Health (with auth): status=healthy (89ms)
  [PASS] Health (wrong key): Returns 401 as expected (78ms)
  [PASS] Gateway backends: Found: ['openai', 'langgraph', 'mock'] (92ms)
  [PASS] Agents endpoint: Found 4 agents (85ms)
  ...

WebSocket Streaming Tests
----------------------------------------
  [PASS] WebSocket (no auth): Rejected with 4001 as expected (45ms)
  [PASS] WebSocket streaming: 15 events, 42 chars (1250ms)
  ...
```

---

## Support

For technical issues or questions:
- Email: lex@gradient-ds.com

---

## Protocol Reference

For detailed protocol documentation, see:
- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui) - Open-source protocol specification
- [HAI API Contract](./hai-contract/HAI_API_CONTRACT.md) - Complete technical specification
