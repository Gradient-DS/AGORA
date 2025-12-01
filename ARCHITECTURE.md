# AGORA Architecture Documentation

**Version:** 1.0.0  
**Last Updated:** December 2025  
**Status:** MVP Implementation (Both Backends)

## Table of Contents

1. [Overview](#overview)
2. [System Context](#system-context)
3. [Closed-Source Architecture (OpenAI Agents SDK)](#closed-source-architecture-openai-agents-sdk)
4. [Open-Source Architecture (LangGraph)](#open-source-architecture-langgraph)
5. [Architecture Comparison](#architecture-comparison)
6. [Shared Components](#shared-components)
7. [Current Implementation Status](#current-implementation-status)
8. [Production Gap Analysis](#production-gap-analysis)
9. [Structurizr C4 Diagrams](#structurizr-c4-diagrams)

---

## Overview

AGORA is a multi-agent compliance platform for NVWA (Netherlands Food and Consumer Product Safety Authority) inspectors. It provides two orchestration backends that implement the same HAI (Human Agent Interface) Protocol:

| Backend | Framework | License | LLM Provider |
|---------|-----------|---------|--------------|
| `server-openai` | OpenAI Agents SDK | Proprietary | OpenAI only |
| `server-langgraph` | LangGraph | Open Source (MIT) | Any OpenAI-compatible |

Both backends share:
- The same frontend (HAI React application)
- The same MCP tool servers
- The same HAI WebSocket Protocol
- The same agent definitions and handoff patterns

---

## System Context

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                         AGORA System                         │
                    │                                                              │
  ┌──────────┐      │   ┌─────────────┐      ┌──────────────────────────────┐    │
  │          │      │   │             │      │                              │    │
  │ Inspector│──────┼──►│  HAI (React)│─────►│  Orchestrator                │    │
  │          │ HTTP │   │  Frontend   │  WS  │  (OpenAI SDK or LangGraph)   │    │
  │          │      │   │             │      │                              │    │
  └──────────┘      │   └─────────────┘      └──────────────┬───────────────┘    │
                    │                                       │                     │
                    │                                       │ MCP Protocol (HTTP) │
                    │                                       ▼                     │
                    │   ┌────────────────────────────────────────────────────┐   │
                    │   │              MCP Tool Servers (FastMCP)             │   │
                    │   │  ┌────────────┐ ┌────────────┐ ┌────────────────┐  │   │
                    │   │  │ Regulation │ │ Inspection │ │   Reporting    │  │   │
                    │   │  │  Analysis  │ │  History   │ │   (HAP PDF)    │  │   │
                    │   │  │  :5002     │ │  :5005     │ │    :5003       │  │   │
                    │   │  └────────────┘ └────────────┘ └────────────────┘  │   │
                    │   └────────────────────────────────────────────────────┘   │
                    │                                                              │
                    └─────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    External Systems                          │
                    │   ┌──────────┐  ┌─────────────┐  ┌──────────────────────┐   │
                    │   │ KVK API  │  │ Weaviate DB │  │ OpenAI / Azure API   │   │
                    │   └──────────┘  └─────────────┘  └──────────────────────┘   │
                    └─────────────────────────────────────────────────────────────┘
```

---

## Closed-Source Architecture (OpenAI Agents SDK)

### Overview

The OpenAI backend leverages the `openai-agents` SDK which provides native multi-agent handoffs, automatic tool execution, and built-in session persistence.

### Container Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          server-openai (FastAPI)                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                           API Layer                                     │ │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────────┐  │ │
│  │  │  FastAPI Server   │  │ HAI Protocol      │  │ REST Endpoints      │  │ │
│  │  │  (WebSocket /ws)  │  │ Handler           │  │ (/agents, /history) │  │ │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │                                      │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        Pipelines Layer                                  │ │
│  │  ┌───────────────────────────────────────┐  ┌─────────────────────────┐ │ │
│  │  │            Orchestrator               │  │       Moderator         │ │ │
│  │  │  - Message processing                 │  │  - Input validation     │ │ │
│  │  │  - Stream/tool callbacks              │  │  - Output filtering     │ │ │
│  │  │  - Approval flow management           │  │  - Blocked patterns     │ │ │
│  │  └───────────────────────────────────────┘  └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │                                      │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                          Core Layer                                     │ │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────────┐  │ │
│  │  │  Agent Registry   │  │   Agent Runner    │  │  Approval Logic     │  │ │
│  │  │                   │  │                   │  │                     │  │ │
│  │  │  - General Agent  │  │  - SQLiteSession  │  │  - High-risk tools  │  │ │
│  │  │  - Regulation     │  │  - Streaming      │  │  - Critical ops     │  │ │
│  │  │  - Reporting      │  │  - Tool callbacks │  │  - Parameter checks │  │ │
│  │  │  - History Agent  │  │  - Handoff detect │  │                     │  │ │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │                                      │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        Adapters Layer                                   │ │
│  │  ┌───────────────────────────────────────┐  ┌─────────────────────────┐ │ │
│  │  │        MCP Tool Registry              │  │      Audit Logger       │ │ │
│  │  │  - MCPServerStreamableHttp            │  │  - OpenTelemetry        │ │ │
│  │  │  - Per-agent tool scoping             │  │  - Message logging      │ │ │
│  │  │  - Native SDK integration             │  │  - Decision tracking    │ │ │
│  │  └───────────────────────────────────────┘  └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  Session Storage: SQLite (sessions.db) - Agents SDK SQLiteSession       │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component Details

#### Agent Registry & Runner
- **AgentRegistry**: Creates and configures `Agent` instances from `AgentConfig` definitions
- **AgentRunner**: Wraps SDK's `Runner.run_streamed()` for streaming responses
- **Handoff Mechanism**: Built-in SDK handoffs via `agent.handoffs = [other_agents]`

#### MCP Integration
- Uses `agents.mcp.MCPServerStreamableHttp` for native MCP server connections
- Each agent receives only relevant MCP servers based on `AGENT_MCP_MAPPING`
- Tool discovery happens automatically via SDK

#### Session Management
- Uses `agents.SQLiteSession` for conversation persistence
- Sessions are keyed by `session_id` (client-generated UUID)
- Full conversation history including tool calls is stored

### Agent Handoff Flow

```
User Message
     │
     ▼
┌─────────────────┐
│  General Agent  │ ◄── Entry point (triage & routing)
│  (No MCP tools) │
└────────┬────────┘
         │ Detects: "KVK number", "regulation", "report"
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    SDK Handoff Mechanism                          │
│                                                                   │
│  Agent calls handoff function → SDK executes → Context transfers  │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
         │
         ├──────────────────────┬──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  History Agent  │    │ Regulation Agent│    │ Reporting Agent │
│  MCP: history   │    │ MCP: regulation │    │ MCP: reporting  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `core/agent_definitions.py` | Agent configurations with instructions |
| `core/agent_runner.py` | AgentRegistry, AgentRunner, streaming |
| `core/approval_logic.py` | Human-in-loop rules |
| `adapters/mcp_tools.py` | MCPToolRegistry with SDK integration |
| `pipelines/orchestrator.py` | Main message processing |
| `api/server.py` | FastAPI server, WebSocket endpoint |

---

## Open-Source Architecture (LangGraph)

### Overview

The LangGraph backend provides an open-source alternative using LangChain's StateGraph for agent orchestration. It supports any OpenAI-compatible LLM provider.

### Container Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          server-langgraph (FastAPI)                          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                           API Layer                                     │ │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────────┐  │ │
│  │  │  FastAPI Server   │  │ HAI Protocol      │  │ REST Endpoints      │  │ │
│  │  │  (WebSocket /ws)  │  │ Handler           │  │ (/agents, /history) │  │ │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │                                      │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        Pipelines Layer                                  │ │
│  │  ┌───────────────────────────────────────┐  ┌─────────────────────────┐ │ │
│  │  │            Orchestrator               │  │       Moderator         │ │ │
│  │  │  - astream_events() processing        │  │  - Input validation     │ │ │
│  │  │  - Event → HAI Protocol mapping       │  │  - Output filtering     │ │ │
│  │  │  - Approval flow management           │  │  - Blocked patterns     │ │ │
│  │  └───────────────────────────────────────┘  └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │                                      │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                          Core Layer                                     │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐ │ │
│  │  │  StateGraph    │  │  Agent Nodes   │  │      Handoff Tools         │ │ │
│  │  │                │  │                │  │                            │ │ │
│  │  │  - AgentState  │  │  - general_    │  │  - transfer_to_history     │ │ │
│  │  │  - ToolNode    │  │    agent()     │  │  - transfer_to_regulation  │ │ │
│  │  │  - Conditional │  │  - regulation_ │  │  - transfer_to_reporting   │ │ │
│  │  │    edges       │  │    agent()     │  │  - transfer_to_general     │ │ │
│  │  │                │  │  - etc.        │  │                            │ │ │
│  │  └────────────────┘  └────────────────┘  └────────────────────────────┘ │ │
│  │                                                                         │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                         Routing Logic                              │ │ │
│  │  │  route_from_agent() ─────► "tools" | "end"                         │ │ │
│  │  │  route_after_tools() ───► detects handoff → target agent           │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                       │                                      │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                        Adapters Layer                                   │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────────┐  │ │
│  │  │ MCP Client Mgr   │  │   Checkpointer   │  │    Audit Logger       │  │ │
│  │  │                  │  │                  │  │                       │  │ │
│  │  │ MultiServerMCP   │  │ AsyncSqliteSaver │  │ OpenTelemetry         │  │ │
│  │  │ Client (langchain│  │ (aiosqlite)      │  │ Message logging       │  │ │
│  │  │ -mcp-adapters)   │  │                  │  │                       │  │ │
│  │  └──────────────────┘  └──────────────────┘  └───────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  Session Storage: SQLite (sessions.db) - LangGraph AsyncSqliteSaver     │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Component Details

#### StateGraph & Nodes
- **AgentState**: TypedDict with `messages`, `session_id`, `current_agent`, `pending_approval`
- **Agent Nodes**: Async functions that invoke ChatOpenAI with bound tools
- **ToolNode**: LangGraph's prebuilt node for tool execution

#### Handoff Pattern (Critical)

Unlike the OpenAI SDK, LangGraph requires explicit handling of handoffs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LangGraph Handoff Pattern                               │
│                                                                             │
│  WRONG (causes 400 errors):                                                 │
│    Agent calls transfer_to_history → Route directly to history-agent        │
│    (Missing ToolMessage breaks OpenAI API contract)                         │
│                                                                             │
│  CORRECT:                                                                   │
│    Agent calls transfer_to_history → ToolNode → ToolMessage added           │
│    → route_after_tools() → history-agent                                    │
│                                                                             │
│  Graph Flow:                                                                │
│    ┌────────────┐     ┌──────────┐     ┌────────────────┐                   │
│    │ Any Agent  │ ──► │ ToolNode │ ──► │ route_after_   │ ──► Target Agent  │
│    │            │     │          │     │ tools()        │                   │
│    └────────────┘     └──────────┘     └────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### MCP Integration
- Uses `langchain-mcp-adapters` package with `MultiServerMCPClient`
- Tools organized by server name (`get_tools_by_server()`)
- Per-agent tool scoping via `AGENT_MCP_MAPPING`

#### Checkpointer
- Uses `langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver`
- Requires `aiosqlite` for async SQLite operations
- Persists conversation state with checkpointing

### Graph Structure

```
                    ┌─────────────────┐
                    │      START      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  general-agent  │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ regulation-agent│ │ reporting-agent │ │  history-agent  │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    ToolNode     │  ◄── All tool calls go here first
                    └────────┬────────┘
                             │
                    route_after_tools()
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
    Back to Agent    Or target agent     Or END
    (non-handoff)    (after handoff)
```

### Key Files

| File | Purpose |
|------|---------|
| `core/state.py` | AgentState TypedDict definition |
| `core/graph.py` | StateGraph construction, routing logic |
| `core/agents.py` | Agent node functions, LLM invocation |
| `core/tools.py` | Handoff tools, agent-tool mapping |
| `adapters/mcp_client.py` | MCPClientManager with langchain-mcp-adapters |
| `adapters/checkpointer.py` | AsyncSqliteSaver setup |
| `pipelines/orchestrator.py` | astream_events → HAI Protocol |
| `api/server.py` | FastAPI server, WebSocket endpoint |

---

## Architecture Comparison

### Side-by-Side Comparison

| Aspect | server-openai | server-langgraph |
|--------|---------------|------------------|
| **Framework** | OpenAI Agents SDK | LangGraph (LangChain) |
| **License** | Proprietary (OpenAI) | MIT (Open Source) |
| **LLM Provider** | OpenAI only | Any OpenAI-compatible |
| **Handoff Mechanism** | SDK built-in | ToolNode + conditional edges |
| **MCP Integration** | `MCPServerStreamableHttp` | `MultiServerMCPClient` |
| **Session Storage** | `SQLiteSession` | `AsyncSqliteSaver` |
| **Streaming** | `Runner.run_streamed()` | `astream_events()` |
| **State Management** | SDK internal | Explicit `AgentState` TypedDict |
| **Graph Definition** | Implicit (handoffs) | Explicit `StateGraph` |
| **Debugging** | SDK events | LangGraph events |

### Pros & Cons

#### OpenAI Agents SDK (server-openai)

**Pros:**
- ✅ Simpler implementation (SDK handles handoffs)
- ✅ Native OpenAI integration
- ✅ Built-in session management
- ✅ Automatic tool execution
- ✅ Less code to maintain

**Cons:**
- ❌ Vendor lock-in (OpenAI only)
- ❌ Proprietary license
- ❌ Limited customization
- ❌ Opaque internals

#### LangGraph (server-langgraph)

**Pros:**
- ✅ Open source (MIT license)
- ✅ Provider-agnostic (Azure, Anthropic, local)
- ✅ Explicit control flow
- ✅ Highly customizable
- ✅ Better for complex workflows
- ✅ LangSmith integration available

**Cons:**
- ❌ More code to write
- ❌ Handoff pattern requires careful implementation
- ❌ More potential for errors

---

## Shared Components

### Human Agent Interface (HAI) Frontend

The HAI React application is used by both backends:

```
HAI/
├── src/
│   ├── components/
│   │   ├── chat/           # ChatInterface, MessageList, MessageInput
│   │   ├── approval/       # ApprovalDialog for human-in-loop
│   │   ├── debug/          # DebugPanel for tool calls
│   │   ├── layout/         # MainLayout, Header
│   │   └── ui/             # shadcn/ui components
│   ├── stores/             # Zustand state management
│   │   ├── useMessageStore.ts
│   │   ├── useSessionStore.ts
│   │   ├── useConnectionStore.ts
│   │   ├── useApprovalStore.ts
│   │   └── useAgentStore.ts
│   ├── hooks/
│   │   ├── useWebSocket.ts    # HAI Protocol WebSocket client
│   │   └── useVoiceMode.ts    # Voice (currently disabled)
│   └── lib/websocket/         # WebSocket client implementation
```

### MCP Tool Servers

All three MCP servers are shared between both backends:

| Server | Port | Tools |
|--------|------|-------|
| **regulation-analysis** | 5002 | `search_regulations`, `get_regulation_context`, `lookup_regulation_articles` |
| **reporting** | 5003 | `start_inspection_report`, `extract_inspection_data`, `verify_inspection_data`, `submit_verification_answers`, `generate_final_report` |
| **inspection-history** | 5005 | `check_company_exists`, `get_inspection_history`, `get_company_violations`, `check_repeat_violation`, `get_follow_up_status` |

### HAI Protocol

Both backends implement the same WebSocket protocol:

| Message Type | Direction | Purpose |
|--------------|-----------|---------|
| `user_message` | Client → Server | User input |
| `assistant_message_chunk` | Server → Client | Streaming response |
| `tool_call` | Server → Client | Tool execution notification |
| `tool_approval_request` | Server → Client | Human approval needed |
| `tool_approval_response` | Client → Server | User's decision |
| `status` | Server → Client | Processing status |
| `error` | Server → Client | Error notification |

---

## Current Implementation Status

### ✅ Implemented Features

| Feature | OpenAI | LangGraph | Notes |
|---------|--------|-----------|-------|
| Multi-agent handoffs | ✅ | ✅ | Different implementation patterns |
| MCP tool integration | ✅ | ✅ | Per-agent tool scoping |
| WebSocket streaming | ✅ | ✅ | Real-time token streaming |
| Human-in-loop approval | ✅ | ✅ | For high-risk tools |
| Session persistence | ✅ | ✅ | SQLite-based |
| Content moderation | ✅ | ✅ | Input/output validation |
| HAI Protocol | ✅ | ✅ | Full specification |
| Chat interface | ✅ | ✅ | React frontend |
| Tool call visualization | ✅ | ✅ | Debug panel |
| Agent definitions | ✅ | ✅ | 4 agents (general, regulation, reporting, history) |
| Health endpoints | ✅ | ✅ | `/health` on all services |

### ⚠️ Partial Implementation

| Feature | Status | Notes |
|---------|--------|-------|
| Voice interface | 🔴 Disabled | Code exists but disabled |
| Audit logging | 🟡 Basic | OpenTelemetry stub, no destination |
| Error recovery | 🟡 Basic | Reconnect logic, no retry |

### ❌ Not Implemented

| Feature | Priority | Notes |
|---------|----------|-------|
| User profiles | High | No user management |
| Memory (long-term) | High | Session only |
| Evals & traces | High | No Langfuse/LangSmith |
| Monitoring dashboard | Medium | No Grafana |
| Rate limiting | Medium | No API throttling |
| Authentication | High | No auth layer |
| Multi-tenancy | High | Single-tenant only |

---

## Production Gap Analysis

### 1. User Profiles & Authentication

**Current State:** No authentication or user management. Session ID is client-generated.

**Required for Production:**
- [ ] User authentication (OAuth2, OIDC)
- [ ] User profile database (PostgreSQL)
- [ ] Role-based access control (RBAC)
- [ ] Inspector vs Admin roles
- [ ] User preferences storage
- [ ] Audit trail per user

**Suggested Implementation:**
```
┌─────────────────────────────────────────────────────────────┐
│                    User Profile Service                      │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │  Auth0/Keycloak│  │  Profile DB   │  │  Preferences    │  │
│  │  Integration  │  │  (PostgreSQL) │  │  Engine         │  │
│  └───────────────┘  └───────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

### 2. Memory & Knowledge Management

**Current State:** Session-based memory only. Conversation cleared when session ends.

**Required for Production:**
- [ ] Long-term memory per user (facts, preferences)
- [ ] Cross-session context retrieval
- [ ] Knowledge graph integration
- [ ] Semantic memory search
- [ ] Memory summarization
- [ ] Tool usage patterns

**Suggested Implementation:**
```
┌─────────────────────────────────────────────────────────────┐
│                    Memory Architecture                       │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ Session Memory  │  │  Long-term      │  │ Knowledge   │  │
│  │ (Current impl)  │  │  Memory Store   │  │ Graph       │  │
│  │ - SQLite        │  │  - Vector DB    │  │ - Neo4j     │  │
│  │ - Checkpointer  │  │  - User facts   │  │ - Relations │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│           │                   │                    │        │
│           └───────────────────┴────────────────────┘        │
│                              ▼                              │
│                    ┌─────────────────┐                      │
│                    │ Memory Manager  │                      │
│                    │ - Retrieval     │                      │
│                    │ - Summarization │                      │
│                    │ - Injection     │                      │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

**Options:**
- **LangChain Memory**: `ConversationBufferMemory`, `ConversationSummaryMemory`
- **Mem0**: Open-source memory layer for AI
- **Zep**: LLM memory server
- **Custom**: Weaviate + summarization

---

### 3. Evaluation & Traces (Langfuse/LangSmith)

**Current State:** Basic console logging. No structured traces or evaluations.

**Required for Production:**
- [ ] Request/response tracing
- [ ] Token usage tracking
- [ ] Latency monitoring
- [ ] Quality evaluations
- [ ] A/B testing capability
- [ ] Cost tracking per user/session

**Suggested Implementation:**

```
┌─────────────────────────────────────────────────────────────┐
│                   Observability Stack                       │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                    Langfuse                           │  │
│  │  - Traces (per request)                               │  │
│  │  - Generations (LLM calls)                            │  │
│  │  - Scores (quality evals)                             │  │
│  │  - Cost tracking                                      │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                              │
│         ┌────────────────────┼────────────────────┐         │
│         ▼                    ▼                    ▼         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
│  │ OpenAI SDK  │     │ LangGraph   │     │ MCP Servers │    │ 
│  │ Instrumented│     │ Callbacks   │     │ Metrics     │    │
│  └─────────────┘     └─────────────┘     └─────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Integration Points:**
- **server-openai**: Langfuse OpenAI wrapper
- **server-langgraph**: Langfuse LangChain integration
- **MCP Servers**: Custom spans for tool execution

**Langfuse Setup Example:**
```python
from langfuse import Langfuse
from langfuse.openai import openai  # Drop-in replacement

langfuse = Langfuse()

# Automatic tracing for OpenAI calls
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    langfuse_trace_id="trace_123",
)
```

---

### 4. Monitoring & Alerting

**Current State:** Health endpoints only. No dashboards or alerts.

**Required for Production:**
- [ ] Real-time dashboards (Grafana)
- [ ] Metrics collection (Prometheus)
- [ ] Distributed tracing (Jaeger)
- [ ] Log aggregation (Loki)
- [ ] Alerting (PagerDuty, Slack)
- [ ] SLA monitoring

**Suggested Stack:**
```
┌─────────────────────────────────────────────────────────────┐
│                  Monitoring Architecture                    │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │  Prometheus   │  │    Loki       │  │    Jaeger       │  │
│  │  (Metrics)    │  │  (Logs)       │  │  (Traces)       │  │
│  └───────┬───────┘  └───────┬───────┘  └────────┬────────┘  │
│          │                  │                   │           │
│          └──────────────────┼───────────────────┘           │
│                             ▼                               │
│                    ┌─────────────────┐                      │
│                    │     Grafana     │                      │
│                    │  (Dashboards)   │                      │
│                    └─────────────────┘                      │
│                             │                               │
│                             ▼                               │
│                    ┌─────────────────┐                      │
│                    │   Alertmanager  │ ──► Slack/PagerDuty  │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

**Key Metrics to Track:**
| Metric | Type | Purpose |
|--------|------|---------|
| `agora_requests_total` | Counter | Total requests |
| `agora_response_latency_seconds` | Histogram | Response time |
| `agora_tool_calls_total` | Counter | Tool executions |
| `agora_handoffs_total` | Counter | Agent transfers |
| `agora_approvals_pending` | Gauge | Pending approvals |
| `agora_tokens_used` | Counter | Token consumption |
| `agora_errors_total` | Counter | Error count |

---

### 5. Structured Logging

**Current State:** Python logging to stdout. No structured format.

**Required for Production:**
- [ ] Structured JSON logging
- [ ] Correlation IDs across services
- [ ] Log levels per environment
- [ ] Sensitive data masking
- [ ] Log rotation and retention

**Suggested Implementation:**
```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),
    ],
)

log = structlog.get_logger()

# Usage
log.info(
    "message_processed",
    session_id=session_id,
    agent_id=agent_id,
    tool_name=tool_name,
    latency_ms=elapsed_ms,
)
```

---

### 6. Additional Production Requirements

#### Security
- [ ] API rate limiting (per user, per IP)
- [ ] Input sanitization (beyond current moderation)
- [ ] Secrets management (Vault/AWS Secrets Manager)
- [ ] TLS/HTTPS enforcement
- [ ] CORS configuration (currently `*`)
- [ ] SQL injection prevention (parameterized queries)

#### Reliability
- [ ] Circuit breakers for MCP servers
- [ ] Retry logic with exponential backoff
- [ ] Graceful degradation
- [ ] Health check improvements
- [ ] Connection pooling

#### Scalability
- [ ] Horizontal scaling for orchestrators
- [ ] Redis for shared state (if multi-instance)
- [ ] Load balancing
- [ ] Connection management
- [ ] Async job queues (Celery/RQ)

#### Compliance
- [ ] GDPR data handling
- [ ] Data retention policies
- [ ] Right to erasure implementation
- [ ] Audit log immutability
- [ ] EU AI Act compliance (already partial)

#### Operations
- [ ] CI/CD pipeline
- [ ] Database migrations
- [ ] Feature flags
- [ ] A/B testing infrastructure
- [ ] Rollback procedures
- [ ] Disaster recovery plan

---

## Structurizr C4 Diagrams

The project includes Structurizr DSL files for architecture visualization:

| File | Description |
|------|-------------|
| `c4/workspace-openai.dsl` | OpenAI Agents SDK architecture |
| `c4/workspace-opensource.dsl` | LangGraph architecture (includes future state) |

### Running Structurizr Locally

```bash
cd c4
npm install
npm run up
# Open http://localhost:8080
```

### Diagram Levels

1. **System Context**: AGORA in relation to external systems
2. **Container**: HAI, Orchestrator, MCP Servers, Visibility
3. **Component**: Detailed breakdown of each container

---

## Appendix: Decision Log

### Why Two Backends?

| Reason | Explanation |
|--------|-------------|
| **Vendor Independence** | Government requirement to avoid lock-in |
| **Cost Flexibility** | LangGraph allows Azure OpenAI, local models |
| **Evaluation** | Compare SDK simplicity vs control |
| **Open Source Contribution** | LangGraph version can be shared |

### Why MCP over Direct Tool Calls?

| Reason | Explanation |
|--------|-------------|
| **Standardization** | MCP is becoming industry standard |
| **Decoupling** | Tools independent of orchestrator |
| **Reusability** | Same tools for multiple agents |
| **Testing** | Easier to test tools in isolation |

### Why SQLite for Sessions?

| Reason | Explanation |
|--------|-------------|
| **Simplicity** | No external DB required |
| **Built-in SDK Support** | Both SDKs support SQLite natively |
| **Sufficient for MVP** | Scales to production with migration path |
| **Local Development** | Easy setup, no Docker required |

---

*Document maintained by: NVWA AGORA Team*  
*For updates, edit `ARCHITECTURE.md` in the repository root.*

