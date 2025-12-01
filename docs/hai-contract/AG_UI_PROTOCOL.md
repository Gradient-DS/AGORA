# AGORA AG-UI Protocol Specification

**Version:** 2.0.0  
**Last Updated:** December 2025  
**Protocol:** AG-UI (Agent-User Interface Protocol)

## Table of Contents

1. [Overview](#overview)
2. [Connection](#connection)
3. [Event Format](#event-format)
4. [Event Types](#event-types)
5. [Conversation Flows](#conversation-flows)
6. [Custom Events (HITL)](#custom-events-hitl)
7. [Implementation Guide](#implementation-guide)
8. [Migration from HAI](#migration-from-hai)

---

## Overview

AGORA uses the open-source **AG-UI Protocol** for communication between the HAI (Human Agent Interface) frontend and the LangGraph orchestrator backend.

**AG-UI Repository:** https://github.com/ag-ui-protocol/ag-ui

### Key Features

- **Event-driven architecture** with typed events
- **Transport agnostic** (WebSocket supported)
- **Streaming-first** for real-time text and tool call updates
- **Lifecycle events** for run and step tracking
- **Custom events** for protocol extensions (HITL approval)
- **Type-safe** with full TypeScript/Python support

### Architecture Context

```
┌─────────────┐         WebSocket          ┌──────────────────┐
│             │◄──────────────────────────►│                  │
│  HAI Client │    AG-UI Events (JSON)     │  LangGraph       │
│  (Frontend) │                            │  Orchestrator    │
│             │                            │                  │
└─────────────┘                            └──────────────────┘
```

---

## Connection

### WebSocket Endpoint

```
Development: ws://localhost:8000/ws
```

### Thread/Session Management

- AG-UI uses `threadId` instead of `session_id`
- Each conversation thread has a unique `threadId` (UUID)
- Client generates and persists `threadId` (e.g., in localStorage)
- Server uses `threadId` for conversation history via checkpointer

---

## Event Format

All events are JSON-encoded with a `type` discriminator field using SCREAMING_CASE.

### Event Direction

| Direction | Event Types |
|-----------|-------------|
| **Client → Server** | `RunAgentInput`, `CUSTOM` (approval response) |
| **Server → Client** | All other event types |

### Base Event Structure

```typescript
interface BaseEvent {
  type: EventType;        // SCREAMING_CASE discriminator
  timestamp?: string;     // ISO 8601 timestamp
}
```

---

## Event Types

### Lifecycle Events

#### RUN_STARTED
Emitted when an agent run begins.

```json
{
  "type": "RUN_STARTED",
  "threadId": "abc123-...",
  "runId": "run-456-...",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

#### RUN_FINISHED
Emitted when an agent run completes.

```json
{
  "type": "RUN_FINISHED",
  "threadId": "abc123-...",
  "runId": "run-456-...",
  "timestamp": "2025-01-15T10:30:05Z"
}
```

#### STEP_STARTED
Emitted when a processing step begins.

```json
{
  "type": "STEP_STARTED",
  "stepName": "thinking",
  "metadata": { "message": "Analyzing request..." },
  "timestamp": "2025-01-15T10:30:01Z"
}
```

#### STEP_FINISHED
Emitted when a processing step completes.

```json
{
  "type": "STEP_FINISHED",
  "stepName": "thinking",
  "timestamp": "2025-01-15T10:30:02Z"
}
```

---

### Text Message Events

#### TEXT_MESSAGE_START
Emitted when a text message begins.

```json
{
  "type": "TEXT_MESSAGE_START",
  "messageId": "msg-789-...",
  "role": "assistant",
  "timestamp": "2025-01-15T10:30:02Z"
}
```

#### TEXT_MESSAGE_CONTENT
Emitted for each content chunk during streaming.

```json
{
  "type": "TEXT_MESSAGE_CONTENT",
  "messageId": "msg-789-...",
  "delta": "Based on the regulations, ",
  "timestamp": "2025-01-15T10:30:02Z"
}
```

#### TEXT_MESSAGE_END
Emitted when a text message is complete.

```json
{
  "type": "TEXT_MESSAGE_END",
  "messageId": "msg-789-...",
  "timestamp": "2025-01-15T10:30:04Z"
}
```

---

### Tool Call Events

#### TOOL_CALL_START
Emitted when a tool call begins.

```json
{
  "type": "TOOL_CALL_START",
  "toolCallId": "call-abc-...",
  "toolCallName": "search_regulations",
  "parentMessageId": "msg-789-...",
  "timestamp": "2025-01-15T10:30:02Z"
}
```

#### TOOL_CALL_ARGS
Emitted to stream tool call arguments.

```json
{
  "type": "TOOL_CALL_ARGS",
  "toolCallId": "call-abc-...",
  "delta": "{\"query\": \"food safety\", \"limit\": 10}",
  "timestamp": "2025-01-15T10:30:02Z"
}
```

#### TOOL_CALL_END
Emitted when a tool call completes (success or error).

```json
{
  "type": "TOOL_CALL_END",
  "toolCallId": "call-abc-...",
  "result": "Found 5 relevant regulations",
  "error": null,
  "timestamp": "2025-01-15T10:30:03Z"
}
```

---

## Conversation Flows

### Flow 1: Basic Text Response

```
Client                                    Server
  |                                         |
  |-- RunAgentInput -------------------->   |
  |    { threadId, messages: [...] }        |
  |                                         |
  | <------------ RUN_STARTED               |
  | <------------ STEP_STARTED (thinking)   |
  |                                         |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ TEXT_MESSAGE_CONTENT      |
  | <------------ TEXT_MESSAGE_CONTENT      |
  | <------------ TEXT_MESSAGE_END          |
  |                                         |
  | <------------ STEP_FINISHED (thinking)  |
  | <------------ RUN_FINISHED              |
```

### Flow 2: Tool Execution

```
Client                                    Server
  |                                         |
  |-- RunAgentInput -------------------->   |
  |                                         |
  | <------------ RUN_STARTED               |
  | <------------ STEP_STARTED (routing)    |
  | <------------ STEP_FINISHED (routing)   |
  | <------------ STEP_STARTED (thinking)   |
  |                                         |
  | <------------ STEP_STARTED (exec_tools) |
  | <------------ TOOL_CALL_START           |
  | <------------ TOOL_CALL_ARGS            |
  | <------------ TOOL_CALL_END             |
  | <------------ STEP_FINISHED (exec_tools)|
  |                                         |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ TEXT_MESSAGE_CONTENT...   |
  | <------------ TEXT_MESSAGE_END          |
  |                                         |
  | <------------ STEP_FINISHED (thinking)  |
  | <------------ RUN_FINISHED              |
```

---

## Custom Events (HITL)

AGORA uses `CUSTOM` events for human-in-the-loop approval flow.

### agora:tool_approval_request

Sent by server to request approval for a tool execution.

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
  },
  "timestamp": "2025-01-15T10:30:02Z"
}
```

### agora:tool_approval_response

Sent by client with the approval decision.

```json
{
  "type": "CUSTOM",
  "name": "agora:tool_approval_response",
  "value": {
    "approvalId": "appr-xyz789",
    "approved": true,
    "feedback": "Looks good, proceed with report generation"
  }
}
```

### agora:error

Sent by server for protocol errors.

```json
{
  "type": "CUSTOM",
  "name": "agora:error",
  "value": {
    "errorCode": "moderation_violation",
    "message": "Your message contains prohibited content",
    "details": { "reason": "profanity" }
  },
  "timestamp": "2025-01-15T10:30:02Z"
}
```

---

## Implementation Guide

### Client Input Format

To start a new run, send a `RunAgentInput`:

```json
{
  "threadId": "abc123-...",
  "runId": "run-456-...",
  "messages": [
    { "role": "user", "content": "What are the food safety regulations?" }
  ],
  "context": {}
}
```

### TypeScript Client Setup

```typescript
import { AGUIWebSocketClient } from '@/lib/websocket';

const client = new AGUIWebSocketClient({
  url: 'ws://localhost:8000/ws',
});

client.onEvent((event) => {
  switch (event.type) {
    case 'TEXT_MESSAGE_START':
      // Start new message bubble
      break;
    case 'TEXT_MESSAGE_CONTENT':
      // Append delta to current message
      break;
    case 'TEXT_MESSAGE_END':
      // Finalize message
      break;
    case 'CUSTOM':
      if (event.name === 'agora:tool_approval_request') {
        // Show approval dialog
      }
      break;
  }
});

client.connect();
client.sendRunInput(threadId, 'Hello!');
```

### Python Server Setup

```python
from agora_langgraph.api.ag_ui_handler import AGUIProtocolHandler
from agora_langgraph.common.ag_ui_types import RunAgentInput

handler = AGUIProtocolHandler(websocket)

# Receive input
input_data = await handler.receive_message()
if isinstance(input_data, RunAgentInput):
    # Process the run
    await handler.send_run_started(input_data.threadId, input_data.runId)
    # ... streaming events ...
    await handler.send_run_finished(input_data.threadId, input_data.runId)
```

---

## Migration from HAI

### Naming Changes

| HAI (v1) | AG-UI (v2) |
|----------|------------|
| `session_id` | `threadId` |
| `message_id` | `messageId` |
| `tool_call_id` | `toolCallId` |
| `approval_id` | `approvalId` |
| `is_final` | N/A (use TEXT_MESSAGE_END) |
| snake_case fields | camelCase fields |

### Message Type Mapping

| HAI Message Type | AG-UI Event(s) |
|-----------------|----------------|
| `user_message` | `RunAgentInput` |
| `assistant_message_chunk` | `TEXT_MESSAGE_START` → `TEXT_MESSAGE_CONTENT` → `TEXT_MESSAGE_END` |
| `tool_call` (started) | `TOOL_CALL_START` → `TOOL_CALL_ARGS` |
| `tool_call` (completed) | `TOOL_CALL_END` |
| `status` | `STEP_STARTED` / `STEP_FINISHED` |
| `tool_approval_request` | `CUSTOM` with `agora:tool_approval_request` |
| `error` | `CUSTOM` with `agora:error` |

---

**Document Maintained By:** Gradient - NVWA  
**Protocol Reference:** https://github.com/ag-ui-protocol/ag-ui

