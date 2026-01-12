# AGORA AG-UI Protocol Contract

This directory contains the contract specification for the AG-UI Protocol used for communication between the HAI (Human Agent Interface) frontend and the AGORA LangGraph orchestrator backend.

## Overview

AGORA uses the open-source **AG-UI Protocol** for real-time, event-driven communication between the frontend and backend.

**AG-UI Repository:** https://github.com/ag-ui-protocol/ag-ui

## Key Features

- **Event-driven streaming** with typed events
- **WebSocket transport** for real-time bidirectional communication
- **Lifecycle events** (`RUN_STARTED`, `RUN_FINISHED`, `STEP_STARTED`, `STEP_FINISHED`)
- **State synchronization** via `STATE_SNAPSHOT` events for agent tracking
- **Text streaming** with `TEXT_MESSAGE_START/CONTENT/END` pattern
- **Tool call events** with `TOOL_CALL_START/ARGS/END/RESULT` pattern
- **Spoken text events** for TTS support (`agora:spoken_text_*`)
- **Custom events** for AGORA-specific extensions (HITL approval)
- **REST API** for session management, user management, and history retrieval
- **Type-safe** with full TypeScript/Python support

## Directory Contents

| File | Description |
|------|-------------|
| `HAI_API_CONTRACT.md` | Complete protocol specification (REST + WebSocket) |
| `asyncapi.yaml` | AsyncAPI 3.0 specification for WebSocket events |
| `openapi.yaml` | OpenAPI 3.0 specification for REST endpoints (sessions, users, agents) |
| `schemas/messages.json` | JSON Schema definitions for events |
| `examples/` | Example event sequences |
| `mock_server.py` | Python mock server for testing |
| `mock_documents/` | Mock PDF/JSON documents for report download testing |

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
Client → Server: RunAgentInput { threadId, runId, userId, messages }

Server → Client: RUN_STARTED { threadId, runId }
Server → Client: STATE_SNAPSHOT { snapshot: { currentAgent: "general-agent", status: "processing" } }
Server → Client: STEP_STARTED { stepName: "routing" }
Server → Client: STEP_FINISHED { stepName: "routing" }
Server → Client: STEP_STARTED { stepName: "thinking" }
Server → Client: TEXT_MESSAGE_START { messageId, role: "assistant" }
Server → Client: TEXT_MESSAGE_CONTENT { messageId, delta: "Based on..." }
Server → Client: TEXT_MESSAGE_CONTENT { messageId, delta: "the regulations..." }
Server → Client: TEXT_MESSAGE_END { messageId }
Server → Client: STEP_FINISHED { stepName: "thinking" }
Server → Client: STATE_SNAPSHOT { snapshot: { currentAgent: "general-agent", status: "completed" } }
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

The mock server runs on `ws://localhost:8000/ws` (same as the real backend).

### Demo Scenario: Inspecteur Koen - Restaurant Bella Rosa

The mock server supports the full demo scenario with realistic Dutch responses and tool calls:

**Step 1 - Start inspection:**
```
Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854
```
→ Triggers `get_company_info` and `get_inspection_history` tool calls

**Step 2 - Document findings:**
```
Ik zie een geopende ton met rauwe vis op kamertemperatuur naast een afvoerputje vol schoonmaakmiddelresten
```
→ Triggers `search_regulations` and `check_repeat_violation` tool calls

**Step 3 - Generate report:**
```
Genereer rapport
```
→ Triggers tool approval dialog for `generate_inspection_report`

### Features

- **Tool calls**: Simulated MCP tool calls with realistic responses
- **Tool approval flow**: Human-in-the-loop approval for report generation
- **Streaming responses**: Realistic text streaming in Dutch
- **State tracking**: Conversation context maintained per connection

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
