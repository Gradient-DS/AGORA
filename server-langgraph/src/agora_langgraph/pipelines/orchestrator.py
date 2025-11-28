"""Orchestrator using LangGraph with astream_events for HAI Protocol streaming."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph.state import CompiledStateGraph

from agora_langgraph.common.hai_types import UserMessage, AssistantMessage
from agora_langgraph.common.schemas import ToolCall
from agora_langgraph.core.approval_logic import requires_human_approval
from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.pipelines.moderator import ModerationPipeline

log = logging.getLogger(__name__)


class Orchestrator:
    """Orchestration using LangGraph with streaming and approval flow."""

    def __init__(
        self,
        graph: CompiledStateGraph,
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
    ):
        """Initialize orchestrator.

        Args:
            graph: Compiled LangGraph StateGraph
            moderator: Content moderation pipeline
            audit_logger: Audit logging instance
        """
        self.graph = graph
        self.moderator = moderator
        self.audit = audit_logger
        self.pending_approvals: dict[str, asyncio.Future[bool]] = {}

    async def _handle_tool_approval_flow(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        session_id: str,
        protocol_handler: Any,
    ) -> None:
        """Handle tool approval flow for high-risk operations.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            session_id: Session identifier
            protocol_handler: HAI Protocol handler
        """
        tool_call_obj = ToolCall(tool_name=tool_name, parameters=parameters)
        requires_approval, reason, risk_level = requires_human_approval(
            [tool_call_obj], {}
        )

        if requires_approval:
            approval_id = str(uuid.uuid4())
            future: asyncio.Future[bool] = asyncio.Future()
            self.pending_approvals[approval_id] = future

            log.info(f"Requesting approval for {tool_name} (id: {approval_id})")
            await self.audit.log_approval_request(
                session_id, tool_name, risk_level, approval_id
            )

            await protocol_handler.send_tool_approval_request(
                tool_name=tool_name,
                tool_description=f"Tool call: {tool_name}",
                parameters=parameters,
                reasoning=reason or "Operation requires human approval",
                risk_level=risk_level,
                session_id=session_id,
                approval_id=approval_id,
            )

            try:
                approved = await future
                await self.audit.log_approval_response(
                    session_id, approval_id, approved
                )
                if not approved:
                    log.info(f"Tool {tool_name} rejected by user")
                    raise Exception("Tool execution rejected by user")
                log.info(f"Tool {tool_name} approved by user")
            finally:
                self.pending_approvals.pop(approval_id, None)

    async def process_message(
        self,
        message: UserMessage,
        session_id: str,
        protocol_handler: Any | None = None,
    ) -> AssistantMessage:
        """Process a user message through the LangGraph pipeline.

        Args:
            message: User message
            session_id: Session identifier
            protocol_handler: Optional HAI Protocol handler for streaming

        Returns:
            Assistant response message
        """
        is_valid, error = await self.moderator.validate_input(message.content)
        if not is_valid:
            log.warning("Input validation failed: %s", error)
            return AssistantMessage(
                content=f"Input validation failed: {error}",
                session_id=session_id,
            )

        await self.audit.log_message(
            session_id=session_id,
            role="user",
            content=message.content,
            metadata=message.metadata,
        )

        try:
            if protocol_handler:
                await protocol_handler.send_status(
                    "routing", "Analyzing request...", session_id
                )

            message_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": session_id}}

            input_state = {
                "messages": [HumanMessage(content=message.content)],
                "session_id": session_id,
                "current_agent": "general-agent",
                "pending_approval": None,
                "metadata": message.metadata or {},
            }

            if protocol_handler:
                response_content, active_agent_id = await self._stream_response(
                    input_state,
                    config,
                    session_id,
                    message_id,
                    protocol_handler,
                )
            else:
                response_content, active_agent_id = await self._run_blocking(
                    input_state, config
                )

            is_valid, error = await self.moderator.validate_output(response_content)
            if not is_valid:
                log.warning("Output validation failed: %s", error)
                response_content = "I apologize, but I cannot provide that response."

            assistant_message = AssistantMessage(
                content=response_content,
                session_id=session_id,
                agent_id=active_agent_id,
            )

            await self.audit.log_message(
                session_id=session_id,
                role="assistant",
                content=response_content,
                metadata={"agent_id": active_agent_id},
            )

            if protocol_handler and protocol_handler.is_connected:
                await protocol_handler.send_status(
                    "completed", "Response ready", session_id
                )

            return assistant_message

        except Exception as e:
            if str(e) == "Tool execution rejected by user":
                log.info("Action cancelled by user")
                if protocol_handler and protocol_handler.is_connected:
                    await protocol_handler.send_status(
                        "completed", "Action cancelled", session_id
                    )
                return AssistantMessage(
                    content="I have cancelled the action as requested.",
                    session_id=session_id,
                )

            log.error("Error processing message: %s", e, exc_info=True)
            return AssistantMessage(
                content="I apologize, but I encountered an error processing your request.",
                session_id=session_id,
            )

    async def _run_blocking(
        self,
        input_state: dict[str, Any],
        config: dict[str, Any],
    ) -> tuple[str, str]:
        """Run graph in blocking mode without streaming.

        Args:
            input_state: Initial graph state
            config: LangGraph config

        Returns:
            Tuple of (response_content, agent_id)
        """
        result = await self.graph.ainvoke(input_state, config=config)

        messages = result.get("messages", [])
        response_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                response_content = str(msg.content)
                break

        agent_id = result.get("current_agent", "general-agent")
        return response_content, agent_id

    async def _stream_response(
        self,
        input_state: dict[str, Any],
        config: dict[str, Any],
        session_id: str,
        message_id: str,
        protocol_handler: Any,
    ) -> tuple[str, str]:
        """Stream graph response using astream_events.

        Args:
            input_state: Initial graph state
            config: LangGraph config
            session_id: Session identifier
            message_id: Message identifier for streaming
            protocol_handler: HAI Protocol handler

        Returns:
            Tuple of (full_response, agent_id)
        """
        full_response: list[str] = []
        current_agent_id = "general-agent"
        active_tool_calls: dict[str, str] = {}

        async for event in self.graph.astream_events(
            input_state, config=config, version="v2"
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content = str(chunk.content)
                    full_response.append(content)

                    if protocol_handler.is_connected:
                        await protocol_handler.send_assistant_message_chunk(
                            content=content,
                            session_id=session_id,
                            agent_id=current_agent_id,
                            message_id=message_id,
                            is_final=False,
                        )

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                run_id = event.get("run_id", str(uuid.uuid4()))
                tool_input = event.get("data", {}).get("input", {})

                active_tool_calls[run_id] = tool_name
                log.info(f"Tool started: {tool_name} (run_id: {run_id})")

                await self._handle_tool_approval_flow(
                    tool_name, tool_input, session_id, protocol_handler
                )

                if protocol_handler.is_connected:
                    await protocol_handler.send_tool_call(
                        tool_call_id=run_id,
                        tool_name=tool_name,
                        parameters=tool_input,
                        session_id=session_id,
                        status="started",
                        agent_id=current_agent_id,
                    )

            elif kind == "on_tool_end":
                run_id = event.get("run_id", "")
                tool_name = active_tool_calls.pop(run_id, "unknown")
                output = event.get("data", {}).get("output", "")

                log.info(f"Tool completed: {tool_name} (run_id: {run_id})")

                if protocol_handler.is_connected:
                    await protocol_handler.send_tool_call(
                        tool_call_id=run_id,
                        tool_name=tool_name,
                        parameters={},
                        session_id=session_id,
                        status="completed",
                        result=str(output)[:500] if output else None,
                        agent_id=current_agent_id,
                    )

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "current_agent" in output:
                    new_agent = output["current_agent"]
                    if new_agent != current_agent_id:
                        log.info(f"Agent changed: {current_agent_id} → {new_agent}")
                        await self.audit.log_handoff(
                            session_id, current_agent_id, new_agent
                        )
                        current_agent_id = new_agent

        if protocol_handler.is_connected:
            await protocol_handler.send_assistant_message_chunk(
                content="",
                session_id=session_id,
                agent_id=current_agent_id,
                message_id=message_id,
                is_final=True,
            )

        return "".join(full_response), current_agent_id

    async def get_conversation_history(
        self, session_id: str, include_tool_calls: bool = False
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier
            include_tool_calls: Whether to include tool calls

        Returns:
            List of conversation messages
        """
        config = {"configurable": {"thread_id": session_id}}

        try:
            state = await self.graph.aget_state(config)
            if not state or not state.values:
                return []

            messages = state.values.get("messages", [])
            history = []

            for msg in messages:
                if hasattr(msg, "type"):
                    if msg.type == "human":
                        history.append(
                            {
                                "role": "user",
                                "content": str(msg.content),
                            }
                        )
                    elif msg.type == "ai":
                        if msg.content:
                            history.append(
                                {
                                    "role": "assistant",
                                    "content": str(msg.content),
                                }
                            )
                        if include_tool_calls and hasattr(msg, "tool_calls"):
                            for tc in msg.tool_calls or []:
                                history.append(
                                    {
                                        "role": "tool_call",
                                        "tool_name": tc.get("name", "unknown"),
                                        "content": str(tc.get("args", {})),
                                    }
                                )
                    elif include_tool_calls and msg.type == "tool":
                        history.append(
                            {
                                "role": "tool",
                                "tool_name": getattr(msg, "name", "unknown"),
                                "content": str(msg.content),
                            }
                        )

            return history
        except Exception as e:
            log.error(f"Error getting conversation history: {e}")
            return []
