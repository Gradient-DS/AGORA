from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
import logging
from agents import Agent, Runner, SQLiteSession
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import RunItemStreamEvent
from openai.types.responses import ResponseTextDeltaEvent
from agora_openai.core.agent_definitions import AgentConfig
from agora_openai.adapters.mcp_tools import MCPToolRegistry
from agora_openai.config import get_settings

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

    def __init__(
        self,
        mcp_registry: MCPToolRegistry,
        tools_by_server: dict[str, list] | None = None,
    ):
        self.mcp_registry = mcp_registry
        self.tools_by_server = tools_by_server or {}
        self.agents: dict[str, Agent] = {}
        self.agent_configs: dict[str, AgentConfig] = {}

    def register_agent(self, config: AgentConfig) -> Agent:
        """Create and register an Agent SDK agent from config."""
        agent_id = config["id"]

        # Get the MCP server names this agent should have access to
        agent_mcp_server_names = AGENT_MCP_MAPPING.get(agent_id, [])

        # Collect FunctionTool wrappers for this agent's MCP servers
        # Using FunctionTools instead of mcp_servers for reliable tool calling
        # after handoffs (workaround for SDK issue #617)
        agent_tools: list = []

        for server_name in agent_mcp_server_names:
            if server_name in self.tools_by_server:
                agent_tools.extend(self.tools_by_server[server_name])

        # Agent SDK doesn't support temperature parameter directly
        # Temperature is set at the Runner.run level or via model string
        # Use model from config if specified, otherwise fall back to settings
        settings = get_settings()
        model = config.get("model") or settings.openai_model

        # Pass FunctionTool wrappers explicitly via tools= parameter
        # NOT using mcp_servers= because SDK's MCP integration is unreliable after handoffs
        agent = Agent(
            name=config["name"],
            instructions=config["instructions"],
            model=model,
            tools=agent_tools,
        )

        self.agents[agent_id] = agent
        self.agent_configs[agent_id] = config

        log.info(
            f"📝 REGISTERED AGENT: {agent_id} with {len(agent_tools)} FunctionTools"
        )
        if agent_tools:
            tool_names = [t.name for t in agent_tools[:5]]
            suffix = "..." if len(agent_tools) > 5 else ""
            log.info(f"    └─ Tools: {tool_names}{suffix}")
            # Log which MCP servers these tools come from
            for server_name in agent_mcp_server_names:
                server_tool_count = len(self.tools_by_server.get(server_name, []))
                log.info(f"    └─ From MCP '{server_name}': {server_tool_count} tools")
        else:
            log.info("    └─ (no tools)")

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
            log.info(f"🆕 Created NEW session: {session_id}")
        else:
            log.info(f"♻️ REUSING existing session: {session_id}")
        return self.sessions[session_id]

    async def _debug_log_session_state(self, session: SQLiteSession, session_id: str) -> None:
        """Debug helper: Log current session state before running agent."""
        try:
            items = await session.get_items()
            log.info(f"📋 SESSION DEBUG [{session_id}]: {len(items)} items in history")

            # Summarize the history
            user_msgs = 0
            assistant_msgs = 0
            tool_calls = 0
            tool_outputs = 0

            for item in items:
                item_type = item.get("type")
                role = item.get("role")
                if role == "user":
                    user_msgs += 1
                elif role == "assistant":
                    assistant_msgs += 1
                elif item_type == "function_call":
                    tool_calls += 1
                    tool_name = item.get("name", "unknown")
                    log.debug(f"  📦 Tool call: {tool_name}")
                elif item_type == "function_call_output":
                    tool_outputs += 1

            log.info(
                f"📊 SESSION SUMMARY [{session_id}]: "
                f"user={user_msgs}, assistant={assistant_msgs}, "
                f"tool_calls={tool_calls}, tool_outputs={tool_outputs}"
            )

            # Log the last few items to see recent context
            if items:
                log.info(f"📜 LAST 3 ITEMS [{session_id}]:")
                for item in items[-3:]:
                    item_type = item.get("type", item.get("role", "unknown"))
                    content_preview = ""
                    if item.get("content"):
                        content_raw = item.get("content")
                        if isinstance(content_raw, str):
                            content_preview = content_raw[:100]
                        elif isinstance(content_raw, list) and content_raw:
                            first = content_raw[0]
                            if isinstance(first, dict):
                                content_preview = first.get("text", "")[:100]
                    elif item.get("name"):
                        content_preview = f"tool: {item.get('name')}"
                    log.info(f"    [{item_type}] {content_preview}...")
        except Exception as e:
            log.warning(f"Failed to debug log session state: {e}")

    async def run_agent(
        self,
        message: str,
        session_id: str,
        stream_callback: Callable[[str, str | None], Awaitable[None]] | None = None,
        tool_callback: (
            Callable[
                [str, str, dict[str, Any], str, str | None, str | None], Awaitable[Any]
            ]
            | None
        ) = None,
    ) -> tuple[str, str]:
        """Run agent with message and return (response, active_agent_id).

        Args:
            message: User message
            session_id: Session identifier for conversation history
            stream_callback: Optional callback(chunk, agent_id) for streaming response chunks
            tool_callback: Optional callback(tool_call_id, tool_name, parameters, status, agent_id, result) for tool execution notifications

        Returns:
            Tuple of (final_response, active_agent_id)
        """
        session = self.get_or_create_session(session_id)
        entry_agent = self.agent_registry.get_entry_agent()

        # Debug: Log session state BEFORE running
        log.info(f"🚀 STARTING AGENT RUN for session: {session_id}")
        log.info(f"📥 User message: {message[:100]}...")
        log.info(f"🎯 Entry agent: {entry_agent.name} (always starts from general-agent)")
        await self._debug_log_session_state(session, session_id)

        # Log available MCP servers for entry agent
        if hasattr(entry_agent, "mcp_servers") and entry_agent.mcp_servers:
            mcp_names = [s.name for s in entry_agent.mcp_servers]
            log.info(f"🔧 Entry agent MCP servers: {mcp_names}")
        else:
            log.info("🔧 Entry agent has NO MCP servers (expected for general-agent)")

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

        # End-of-run summary
        log.info("=" * 60)
        log.info(f"🏁 AGENT RUN COMPLETED")
        log.info(f"   Final agent: {state.current_agent_id}")
        log.info(f"   Output length: {len(final_output)} characters")
        log.info(f"   Total tool calls: {len(state.tool_calls_info)}")
        if state.tool_calls_info:
            log.info(f"   Tools called: {list(state.tool_calls_info.values())}")
        log.info("=" * 60)

        # Debug: Log session state AFTER running
        await self._debug_log_session_state(session, f"{session.session_id}-AFTER")

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

            # Categorize tool type for debugging
            is_handoff = "transfer" in tool_name.lower() or "handoff" in tool_name.lower()
            is_mcp_tool = not is_handoff and any(
                prefix in tool_name.lower()
                for prefix in ["search_", "get_", "check_", "lookup_", "generate_", "extract_", "verify_", "analyze_"]
            )

            if is_handoff:
                log.info(f"🔄 HANDOFF TOOL CALL: {tool_name} (current: {state.current_agent_id})")
            elif is_mcp_tool:
                log.info(
                    f"🌐 MCP TOOL CALL: {tool_name} by {state.current_agent_id} "
                    f"(params: {json.dumps(parameters)[:200]}...)"
                )
            else:
                log.info(
                    f"🔧 Tool call started: {tool_name} (ID: {tool_call_id}) by agent {state.current_agent_id}"
                )
            await tool_callback(
                tool_call_id,
                tool_name,
                parameters,
                "started",
                state.current_agent_id,
                None,  # No result yet
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
            output_content = raw_item.get("output", "")
        else:
            output_call_id = getattr(raw_item, "call_id", None)
            output_content = getattr(raw_item, "output", "")

        # Try to get output from the item itself if not in raw_item
        if not output_content and hasattr(item, "output"):
            output_content = str(item.output) if item.output else ""

        log.info(
            f"Tool output raw_item: call_id={output_call_id}, output_len={len(str(output_content)) if output_content else 0}"
        )

        if output_call_id:
            original_tool_call_id = state.tool_call_id_mapping.get(
                output_call_id, output_call_id
            )
            tool_name = state.tool_calls_info.get(
                output_call_id,
                state.tool_calls_info.get(original_tool_call_id, "unknown"),
            )

            # Truncate result for logging but keep full for callback
            result_str = str(output_content)[:500] if output_content else ""

            log.info(
                f"✅ Tool call completed: {tool_name} (output_call_id: {output_call_id}, original_id: {original_tool_call_id}, result_preview: {result_str[:100]}...)"
            )

            await tool_callback(
                original_tool_call_id,
                tool_name,
                {},
                "completed",
                state.current_agent_id,
                result_str,  # Pass the result content
            )

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

            # Log FunctionTools available to the new agent
            new_agent = self.agent_registry.get_agent(state.current_agent_id)
            if new_agent:
                # Log FunctionTools (these are MCP tool wrappers)
                if hasattr(new_agent, "tools") and new_agent.tools:
                    tool_names = [t.name for t in new_agent.tools[:5]]
                    suffix = "..." if len(new_agent.tools) > 5 else ""
                    log.info(
                        f"🔧 NEW AGENT TOOLS [{state.current_agent_id}]: "
                        f"{len(new_agent.tools)} FunctionTools ({tool_names}{suffix})"
                    )
                else:
                    log.info(
                        f"🔧 NEW AGENT [{state.current_agent_id}] has NO tools"
                    )

            state.pending_handoff_target = None
        else:
            log.warning(
                f"⚠️ HANDOFF EVENT but no pending target! "
                f"current_agent={state.current_agent_id}"
            )

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
                f"Transferred to {state.current_agent_id}",  # Handoff result
            )

            state.tool_calls_info.pop(transfer_tool_id, None)

    def _get_agent_id_from_agent(self, agent: Agent) -> str:
        """Get agent ID from Agent object by name matching."""
        for agent_id, registered_agent in self.agent_registry.agents.items():
            if registered_agent.name == agent.name:
                return agent_id
        return "general-agent"

    async def get_conversation_history(
        self,
        session_id: str,
        include_tool_calls: bool = False,
        stored_tool_calls: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier
            include_tool_calls: If True, includes tool calls and their results in the history
            stored_tool_calls: Full tool call data from session_metadata storage

        Returns:
            List of conversation items with role, content, and agent_id
        """
        if session_id not in self.sessions:
            self.get_or_create_session(session_id)

        session = self.sessions[session_id]
        items = await session.get_items()
        stored_tool_calls = stored_tool_calls or []

        # Build lookup for tool calls by ID
        tool_calls_by_id = {tc["tool_call_id"]: tc for tc in stored_tool_calls}

        # Track which tool calls we've added (to avoid duplicates)
        added_tool_calls: set[str] = set()

        history = []
        current_agent_id = "general-agent"

        # Build mapping from call_id to tool_call_id and tool_name during first pass
        # This is needed because function_call has both 'id' (fc_...) and 'call_id' (call_...)
        # but function_call_output only has 'call_id'
        call_id_to_info: dict[str, dict[str, str]] = {}
        for item in items:
            if item.get("type") == "function_call":
                call_id = item.get("call_id", "")
                tool_call_id = item.get("id", call_id)
                tool_name = item.get("name", "unknown_tool")
                if call_id:
                    call_id_to_info[call_id] = {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                    }

        for item in items:
            role = item.get("role")
            item_type = item.get("type")

            if role == "user":
                content = self._extract_content(item)
                if content:
                    history.append({"role": "user", "content": content})

            elif role == "assistant":
                content = self._extract_content(item)
                if content:
                    history.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "agent_id": current_agent_id,
                        }
                    )

            elif item_type == "function_call" and include_tool_calls:
                # OpenAI SDK stores tool calls with type="function_call"
                # call_id is used to correlate with function_call_output
                call_id = item.get("call_id", "unknown")
                tool_call_id = item.get("id", call_id)  # 'id' field has the full ID
                tool_name = item.get("name", "unknown_tool")
                arguments = item.get("arguments", "{}")

                # Look up stored tool call data (keyed by the full ID)
                stored_tc = tool_calls_by_id.get(tool_call_id)

                if tool_call_id not in added_tool_calls:
                    # Update current agent from stored data
                    if stored_tc and stored_tc.get("agent_id"):
                        current_agent_id = stored_tc["agent_id"]

                    history.append(
                        {
                            "role": "tool_call",
                            "tool_call_id": tool_call_id,
                            "tool_name": (
                                stored_tc.get("tool_name", tool_name)
                                if stored_tc
                                else tool_name
                            ),
                            "content": (
                                stored_tc.get("parameters", arguments)
                                if stored_tc
                                else arguments
                            ),
                            "agent_id": (
                                stored_tc.get("agent_id", current_agent_id)
                                if stored_tc
                                else current_agent_id
                            ),
                        }
                    )
                    added_tool_calls.add(tool_call_id)

            elif item_type == "function_call_output" and include_tool_calls:
                # OpenAI SDK stores tool results with type="function_call_output"
                call_id = item.get("call_id", "unknown")
                output = item.get("output", "")

                # Look up the full tool_call_id and tool_name from our mapping
                call_info = call_id_to_info.get(call_id, {})
                tool_call_id = call_info.get("tool_call_id", call_id)
                tool_name = call_info.get("tool_name", "unknown_tool")

                # Also check stored data for additional info
                stored_tc = tool_calls_by_id.get(tool_call_id)
                if stored_tc:
                    tool_name = stored_tc.get("tool_name", tool_name)

                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "content": output,
                    }
                )

            elif role == "tool" and include_tool_calls:
                # Legacy format: Tool result with role="tool"
                tool_call_id = item.get("tool_call_id", "unknown")
                tool_name = item.get("name", "unknown_tool")
                result_content = self._extract_content(item)

                # Get stored tool call data if available
                stored_tc = tool_calls_by_id.get(tool_call_id)

                if stored_tc and tool_call_id not in added_tool_calls:
                    # Update current agent from stored data
                    if stored_tc.get("agent_id"):
                        current_agent_id = stored_tc["agent_id"]

                    # Add tool_call entry BEFORE the tool result
                    history.append(
                        {
                            "role": "tool_call",
                            "tool_call_id": tool_call_id,
                            "tool_name": stored_tc.get("tool_name", tool_name),
                            "content": stored_tc.get("parameters", "{}"),
                            "agent_id": stored_tc.get("agent_id", current_agent_id),
                        }
                    )
                    added_tool_calls.add(tool_call_id)

                # Add tool result
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "content": result_content,
                    }
                )

        return history

    def _extract_content(self, item: dict) -> str:
        """Extract text content from a session item.

        Args:
            item: Session item dict

        Returns:
            Extracted text content
        """
        content_raw = item.get("content")
        if isinstance(content_raw, str):
            return content_raw
        if isinstance(content_raw, list):
            parts = []
            for part in content_raw:
                if isinstance(part, dict):
                    parts.append(
                        part.get("text", "")
                        or part.get("input_text", "")
                        or part.get("output_text", "")
                    )
            return "".join(parts)
        return ""
