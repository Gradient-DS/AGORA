# C4 Architecture Model Update - November 18, 2025

## Overview
Updated the C4 architecture model (`workspace-openai.dsl` and `workspace-openai.json`) to reflect the actual implementation of AGORA using OpenAI Agents SDK.

---

## Significant Changes Made

### 1. **HAI (Human Agent Interface) Components - Complete Restructure**

#### OLD Structure:
- UI Components (generic React components)
- Audio Interface (Whisper + ElevenLabs)
- WebSocket Client (single WebSocket connection)

#### NEW Structure (Actual Implementation):
- **Chat Components** - Chat interface, message list, input and tool call visualizations
- **Voice Components** - Voice UI with audio visualizer and voice controls
- **Approval Components** - Human-in-the-loop approval queue and dialogs for tool call approvals
- **State Management** - Zustand stores managing: messages, sessions, connections, voice state, approvals, agents, and users
- **WebSocket Client** - HAI Protocol WebSocket for text-based chat
- **Voice WebSocket Client** - Dedicated OpenAI Realtime API client for voice mode

**Rationale**: The actual implementation uses a clear separation between chat and voice modes, with dedicated WebSocket clients for each. State management is centralized using Zustand stores rather than distributed across components.

---

### 2. **Orchestrator Components - Major Architecture Change**

#### OLD Structure (LangGraph-based):
- Reasoning LLM (GPT-5/Sonnet-4.5)
- MCP Client (Model Context Protocol client)
- Moderator (Guardrails-AI)
- Tool Selector (Policy Engine + Context Collector)
- Memory Manager (LangChain Memory)
- State Manager (LangGraph State + Checkpointer)
- Audit Logger (OpenTelemetry)

#### NEW Structure (OpenAI Agents SDK-based):
- **Agent Runner** - OpenAI Agents SDK Runner managing agent execution with streaming support, tool callbacks, and SQLite session management
- **Agent Registry** - Multi-agent registry with 4 specialized agents:
  - General Agent (triage and coordination)
  - Regulation Agent (compliance analysis)
  - Reporting Agent (HAP report generation)
  - History Agent (company and inspection history)
  - All agents support handoff functionality between each other
- **MCP Tool Registry** - Native Agent SDK MCP server integration (no custom client needed)
- **Moderator** - Simplified input/output validation (pattern-based, not Guardrails-AI)
- **Audit Logger** - OpenTelemetry logging (unchanged concept)
- **HAI Protocol Handler** - Manages WebSocket communication for HAI protocol (user messages, assistant chunks, tool calls, status updates)
- **Voice Handler** - OpenAI Realtime API integration for voice mode
- **Session Storage** - SQLite-based conversation history via Agents SDK SQLiteSession

**Rationale**: The architecture shifted from a custom LangGraph orchestration to using OpenAI's Agents SDK, which provides built-in:
- Multi-agent support with handoffs
- Native MCP integration
- Session/memory management via SQLite
- Streaming support

This eliminates the need for custom components like Tool Selector, Memory Manager, and State Manager, as these are handled by the SDK.

---

### 3. **Removed Containers**

#### Containers Removed:
- **Tool Catalog** (PostgreSQL database with Tool Registry and Tool Config components)
- **User Profile** (PostgreSQL database with Profile Data, Preferences, and History components)

**Rationale**: The current implementation uses:
- MCP server discovery via the Agent SDK (no need for Tool Catalog database)
- Session-based storage in SQLite (no separate User Profile database yet)

These may be added in future iterations, but they're not part of the current implementation.

---

### 4. **Technology Stack Updates**

#### HAI Container:
- OLD: "React + Audio (Whisper, ElevenLabs)"
- NEW: "React + Vite + Zustand"

#### Orchestrator Container:
- OLD: "LangGraph + LLM (GPT-5/Sonnet-4.5)"
- NEW: "OpenAI Agents SDK + FastAPI"

---

### 5. **Relationship Changes**

#### Added:
- `hai.voiceClient -> orchestrator.voiceHandler` - Voice mode audio streaming
- `orchestrator.agentRunner -> orchestrator.sessionStorage` - State persistence
- `orchestrator.agentRegistry -> orchestrator.mcpToolRegistry` - MCP tool configuration per agent
- `orchestrator.haiProtocolHandler -> orchestrator.agentRunner` - Request routing

#### Removed:
- All relationships to `toolCatalog` and `userProfile` containers
- `toolSelector` relationships (component no longer exists)
- `reasoningLLM` direct relationships (replaced by agent-based architecture)

---

### 6. **Component View Updates**

#### Orchestrator Component View:
- Removed: Tool Catalog and User Profile from the view
- Updated description to reflect Agent SDK components

#### HAI Component View:
- Updated to show 6 components instead of 3
- More detailed breakdown of frontend architecture

#### Removed Views:
- ToolCatalogComponents (container removed)
- UserProfileComponents (container removed)

---

## Key Architectural Insights

### Multi-Agent Architecture
The system now uses a **specialized agent pattern** with handoffs:
1. **General Agent** acts as triage/coordinator
2. Specialized agents handle specific domains (regulation, reporting, history)
3. Agents can hand off to each other while maintaining conversation context
4. Each agent has selective access to MCP tools (principle of least privilege)

### Dual-Mode Operation
The system supports two distinct interaction modes:
1. **Chat Mode**: Traditional text-based chat via WebSocket using HAI Protocol
2. **Voice Mode**: Real-time audio streaming via OpenAI Realtime API

### Session Management
- Conversation history stored in SQLite via OpenAI Agents SDK
- Sessions persist across connections
- MCP servers can query conversation history via `/sessions/{session_id}/history` endpoint

---

## Migration Notes

If implementing the architecture shown in the OLD structure:
1. Tool Catalog database would need to be created
2. User Profile database would need to be created
3. Custom routing logic would need to be implemented (currently handled by Agent SDK handoffs)
4. Memory management would need custom implementation (currently handled by SQLiteSession)

The current implementation prioritizes rapid development by leveraging OpenAI's Agents SDK capabilities rather than building custom orchestration infrastructure.

---

## Files Updated
- `/Users/lexlubbers/Code/AGORA/c4/workspace-openai.dsl`
- `/Users/lexlubbers/Code/AGORA/c4/workspace-openai.json`

## Verification
To view the updated architecture diagrams:
```bash
cd /Users/lexlubbers/Code/AGORA/c4
npm run up:openai
```

Then navigate to http://localhost:8080 to see the Structurizr diagrams.

