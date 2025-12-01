# AGORA AG-UI Protocol Contract

This directory contains the contract specification for the AG-UI Protocol used for communication between the HAI (Human Agent Interface) frontend and the AGORA LangGraph orchestrator backend.

## Overview

AGORA uses the open-source **AG-UI Protocol** for real-time, event-driven communication between the frontend and backend.

**AG-UI Repository:** https://github.com/ag-ui-protocol/ag-ui

## Key Features

- **Event-driven streaming** with typed events
- **WebSocket transport** for real-time bidirectional communication
- **Lifecycle events** (`RUN_STARTED`, `RUN_FINISHED`, `STEP_STARTED`, `STEP_FINISHED`)
- **Text streaming** with `TEXT_MESSAGE_START/CONTENT/END` pattern
- **Tool call events** with `TOOL_CALL_START/ARGS/END`
- **Custom events** for AGORA-specific extensions (HITL approval)
- **Type-safe** with full TypeScript/Python support

## Directory Contents

| File | Description |
|------|-------------|
| `AG_UI_PROTOCOL.md` | Complete protocol specification |
| `asyncapi.yaml` | AsyncAPI 3.0 specification for WebSocket events |
| `openapi.yaml` | OpenAPI 3.0 specification for REST endpoints |
| `schemas/messages.json` | JSON Schema definitions for events |
| `examples/` | Example event sequences |
| `mock_server.py` | Python mock server for testing |

## Quick Start

### Connect via WebSocket

```typescript
import { AGUIWebSocketClient } from '@/lib/websocket';

const client = new AGUIWebSocketClient({
  url: 'ws://localhost:8000/ws',
});

client.onEvent((event) => {
  console.log('Received:', event.type);
});

client.connect();
client.sendRunInput('thread-123', 'Hello!');
```

### Event Flow Example

```
Client → Server: RunAgentInput { threadId, runId, messages }

Server → Client: RUN_STARTED { threadId, runId }
Server → Client: STEP_STARTED { stepName: "routing" }
Server → Client: STEP_FINISHED { stepName: "routing" }
Server → Client: STEP_STARTED { stepName: "thinking" }
Server → Client: TEXT_MESSAGE_START { messageId, role: "assistant" }
Server → Client: TEXT_MESSAGE_CONTENT { messageId, delta: "Based on..." }
Server → Client: TEXT_MESSAGE_CONTENT { messageId, delta: "the regulations..." }
Server → Client: TEXT_MESSAGE_END { messageId }
Server → Client: STEP_FINISHED { stepName: "thinking" }
Server → Client: RUN_FINISHED { threadId, runId }
```

## AGORA Custom Events

AGORA extends AG-UI with custom events for human-in-the-loop approval:

### Tool Approval Request

```json
{
  "type": "CUSTOM",
  "name": "agora:tool_approval_request",
  "value": {
    "toolName": "generate_final_report",
    "toolDescription": "Generates an official inspection report PDF",
    "parameters": { "inspection_id": "INS-2024-001" },
    "reasoning": "User requested to finalize the inspection report",
    "riskLevel": "high",
    "approvalId": "appr-xyz789"
  }
}
```

### Tool Approval Response

```json
{
  "type": "CUSTOM",
  "name": "agora:tool_approval_response",
  "value": {
    "approvalId": "appr-xyz789",
    "approved": true,
    "feedback": "Looks good, proceed"
  }
}
```

### Error Event

```json
{
  "type": "CUSTOM",
  "name": "agora:error",
  "value": {
    "errorCode": "moderation_violation",
    "message": "Content blocked",
    "details": { "reason": "profanity" }
  }
}
```

## Testing with Mock Server

Start the mock server for frontend development:

```bash
cd docs/hai-contract
python mock_server.py
```

The mock server runs on `ws://localhost:8765` and simulates:
- Basic conversation flow with streaming responses
- Tool approval flow (triggered by messages containing "report" or "generate")

## Migration from HAI Protocol v1

| HAI v1 | AG-UI v2 |
|--------|----------|
| `session_id` | `threadId` |
| `message_id` | `messageId` |
| snake_case | camelCase |
| `assistant_message_chunk` | `TEXT_MESSAGE_START/CONTENT/END` |
| `tool_call` | `TOOL_CALL_START/ARGS/END` |
| `status` | `STEP_STARTED/FINISHED` |
| `tool_approval_request` | `CUSTOM` with `agora:tool_approval_request` |

## Related Documentation

- [AGORA Architecture](../../ARCHITECTURE.md)
- [HAI Frontend](../../HAI/README.md)
- [LangGraph Backend](../../server-langgraph/README.md)
- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)
