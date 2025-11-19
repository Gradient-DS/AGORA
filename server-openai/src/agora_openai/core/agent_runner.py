from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
import logging
from agents import Agent, Runner, SQLiteSession
from agents.mcp import MCPServerStreamableHttp
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import RunItemStreamEvent
from openai.types.responses import ResponseTextDeltaEvent
from agora_openai.core.agent_definitions import AgentConfig
from agora_openai.adapters.mcp_tools import MCPToolRegistry

log = logging.getLogger(__name__)


@dataclass
class StreamState:
    """State tracking for streaming sessions."""

    full_response: list[str] = field(default_factory=list)
    tool_calls_info: dict[str, str] = field(default_factory=dict)
    tool_call_id_mapping: dict[str, str] = field(default_factory=dict)
    current_agent_id: str = "general-agent"
    pending_handoff_target: str | None = None


# Mapping of agent IDs to MCP server names they should have access to
AGENT_MCP_MAPPING = {
    "general-agent": [],  # No MCP tools needed
    "regulation-agent": ["regulation"],  # Only regulation MCP server
    "reporting-agent": ["reporting"],  # Only reporting MCP server
    "history-agent": ["history"],  # Only history MCP server
}


class AgentRegistry:
    """Registry for Agent SDK agents with handoff support."""

    def __init__(self, mcp_registry: MCPToolRegistry):
        self.mcp_registry = mcp_registry
        self.agents: dict[str, Agent] = {}
        self.agent_configs: dict[str, AgentConfig] = {}

    def register_agent(self, config: AgentConfig) -> Agent:
        """Create and register an Agent SDK agent from config."""
        agent_id = config["id"]

        # Get only the MCP servers this agent should have access to
        agent_mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])
        agent_mcp_servers: list[MCPServerStreamableHttp] = []

        # mcp_registry.mcp_servers is a list, so we need to filter by name
        for mcp_server in self.mcp_registry.mcp_servers:
            if mcp_server.name in agent_mcp_server_names:
                agent_mcp_servers.append(mcp_server)

        # Agent SDK doesn't support temperature parameter directly
        # Temperature is set at the Runner.run level or via model string
        agent = Agent(
            name=config["name"],
            instructions=config["instructions"],
            model=config["model"],
            mcp_servers=agent_mcp_servers,
        )

        self.agents[agent_id] = agent
        self.agent_configs[agent_id] = config

        log.info(
            f"Registered agent: {agent_id} with {len(agent_mcp_servers)} MCP servers: {agent_mcp_server_names}"
        )

        return agent

    def configure_handoffs(self) -> None:
        """Configure handoffs between agents after all are registered."""
        for agent_id, config in self.agent_configs.items():
            agent = self.agents[agent_id]
            handoff_ids = config.get("handoffs", [])

            handoff_agents = []
            for handoff_id in handoff_ids:
                if handoff_id in self.agents:
                    handoff_agents.append(self.agents[handoff_id])
                else:
                    log.warning(
                        f"Handoff target '{handoff_id}' not found for agent '{agent_id}'"
                    )

            agent.handoffs = handoff_agents
            log.info(f"Configured {len(handoff_agents)} handoffs for agent: {agent_id}")

    def get_agent(self, agent_id: str) -> Agent | None:
        """Get agent by ID."""
        return self.agents.get(agent_id)

    def get_entry_agent(self) -> Agent:
        """Get the entry point agent (general-agent)."""
        return self.agents["general-agent"]


class AgentRunner:
    """Wrapper for Agent SDK Runner with session management and streaming."""

    def __init__(
        self, agent_registry: AgentRegistry, sessions_db_path: str = "sessions.db"
    ):
        self.agent_registry = agent_registry
        self.sessions_db_path = sessions_db_path
        self.sessions: dict[str, SQLiteSession] = {}

    def get_or_create_session(self, session_id: str) -> SQLiteSession:
        """Get or create a SQLite session for conversation history."""
        if session_id not in self.sessions:
            self.sessions[session_id] = SQLiteSession(
                session_id=session_id,
                db_path=self.sessions_db_path,
            )
            log.info(f"Created new session: {session_id}")
        return self.sessions[session_id]

    async def run_agent(
        self,
        message: str,
        session_id: str,
        stream_callback: Callable[[str, str | None], Awaitable[None]] | None = None,
        tool_callback: (
            Callable[[str, str, dict[str, Any], str, str | None], Awaitable[Any]] | None
        ) = None,
    ) -> tuple[str, str]:
        """Run agent with message and return (response, active_agent_id).

        Args:
            message: User message
            session_id: Session identifier for conversation history
            stream_callback: Optional callback(chunk, agent_id) for streaming response chunks
            tool_callback: Optional callback(tool_call_id, tool_name, parameters, status, agent_id) for tool execution notifications

        Returns:
            Tuple of (final_response, active_agent_id)
        """
        session = self.get_or_create_session(session_id)
        entry_agent = self.agent_registry.get_entry_agent()

        if stream_callback:
            return await self._run_streamed_session(
                session, entry_agent, message, stream_callback, tool_callback
            )
        else:
            return await self._run_blocking_session(session, entry_agent, message)

    async def _run_blocking_session(
        self, session: SQLiteSession, entry_agent: Agent, message: str
    ) -> tuple[str, str]:
        """Run agent in blocking mode."""
        log.info("Running agent without streaming")
        result = await Runner.run(
            entry_agent,
            input=message,
            session=session,
        )
        final_output = result.final_output or ""
        log.info(f"Agent run completed. Output: {len(final_output)} characters")

        # Try to determine which agent was active at the end
        active_agent_id = self._get_agent_id_from_agent(entry_agent)
        log.info(f"Agent run completed. Active agent: {active_agent_id}")
        return final_output, active_agent_id

    async def _run_streamed_session(
        self,
        session: SQLiteSession,
        entry_agent: Agent,
        message: str,
        stream_callback: Callable[[str, str | None], Awaitable[None]],
        tool_callback: Callable | None,
    ) -> tuple[str, str]:
        """Run agent in streaming mode."""
        log.info("Running agent with streaming enabled")
        result = Runner.run_streamed(
            entry_agent,
            input=message,
            session=session,
        )

        state = StreamState(current_agent_id=self._get_agent_id_from_agent(entry_agent))

        async for event in result.stream_events():
            await self._process_stream_event(
                event, state, stream_callback, tool_callback
            )

        final_output = "".join(state.full_response)
        log.info(f"Streaming completed. Total output: {len(final_output)} characters")
        log.info(f"Agent run completed. Active agent: {state.current_agent_id}")
        return final_output, state.current_agent_id

    async def _process_stream_event(
        self,
        event: Any,
        state: StreamState,
        stream_callback: Callable,
        tool_callback: Callable | None,
    ) -> None:
        """Process individual stream events."""
        event_type = event.type
        log.debug(f"Stream event: {event_type}")

        if event_type == "raw_response_event":
            if isinstance(event.data, ResponseTextDeltaEvent):
                delta = event.data.delta
                if delta:
                    state.full_response.append(delta)
                    await stream_callback(delta, state.current_agent_id)

        elif event_type == "run_item_stream_event" and isinstance(
            event, RunItemStreamEvent
        ):
            await self._process_run_item_event(event, state, tool_callback)

    async def _process_run_item_event(
        self,
        event: RunItemStreamEvent,
        state: StreamState,
        tool_callback: Callable | None,
    ) -> None:
        """Process run item events (tool calls, outputs, handoffs)."""
        if event.name == "tool_called" and isinstance(event.item, ToolCallItem):
            await self._handle_tool_call(event.item, state, tool_callback)

        elif event.name == "tool_output" and isinstance(event.item, ToolCallOutputItem):
            await self._handle_tool_output(event.item, state, tool_callback)

        elif event.name == "handoff_occured":
            await self._handle_handoff_event(state, tool_callback)

    async def _handle_tool_call(
        self,
        item: ToolCallItem,
        state: StreamState,
        tool_callback: Callable | None,
    ) -> None:
        """Handle tool call initiation."""
        if not tool_callback:
            return

        raw_item = item.raw_item
        # Handle both dict and object forms of raw_item
        if isinstance(raw_item, dict):
            tool_call_id = raw_item.get("id")
            tool_name = raw_item.get("name", "unknown")
            tool_args_str = raw_item.get("arguments", "{}")
            output_call_id = raw_item.get("call_id")
        else:
            tool_call_id = getattr(raw_item, "id", None)
            tool_name = getattr(raw_item, "name", "unknown")
            tool_args_str = getattr(raw_item, "arguments", "{}")
            output_call_id = getattr(raw_item, "call_id", None)

        log.info(
            f"Tool call raw_item: id={tool_call_id}, call_id={output_call_id}, name={tool_name}"
        )

        self._detect_handoff_target(tool_name, state)

        if tool_call_id:
            state.tool_calls_info[tool_call_id] = tool_name

            if output_call_id and output_call_id != tool_call_id:
                state.tool_call_id_mapping[output_call_id] = tool_call_id
                state.tool_calls_info[output_call_id] = tool_name
                log.info(
                    f"Mapped output call_id {output_call_id} -> tool_call_id {tool_call_id}"
                )

            try:
                parameters = (
                    json.loads(tool_args_str) if isinstance(tool_args_str, str) else {}
                )
            except:
                parameters = {}

            log.info(
                f"🔧 Tool call started: {tool_name} (ID: {tool_call_id}) by agent {state.current_agent_id}"
            )
            await tool_callback(
                tool_call_id,
                tool_name,
                parameters,
                "started",
                state.current_agent_id,
            )

    def _detect_handoff_target(self, tool_name: str, state: StreamState) -> None:
        """Detect if a tool call implies a handoff and update state."""
        if not tool_name or not (
            "transfer" in tool_name.lower() or "handoff" in tool_name.lower()
        ):
            return

        tool_name_lower = tool_name.lower()
        if "company" in tool_name_lower or "history" in tool_name_lower:
            state.pending_handoff_target = "history-agent"
            log.info(f"🔄 Detected transfer to history-agent from tool: {tool_name}")
        elif "regulation" in tool_name_lower:
            state.pending_handoff_target = "regulation-agent"
            log.info(f"🔄 Detected transfer to regulation-agent from tool: {tool_name}")
        elif "report" in tool_name_lower or "hap" in tool_name_lower:
            state.pending_handoff_target = "reporting-agent"
            log.info(f"🔄 Detected transfer to reporting-agent from tool: {tool_name}")

    async def _handle_tool_output(
        self,
        item: ToolCallOutputItem,
        state: StreamState,
        tool_callback: Callable | None,
    ) -> None:
        """Handle tool output (completion)."""
        if not tool_callback:
            return

        raw_item = item.raw_item
        if isinstance(raw_item, dict):
            output_call_id = raw_item.get("call_id")
        else:
            output_call_id = getattr(raw_item, "call_id", None)

        log.info(f"Tool output raw_item: call_id={output_call_id}")

        if output_call_id:
            original_tool_call_id = state.tool_call_id_mapping.get(
                output_call_id, output_call_id
            )
            tool_name = state.tool_calls_info.get(
                output_call_id,
                state.tool_calls_info.get(original_tool_call_id, "unknown"),
            )

            log.info(
                f"✅ Tool call completed: {tool_name} (output_call_id: {output_call_id}, original_id: {original_tool_call_id})"
            )

            await tool_callback(
                original_tool_call_id,
                tool_name,
                {},
                "completed",
                state.current_agent_id,
            )

    async def _handle_handoff_event(
        self, state: StreamState, tool_callback: Callable | None
    ) -> None:
        """Handle handoff occurrence."""
        log.info(f"🔄 Handoff occurred event detected")

        if state.pending_handoff_target:
            state.current_agent_id = state.pending_handoff_target
            log.info(
                f"✅ Agent handoff completed. Now active: {state.current_agent_id}"
            )
            state.pending_handoff_target = None

        if tool_callback:
            await self._complete_transfer_tool_call(state, tool_callback)

    async def _complete_transfer_tool_call(
        self, state: StreamState, tool_callback: Callable
    ) -> None:
        """Mark transfer tool call as completed."""
        log.info(f"Marking transfer tool call as completed")

        transfer_tool_ids = [
            tool_id
            for tool_id, name in state.tool_calls_info.items()
            if "transfer" in name.lower() or "handoff" in name.lower()
        ]

        if transfer_tool_ids:
            transfer_tool_id = transfer_tool_ids[0]
            tool_name = state.tool_calls_info.get(transfer_tool_id, "transfer")
            old_agent_id = "general-agent"

            log.info(
                f"✅ Handoff transfer tool completed: {tool_name} (ID: {transfer_tool_id})"
            )
            await tool_callback(
                transfer_tool_id,
                tool_name,
                {},
                "completed",
                old_agent_id,
            )

            state.tool_calls_info.pop(transfer_tool_id, None)

    def _get_agent_id_from_agent(self, agent: Agent) -> str:
        """Get agent ID from Agent object by name matching."""
        for agent_id, registered_agent in self.agent_registry.agents.items():
            if registered_agent.name == agent.name:
                return agent_id
        return "general-agent"

    async def get_conversation_history(
        self, session_id: str, include_tool_calls: bool = False
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier
            include_tool_calls: If True, includes tool calls and their results in the history

        Returns:
            List of conversation items with role and content
        """
        if session_id not in self.sessions:
            return []

        session = self.sessions[session_id]
        items = await session.get_items()

        history = []
        for item in items:
            role = item.get("role")

            if role in ["user", "assistant"]:
                content = ""
                if isinstance(item.get("content"), list):
                    for content_item in item["content"]:
                        if isinstance(content_item, dict):
                            if "text" in content_item:
                                content += content_item["text"]
                            elif "input_text" in content_item:
                                content += content_item["input_text"]
                            elif "output_text" in content_item:
                                content += content_item["output_text"]
                elif isinstance(item.get("content"), str):
                    content = item["content"]

                if content:
                    history.append(
                        {
                            "role": role,
                            "content": content,
                        }
                    )

            elif include_tool_calls and role == "tool":
                tool_name = item.get("name", "unknown_tool")
                tool_call_id = item.get("tool_call_id", "unknown")

                content = ""
                if isinstance(item.get("content"), list):
                    for content_item in item["content"]:
                        if isinstance(content_item, dict):
                            if "text" in content_item:
                                content += content_item["text"]
                            elif "output_text" in content_item:
                                content += content_item["output_text"]
                elif isinstance(item.get("content"), str):
                    content = item["content"]

                history.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "content": content,
                    }
                )

        return history
