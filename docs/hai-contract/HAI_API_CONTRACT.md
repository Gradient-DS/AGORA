# AGORA HAI API Contract

**Version:** 2.4.1
**Last Updated:** December 2025

This document defines the complete API contract between the HAI (Human Agent Interface) frontend and the AGORA orchestrator backend. It covers both real-time WebSocket communication and REST endpoints.

## Table of Contents

### REST API
1. [Session Management](#session-management-rest-api)

### WebSocket Protocol (AG-UI)
2. [Overview](#overview)
3. [Connection](#connection)
4. [Event Format](#event-format)
5. [Event Types](#event-types)
6. [Event Lifecycle Rules](#event-lifecycle-rules)
7. [Conversation Flows](#conversation-flows)
8. [Custom Events (HITL)](#custom-events-hitl)
9. [Future: Voice Support](#future-voice-support)
10. [Implementation Guide](#implementation-guide)
11. [Official AG-UI Package Usage](#official-ag-ui-package-usage)

---

# REST API

The REST API handles non-real-time operations such as session management, conversation history retrieval, and user preferences.

---

## Session Management (REST API)

The REST endpoints manage conversation sessions and history. These are called before establishing WebSocket connections or when switching between conversations.

### Endpoints

#### GET /sessions

List all sessions for a user, ordered by last activity (most recent first).

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_id` | string | Yes | - | Inspector persona ID (e.g., "koen", "fatima") |
| `limit` | integer | No | 50 | Max sessions to return (1-100) |
| `offset` | integer | No | 0 | Pagination offset |

**Response:**

```json
{
  "success": true,
  "sessions": [
    {
      "sessionId": "abc-123-def-456",
      "userId": "koen",
      "title": "Inspectie bij Restaurant Bella Rosa",
      "firstMessagePreview": "Start inspectie bij Restaurant...",
      "messageCount": 12,
      "createdAt": "2025-12-01T10:30:00Z",
      "lastActivity": "2025-12-01T11:45:00Z"
    }
  ],
  "totalCount": 42
}
```

#### GET /sessions/{session_id}/history

Retrieve the full conversation history for a session, including messages and optionally tool calls.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session/thread identifier |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `include_tools` | boolean | No | false | Include tool calls and results in history |

**Response:**

```json
{
  "success": true,
  "threadId": "abc-123-def-456",
  "history": [
    {"role": "user", "content": "Start inspectie bij Restaurant Bella Rosa"},
    {"role": "assistant", "content": "Inspectie gestart...", "agent_id": "history-agent"},
    {"role": "tool_call", "tool_call_id": "tc-1", "tool_name": "get_company_info", "content": "{\"kvk_number\": \"92251854\"}", "agent_id": "history-agent"},
    {"role": "tool", "tool_call_id": "tc-1", "tool_name": "get_company_info", "content": "{\"name\": \"Restaurant Bella Rosa\", ...}"}
  ],
  "messageCount": 4
}
```

**History Message Roles:**

| Role | Description |
|------|-------------|
| `user` | User input message |
| `assistant` | Agent response (includes `agent_id` field) |
| `tool_call` | Tool invocation (includes `tool_call_id`, `tool_name`, `agent_id`) |
| `tool` | Tool result (includes `tool_call_id`, `tool_name`) |

#### GET /sessions/{session_id}/metadata

Get session metadata without the full conversation history.

**Response:**

```json
{
  "success": true,
  "session": {
    "sessionId": "abc-123-def-456",
    "userId": "koen",
    "title": "Inspectie bij Restaurant Bella Rosa",
    "firstMessagePreview": "Start inspectie bij Restaurant...",
    "messageCount": 12,
    "createdAt": "2025-12-01T10:30:00Z",
    "lastActivity": "2025-12-01T11:45:00Z"
  }
}
```

#### DELETE /sessions/{session_id}

Delete a session and all its associated data.

**Response:**

```json
{
  "success": true,
  "message": "Session deleted"
}
```

**Error Response (404):**

```json
{
  "detail": "Session not found"
}
```

### Session Restoration Flow

When a user returns to the application or switches between conversations:

```
Client                                    Server
  |                                         |
  |-- GET /sessions?user_id=koen -------->  |
  |                                         |
  | <-------- Session list                  |
  |                                         |
  |-- GET /sessions/{id}/history?include_tools=true -->
  |                                         |
  | <-------- Messages + Tool Calls         |
  |                                         |
  |  [Populate UI with history]             |
  |                                         |
  |-- WebSocket /ws ----------------------> |
  |                                         |
  |  [Continue conversation via WebSocket]  |
```

1. **Page Load**: Fetch session list via `GET /sessions?user_id={userId}`
2. **Session Selection**: User selects a past conversation from sidebar
3. **Load History**: Fetch full history via `GET /sessions/{id}/history?include_tools=true`
4. **Populate UI**: Load messages into chat and tool calls into debug panel
5. **Connect WebSocket**: Establish connection for new messages using the same `threadId`

---

# WebSocket Protocol (AG-UI)

Real-time communication uses the open-source **AG-UI Protocol** for streaming events between the HAI frontend and the orchestrator backend.

**AG-UI Repository:** https://github.com/ag-ui-protocol/ag-ui
**Official Package:** `ag-ui-protocol` (Python), `@ag-ui/core` (TypeScript)

---

## Overview

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
| **Server → Client** | `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, `STEP_STARTED`, `STEP_FINISHED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `STATE_SNAPSHOT`, `STATE_DELTA`, `CUSTOM` (spoken text, approval request, error) |

### Base Event Structure

```typescript
interface BaseEvent {
  type: EventType;        // SCREAMING_CASE discriminator
  timestamp?: number;     // Unix timestamp in milliseconds (integer)
}
```

### Naming Convention

The official AG-UI package uses **snake_case** for Python field names with automatic **camelCase** aliases for JSON serialization (via Pydantic's alias generator).

### Timestamp Format

All timestamps are **Unix timestamps in milliseconds** (integers), not ISO 8601 strings.

```json
{
  "type": "RUN_STARTED",
  "timestamp": 1705318200000
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
  "timestamp": 1705318200000
}
```

#### RUN_FINISHED
Emitted when an agent run completes (always sent, even after errors).

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
Emitted when an agent run encounters an error. Use this for processing errors.

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
Emitted when a processing step completes. **Must be sent before starting a new step.**

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
Emitted for each content chunk during streaming. **Delta must be non-empty.**

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
  "toolSpokenName": "Ik ga de regelgeving doorzoeken",
  "parentMessageId": "msg-789-...",
  "timestamp": 1705318202000
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `toolCallId` | string | Yes | Unique identifier for this tool call |
| `toolCallName` | string | Yes | Technical name of the tool |
| `toolSpokenName` | string | No | Human-readable spoken description for TTS |
| `parentMessageId` | string | No | ID of the parent message |

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
Emitted when tool call argument streaming completes. **Does NOT contain the result.**

```json
{
  "type": "TOOL_CALL_END",
  "toolCallId": "call-abc-...",
  "timestamp": 1705318203000
}
```

> **Important:** `TOOL_CALL_END` only signals that argument streaming is complete. 
> The actual tool execution result comes via `TOOL_CALL_RESULT`.

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
Emitted for full state synchronization. **Recommended at run start and run end.**

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

## Event Lifecycle Rules

### Step Lifecycle

Steps must follow proper lifecycle management:

1. `STEP_FINISHED` must be sent **before** starting a new step
2. Only one step should be active at a time
3. Common step names: `routing`, `thinking`, `executing_tools`

```
STEP_STARTED(routing) → STEP_FINISHED(routing) →
STEP_STARTED(thinking) → STEP_FINISHED(thinking) →
STEP_STARTED(executing_tools) → STEP_FINISHED(executing_tools) →
STEP_STARTED(thinking) → ...
```

### Tool Call Lifecycle

Tool calls follow a four-event sequence:

```
TOOL_CALL_START → TOOL_CALL_ARGS → TOOL_CALL_END → TOOL_CALL_RESULT
```

| Event | Purpose |
|-------|---------|
| `TOOL_CALL_START` | Begin tool call, identify tool |
| `TOOL_CALL_ARGS` | Stream arguments (can be multiple) |
| `TOOL_CALL_END` | Signal end of argument streaming |
| `TOOL_CALL_RESULT` | Deliver execution result |

### State Snapshot Pattern

Send `STATE_SNAPSHOT` at these points:

1. **After `RUN_STARTED`** - Initial state with `status: "processing"`
2. **On agent change** - When `currentAgent` changes
3. **Before `RUN_FINISHED`** - Final state with `status: "completed"`

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
  | <------------ STATE_SNAPSHOT (initial)  |
  | <------------ STEP_STARTED (routing)    |
  | <------------ STEP_FINISHED (routing)   |
  | <------------ STEP_STARTED (thinking)   |
  |                                         |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ agora:spoken_text_start   |  (CUSTOM, parallel TTS)
  | <------------ TEXT_MESSAGE_CONTENT      |
  | <------------ agora:spoken_text_content |
  | <------------ TEXT_MESSAGE_CONTENT      |
  | <------------ agora:spoken_text_content |
  | <------------ TEXT_MESSAGE_END          |
  | <------------ agora:spoken_text_end     |
  |                                         |
  | <------------ STEP_FINISHED (thinking)  |
  | <------------ STATE_SNAPSHOT (final)    |
  | <------------ RUN_FINISHED              |
```

> **Note:** `agora:spoken_text_*` CUSTOM events share the same `messageId` as their `TEXT_MESSAGE_*` counterparts and are sent in parallel for TTS processing.

### Flow 2: Tool Execution

```
Client                                    Server
  |                                         |
  |-- RunAgentInput -------------------->   |
  |                                         |
  | <------------ RUN_STARTED               |
  | <------------ STATE_SNAPSHOT (initial)  |
  | <------------ STEP_STARTED (routing)    |
  | <------------ STEP_FINISHED (routing)   |
  | <------------ STEP_STARTED (thinking)   |
  | <------------ STEP_FINISHED (thinking)  |
  |                                         |
  | <------------ STEP_STARTED (exec_tools) |
  | <------------ TOOL_CALL_START           |  (includes toolSpokenName)
  | <------------ TOOL_CALL_ARGS            |
  | <------------ TOOL_CALL_END             |
  | <------------ TOOL_CALL_RESULT          |
  | <------------ STEP_FINISHED (exec_tools)|
  |                                         |
  | <------------ STEP_STARTED (thinking)   |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ agora:spoken_text_start   |
  | <------------ TEXT_MESSAGE_CONTENT...   |
  | <------------ agora:spoken_text_content...|
  | <------------ TEXT_MESSAGE_END          |
  | <------------ agora:spoken_text_end     |
  | <------------ STEP_FINISHED (thinking)  |
  |                                         |
  | <------------ STATE_SNAPSHOT (final)    |
  | <------------ RUN_FINISHED              |
```

### Flow 3: Error Handling

```
Client                                    Server
  |                                         |
  |-- RunAgentInput -------------------->   |
  |                                         |
  | <------------ RUN_STARTED               |
  | <------------ STATE_SNAPSHOT            |
  | <------------ STEP_STARTED (thinking)   |
  |                                         |
  | <------------ RUN_ERROR                 |
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

Sent by server for AGORA-specific protocol errors (e.g., moderation violations). For general run errors, use `RUN_ERROR` instead.

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

### Spoken Text Events

These events stream text optimized for text-to-speech (TTS). They run **in parallel** with regular text message events and share the same `messageId`. The spoken text may be simplified, abbreviations expanded, or formatted differently for natural speech.

#### agora:spoken_text_start

Emitted when a spoken text message begins (same timing as TEXT_MESSAGE_START).

```json
{
  "type": "CUSTOM",
  "name": "agora:spoken_text_start",
  "value": {
    "messageId": "msg-789-...",
    "role": "assistant"
  },
  "timestamp": 1705318202000
}
```

#### agora:spoken_text_content

Emitted for each spoken content chunk during streaming.

```json
{
  "type": "CUSTOM",
  "name": "agora:spoken_text_content",
  "value": {
    "messageId": "msg-789-...",
    "delta": "Based on the regulations, "
  },
  "timestamp": 1705318202100
}
```

#### agora:spoken_text_end

Emitted when a spoken text message is complete.

```json
{
  "type": "CUSTOM",
  "name": "agora:spoken_text_end",
  "value": {
    "messageId": "msg-789-..."
  },
  "timestamp": 1705318204000
}
```

---

## Future: Voice Support

> **Status:** Planned  
> **AG-UI Tracking:** [github.com/ag-ui-protocol/ag-ui/issues/126](https://github.com/ag-ui-protocol/ag-ui/issues/126)

### Overview

AGORA will support voice input/output for hands-free inspector interactions. The AG-UI protocol does not currently support audio natively, but multimodal support (audio, images, files) is on the AG-UI roadmap.

### Migration Strategy

1. **Phase 1 (Current):** Implement voice using AGORA `CUSTOM` events
2. **Phase 2 (Future):** Migrate to native AG-UI audio events when available

This approach ensures compatibility with the current AG-UI protocol while allowing seamless migration to native support.

### Planned Custom Events

#### agora:audio_input_start

Sent by client when user starts speaking.

```json
{
  "type": "CUSTOM",
  "name": "agora:audio_input_start",
  "value": {
    "messageId": "audio-input-123",
    "format": "pcm",
    "sampleRate": 16000,
    "channels": 1
  }
}
```

#### agora:audio_input_chunk

Sent by client with audio data chunks during recording.

```json
{
  "type": "CUSTOM",
  "name": "agora:audio_input_chunk",
  "value": {
    "messageId": "audio-input-123",
    "data": "<base64-encoded-audio>",
    "sequence": 0
  }
}
```

#### agora:audio_input_end

Sent by client when user stops speaking.

```json
{
  "type": "CUSTOM",
  "name": "agora:audio_input_end",
  "value": {
    "messageId": "audio-input-123"
  }
}
```

#### agora:audio_output_start

Sent by server when starting audio response.

```json
{
  "type": "CUSTOM",
  "name": "agora:audio_output_start",
  "value": {
    "messageId": "audio-output-456",
    "format": "pcm",
    "sampleRate": 24000,
    "channels": 1
  },
  "timestamp": 1705318202000
}
```

#### agora:audio_output_chunk

Sent by server with audio response chunks.

```json
{
  "type": "CUSTOM",
  "name": "agora:audio_output_chunk",
  "value": {
    "messageId": "audio-output-456",
    "data": "<base64-encoded-audio>",
    "sequence": 0
  },
  "timestamp": 1705318202100
}
```

#### agora:audio_output_end

Sent by server when audio response is complete.

```json
{
  "type": "CUSTOM",
  "name": "agora:audio_output_end",
  "value": {
    "messageId": "audio-output-456"
  },
  "timestamp": 1705318203000
}
```

### Audio Format Considerations

| Property | Input (Client → Server) | Output (Server → Client) |
|----------|------------------------|--------------------------|
| Format | PCM, WebM, Opus | PCM, MP3, Opus |
| Sample Rate | 16000 Hz | 24000 Hz |
| Channels | 1 (mono) | 1 (mono) |
| Encoding | Base64 | Base64 |

### Flow: Voice Conversation

```
Client                                    Server
  |                                         |
  |-- agora:audio_input_start ---------->   |
  |-- agora:audio_input_chunk ---------->   |
  |-- agora:audio_input_chunk ---------->   |
  |-- agora:audio_input_end ------------>   |
  |                                         |
  | <------------ RUN_STARTED               |
  | <------------ STATE_SNAPSHOT            |
  | <------------ STEP_STARTED (processing) |
  |                                         |
  | <------------ agora:audio_output_start  |
  | <------------ agora:audio_output_chunk  |
  | <------------ agora:audio_output_chunk  |
  | <------------ agora:audio_output_end    |
  |                                         |
  | <------------ TEXT_MESSAGE_START        |
  | <------------ TEXT_MESSAGE_CONTENT      |  (transcript)
  | <------------ TEXT_MESSAGE_END          |
  |                                         |
  | <------------ STEP_FINISHED             |
  | <------------ RUN_FINISHED              |
```

> **Note:** Text transcript events are sent alongside audio for accessibility and chat history.

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
      console.error(event.message);
      break;
    case 'STATE_SNAPSHOT':
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
    case 'TOOL_CALL_END':
      // Arguments complete, wait for TOOL_CALL_RESULT
      break;
    case 'TOOL_CALL_RESULT':
      // Tool execution result available
      updateToolResult(event.toolCallId, event.content);
      break;
    case 'CUSTOM':
      if (event.name === 'agora:tool_approval_request') {
        showApprovalDialog(event.value);
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
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
)

from agora_langgraph.common.ag_ui_types import RunAgentInput

# Receive input
input_data = await handler.receive_message()
if isinstance(input_data, RunAgentInput):
    # Emit RUN_STARTED
    await handler.send_run_started(input_data.thread_id, run_id)
    
    # Emit initial STATE_SNAPSHOT
    await handler.send_state_snapshot({
        "threadId": input_data.thread_id,
        "runId": run_id,
        "currentAgent": "general-agent",
        "status": "processing",
    })
    
    # ... process with streaming events ...
    
    # Emit final STATE_SNAPSHOT
    await handler.send_state_snapshot({
        "threadId": input_data.thread_id,
        "runId": run_id,
        "currentAgent": "general-agent",
        "status": "completed",
    })
    
    # Emit RUN_FINISHED
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
```

### AGORA Extensions

AGORA extends the official types with:

- `RunAgentInput` - Simplified input format for the frontend
- `ToolApprovalRequestPayload` - HITL approval request
- `ToolApprovalResponsePayload` - HITL approval response
- `ErrorPayload` - AGORA-specific error details

These are defined in `agora_langgraph.common.ag_ui_types`.

---

## Changelog

### v2.4.1 (December 2025)
- **BREAKING**: Migrated spoken text events from top-level event types to CUSTOM events
- Old events `TEXT_SPOKEN_MESSAGE_START/CONTENT/END` replaced with `agora:spoken_text_start/content/end`
- Follows AG-UI protocol extension pattern (same as HITL approval and error events)
- Spoken text event payloads are now nested under the `value` field

### v2.4.0 (December 2025)
- Added spoken text events for TTS support (now migrated to CUSTOM events in v2.4.1)
- Spoken message events stream in parallel with regular text messages, sharing the same `messageId`
- Added `toolSpokenName` optional field to `TOOL_CALL_START` for human-readable spoken tool descriptions

### v2.3.0 (December 2025)
- **Renamed**: `AG_UI_PROTOCOL.md` → `HAI_API_CONTRACT.md` to reflect unified REST + WebSocket contract
- **Restructured**: Document now has clear REST API and WebSocket Protocol sections
- Added Session Management REST API endpoints: `GET /sessions`, `GET /sessions/{id}/history`, `GET /sessions/{id}/metadata`, `DELETE /sessions/{id}`
- Documented history message roles including `tool_call` for tool invocations
- Added Session Restoration Flow diagram

### v2.2.0 (December 2025)
- Added "Future: Voice Support" section with planned `CUSTOM` event specifications
- Documented migration strategy: AGORA custom events → native AG-UI audio (when available)
- Added audio input/output event definitions and flow diagram

### v2.1.1 (December 2025)
- Clarified `TOOL_CALL_END` does not contain result (result is in `TOOL_CALL_RESULT`)
- Added "Event Lifecycle Rules" section with step and tool call patterns
- Clarified timestamp format as Unix milliseconds
- Added STATE_SNAPSHOT pattern recommendations
- Updated mock_server.py to match protocol exactly

### v2.1.0 (November 2025)
- Added `RUN_ERROR` event handling
- Added `TOOL_CALL_RESULT` event
- Added `STATE_SNAPSHOT` at run start/end
- Removed legacy HAI protocol support

---

**Document Maintained By:** Gradient - NVWA  
**Protocol Reference:** https://github.com/ag-ui-protocol/ag-ui
