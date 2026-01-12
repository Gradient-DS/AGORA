# Fix MCP Tools Not Called After Handoff in server-openai

## Overview

The OpenAI implementation of the backend (server-openai) does not properly use MCP tools after agent handoffs. When `general-agent` hands off to `regulation-agent`, the regulation MCP tools are not being called - the agent responds using training knowledge instead of querying the regulation database. This plan implements explicit tool management to match the behavior of the LangGraph implementation.

## Current State Analysis

### Problem Statement
From the debug logs:
```
🔧 NEW AGENT MCP SERVERS [regulation-agent]: ['regulation']
...
🏁 AGENT RUN COMPLETED
   Final agent: regulation-agent
   Total tool calls: 1
   Tools called: ['transfer_to_regulation_analysis_expert']  ← ONLY the handoff, NO MCP calls!
```

The regulation-agent HAS the MCP server assigned, but is NOT calling its tools. Compare to `history-agent` and `reporting-agent` which correctly call their MCP tools.

### Root Cause
Per research in `thoughts/shared/research/2026-01-12-regulation-mcp-not-called-server-openai.md`:

1. **SDK Internal Tool Discovery**: The OpenAI Agents SDK uses implicit tool discovery from `mcp_servers`. This appears unreliable after handoffs.
2. **Known SDK Limitation**: GitHub Issue #617 ("Handoff Agent and Tool Call Not Triggering Reliably") was closed as "not planned", suggesting this is a fundamental SDK limitation.
3. **LangGraph Difference**: The LangGraph implementation uses explicit `llm.bind_tools(tools)` at runtime, guaranteeing tool availability.

### Key Discoveries
- `server-openai/src/agora_openai/core/agent_runner.py:65-69` - MCP servers are passed to Agent constructor but SDK doesn't reliably surface them after handoffs
- `server-openai/src/agora_openai/adapters/mcp_tools.py:83-91` - MCP servers have `_tools` attribute after connection with discovered tools
- OpenAI SDK provides `agent.get_all_tools(run_context)` and `agent.get_mcp_tools(run_context)` methods
- SDK supports explicit `tools=[]` parameter alongside `mcp_servers=[]`

## Desired End State

After this plan is complete:
1. All specialist agents (regulation-agent, history-agent, reporting-agent) reliably call their MCP tools after handoffs
2. Tool availability is explicit and verifiable, not dependent on SDK internal behavior
3. Debug logging confirms tools are bound to LLM requests

### Verification
- Start new inspection, ask about regulations (e.g., "Welke regels gelden voor bewaring van vis?")
- Logs should show `🌐 MCP TOOL CALL: search_regulations by regulation-agent`
- Response should cite specific regulations from the MCP server, not general knowledge

## What We're NOT Doing

- NOT migrating server-openai to a completely different architecture
- NOT changing the agent definitions or instructions (these are fine)
- NOT modifying the MCP servers themselves
- NOT changing the handoff mechanism (SDK handoffs work, just tool binding doesn't)
- NOT removing MCP server support entirely (we'll use both approaches)

## Implementation Approach

Convert from implicit MCP server tool discovery to explicit tool fetching and passing. This mirrors the LangGraph approach while staying within the OpenAI SDK framework.

**Strategy**:
1. Fetch tools from MCP servers at startup (after connection)
2. Store tools per agent in a dedicated registry
3. Pass tools explicitly via `tools=[]` parameter to Agent constructor
4. Keep `mcp_servers=[]` as fallback for any tools we might miss

---

## Phase 1: Add Explicit Tool Fetching to MCPToolRegistry

### Overview
Extend `MCPToolRegistry` to fetch and store tools from connected MCP servers in a format suitable for passing to Agent constructors.

### Changes Required:

#### 1. Update MCPToolRegistry to fetch and store tools
**File**: `server-openai/src/agora_openai/adapters/mcp_tools.py`

**Changes**: Add method to extract tools from connected MCP servers and convert them to the format expected by the Agent `tools=[]` parameter.

```python
# Add after line 113 (after disconnect_all method)

from agents import FunctionTool
from typing import Dict, List

def get_tools_by_server(self) -> dict[str, list]:
    """Get discovered tools organized by MCP server name.

    Must be called after connect_all() completes.

    Returns:
        Dict mapping server name to list of tool definitions
    """
    if not self._connected:
        log.warning("get_tools_by_server called before servers connected")
        return {}

    tools_by_server: dict[str, list] = {}

    for mcp_server in self.mcp_servers:
        server_name = mcp_server.name
        tools_by_server[server_name] = []

        # Access the internal _tools list populated after connect()
        if hasattr(mcp_server, "_tools") and mcp_server._tools:
            for tool in mcp_server._tools:
                tools_by_server[server_name].append(tool)
                tool_name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "unknown")
                log.debug(f"Extracted tool '{tool_name}' from server '{server_name}'")
        else:
            log.warning(f"No tools found for MCP server: {server_name}")

    log.info(f"Extracted tools from {len(tools_by_server)} servers: {list(tools_by_server.keys())}")
    for server_name, tools in tools_by_server.items():
        log.info(f"  - {server_name}: {len(tools)} tools")

    return tools_by_server
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `mypy server-openai/src/`
- [ ] Linting passes: `ruff check server-openai/src/`
- [ ] Unit tests pass: `pytest server-openai/`

#### Manual Verification:
- [ ] Start server and check logs for "Extracted tools from X servers" message
- [ ] Verify tool counts match expected (regulation: ~10 tools, reporting: ~5 tools, history: ~6 tools)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Pass Tools Explicitly to Agents During Registration

### Overview
Modify `AgentRegistry.register_agent()` to pass tools explicitly via the `tools=[]` parameter in addition to `mcp_servers=[]`. This ensures tools are available regardless of SDK internal behavior.

### Changes Required:

#### 1. Update AgentRegistry to accept tools_by_server
**File**: `server-openai/src/agora_openai/core/agent_runner.py`

**Changes**:
1. Add `tools_by_server` parameter to `__init__`
2. Modify `register_agent` to pass explicit tools

```python
# Update AgentRegistry class (starting around line 38)

class AgentRegistry:
    """Registry for Agent SDK agents with handoff support."""

    def __init__(
        self,
        mcp_registry: MCPToolRegistry,
        tools_by_server: dict[str, list] | None = None
    ):
        self.mcp_registry = mcp_registry
        self.tools_by_server = tools_by_server or {}
        self.agents: dict[str, Agent] = {}
        self.agent_configs: dict[str, AgentConfig] = {}

    def register_agent(self, config: AgentConfig) -> Agent:
        """Create and register an Agent SDK agent from config."""
        agent_id = config["id"]

        # Get only the MCP servers this agent should have access to
        agent_mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
        agent_mcp_servers: list[MCPServerStreamableHttp] = []

        # Collect explicit tools for this agent
        explicit_tools: list = []

        for mcp_server in self.mcp_registry.mcp_servers:
            if mcp_server.name in agent_mcp_server_names:
                agent_mcp_servers.append(mcp_server)

                # Also collect explicit tools from this server
                if mcp_server.name in self.tools_by_server:
                    explicit_tools.extend(self.tools_by_server[mcp_server.name])

        settings = get_settings()
        model = config.get("model") or settings.openai_model

        # Pass BOTH explicit tools AND mcp_servers for redundancy
        agent = Agent(
            name=config["name"],
            instructions=config["instructions"],
            model=model,
            tools=explicit_tools,  # Explicit tools for reliability
            mcp_servers=agent_mcp_servers,  # Keep as fallback
        )

        self.agents[agent_id] = agent
        self.agent_configs[agent_id] = config

        log.info(
            f"📝 REGISTERED AGENT: {agent_id} with {len(agent_mcp_servers)} MCP servers, {len(explicit_tools)} explicit tools"
        )
        if explicit_tools:
            tool_names = [t.get("name") if isinstance(t, dict) else getattr(t, "name", "?") for t in explicit_tools[:5]]
            log.info(f"    └─ Tools: {tool_names}{'...' if len(explicit_tools) > 5 else ''}")
        if agent_mcp_servers:
            for mcp in agent_mcp_servers:
                log.info(f"    └─ MCP: {mcp.name}")
        if not explicit_tools and not agent_mcp_servers:
            log.info(f"    └─ (no tools or MCP servers)")

        return agent
```

#### 2. Update server.py to pass tools_by_server to AgentRegistry
**File**: `server-openai/src/agora_openai/api/server.py`

**Changes**: After MCP registry connects, fetch tools and pass to AgentRegistry.

```python
# In the lifespan function, after mcp_registry.discover_and_register_tools()
# Find the section where AgentRegistry is created and update it

# After: await mcp_registry.discover_and_register_tools()
# Add:
tools_by_server = mcp_registry.get_tools_by_server()

# Then update AgentRegistry creation:
agent_registry = AgentRegistry(mcp_registry, tools_by_server=tools_by_server)
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `mypy server-openai/src/`
- [ ] Linting passes: `ruff check server-openai/src/`
- [ ] Unit tests pass: `pytest server-openai/`

#### Manual Verification:
- [ ] Start server and verify logs show "X explicit tools" for each agent
- [ ] regulation-agent should show ~10 explicit tools
- [ ] history-agent should show ~6 explicit tools
- [ ] reporting-agent should show ~5 explicit tools
- [ ] general-agent should show 0 explicit tools (expected)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Verify MCP Tools Work After Handoff

### Overview
Add verification logging to confirm tools are being sent to OpenAI API after handoffs, and test the fix end-to-end.

### Changes Required:

#### 1. Add tool availability logging in stream processing
**File**: `server-openai/src/agora_openai/core/agent_runner.py`

**Changes**: When a handoff occurs, log the tools available to the target agent.

```python
# In _handle_handoff_event method (around line 472)
# After the agent transition, add tool verification logging

async def _handle_handoff_event(
    self, state: StreamState, tool_callback: Callable | None
) -> None:
    """Handle handoff occurrence."""
    old_agent_id = state.current_agent_id
    log.info(f"🔄 HANDOFF EVENT DETECTED (from {old_agent_id})")

    if state.pending_handoff_target:
        state.current_agent_id = state.pending_handoff_target
        log.info(
            f"✅ AGENT TRANSITION: {old_agent_id} → {state.current_agent_id}"
        )

        # Log MCP servers available to the new agent
        new_agent = self.agent_registry.get_agent(state.current_agent_id)
        if new_agent:
            # Log MCP servers
            if hasattr(new_agent, "mcp_servers") and new_agent.mcp_servers:
                mcp_names = [s.name for s in new_agent.mcp_servers]
                log.info(f"🔧 NEW AGENT MCP SERVERS [{state.current_agent_id}]: {mcp_names}")
            else:
                log.info(f"🔧 NEW AGENT [{state.current_agent_id}] has NO MCP servers")

            # NEW: Log explicit tools
            if hasattr(new_agent, "tools") and new_agent.tools:
                tool_names = [
                    t.get("name") if isinstance(t, dict) else getattr(t, "name", "?")
                    for t in new_agent.tools[:5]
                ]
                log.info(f"🛠️ NEW AGENT EXPLICIT TOOLS [{state.current_agent_id}]: {tool_names}{'...' if len(new_agent.tools) > 5 else ''} ({len(new_agent.tools)} total)")
            else:
                log.info(f"🛠️ NEW AGENT [{state.current_agent_id}] has NO explicit tools")

        state.pending_handoff_target = None
    else:
        log.warning(f"⚠️ HANDOFF EVENT but no pending target! current_agent={state.current_agent_id}")

    if tool_callback:
        await self._complete_transfer_tool_call(state, tool_callback)
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `mypy server-openai/src/`
- [ ] Linting passes: `ruff check server-openai/src/`
- [ ] Unit tests pass: `pytest server-openai/`

#### Manual Verification:
- [ ] Start server, begin inspection conversation
- [ ] Ask a regulation question: "Ik zie rauwe vis op kamertemperatuur, welke regels gelden hiervoor?"
- [ ] Verify logs show:
  - `✅ AGENT TRANSITION: general-agent → regulation-agent`
  - `🛠️ NEW AGENT EXPLICIT TOOLS [regulation-agent]: ['search_regulations', ...] (X total)`
  - `🌐 MCP TOOL CALL: search_regulations by regulation-agent`
- [ ] Response should cite specific EU regulations (852/2004, etc.) from the database

**Implementation Note**: After completing this phase, the fix should be verified. Proceed to Phase 4 if tests pass.

---

## Phase 4: Integration Tests

### Overview
Add integration tests to verify MCP tools are called after handoffs.

### Changes Required:

#### 1. Add test for tool calling after handoff
**File**: `server-openai/tests/test_agent_handoff_tools.py` (new file)

```python
"""Tests for MCP tool calling after agent handoffs."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agora_openai.core.agent_runner import AgentRegistry, AgentRunner, AGENT_MCP_MAPPING
from agora_openai.core.agent_definitions import AGENT_CONFIGS


class TestAgentToolsAfterHandoff:
    """Test that agents have correct tools after handoff."""

    def test_agent_mcp_mapping_defined(self):
        """Verify all agents have MCP mapping defined."""
        for config in AGENT_CONFIGS:
            agent_id = config["id"]
            assert agent_id in AGENT_MCP_MAPPING, f"Missing mapping for {agent_id}"

    def test_regulation_agent_has_regulation_server(self):
        """Verify regulation-agent is mapped to regulation MCP server."""
        assert "regulation" in AGENT_MCP_MAPPING["regulation-agent"]

    def test_history_agent_has_history_server(self):
        """Verify history-agent is mapped to history MCP server."""
        assert "history" in AGENT_MCP_MAPPING["history-agent"]

    def test_reporting_agent_has_reporting_server(self):
        """Verify reporting-agent is mapped to reporting MCP server."""
        assert "reporting" in AGENT_MCP_MAPPING["reporting-agent"]

    def test_general_agent_has_no_servers(self):
        """Verify general-agent has no MCP servers (it's the router)."""
        assert AGENT_MCP_MAPPING["general-agent"] == []


class TestAgentRegistryWithTools:
    """Test AgentRegistry with explicit tools."""

    def test_registry_accepts_tools_by_server(self):
        """Verify AgentRegistry accepts tools_by_server parameter."""
        mock_mcp_registry = MagicMock()
        mock_mcp_registry.mcp_servers = []

        tools_by_server = {
            "regulation": [{"name": "search_regulations", "description": "Search"}],
            "history": [{"name": "check_company_exists", "description": "Check"}],
        }

        registry = AgentRegistry(mock_mcp_registry, tools_by_server=tools_by_server)
        assert registry.tools_by_server == tools_by_server

    def test_registry_passes_tools_to_agent(self):
        """Verify explicit tools are passed to Agent constructor."""
        # This would require mocking the Agent class
        # Implementation depends on test infrastructure
        pass
```

### Success Criteria:

#### Automated Verification:
- [ ] All new tests pass: `pytest server-openai/tests/test_agent_handoff_tools.py -v`
- [ ] Full test suite passes: `pytest server-openai/`

#### Manual Verification:
- [ ] Tests cover the key scenarios for tool availability after handoff

---

## Testing Strategy

### Unit Tests
- Test `MCPToolRegistry.get_tools_by_server()` returns correct tools
- Test `AgentRegistry` correctly passes tools to agents
- Test AGENT_MCP_MAPPING is complete for all agents

### Integration Tests
- Test regulation-agent calls MCP tools after handoff from general-agent
- Test history-agent calls MCP tools after handoff
- Test reporting-agent calls MCP tools after handoff

### Manual Testing Steps
1. Start server-openai with `python -m agora_openai.api.server`
2. Connect HAI frontend
3. Start new inspection: "Start inspectie bij Bakkerij Jansen KVK 12345678"
4. Ask regulation question: "Welke regels gelden voor bewaring van brood?"
5. Verify logs show MCP tool calls by regulation-agent
6. Request report: "Genereer rapport"
7. Verify logs show MCP tool calls by reporting-agent

## Performance Considerations

- Tool fetching happens once at startup, not per-request
- Explicit tools are stored in memory alongside MCP server references
- No additional network calls during agent execution
- Redundant tool sources (explicit + MCP) add negligible memory overhead

## Migration Notes

This change is backwards compatible:
- Existing sessions will work as before (but with improved tool reliability)
- No database migrations required
- No API changes
- Agent definitions unchanged

## References

- Research document: `thoughts/shared/research/2026-01-12-regulation-mcp-not-called-server-openai.md`
- LangGraph comparison: `server-langgraph/src/agora_langgraph/core/agents.py:77-83`
- OpenAI Agents SDK MCP docs: https://openai.github.io/openai-agents-python/mcp/
- GitHub Issue #617 (closed as not planned): https://github.com/openai/openai-agents-python/issues/617
