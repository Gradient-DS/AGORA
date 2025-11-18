# AGORA HAI Protocol - Contract Documentation

This directory contains the complete API contract documentation for the HAI (Human Agent Interface) Protocol used by AGORA.

## 📋 Contents

### Core Documentation

- **[HAI_PROTOCOL.md](./HAI_PROTOCOL.md)** - Comprehensive human-readable protocol specification
  - Message types and formats
  - Conversation flows
  - Error handling patterns
  - Implementation guide with code examples
  - TypeScript type definitions

- **[asyncapi.yaml](./asyncapi.yaml)** - Machine-readable AsyncAPI 3.0 specification
  - Formal contract for WebSocket API
  - Can be used with AsyncAPI tools for:
    - Documentation generation
    - Contract testing
    - Client SDK generation
    - Mock server creation

### Schemas

- **[schemas/messages.json](./schemas/messages.json)** - JSON Schema definitions
  - All message type schemas
  - Can be used for validation
  - Compatible with code generation tools

### Examples

- **[examples/basic-conversation.json](./examples/basic-conversation.json)**
  - Simple Q&A flow
  - Streaming response handling
  - Follow-up questions

- **[examples/tool-approval-flow.json](./examples/tool-approval-flow.json)**
  - Human-in-the-loop approval workflow
  - High-risk tool execution
  - Approval and rejection paths

- **[examples/error-handling.json](./examples/error-handling.json)**
  - All error scenarios
  - Recovery strategies
  - Reconnection patterns

## 🚀 Quick Start

### For Frontend Developers

1. Read [HAI_PROTOCOL.md](./HAI_PROTOCOL.md) for complete protocol documentation
2. Copy TypeScript types from the Implementation Guide section
3. Reference [examples/](./examples/) for message flow patterns
4. Use [schemas/messages.json](./schemas/messages.json) for validation

### For API Contract Testing

1. Load [asyncapi.yaml](./asyncapi.yaml) into [AsyncAPI Studio](https://studio.asyncapi.com)
2. Generate documentation or client SDKs
3. Use with Microcks for contract testing
4. Integrate with CI/CD for contract validation

## 🔌 Connection Details

### Endpoints

```
Development: ws://localhost:8000/ws
```

### Authentication

Currently no authentication required. Future versions may include token-based auth.

### Session Management

- Client generates UUID as `session_id`
- Persist in localStorage for conversation continuity
- Include in all messages

## 📝 Message Types Overview

| Type | Direction | Purpose |
|------|-----------|---------|
| `user_message` | Client → Server | User input |
| `assistant_message` | Server → Client | Complete response (non-streaming) |
| `assistant_message_chunk` | Server → Client | Streaming response chunk ⭐ |
| `tool_call` | Server → Client | Tool execution notification |
| `tool_approval_request` | Server → Client | Request permission for tool |
| `tool_approval_response` | Client → Server | User's approval decision |
| `status` | Server → Client | Processing status |
| `error` | Server → Client | Error notification |

## 🛠 Tools & Resources

### AsyncAPI Ecosystem

- **[AsyncAPI Studio](https://studio.asyncapi.com)** - Online editor and visualizer
- **[AsyncAPI Generator](https://www.asyncapi.com/tools/generator)** - Generate docs, code, tests
- **[Microcks](https://microcks.io/)** - Mock server and contract testing
- **[Spectral](https://stoplight.io/open-source/spectral)** - Linting and validation

### Testing Tools

- **[websocat](https://github.com/vi/websocat)** - CLI WebSocket client
  ```bash
  websocat ws://localhost:8000/ws
  ```
- **[wscat](https://github.com/websockets/wscat)** - Alternative CLI client
  ```bash
  wscat -c ws://localhost:8000/ws
  ```
- **Postman** - GUI with WebSocket support

### Code Generation

Generate TypeScript types from JSON Schema:
```bash
npm install -g json-schema-to-typescript
json2ts schemas/messages.json > types.ts
```

## 📖 Documentation Versions

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-17 | Initial protocol specification |

## 🤝 Integration Checklist

Use this checklist when integrating the HAI protocol:

### Required Implementation

- [ ] WebSocket connection to `/ws`
- [ ] Session ID generation and persistence
- [ ] User message sending
- [ ] Streaming chunk handling (concat by `message_id`)
- [ ] Status indicator mapping
- [ ] Error message display
- [ ] Connection loss recovery

### Recommended Implementation

- [ ] Tool execution notifications
- [ ] Human-in-the-loop approval UI
- [ ] Reconnection with exponential backoff
- [ ] Message validation using JSON Schema
- [ ] Proper error code handling
- [ ] Loading state management

### Optional Enhancements

- [ ] Message history persistence
- [ ] Typing indicators
- [ ] Read receipts
- [ ] Message reactions
- [ ] Rich media support

## 📞 Support

For questions or issues with the protocol:

- **Technical Questions**: dev@nvwa.nl
- **Bug Reports**: Submit via project issue tracker
- **Protocol Changes**: Propose via RFC process

## 📄 License

Proprietary - NVWA

---

**Maintained by:** Gradient - NVWA  
**Last Updated:** November 17, 2025

