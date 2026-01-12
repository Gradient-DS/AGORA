---
date: 2026-01-12T12:00:00+01:00
researcher: Claude Code
git_commit: ea075144afe772c5dd02f2860aad0643e4ceb5ae
branch: feat/parallel-spoken
repository: AGORA
topic: "Why regulation MCP server is not called in server-openai after handoff"
tags: [research, codebase, server-openai, server-langgraph, mcp, handoff, debugging]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude Code
---

# Research: Why regulation MCP server is not called in server-openai after handoff

**Date**: 2026-01-12T12:00:00+01:00
**Researcher**: Claude Code
**Git Commit**: ea075144afe772c5dd02f2860aad0643e4ceb5ae
**Branch**: feat/parallel-spoken
**Repository**: AGORA

## Research Question

The OpenAI version of the backend (server-openai) does not use the regulation MCP server after transferring to the regulation-agent specialist, while the LangGraph version (server-langgraph) works correctly. What is causing this difference?

## Summary

The root cause is a **fundamental architectural difference** in how the two implementations handle tool binding:

1. **server-langgraph** (WORKS): Explicitly fetches MCP tools at startup and binds them to each agent's LLM at runtime via `llm.bind_tools(tools)`. Each agent dynamically receives its tools when it runs.

2. **server-openai** (BROKEN): Relies on the OpenAI Agents SDK to internally discover and use tools from `MCPServerStreamableHttp` objects passed to the Agent constructor. The SDK appears to not properly discover/use MCP tools after a handoff occurs.

**Most likely cause**: The OpenAI Agents SDK may be caching tool discovery at the Runner level rather than re-discovering tools when switching agents during a handoff.

## Detailed Findings

### 1. server-openai Implementation (Not Working)

#### Agent Registration (`server-openai/src/agora_openai/core/agent_runner.py:46-79`)

MCP servers are filtered and assigned during agent construction:

```python
def register_agent(self, config: AgentConfig) -> Agent:
    agent_id = config["id"]

    # Get only the MCP servers this agent should have access to
    agent_mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
    agent_mcp_servers: list[MCPServerStreamableHttp] = []

    for mcp_server in self.mcp_registry.mcp_servers:
        if mcp_server.name in agent_mcp_server_names:
            agent_mcp_servers.append(mcp_server)

    agent = Agent(
        name=config["name"],
        instructions=config["instructions"],
        model=model,
        mcp_servers=agent_mcp_servers,  # MCP servers assigned here
    )
```

For `regulation-agent`, the mapping at line 32 specifies `["regulation"]`, so it should receive the regulation MCP server.

#### MCP Tool Registry (`server-openai/src/agora_openai/adapters/mcp_tools.py:44-68`)

MCP servers are created and connected at startup:

```python
mcp_server = MCPServerStreamableHttp(
    name=server_name,
    params={
        "url": mcp_url,
        "timeout": timedelta(seconds=30),
        "sse_read_timeout": timedelta(seconds=120),
    },
    client_session_timeout_seconds=120,
)
```

#### Execution Flow (`server-openai/src/agora_openai/core/agent_runner.py:179-205`)

**Critical issue**: The runner ALWAYS starts with the entry agent:

```python
result = Runner.run_streamed(
    entry_agent,  # Always starts from general-agent
    input=message,
    session=session,
)
```

The SDK is expected to:
1. Run general-agent with its tools (none - no MCP servers assigned)
2. When handoff occurs, switch to regulation-agent
3. Use regulation-agent's MCP servers for tool discovery

**The SDK is responsible for this internal tool switching, which appears to not work correctly.**

### 2. server-langgraph Implementation (Working)

#### MCP Tool Fetching (`server-langgraph/src/agora_langgraph/adapters/mcp_client.py:25-51`)

Tools are explicitly fetched from MCP servers as `BaseTool` objects:

```python
async def connect(self) -> None:
    for server_name, base_url in self.server_urls.items():
        client = MultiServerMCPClient(config)
        tools = await client.get_tools()  # Explicit tool fetching
        self._tools_by_server[server_name] = tools
```

#### Tool Assignment (`server-langgraph/src/agora_langgraph/core/tools.py:79-114`)

Tools are explicitly assigned to each agent:

```python
def get_tools_for_agent(agent_id: str, mcp_tools_by_server: dict) -> list[Any]:
    tools: list[Any] = []

    # Add handoff tools
    if agent_id == "general-agent":
        tools.extend([transfer_to_history, transfer_to_regulation, transfer_to_reporting])
    else:
        tools.append(transfer_to_general)

    # Add MCP tools from mapped servers
    mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
    for server_name in mcp_server_names:
        if server_name in mcp_tools_by_server:
            tools.extend(mcp_tools_by_server[server_name])

    return tools
```

#### Runtime Tool Binding (`server-langgraph/src/agora_langgraph/core/agents.py:77-83`)

Tools are dynamically bound to the LLM each time an agent runs:

```python
llm = get_llm_for_agent(agent_id)
tools = get_agent_tools(agent_id)  # Retrieved from global storage

if tools:
    llm_with_tools = llm.bind_tools(tools)  # Explicit binding!
```

**This explicit binding guarantees tools are available when the agent runs.**

### 3. Key Architectural Differences

| Aspect | server-openai | server-langgraph |
|--------|---------------|------------------|
| **Tool Discovery** | SDK internal (implicit) | Explicit fetch via `get_tools()` |
| **Tool Binding** | SDK handles internally | `llm.bind_tools(tools)` at runtime |
| **Handoff Mechanism** | SDK auto-generates transfer tools | Explicit `transfer_to_X` tools |
| **Tool Availability** | Depends on SDK behavior | Guaranteed by explicit assignment |
| **State During Handoff** | SDK black-box | Graph routing preserves state |

### 4. Potential Root Causes in server-openai

1. **SDK Tool Discovery Cache**: The OpenAI Agents SDK may discover tools at the start of `Runner.run_streamed()` based on the entry agent only, and not re-discover when handoffs occur.

2. **MCP Connection State**: The MCP servers might need to be re-connected or have their tools re-discovered after a handoff.

3. **Agent.mcp_servers Not Used**: The SDK might not be properly accessing the `mcp_servers` property of target agents after handoff.

4. **Missing Tool Exposure**: The SDK might require additional configuration to expose MCP tools to the LLM during agent execution.

## Code References

- `server-openai/src/agora_openai/core/agent_runner.py:30-35` - AGENT_MCP_MAPPING definition
- `server-openai/src/agora_openai/core/agent_runner.py:46-79` - Agent registration with MCP servers
- `server-openai/src/agora_openai/core/agent_runner.py:189-193` - Runner.run_streamed invocation
- `server-openai/src/agora_openai/core/agent_definitions.py:71-111` - regulation-agent definition
- `server-openai/src/agora_openai/adapters/mcp_tools.py:44-68` - MCP server registration
- `server-langgraph/src/agora_langgraph/core/tools.py:79-114` - get_tools_for_agent function
- `server-langgraph/src/agora_langgraph/core/agents.py:77-83` - Runtime tool binding

## Architecture Insights

The OpenAI Agents SDK uses a more "black-box" approach where you configure agents with their capabilities (MCP servers, handoffs) and trust the SDK to handle execution. This works well when the SDK behavior matches expectations, but becomes difficult to debug when issues arise.

The LangGraph implementation uses explicit tool management at every step, providing:
- Full control over which tools each agent receives
- Clear visibility into tool binding at runtime
- Deterministic behavior across handoffs

## Recommended Investigation Steps

1. **Enable SDK Debug Logging**: Check if the OpenAI Agents SDK has verbose logging that shows tool discovery and usage.

2. **Verify MCP Server Tool Discovery**: Add logging after `mcp_server.connect()` to confirm tools are discovered:
   ```python
   for tool in mcp_server._tools:
       log.info(f"Discovered tool: {tool.name}")
   ```

3. **Check SDK Tool Exposure**: Verify if the SDK is exposing MCP tools to the LLM by inspecting the messages sent to OpenAI API.

4. **Test Direct Agent Execution**: Try running `regulation-agent` directly (not via handoff) to see if its MCP tools work in isolation.

5. **Review SDK Source/Docs**: Check the OpenAI Agents SDK documentation or source code for how `mcp_servers` are used during execution and handoffs.

## Potential Fix Approaches

### Option 1: Explicit Tool Discovery (Recommended)
Similar to LangGraph, explicitly fetch tools from MCP servers and pass them to agents:
```python
# In agent_runner.py
async def register_agent(self, config: AgentConfig) -> Agent:
    # Fetch tools explicitly
    agent_tools = []
    for mcp_server in agent_mcp_servers:
        tools = await mcp_server.get_tools()  # If SDK supports this
        agent_tools.extend(tools)

    agent = Agent(
        name=config["name"],
        instructions=config["instructions"],
        tools=agent_tools,  # Pass tools explicitly
    )
```

### Option 2: Re-discover on Handoff
Force tool re-discovery when a handoff occurs:
```python
# In _handle_handoff_event
async def _handle_handoff_event(self, state, tool_callback):
    # ... existing code ...

    # Force re-connect MCP servers for target agent
    target_agent = self.agent_registry.get_agent(state.current_agent_id)
    for mcp_server in target_agent.mcp_servers:
        await mcp_server.connect()  # Re-discover tools
```

### Option 3: Use SDK Native Handoff Configuration
Check if the SDK has a specific way to configure tool inheritance during handoffs.

## Open Questions

1. Does the OpenAI Agents SDK documentation specify how MCP tools should be discovered and used during handoffs?

2. Is there a way to force tool re-discovery in the SDK after a handoff?

3. Should we migrate server-openai to use explicit tool management like server-langgraph for consistency?

4. Are there SDK version-specific issues that might affect MCP tool handling?
