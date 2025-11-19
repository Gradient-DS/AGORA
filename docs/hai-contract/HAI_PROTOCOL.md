# AGORA HAI Protocol Specification

**Version:** 1.1.0  
**Last Updated:** November 19, 2025

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

### Scope: Text & Control Only
This version of the protocol (v1.x) specifically covers **text-based communication and control signals** (like tool approvals). It does **not** cover real-time audio/video streaming. Voice interactions are handled via separate dedicated endpoints (e.g., `/ws/voice`) or protocols to ensure clear separation of concerns.

### Key Features

- **Real-time bidirectional communication** via WebSocket
- **Streaming responses** for immediate user feedback
- **Tool execution transparency** with distinct lifecycle events
- **Human-in-the-loop approvals** for sensitive operations
- **Session-based continuity** for conversation history

### Architecture Context

```
┌─────────────┐         WebSocket          ┌──────────────────┐
│             │◄──────────────────────────►│                  │
│  HAI Client │    HAI Protocol (JSON)     │  Orchestrator    │
│  (Frontend) │  (Text/Control Only)     │  (Backend)       │
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
| **Server → Client** | `assistant_message`, `assistant_message_chunk`, `tool_call_start`, `tool_call_end`, `tool_call_error`, `tool_approval_request`, `status`, `error` |

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

### 4. Tool Call Messages (Server → Client)

Notification about tool execution lifecycle, split into distinct events for clearer state management.

#### 4a. Tool Call Start

Indicates a tool execution has begun.

```typescript
interface ToolCallStart {
  type: "tool_call_start";
  tool_call_id: string;         // Unique identifier
  tool_name: string;            // e.g., "search_regulations"
  parameters: Record<string, any>; // Tool input params
  session_id: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}
```

**Example:**
```json
{
  "type": "tool_call_start",
  "tool_call_id": "call_abc123",
  "tool_name": "search_regulations",
  "parameters": {"query": "food safety"},
  "session_id": "123e4567...",
  "agent_id": "regulation_agent"
}
```
*UI Action: Show "Searching regulations..." indicator*

#### 4b. Tool Call End

Indicates successful completion of a tool execution.

```typescript
interface ToolCallEnd {
  type: "tool_call_end";
  tool_call_id: string;         // Matches the start ID
  tool_name: string;
  result: string;               // Tool output summary
  session_id: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}
```

**Example:**
```json
{
  "type": "tool_call_end",
  "tool_call_id": "call_abc123",
  "tool_name": "search_regulations",
  "result": "Found 5 relevant regulations",
  "session_id": "123e4567...",
  "metadata": {
    "documents_found": 5
  }
}
```
*UI Action: Update indicator to success badge, optionally show result summary*

#### 4c. Tool Call Error

Indicates tool execution failed.

```typescript
interface ToolCallError {
  type: "tool_call_error";
  tool_call_id: string;         // Matches the start ID
  tool_name: string;
  error: string;                // Error message
  session_id: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}
```

**Example:**
```json
{
  "type": "tool_call_error",
  "tool_call_id": "call_abc123",
  "tool_name": "search_regulations",
  "error": "Database connection timeout",
  "session_id": "123e4567..."
}
```
*UI Action: Update indicator to error state, show retry option if applicable*

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
- Color-code by `risk_level`
- Provide "Approve" and "Reject" buttons

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

### Flow 1: Tool Execution

```
Client                                    Server
  |                                         |
  |-- UserMessage -----------------------> |
  |   "Search for restaurant regulations"  |
  |                                         |
  | <------------ StatusMessage: routing   |
  | <----- StatusMessage: executing_tools  |
  |                                         |
  | <--------- ToolCallStart ------------- |
  |            (tool: search_regulations)  |
  |                                         |
  | <--------- ToolCallEnd --------------- |
  |           (result: "Found 5 docs")     |
  |                                         |
  | <------------ AssistantMessageChunk... |
  | <------------ StatusMessage: completed |
```

### Flow 2: Human-in-the-Loop Approval

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
  | <--------- ToolCallStart ------------- |
  | <--------- ToolCallEnd --------------- |
  |                                         |
  | <------------ AssistantMessageChunk... |
  | <------------ StatusMessage: completed |
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

- [ ] **Message Handling**
  - [ ] Parse incoming JSON messages
  - [ ] Route by `type` discriminator
  - [ ] Validate required fields

- [ ] **Tool Execution UI**
  - [ ] Listen for `tool_call_start` to show progress
  - [ ] Listen for `tool_call_end` to show success
  - [ ] Listen for `tool_call_error` to handle failures

- [ ] **Approval Flow**
  - [ ] Render approval modal on `tool_approval_request`
  - [ ] Send `tool_approval_response`

### TypeScript Types

```typescript
// types.ts
export type HAIMessage =
  | UserMessage
  | AssistantMessage
  | AssistantMessageChunk
  | ToolCallStart
  | ToolCallEnd
  | ToolCallError
  | ToolApprovalRequest
  | ToolApprovalResponse
  | StatusMessage
  | ErrorMessage;

// ... [other types unchanged]

export interface ToolCallStart {
  type: "tool_call_start";
  tool_call_id: string;
  tool_name: string;
  parameters: Record<string, any>;
  session_id: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}

export interface ToolCallEnd {
  type: "tool_call_end";
  tool_call_id: string;
  tool_name: string;
  result: string;
  session_id: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}

export interface ToolCallError {
  type: "tool_call_error";
  tool_call_id: string;
  tool_name: string;
  error: string;
  session_id: string;
  agent_id?: string;
  metadata?: Record<string, any>;
}
```

---

## Testing

### Manual Testing with WebSocket Tools

You can test the protocol using tools like:
- **websocat** (CLI): `websocat ws://localhost:8000/ws`
- **Postman** (GUI): Supports WebSocket testing

**Example Test Session:**
```bash
$ websocat ws://localhost:8000/ws

# Send user message
{"type":"user_message","content":"Hello!","session_id":"test-123"}

# Server responds with chunks
{"type":"assistant_message_chunk","content":"Hi ","message_id":"msg_1","session_id":"test-123","is_final":false}
{"type":"assistant_message_chunk","content":"there!","message_id":"msg_1","session_id":"test-123","is_final":true}
```

---

**Document Maintained By:** Gradient - NVWA  
**License:** Proprietary - NVWA
