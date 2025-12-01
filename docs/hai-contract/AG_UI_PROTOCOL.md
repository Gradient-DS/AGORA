# AGORA AG-UI Protocol Specification

**Version:** 2.1.0  
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
8. [Official AG-UI Package Usage](#official-ag-ui-package-usage)

---

## Overview

AGORA uses the open-source **AG-UI Protocol** for communication between the HAI (Human Agent Interface) frontend and the LangGraph orchestrator backend.

**AG-UI Repository:** https://github.com/ag-ui-protocol/ag-ui  
**Official Package:** `ag-ui-protocol` (Python), `@ag-ui/core` (TypeScript)

### Key Features

- **Event-driven architecture** with typed events
- **Transport agnostic** (WebSocket supported)
- **Streaming-first** for real-time text and tool call updates
- **Lifecycle events** for run and step tracking
- **State synchronization** via `STATE_SNAPSHOT` and `STATE_DELTA` events
- **Custom events** for protocol extensions (HITL approval)
- **Type-safe** with full TypeScript/Python support using official packages

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
  timestamp?: number;     // Unix timestamp in milliseconds
}
```

### Naming Convention

The official AG-UI package uses **snake_case** for Python field names with automatic **camelCase** aliases for JSON serialization (via Pydantic's alias generator).

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
  "timestamp": 1705318200000
}
```

#### RUN_FINISHED
Emitted when an agent run completes.

```json
{
  "type": "RUN_FINISHED",
  "threadId": "abc123-...",
  "runId": "run-456-...",
  "result": null,
  "timestamp": 1705318205000
}
```

#### RUN_ERROR
Emitted when an agent run encounters an error.

```json
{
  "type": "RUN_ERROR",
  "message": "Error processing request",
  "code": "processing_error",
  "timestamp": 1705318205000
}
```

#### STEP_STARTED
Emitted when a processing step begins.

```json
{
  "type": "STEP_STARTED",
  "stepName": "thinking",
  "timestamp": 1705318201000
}
```

#### STEP_FINISHED
Emitted when a processing step completes.

```json
{
  "type": "STEP_FINISHED",
  "stepName": "thinking",
  "timestamp": 1705318202000
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
  "timestamp": 1705318202000
}
```

#### TEXT_MESSAGE_CONTENT
Emitted for each content chunk during streaming. Delta must be non-empty.

```json
{
  "type": "TEXT_MESSAGE_CONTENT",
  "messageId": "msg-789-...",
  "delta": "Based on the regulations, ",
  "timestamp": 1705318202100
}
```

#### TEXT_MESSAGE_END
Emitted when a text message is complete.

```json
{
  "type": "TEXT_MESSAGE_END",
  "messageId": "msg-789-...",
  "timestamp": 1705318204000
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
  "timestamp": 1705318202000
}
```

#### TOOL_CALL_ARGS
Emitted to stream tool call arguments.

```json
{
  "type": "TOOL_CALL_ARGS",
  "toolCallId": "call-abc-...",
  "delta": "{\"query\": \"food safety\", \"limit\": 10}",
  "timestamp": 1705318202100
}
```

#### TOOL_CALL_END
Emitted when tool call argument streaming completes.

```json
{
  "type": "TOOL_CALL_END",
  "toolCallId": "call-abc-...",
  "timestamp": 1705318203000
}
```

#### TOOL_CALL_RESULT
Emitted with the tool execution result.

```json
{
  "type": "TOOL_CALL_RESULT",
  "messageId": "tool-result-abc",
  "toolCallId": "call-abc-...",
  "content": "Found 5 relevant regulations",
  "role": "tool",
  "timestamp": 1705318203100
}
```

---

### State Events

#### STATE_SNAPSHOT
Emitted for full state synchronization.

```json
{
  "type": "STATE_SNAPSHOT",
  "snapshot": {
    "threadId": "abc123-...",
    "runId": "run-456-...",
    "currentAgent": "regulation-agent",
    "status": "processing"
  },
  "timestamp": 1705318200000
}
```

#### STATE_DELTA
Emitted for incremental state updates (JSON Patch format, RFC 6902).

```json
{
  "type": "STATE_DELTA",
  "delta": [
    { "op": "replace", "path": "/currentAgent", "value": "reporting-agent" }
  ],
  "timestamp": 1705318201000
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
  | <------------ STATE_SNAPSHOT            |
  | <------------ STEP_STARTED (routing)    |
  | <------------ STEP_FINISHED (routing)   |
  | <------------ STEP_STARTED (thinking)   |
  |                                         |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ TEXT_MESSAGE_CONTENT      |
  | <------------ TEXT_MESSAGE_CONTENT      |
  | <------------ TEXT_MESSAGE_END          |
  |                                         |
  | <------------ STEP_FINISHED (thinking)  |
  | <------------ STATE_SNAPSHOT (final)    |
  | <------------ RUN_FINISHED              |
```

### Flow 2: Tool Execution

```
Client                                    Server
  |                                         |
  |-- RunAgentInput -------------------->   |
  |                                         |
  | <------------ RUN_STARTED               |
  | <------------ STATE_SNAPSHOT            |
  | <------------ STEP_STARTED (routing)    |
  | <------------ STEP_FINISHED (routing)   |
  | <------------ STEP_STARTED (thinking)   |
  |                                         |
  | <------------ STEP_FINISHED (thinking)  |
  | <------------ STEP_STARTED (exec_tools) |
  | <------------ TOOL_CALL_START           |
  | <------------ TOOL_CALL_ARGS            |
  | <------------ TOOL_CALL_END             |
  | <------------ TOOL_CALL_RESULT          |
  | <------------ STEP_FINISHED (exec_tools)|
  |                                         |
  | <------------ STEP_STARTED (thinking)   |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ TEXT_MESSAGE_CONTENT...   |
  | <------------ TEXT_MESSAGE_END          |
  |                                         |
  | <------------ STEP_FINISHED (thinking)  |
  | <------------ STATE_SNAPSHOT (final)    |
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
    "parameters": { "inspectionId": "INS-2024-001" },
    "reasoning": "User requested to finalize the inspection report",
    "riskLevel": "high",
    "approvalId": "appr-xyz789"
  },
  "timestamp": 1705318202000
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

Sent by server for AGORA-specific protocol errors. For general run errors, use `RUN_ERROR` instead.

```json
{
  "type": "CUSTOM",
  "name": "agora:error",
  "value": {
    "errorCode": "moderation_violation",
    "message": "Your message contains prohibited content",
    "details": { "reason": "profanity" }
  },
  "timestamp": 1705318202000
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

Note: `runId` is optional - the server will generate one if not provided.

### TypeScript Client Setup

```typescript
import { AGUIWebSocketClient } from '@/lib/websocket';

const client = new AGUIWebSocketClient({
  url: 'ws://localhost:8000/ws',
});

client.onEvent((event) => {
  switch (event.type) {
    case 'RUN_ERROR':
      // Handle run error
      console.error(event.message);
      break;
    case 'STATE_SNAPSHOT':
      // Update local state
      updateState(event.snapshot);
      break;
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
from ag_ui.core import (
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StateSnapshotEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
)
from ag_ui.encoder import EventEncoder

from agora_langgraph.common.ag_ui_types import RunAgentInput

encoder = EventEncoder()

# Receive input
input_data = await handler.receive_message()
if isinstance(input_data, RunAgentInput):
    # Process the run using official AG-UI event types
    await handler.send_run_started(input_data.thread_id, run_id)
    await handler.send_state_snapshot({"status": "processing"})
    # ... streaming events ...
    await handler.send_run_finished(input_data.thread_id, run_id)
```

---

## Official AG-UI Package Usage

AGORA uses the official `ag-ui-protocol` Python package for event types:

### Installation

```bash
pip install ag-ui-protocol>=0.1.0
```

### Import Official Types

```python
from ag_ui.core import (
    EventType,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    StateSnapshotEvent,
    StateDeltaEvent,
    CustomEvent,
)
from ag_ui.encoder import EventEncoder
```

### AGORA Extensions

AGORA extends the official types with:

- `RunAgentInput` - Simplified input format for the frontend
- `ToolApprovalRequestPayload` - HITL approval request
- `ToolApprovalResponsePayload` - HITL approval response
- `ErrorPayload` - AGORA-specific error details

These are defined in `agora_langgraph.common.ag_ui_types`.

---

**Document Maintained By:** Gradient - NVWA  
**Protocol Reference:** https://github.com/ag-ui-protocol/ag-ui
