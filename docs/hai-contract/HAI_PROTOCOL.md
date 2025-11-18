# AGORA HAI Protocol Specification

**Version:** 1.0.0  
**Last Updated:** November 17, 2025

## Table of Contents

1. [Overview](#overview)
2. [Connection](#connection)
3. [Message Format](#message-format)
4. [Message Types](#message-types)
5. [Conversation Flows](#conversation-flows)
6. [Error Handling](#error-handling)
7. [Implementation Guide](#implementation-guide)
8. [Testing](#testing)

---

## Overview

The HAI (Human Agent Interface) Protocol defines the WebSocket-based communication contract between the frontend HAI client and the AGORA backend orchestrator.

### Key Features

- **Real-time bidirectional communication** via WebSocket
- **Streaming responses** for immediate user feedback
- **Tool execution transparency** with lifecycle notifications
- **Human-in-the-loop approvals** for sensitive operations
- **Session-based continuity** for conversation history

### Architecture Context

```
┌─────────────┐         WebSocket          ┌──────────────────┐
│             │◄──────────────────────────►│                  │
│  HAI Client │    HAI Protocol (JSON)     │  Orchestrator    │
│  (Frontend) │                            │  (Backend)       │
│             │                            │                  │
└─────────────┘                            └──────────────────┘
```

---

## Connection

### WebSocket Endpoint

```
Development: ws://localhost:8000/ws
```

### Connection Lifecycle

1. **Initiate**: Client opens WebSocket connection to `/ws`
2. **Accept**: Server accepts connection
3. **Authenticate** (future): Optional authentication handshake
4. **Communicate**: Bidirectional message exchange
5. **Close**: Either party can close connection gracefully

### Session Management

- Each conversation has a unique `session_id` (UUID format recommended)
- Client generates and persists `session_id` (e.g., in localStorage)
- Server uses `session_id` to retrieve conversation history from SQLite
- Sessions persist across page reloads and reconnections

**Example Session Flow:**
```javascript
// First visit - generate new session
const sessionId = crypto.randomUUID();
localStorage.setItem('agora_session_id', sessionId);

// Reconnection - reuse existing session
const sessionId = localStorage.getItem('agora_session_id') || crypto.randomUUID();
```

---

## Message Format

All messages are JSON-encoded text frames with a `type` discriminator field.

### Message Direction

| Direction | Message Types |
|-----------|--------------|
| **Client → Server** | `user_message`, `tool_approval_response` |
| **Server → Client** | `assistant_message`, `assistant_message_chunk`, `tool_call`, `tool_approval_request`, `status`, `error` |

### Type Discriminator

Every message includes a `type` field that determines its schema:

```json
{
  "type": "user_message",
  "content": "...",
  ...
}
```

---

## Message Types

### 1. User Message (Client → Server)

User input sent to the assistant.

```typescript
interface UserMessage {
  type: "user_message";
  content: string;              // User's message (1-10,000 chars)
  session_id: string;           // Session UUID
  metadata?: Record<string, any>; // Optional metadata
}
```

**Example:**
```json
{
  "type": "user_message",
  "content": "What are the regulations for food storage?",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "metadata": {}
}
```

**Required Fields:** `type`, `content`, `session_id`

---

### 2. Assistant Message (Server → Client)

Complete assistant response (non-streaming mode).

```typescript
interface AssistantMessage {
  type: "assistant_message";
  content: string;              // Complete response text
  session_id?: string;
  agent_id?: string;            // Which agent responded
  metadata?: Record<string, any>;
}
```

**Example:**
```json
{
  "type": "assistant_message",
  "content": "Based on the regulations, restaurants must maintain proper temperature control...",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "agent_id": "regulation_agent",
  "metadata": {}
}
```

---

### 3. Assistant Message Chunk (Server → Client) ⭐ PREFERRED

**Streaming response chunk** for real-time display.

```typescript
interface AssistantMessageChunk {
  type: "assistant_message_chunk";
  content: string;              // Partial text chunk
  session_id: string;
  agent_id?: string;
  message_id: string;           // Groups chunks together
  is_final: boolean;            // True for last chunk
}
```

**Example Flow:**
```json
// Chunk 1
{
  "type": "assistant_message_chunk",
  "content": "Based on ",
  "message_id": "msg_001",
  "session_id": "123e4567...",
  "is_final": false
}

// Chunk 2
{
  "type": "assistant_message_chunk",
  "content": "the regulations, ",
  "message_id": "msg_001",
  "session_id": "123e4567...",
  "is_final": false
}

// Final chunk
{
  "type": "assistant_message_chunk",
  "content": "you must maintain...",
  "message_id": "msg_001",
  "session_id": "123e4567...",
  "is_final": true
}
```

**Implementation Notes:**
- Concatenate chunks with the same `message_id`
- Display streaming text in real-time
- When `is_final: true`, finalize the message (stop spinner, enable input)
- Handle potential out-of-order delivery by buffering

---

### 4. Tool Call Message (Server → Client)

Notification about tool execution lifecycle.

```typescript
interface ToolCallMessage {
  type: "tool_call";
  tool_call_id: string;         // Unique identifier
  tool_name: string;            // e.g., "search_regulations"
  parameters: Record<string, any>; // Tool input params
  session_id: string;
  status: "started" | "completed" | "failed";
  result?: string;              // Present when status="completed"
  agent_id?: string;
  metadata?: Record<string, any>;
}
```

**Status Lifecycle:**

1. **`started`** - Tool execution begins
   ```json
   {
     "type": "tool_call",
     "tool_call_id": "call_abc123",
     "tool_name": "search_regulations",
     "parameters": {"query": "food safety"},
     "session_id": "123e4567...",
     "status": "started"
   }
   ```
   *UI: Show "Searching regulations..." indicator*

2. **`completed`** - Tool execution succeeded
   ```json
   {
     "type": "tool_call",
     "tool_call_id": "call_abc123",
     "tool_name": "search_regulations",
     "parameters": {"query": "food safety"},
     "session_id": "123e4567...",
     "status": "completed",
     "result": "Found 5 relevant regulations"
   }
   ```
   *UI: Show "Found 5 relevant regulations" success badge*

3. **`failed`** - Tool execution failed
   ```json
   {
     "type": "tool_call",
     "tool_call_id": "call_abc123",
     "tool_name": "search_regulations",
     "status": "failed",
     "result": "Database connection timeout"
   }
   ```
   *UI: Show error indicator*

---

### 5. Tool Approval Request (Server → Client)

Request user permission before executing sensitive operations.

```typescript
interface ToolApprovalRequest {
  type: "tool_approval_request";
  tool_name: string;
  tool_description: string;     // What the tool does
  parameters: Record<string, any>;
  reasoning: string;            // Why agent wants to use it
  risk_level: "low" | "medium" | "high" | "critical";
  session_id: string;
  approval_id: string;          // Unique request ID
}
```

**Example:**
```json
{
  "type": "tool_approval_request",
  "tool_name": "generate_inspection_report",
  "tool_description": "Generates official PDF inspection report that will be stored permanently",
  "parameters": {"inspection_id": "INS-2024-001"},
  "reasoning": "User requested to finalize the inspection report",
  "risk_level": "high",
  "session_id": "123e4567...",
  "approval_id": "appr_abc123"
}
```

**UI Implementation:**
- Show modal dialog with tool details
- Display `tool_description` and `reasoning`
- Show `parameters` in expandable section
- Color-code by `risk_level`:
  - `low` - Green
  - `medium` - Yellow
  - `high` - Orange
  - `critical` - Red
- Provide "Approve" and "Reject" buttons
- Optional feedback textarea

---

### 6. Tool Approval Response (Client → Server)

User's approval/rejection decision.

```typescript
interface ToolApprovalResponse {
  type: "tool_approval_response";
  approval_id: string;          // Must match request
  approved: boolean;            // true = proceed, false = cancel
  feedback?: string;            // Optional user comment
}
```

**Example (Approved):**
```json
{
  "type": "tool_approval_response",
  "approval_id": "appr_abc123",
  "approved": true,
  "feedback": "Looks good, proceed with report generation"
}
```

**Example (Rejected):**
```json
{
  "type": "tool_approval_response",
  "approval_id": "appr_abc123",
  "approved": false,
  "feedback": "I need to add more inspection details first"
}
```

---

### 7. Status Message (Server → Client)

Processing status updates for loading indicators.

```typescript
interface StatusMessage {
  type: "status";
  status: "thinking" | "routing" | "executing_tools" | "completed";
  message?: string;             // Optional status text
  session_id?: string;
}
```

**UI Mapping:**

| Status | UI Behavior | Example Message |
|--------|------------|----------------|
| `thinking` | Show "thinking" spinner | "Assistant is thinking..." |
| `routing` | Show routing indicator | "Routing to specialist agent..." |
| `executing_tools` | Show tool execution progress | "Searching database..." |
| `completed` | Hide all loading indicators | null |

**Example:**
```json
{
  "type": "status",
  "status": "thinking",
  "message": "Analyzing your question...",
  "session_id": "123e4567..."
}
```

---

### 8. Error Message (Server → Client)

Error notification with details.

```typescript
interface ErrorMessage {
  type: "error";
  error_code: string;           // Machine-readable code
  message: string;              // Human-readable message
  details?: Record<string, any>; // Additional context
}
```

**Common Error Codes:**

| Error Code | Meaning | User Action |
|-----------|---------|------------|
| `moderation_violation` | Content blocked by filter | Rephrase message |
| `rate_limit_exceeded` | Too many requests | Wait and retry |
| `tool_execution_failed` | Tool call failed | Check parameters |
| `invalid_session` | Session not found | Create new session |
| `invalid_json` | Malformed message | Check client code |

**Example:**
```json
{
  "type": "error",
  "error_code": "moderation_violation",
  "message": "Your message contains prohibited content",
  "details": {
    "blocked_pattern": "profanity",
    "severity": "medium"
  }
}
```

---

## Conversation Flows

### Flow 1: Basic Question-Answer

```
Client                                    Server
  |                                         |
  |-- UserMessage -----------------------> |
  |   "What are food safety regs?"         |
  |                                         |
  | <------------ StatusMessage: thinking  |
  |                                         |
  | <------------ AssistantMessageChunk    |
  | <------------ AssistantMessageChunk    |
  | <------------ AssistantMessageChunk    |
  | <------ AssistantMessageChunk (final)  |
  |                                         |
  | <------------ StatusMessage: completed |
```

### Flow 2: Tool Execution

```
Client                                    Server
  |                                         |
  |-- UserMessage -----------------------> |
  |   "Search for restaurant regulations"  |
  |                                         |
  | <------------ StatusMessage: routing   |
  | <----- StatusMessage: executing_tools  |
  |                                         |
  | <--------- ToolCallMessage: started    |
  |            (tool: search_regulations)  |
  |                                         |
  | <-------- ToolCallMessage: completed   |
  |           (result: "Found 5 docs")     |
  |                                         |
  | <------------ AssistantMessageChunk... |
  | <------------ StatusMessage: completed |
```

### Flow 3: Human-in-the-Loop Approval

```
Client                                    Server
  |                                         |
  |-- UserMessage -----------------------> |
  |   "Generate the inspection report"     |
  |                                         |
  | <------------ StatusMessage: thinking  |
  |                                         |
  | <-------- ToolApprovalRequest -------- |
  |           (tool: generate_report)      |
  |           [MODAL SHOWN TO USER]        |
  |                                         |
  |-- ToolApprovalResponse --------------> |
  |   (approved: true)                     |
  |                                         |
  | <--------- ToolCallMessage: started    |
  | <-------- ToolCallMessage: completed   |
  |                                         |
  | <------------ AssistantMessageChunk... |
  | <------------ StatusMessage: completed |
```

### Flow 4: Error Handling

```
Client                                    Server
  |                                         |
  |-- UserMessage (with profanity) ------> |
  |                                         |
  | <------------ ErrorMessage ----------- |
  |   (error_code: moderation_violation)   |
  |   [ERROR SHOWN TO USER]                |
  |                                         |
  |-- UserMessage (rephrased) -----------> |
  |   [NORMAL FLOW CONTINUES]              |
```

---

## Error Handling

### Client-Side Error Handling

```typescript
// WebSocket connection error
websocket.onerror = (error) => {
  console.error('WebSocket error:', error);
  showNotification('Connection error. Retrying...');
  // Implement exponential backoff retry
};

// WebSocket closed
websocket.onclose = (event) => {
  if (!event.wasClean) {
    console.error('Connection closed unexpectedly:', event.code);
    attemptReconnection();
  }
};

// Message parsing error
websocket.onmessage = (event) => {
  try {
    const message = JSON.parse(event.data);
    handleMessage(message);
  } catch (error) {
    console.error('Failed to parse message:', error);
    // Log to monitoring system
  }
};

// Protocol error message
function handleErrorMessage(error: ErrorMessage) {
  switch (error.error_code) {
    case 'moderation_violation':
      showError('Your message was blocked. Please rephrase.');
      break;
    case 'rate_limit_exceeded':
      showError('Too many requests. Please wait a moment.');
      setTimeout(() => enableInput(), 5000);
      break;
    case 'invalid_session':
      // Create new session
      localStorage.removeItem('agora_session_id');
      location.reload();
      break;
    default:
      showError(error.message);
  }
}
```

### Reconnection Strategy

```typescript
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_DELAY = 1000; // ms

function attemptReconnection() {
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    showError('Unable to connect. Please refresh the page.');
    return;
  }
  
  const delay = BASE_DELAY * Math.pow(2, reconnectAttempts);
  reconnectAttempts++;
  
  setTimeout(() => {
    console.log(`Reconnection attempt ${reconnectAttempts}...`);
    connectWebSocket();
  }, delay);
}

function connectWebSocket() {
  const ws = new WebSocket('ws://localhost:8000/ws');
  
  ws.onopen = () => {
    reconnectAttempts = 0; // Reset on successful connection
    showNotification('Connected!');
  };
  
  ws.onclose = attemptReconnection;
}
```

---

## Implementation Guide

### Client Implementation Checklist

- [ ] **WebSocket Connection**
  - [ ] Connect to `/ws` endpoint
  - [ ] Handle connection lifecycle (open, close, error)
  - [ ] Implement reconnection with exponential backoff

- [ ] **Session Management**
  - [ ] Generate and persist `session_id`
  - [ ] Include `session_id` in all messages
  - [ ] Handle session expiry

- [ ] **Message Handling**
  - [ ] Parse incoming JSON messages
  - [ ] Route by `type` discriminator
  - [ ] Validate required fields

- [ ] **Streaming Responses**
  - [ ] Concatenate chunks by `message_id`
  - [ ] Display text progressively
  - [ ] Finalize on `is_final: true`

- [ ] **Tool Execution UI**
  - [ ] Show tool execution indicators
  - [ ] Display tool names and status
  - [ ] Handle lifecycle (started → completed/failed)

- [ ] **Approval Flow**
  - [ ] Render approval modal
  - [ ] Display tool details and risk level
  - [ ] Send approval response
  - [ ] Block UI until user decision

- [ ] **Status Indicators**
  - [ ] Show appropriate loading states
  - [ ] Map status to UI elements
  - [ ] Clear indicators on completion

- [ ] **Error Handling**
  - [ ] Display error messages
  - [ ] Handle specific error codes
  - [ ] Log errors for debugging

### TypeScript Types

```typescript
// types.ts
export type HAIMessage =
  | UserMessage
  | AssistantMessage
  | AssistantMessageChunk
  | ToolCallMessage
  | ToolApprovalRequest
  | ToolApprovalResponse
  | StatusMessage
  | ErrorMessage;

export interface UserMessage {
  type: "user_message";
  content: string;
  session_id: string;
  metadata?: Record<string, any>;
}

export interface AssistantMessage {
  type: "assistant_message";
  content: string;
  session_id?: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}

export interface AssistantMessageChunk {
  type: "assistant_message_chunk";
  content: string;
  session_id: string;
  agent_id?: string;
  message_id: string;
  is_final: boolean;
}

export interface ToolCallMessage {
  type: "tool_call";
  tool_call_id: string;
  tool_name: string;
  parameters: Record<string, any>;
  session_id: string;
  status: "started" | "completed" | "failed";
  result?: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}

export interface ToolApprovalRequest {
  type: "tool_approval_request";
  tool_name: string;
  tool_description: string;
  parameters: Record<string, any>;
  reasoning: string;
  risk_level: "low" | "medium" | "high" | "critical";
  session_id: string;
  approval_id: string;
}

export interface ToolApprovalResponse {
  type: "tool_approval_response";
  approval_id: string;
  approved: boolean;
  feedback?: string;
}

export interface StatusMessage {
  type: "status";
  status: "thinking" | "routing" | "executing_tools" | "completed";
  message?: string;
  session_id?: string;
}

export interface ErrorMessage {
  type: "error";
  error_code: string;
  message: string;
  details?: Record<string, any>;
}

// Type guard helpers
export function isUserMessage(msg: HAIMessage): msg is UserMessage {
  return msg.type === "user_message";
}

export function isAssistantChunk(msg: HAIMessage): msg is AssistantMessageChunk {
  return msg.type === "assistant_message_chunk";
}

// ... add more type guards as needed
```

### Example Client Implementation

```typescript
// websocket-client.ts
import { HAIMessage, UserMessage } from './types';

export class HAIClient {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private messageHandlers: Map<string, (msg: any) => void> = new Map();
  
  constructor(private url: string) {
    this.sessionId = this.getOrCreateSessionId();
  }
  
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log('Connected to AGORA');
        resolve();
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message: HAIMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      };
    });
  }
  
  sendUserMessage(content: string, metadata: Record<string, any> = {}): void {
    const message: UserMessage = {
      type: "user_message",
      content,
      session_id: this.sessionId,
      metadata,
    };
    this.send(message);
  }
  
  onAssistantChunk(handler: (chunk: AssistantMessageChunk) => void): void {
    this.messageHandlers.set('assistant_message_chunk', handler);
  }
  
  onToolCall(handler: (toolCall: ToolCallMessage) => void): void {
    this.messageHandlers.set('tool_call', handler);
  }
  
  onApprovalRequest(handler: (request: ToolApprovalRequest) => void): void {
    this.messageHandlers.set('tool_approval_request', handler);
  }
  
  onStatus(handler: (status: StatusMessage) => void): void {
    this.messageHandlers.set('status', handler);
  }
  
  onError(handler: (error: ErrorMessage) => void): void {
    this.messageHandlers.set('error', handler);
  }
  
  private send(message: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected');
      return;
    }
    this.ws.send(JSON.stringify(message));
  }
  
  private handleMessage(message: HAIMessage): void {
    const handler = this.messageHandlers.get(message.type);
    if (handler) {
      handler(message);
    }
  }
  
  private getOrCreateSessionId(): string {
    let sessionId = localStorage.getItem('agora_session_id');
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      localStorage.setItem('agora_session_id', sessionId);
    }
    return sessionId;
  }
  
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
```

---

## Testing

### Manual Testing with WebSocket Tools

You can test the protocol using tools like:
- **websocat** (CLI): `websocat ws://localhost:8000/ws`
- **Postman** (GUI): Supports WebSocket testing
- **wscat** (CLI): `wscat -c ws://localhost:8000/ws`

**Example Test Session:**
```bash
$ websocat ws://localhost:8000/ws

# Send user message
{"type":"user_message","content":"Hello!","session_id":"test-123"}

# Server responds with chunks
{"type":"assistant_message_chunk","content":"Hi ","message_id":"msg_1","session_id":"test-123","is_final":false}
{"type":"assistant_message_chunk","content":"there!","message_id":"msg_1","session_id":"test-123","is_final":true}
```

### Automated Testing

See `examples/` directory for ready-to-use test scenarios:
- `basic-conversation.json` - Simple Q&A flow
- `tool-approval-flow.json` - HITL approval scenario
- `error-handling.json` - Error scenarios

### Contract Testing

Use the AsyncAPI specification with tools like:
- **AsyncAPI Studio**: https://studio.asyncapi.com
- **Microcks**: For contract testing and mocking
- **Spectral**: For linting the AsyncAPI spec

---

## Versioning & Changes

### Version 1.0.0 (Current)
- Initial protocol specification
- Core message types: user, assistant, tool, status, error
- Streaming support via chunks
- Human-in-the-loop approval workflow

### Future Considerations
- Binary message support (images, files)
- Multi-modal interactions (voice, video)
- Presence indicators (typing, recording)
- Message editing and deletion
- Reaction support

---

## Support & Contact

For questions, issues, or clarifications:
- **Email**: dev@nvwa.nl
- **Documentation**: See `asyncapi.yaml` for machine-readable spec
- **Examples**: See `examples/` directory

---

**Document Maintained By:** Gradient - NVWA  
**License:** Proprietary - NVWA

