---
date: 2026-02-03T12:00:00+01:00
researcher: claude
git_commit: c9fa6fb
branch: feat/benchmark
repository: AGORA
topic: "C4 Architecture Update: User Preferences, Agent Memory, Agent Management Components"
tags: [research, codebase, c4, architecture, agent-registry, agent-management, user-preferences, memory]
status: complete
last_updated: 2026-02-03
last_updated_by: claude
---

# Research: C4 Architecture Update for Agent Management Components

**Date**: 2026-02-03T12:00:00+01:00
**Researcher**: claude
**Git Commit**: c9fa6fb
**Branch**: feat/benchmark
**Repository**: AGORA

## Research Question

What needs to change in the C4 architecture (`c4/workspace.dsl`) to reflect:
1. User preferences changed from NOT IMPLEMENTED → IMPLEMENTED
2. Memory → Agent Memory
3. New agent management components: Agent Registry, Agent Loader, Management Interface (Beheersinterface)

## Summary

The C4 architecture needs updates at **three levels** (C2 containers, C3 components in both orchestrators). User preferences are already implemented and should be un-tagged from `NotImplemented`. The Memory container should be reframed as "Agent Memory" for cross-session agent context. Three new architectural components for agent management need to be added: Agent Registry (data store), Agent Loader (orchestrator component), and a Management Interface (either new container or extension of HAI).

---

## Detailed Findings

### 1. User Preferences: NOT IMPLEMENTED → IMPLEMENTED

**Current C4 state** (`c4/workspace.dsl:273-276`):
```dsl
userProfile = container "User Profile" "PostgreSQL" "Database" {
    description "[Shared] [NOT IMPLEMENTED] User profiles, preferences, roles (RBAC)"
    tags "Database" "NotImplemented" "Shared"
}
```

**Actual codebase state**: Fully implemented across the stack:
- **Backend**: `UserManager` class in both backends with SQLite `users` table (preferences stored as JSON blob)
- **API**: Full REST endpoints (`/users`, `/users/me/preferences`)
- **Frontend**: Admin panel with user CRUD (`HAI/src/components/admin/`), preferences editing, user switching
- **Runtime consumption**: `spoken_text_type` controls dual-channel streaming, `email_reports` injected into graph metadata, `interaction_mode` is session-level

**Required changes**:
- Remove `NotImplemented` tag
- Update technology from `"PostgreSQL"` to `"SQLite"` (or keep abstract)
- Update description to reflect actual state: user profiles, preferences (spoken_text_type, email_reports, interaction_mode)
- Note that RBAC is still not enforced (role column exists but unused)
- Add relationship edges: orchestrator → userProfile (reads preferences), HAI → userProfile (via REST API)

### 2. Memory → Agent Memory

**Current C4 state** (`c4/workspace.dsl:278-281`):
```dsl
memory = container "Memory Service" "Vector DB + PostgreSQL" "Service" {
    description "[Shared] [NOT IMPLEMENTED] Long-term memory, cross-session context"
    tags "Backend" "NotImplemented" "Shared"
}
```

**Actual codebase state**:
- **Session memory**: Fully implemented per-session via `SQLiteSession` (OpenAI) and `AsyncSqliteSaver` (LangGraph)
- **Agent-specific memory**: Not implemented — agents are stateless between invocations
- **Cross-session context**: Not implemented
- **Vector DB for regulations**: Exists (Weaviate) but is domain knowledge, not agent memory

**Required changes**:
- Rename to "Agent Memory Service" or "Agent Memory"
- Keep `NotImplemented` tag (since cross-session agent memory doesn't exist yet)
- Update description to clarify purpose: "Long-term agent memory, cross-session context, learned preferences and patterns"
- Consider distinguishing from session persistence (which IS implemented as part of the orchestrator)

### 3. Agent Registry (New Component)

**Current state**: Agents are hardcoded in `agent_definitions.py` (both backends) as Python `TypedDict` lists with inline system prompts, model settings, temperature, handoff targets, and MCP server associations.

**What an Agent Registry would add**:
- Centralized database or config store for agent definitions
- Fields: name, system prompt, linked MCP servers, tool risk levels, LLM model
- Decouples agent definitions from orchestrator code
- Enables runtime modification without code changes

**Where it fits in C4**:

At **C2 level**: New container alongside the existing ones:
```
agentRegistry = container "Agent Registry" "PostgreSQL/SQLite" "Database" {
    description "[Shared] Central register of agent definitions: name, system prompt, MCP server mappings, tool risk levels, LLM model configuration"
    tags "Database" "Shared"
}
```

At **C3 level** (both orchestrators): The existing components that would change:
- **server-openai**: `oaiAgentDefinitions` currently described as "SDK Agent instances with instructions and handoff configuration" → would read from registry instead of hardcoded `AGENT_CONFIGS`
- **server-langgraph**: `lgAgentDefinitions` currently described as "Async functions invoking ChatOpenAI with bound tools" → would read from registry

**Relationships**:
- `orchestrator → agentRegistry` "reads agent definitions"
- `managementInterface → agentRegistry` "manages agent configurations"

### 4. Agent Loader (New Orchestrator Component)

**Current state**:
- **server-openai**: `AgentRegistry` class in `agent_runner.py:42-136` iterates hardcoded `AGENT_CONFIGS` at startup, calls `register_agent()` for each, and `configure_handoffs()` after all are registered
- **server-langgraph**: `build_agent_graph()` in `graph.py:564` hardcodes the four agent IDs in a loop, assigns tools via `get_tools_for_agent()` and `set_agent_tools()`

**What an Agent Loader would add**:
- Reads agent definitions from the Agent Registry at startup or dynamically at runtime
- In LangGraph: programmatically creates graph nodes based on registry
- In OpenAI SDK: dynamically generates `Agent` objects from registry data
- Supports hot-reload or lazy instantiation of agents

**Where it fits in C4**:

At **C3 level** (inside both orchestrator containers), as a new component in the Core Layer:

For **OpenAI orchestrator**:
```
oaiAgentLoader = component "[Shared] Agent Loader" "Python" {
    description "Dynamically instantiates Agent objects from the Agent Registry at startup or runtime"
    tags "Shared"
}
```
Relationships:
- `oaiAgentLoader → agentRegistry` "reads agent configs"
- `oaiAgentLoader → oaiAgentDefinitions` "creates agents"
- `oaiAgentLoader → oaiMcpAdapter` "resolves MCP tool mappings"

For **LangGraph orchestrator**:
```
lgAgentLoader = component "[Shared] Agent Loader" "Python" {
    description "Programmatically creates StateGraph nodes from Agent Registry definitions at startup or runtime"
    tags "Shared"
}
```
Relationships:
- `lgAgentLoader → agentRegistry` "reads agent configs"
- `lgAgentLoader → lgAgentDefinitions` "creates agent nodes"
- `lgAgentLoader → lgMcpAdapter` "resolves MCP tool mappings"

### 5. Management Interface (Beheersinterface)

**Current state**:
- User management admin panel exists in HAI (`AdminPanel.tsx`, `UserList.tsx`, `UserForm.tsx`)
- `GET /agents` endpoint returns read-only agent list
- No CRUD endpoints for agents
- No agent configuration UI

**What a Management Interface would add**:
- Web interface for administrators to add, configure, activate/deactivate agents
- No orchestrator code changes needed for agent management
- Could be an extension of the existing HAI admin panel or a separate admin application

**Where it fits in C4**:

**Option A — Extend HAI** (lower complexity):
Add new C3 components inside the HAI container:
```
agentManagement = component "[Shared] Agent Management Panel" "React" {
    description "Admin interface for adding, configuring, activating/deactivating agents without code changes"
    tags "Shared"
}
```

**Option B — Separate container** (cleaner separation of concerns):
```
adminInterface = container "Management Interface" "React SPA" "Web Application" {
    description "[Shared] Admin application for managing agent configurations, MCP server mappings, and system settings"
    tags "Frontend" "Shared"
}
```

Relationships (either option):
- `managementInterface → agentRegistry` "CRUD agent configs" (via REST API)
- `managementInterface → orchestrator` "triggers agent reload" (optional)

---

## Proposed Changes to workspace.dsl

### C2 Level Changes

1. **Update `userProfile` container** — remove NotImplemented, update tech/description
2. **Rename `memory` container** — to "Agent Memory Service", update description
3. **Add `agentRegistry` container** — new database container
4. **Add `adminInterface` container** (if Option B) — new frontend container
5. **Add relationship edges** between new containers and orchestrator

### C3 Level Changes (Both Orchestrators)

6. **Add `Agent Loader` component** in Core Layer of both orchestrators
7. **Update `Agent Definitions` component** description to reflect registry-backed loading
8. **Add `Agent Management Panel` component** in HAI (if Option A)

### C3 HAI Level Changes

9. **Add admin/management components** for agent configuration UI (if extending HAI)

### Views Changes

10. **Update C2 container view** to include new containers
11. **Potentially add a new C3 view** for agent management flow

---

## Architecture Insights

### Current Agent Definition Flow (Hardcoded)
```
AGENT_CONFIGS (Python list)
    → AgentRegistry.register_agent() / build_agent_graph()
    → Agent/ChatOpenAI instances with bound tools
    → AGENT_MCP_MAPPING resolves MCP server scoping
```

### Proposed Agent Definition Flow (Registry-Based)
```
Management Interface → Agent Registry DB (CRUD)
    → Agent Loader reads registry at startup/runtime
    → Dynamically creates Agent/Graph nodes
    → AGENT_MCP_MAPPING stored in registry per agent
    → Hot-reload possible without restart
```

### Key Design Decision: Where Does the Agent Registry Live?

**Option 1 — Same SQLite database** (`sessions.db`): Simplest, consistent with current pattern. Add an `agents` table.

**Option 2 — Separate PostgreSQL**: As originally envisioned in C4. Better for production, supports concurrent access from management interface and orchestrator.

**Option 3 — Configuration file** (YAML/JSON): Simpler than a database, version-controllable, but less dynamic.

### AGENT_MCP_MAPPING Integration

Currently hardcoded as a Python dict in both backends (`agent_runner.py:34-39` for OpenAI, `tools.py:203-208` for LangGraph). In a registry-based model, this mapping would be stored per-agent as part of the agent definition, eliminating the separate mapping constant.

---

## Code References

- `c4/workspace.dsl:273-276` — Current userProfile container (NOT IMPLEMENTED)
- `c4/workspace.dsl:278-281` — Current memory container (NOT IMPLEMENTED)
- `server-openai/src/agora_openai/core/agent_definitions.py:4-16` — AgentConfig TypedDict + AGENT_CONFIGS
- `server-openai/src/agora_openai/core/agent_runner.py:34-39` — AGENT_MCP_MAPPING
- `server-openai/src/agora_openai/core/agent_runner.py:42-136` — AgentRegistry class
- `server-openai/src/agora_openai/api/server.py:59-67` — Agent registration at startup
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:6-19` — AgentConfig TypedDict
- `server-langgraph/src/agora_langgraph/core/graph.py:564-596` — build_agent_graph()
- `server-langgraph/src/agora_langgraph/core/tools.py:203-208` — AGENT_MCP_MAPPING
- `server-openai/src/agora_openai/adapters/user_manager.py:62-74` — Users table schema
- `HAI/src/components/admin/AdminPanel.tsx` — Existing user admin panel

## Open Questions

1. **Should the Management Interface be part of HAI or a separate application?** HAI is inspector-facing; a separate admin app provides cleaner separation of concerns.
2. **Should the Agent Registry use SQLite (consistent with current pattern) or PostgreSQL (as C4 originally envisioned)?**
3. **Should the Agent Loader support hot-reload (runtime re-instantiation) or only load at startup?**
4. **How should agent versioning work in the registry?** (e.g., keeping history of prompt changes)
5. **Should the `AGENT_MCP_MAPPING` move into the registry or remain as a separate concern?**
6. **What level of RBAC is needed for the management interface?** (Currently no auth exists)
