---
date: 2026-01-08T12:00:00+01:00
researcher: Claude
git_commit: 6b442c7e3f5bbc71f8995504bbec08980494ffdf
branch: main
repository: AGORA
topic: "AGORA Backend Design Choices Documentation"
tags: [research, architecture, design-choices, backend, server-openai, server-langgraph, ag-ui-protocol, mcp]
status: complete
last_updated: 2026-01-08
last_updated_by: Claude
---

# AGORA Backend Design Choices

## Executive Summary

AGORA is a multi-agent compliance platform designed for NVWA (Dutch Food & Consumer Authority) inspectors. The architecture follows a **vendor-flexible** design philosophy, providing two interchangeable backend implementations that allow organizations to choose between proprietary convenience and open-source independence without changing any frontend code or agent behavior.

This document covers the key design choices made for the backend architecture, including the orchestration layer, language model integration, communication protocols, and supporting infrastructure.

---

## 1. The Orchestrator

The orchestrator is the central coordination layer that manages conversations between users and AI agents. AGORA provides **two functionally equivalent implementations** with identical external interfaces.

### 1.1 Closed-Source Approach: OpenAI Agents SDK

**Package:** `server-openai`

The OpenAI Agents SDK implementation leverages Anthropic's competitor's native multi-agent framework, providing a streamlined development experience with built-in capabilities.

**Key Characteristics:**

| Aspect | Description |
|--------|-------------|
| **Framework** | OpenAI Agents SDK (`openai-agents` package) |
| **Agent Definition** | Native `Agent` class with declarative configuration |
| **Handoff Mechanism** | Built-in SDK feature via `agent.handoffs` list |
| **Session Storage** | SDK-provided `SQLiteSession` for conversation persistence |
| **MCP Integration** | Native `MCPServerStreamableHttp` client |

**How It Works:**

The SDK provides high-level abstractions that handle much of the complexity:
- Agents are defined with instructions, tools, and handoff targets
- The SDK automatically manages conversation context during handoffs
- Tool execution and streaming are handled natively
- Session persistence is built into the SDK

**Advantages:**
- Rapid development with minimal boilerplate
- Native voice support included
- Optimized for OpenAI's models
- Regular updates and support from OpenAI

**Trade-offs:**
- Vendor lock-in to OpenAI's ecosystem
- Limited to OpenAI's language models only
- Less control over internal orchestration logic
- Dependency on proprietary closed-source code

### 1.2 Open-Source Approach: LangGraph

**Package:** `server-langgraph`

The LangGraph implementation uses an open-source graph-based orchestration framework from LangChain, providing full control and vendor independence.

**Key Characteristics:**

| Aspect | Description |
|--------|-------------|
| **Framework** | LangGraph (`langgraph` + `langchain` packages) |
| **Agent Definition** | Async Python functions as graph nodes |
| **Handoff Mechanism** | Explicit `transfer_to_*` tools with conditional routing |
| **Session Storage** | `AsyncSqliteSaver` checkpointer for state persistence |
| **MCP Integration** | `langchain-mcp-adapters` library |

**How It Works:**

LangGraph models the multi-agent system as a directed graph:
- Each agent is a **node** in the graph (an async function)
- A shared **ToolNode** executes all tools from MCP servers
- **Conditional edges** route between agents based on tool calls
- State flows through the graph as a typed dictionary

The handoff pattern requires explicit implementation:
1. Agent calls a `transfer_to_*` tool (e.g., `transfer_to_regulation`)
2. The routing logic detects this tool name pattern
3. Control transfers to the target agent node
4. Context is preserved in the shared state

**Advantages:**
- Full control over orchestration logic
- Supports any OpenAI-compatible LLM provider
- Open-source with active community
- Can be customized for specific requirements
- No vendor lock-in

**Trade-offs:**
- More code to maintain
- Manual implementation of features that are built-in elsewhere
- Requires deeper understanding of graph-based orchestration

### 1.3 Comparison Summary

Both implementations expose **identical APIs** to the frontend:

| Feature | server-openai | server-langgraph |
|---------|---------------|------------------|
| WebSocket endpoint | `/ws` | `/ws` |
| REST endpoints | `/health`, `/agents`, `/sessions/*` | `/health`, `/agents`, `/sessions/*` |
| AG-UI Protocol | Full support | Full support |
| Human-in-the-Loop | Supported | Supported |
| Streaming responses | Yes | Yes |

**When to Choose OpenAI SDK:**
- Rapid prototyping and development
- OpenAI is the preferred/mandated LLM provider
- Voice features are required
- Minimal maintenance overhead is priority

**When to Choose LangGraph:**
- Vendor independence is required
- Alternative LLM providers are needed (local models, Azure, etc.)
- Custom orchestration logic is anticipated
- Full control over the codebase is important

---

## 2. Large Language Models (LLMs)

The choice of language model directly impacts the capabilities, costs, and deployment options of the system.

### 2.1 Closed-Source Approach: OpenAI

**Default Model:** `gpt-4o`

Both orchestrator implementations can use OpenAI's models, which provide state-of-the-art capabilities for the inspection workflow.

**Usage Points:**
- **Agent Conversations** - All four agents (general, regulation, history, reporting) use the configured model
- **Data Extraction** - The reporting MCP server uses GPT-4 to extract structured data from conversation summaries
- **Report Generation** - Final HAP reports are composed with LLM assistance

**Configuration:**
```
OPENAI_AGENTS_OPENAI_API_KEY=your_api_key
OPENAI_AGENTS_OPENAI_MODEL=gpt-4o
```

**Advantages:**
- Best-in-class performance for complex reasoning
- Consistent, well-documented behavior
- Regular model improvements from OpenAI
- Strong tool-calling capabilities

**Trade-offs:**
- Per-token costs can be significant at scale
- Data is processed on external servers
- Dependency on external service availability
- No ability to fine-tune or customize the model

### 2.2 Open-Source Approach: OpenAI-Compatible Providers

**Supported via:** `server-langgraph` only

The LangGraph implementation accepts any API endpoint that implements the OpenAI Chat Completions API specification.

**Compatible Providers:**

| Provider | Type | Use Case |
|----------|------|----------|
| **Ollama** | Local | Self-hosted models on own hardware |
| **vLLM** | Self-hosted | High-performance inference server |
| **Azure OpenAI** | Cloud | OpenAI models via Azure compliance |
| **Together.ai** | Cloud | Access to various open models |
| **Anyscale** | Cloud | Scalable open model hosting |

**Configuration:**
```
LANGGRAPH_OPENAI_API_KEY=your_api_key
LANGGRAPH_OPENAI_BASE_URL=http://localhost:11434/v1  # Ollama example
LANGGRAPH_OPENAI_MODEL=llama3.1:70b
```

**Advantages:**
- Data stays within organizational boundaries
- No per-token costs for self-hosted models
- Full control over model selection and fine-tuning
- Compliance with data sovereignty requirements

**Trade-offs:**
- Requires infrastructure for self-hosting
- Open models may have lower capability than GPT-4
- More operational complexity
- Model quality varies significantly

### 2.3 Embedding Models

For semantic search in the regulation database, AGORA uses a **local, open-source embedding model**:

**Model:** `nomic-ai/nomic-embed-text-v1.5`

This model runs locally via the `sentence-transformers` library, meaning:
- No external API calls for embeddings
- Documents and queries stay local
- One-time download (~550MB)
- Runs on CPU or GPU

---

## 3. The HAI Contract (AG-UI Protocol)

The communication between frontend and backend follows the **AG-UI Protocol** (Agent-User Interface Protocol), an open-source standard for real-time agent-human interaction.

### 3.1 What is AG-UI?

AG-UI is a WebSocket-based event protocol designed specifically for multi-agent AI systems. It provides:
- **Real-time streaming** of text and events
- **Standardized event types** for common operations
- **Extensibility** via custom events
- **State synchronization** between client and server

AGORA uses the official packages:
- Python: `ag-ui-protocol>=0.1.0`
- TypeScript: `@ag-ui/core`

### 3.2 Event Categories

The protocol defines events in several categories:

**Lifecycle Events:**
| Event | Purpose |
|-------|---------|
| `RUN_STARTED` | A new agent run has begun |
| `RUN_FINISHED` | The run completed successfully |
| `RUN_ERROR` | The run encountered an error |
| `STEP_STARTED` | Processing phase began (routing, thinking, executing tools) |
| `STEP_FINISHED` | Processing phase completed |

**Text Message Events (Streaming):**
| Event | Purpose |
|-------|---------|
| `TEXT_MESSAGE_START` | New message from agent begins |
| `TEXT_MESSAGE_CONTENT` | Chunk of message text (streamed) |
| `TEXT_MESSAGE_END` | Message complete |

**Tool Call Events:**
| Event | Purpose |
|-------|---------|
| `TOOL_CALL_START` | Agent is calling a tool |
| `TOOL_CALL_ARGS` | Tool parameters (may be streamed) |
| `TOOL_CALL_END` | Tool invocation complete |
| `TOOL_CALL_RESULT` | Tool returned a result |

**State Events:**
| Event | Purpose |
|-------|---------|
| `STATE_SNAPSHOT` | Current system state (active agent, status) |
| `CUSTOM` | Extension point for application-specific events |

### 3.3 AGORA Extensions

AGORA extends AG-UI with custom events in the `agora:*` namespace:

| Event | Direction | Purpose |
|-------|-----------|---------|
| `agora:tool_approval_request` | Server to Client | Request human approval for a high-risk tool |
| `agora:tool_approval_response` | Client to Server | User's approval decision |
| `agora:error` | Server to Client | Application-specific errors (e.g., moderation) |
| `agora:spoken_text_*` | Server to Client | Text-to-speech audio events |

### 3.4 Human-in-the-Loop Flow

The approval flow demonstrates the protocol's extensibility:

1. Agent decides to call a tool flagged as high-risk
2. Backend sends `agora:tool_approval_request` with:
   - Tool name and description
   - Parameters being passed
   - Risk level (`low`, `medium`, `high`, `critical`)
   - Reasoning for the action
3. Frontend displays approval dialog to user
4. User approves or rejects with optional feedback
5. Backend receives `agora:tool_approval_response`
6. Tool execution proceeds or is cancelled

### 3.5 Protocol-First Development

The AG-UI contract is formally specified in:
- **AsyncAPI 3.0** specification (`docs/hai-contract/asyncapi.yaml`)
- **JSON Schema** definitions (`docs/hai-contract/schemas/`)
- **Human-readable documentation** (`docs/hai-contract/HAI_API_CONTRACT.md`)
- **Mock server** for frontend development (`docs/hai-contract/mock_server.py`)

This approach ensures:
- Clear contracts between frontend and backend teams
- Testable specifications
- Consistent implementation across both orchestrators

---

## 4. Agent-Orchestrator Coupling (MCP)

The Model Context Protocol (MCP) provides the mechanism for agents to access external tools and capabilities.

### 4.1 What is MCP?

MCP is an open protocol for exposing tools that AI models can call. In AGORA:
- **MCP Servers** are standalone microservices that expose domain-specific tools
- **The Orchestrator** acts as an MCP client, discovering and calling these tools
- **HTTP Transport** enables standard web infrastructure (load balancing, monitoring)

### 4.2 MCP Server Architecture

Each MCP server is an independent service built with the **FastMCP** framework:

**regulation-analysis (port 5002):**
- Semantic search over Dutch food safety regulations
- Vector database (Weaviate) for similarity search
- Tools: `search_regulations`, `get_regulation_context`, `get_database_stats`

**reporting (port 5003):**
- HAP inspection report generation workflow
- Multi-step process: extract data → verify → generate
- Tools: `start_inspection_report`, `extract_inspection_data`, `verify_inspection_data`, `generate_final_report`
- Outputs: JSON and PDF reports

**inspection-history (port 5005):**
- Company verification via KVK (Dutch Chamber of Commerce)
- Inspection history lookup
- Tools: `check_company_exists`, `get_inspection_history`, `get_company_violations`, `check_repeat_violation`

### 4.3 Scoped Tool Access

Each agent only receives tools from designated MCP servers:

| Agent | MCP Servers | Purpose |
|-------|-------------|---------|
| `general-agent` | None | Triage and handoff only |
| `regulation-agent` | regulation-analysis | Regulatory compliance |
| `reporting-agent` | reporting | Report generation |
| `history-agent` | inspection-history | Company verification |

This scoping:
- Prevents agents from accessing unrelated functionality
- Reduces cognitive load on the LLM (fewer tools to consider)
- Enforces domain boundaries by design

### 4.4 Benefits of MCP Architecture

**Separation of Concerns:**
- Each server handles one domain
- Independent development and deployment
- Different technology stacks per server if needed

**Auditability:**
- HTTP transport enables standard logging
- All tool calls can be monitored and recorded
- Clear request/response boundaries

**Extensibility:**
- New MCP servers can be added without modifying orchestrators
- Agents gain new tools through configuration, not code changes

**Testability:**
- Each server can be tested in isolation
- Mock servers for development and testing
- Clear API contracts

---

## 5. Logging

### 5.1 Current Implementation

Both orchestrators use **structured logging** via the `structlog` library:
- JSON-formatted log output
- Correlation IDs across requests
- Contextual information attached to log entries

**Key logging points:**
- WebSocket connection lifecycle
- Agent handoffs
- Tool call execution
- MCP server communication
- Error conditions

### 5.2 Audit Logging

An `AuditLogger` adapter exists in both backends for compliance-oriented logging:
- Captures all agent decisions
- Records tool calls with parameters
- Tracks approval requests and responses
- Designed for OpenTelemetry integration

---

## 6. Monitoring

### 6.1 Current State

Basic monitoring infrastructure is in place:
- Health check endpoints (`/health`) on all services
- Docker health checks for container orchestration
- Connection status tracking in the frontend

### 6.2 Planned Visibility Stack

The C4 architecture defines (but does not yet implement) a comprehensive monitoring solution:

**Grafana + Prometheus:**
- Metrics visualization dashboards
- Request rate and latency tracking
- Error rate monitoring
- Resource utilization

**Implementation Path:**
1. Add Prometheus metrics endpoints to orchestrators
2. Deploy Prometheus for metrics collection
3. Deploy Grafana with pre-built dashboards
4. Configure alerting rules

---

## 7. Observability

### 7.1 OpenTelemetry Integration

Both backends include OpenTelemetry dependencies:
- `opentelemetry-api` and `opentelemetry-sdk`
- `opentelemetry-instrumentation-fastapi`

Configuration is available but not connected:
```
OPENAI_AGENTS_OTEL_ENDPOINT=http://jaeger:4317
```

### 7.2 Distributed Tracing

When enabled, tracing will capture:
- Full request lifecycle across services
- MCP server call latency
- LLM inference timing
- Agent handoff sequences

**Planned Tools:**
- **Jaeger** for trace visualization
- **Langfuse** for LLM-specific observability (token usage, cost tracking, quality evaluation)

### 7.3 Implementation Approach

```yaml
# Example docker-compose addition
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
```

---

## 8. Moderators

### 8.1 Moderation Pipeline

Both orchestrators include a `ModerationPipeline` component that validates input and output:

**Input Validation:**
- Checks user messages before agent processing
- Can reject inappropriate or harmful content
- Configurable via environment variable

**Output Validation:**
- Validates agent responses before sending to user
- Ensures responses meet quality guidelines
- Can replace or filter problematic content

**Configuration:**
```
OPENAI_AGENTS_GUARDRAILS_ENABLED=true
```

### 8.2 Error Handling

Moderation violations are communicated via the custom `agora:error` event:
- Error code for programmatic handling
- Human-readable message for display
- Does not crash the conversation session

---

## 9. Guardrails

### 9.1 Human-in-the-Loop Approval

High-risk operations require explicit user approval:

**Risk Pattern Detection:**
- Tool names matching patterns: `delete`, `remove`, `destroy`, `submit_final`, `publish_report`
- Parameter thresholds: amounts over 10,000, company-wide scope
- Always-approve list: `generate_final_report`

**Risk Levels:**
| Level | Description |
|-------|-------------|
| `low` | Informational, minimal impact |
| `medium` | Standard operations |
| `high` | Significant actions requiring attention |
| `critical` | Final/irreversible actions |

### 9.2 Scoped Capabilities

Agents can only access tools relevant to their domain:
- Prevents accidental access to unrelated functionality
- Reduces risk of inappropriate tool usage
- Enforced at orchestrator level

### 9.3 Session Isolation

Each conversation session is isolated:
- Separate session ID and state
- No cross-session data leakage
- User-specific session ownership

---

## 10. Additional Considerations

### 10.1 Session Persistence

Both backends use SQLite for session storage:
- Conversation history survives server restarts
- Session metadata (title, message count, timestamps)
- User ownership tracking

**Future:** PostgreSQL is planned for production user profile storage.

### 10.2 Graceful Degradation

The system handles partial failures gracefully:
- If MCP servers are unavailable, agents operate without those tools
- WebSocket reconnection with exponential backoff
- Error states communicated clearly to users

### 10.3 Protocol Evolution

The `CUSTOM` event type enables adding new features without protocol version changes:
- New `agora:*` events can be added
- Clients ignore unknown custom events
- Backward compatibility preserved

### 10.4 Accessibility

The HAI frontend follows WCAG 2.1 AA guidelines:
- Keyboard navigation throughout
- Screen reader support
- Appropriate color contrast
- Focus management in dialogs

### 10.5 Compliance Design

The architecture considers EU regulatory requirements:

| Regulation | Relevant Features |
|------------|-------------------|
| **EU AI Act** | Human-in-the-loop, traceability, risk assessment |
| **AVG/GDPR** | Data minimization, user consent (planned) |
| **BIO** | Appropriate security for government use |
| **WCAG** | Accessible user interface |

---

## Appendix: Architecture Diagram Reference

The complete architecture is documented in C4 diagrams:
- **C1 (System Context):** Inspector, AGORA, MCP Ecosystem
- **C2 (Containers):** HAI, Orchestrator, MCP Servers, planned services
- **C3 (Components):** Internal structure of each container

View with: `cd c4 && npm run up` (Structurizr on port 8085)
