"""Orchestrator using LangGraph with astream_events for AG-UI Protocol streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph.state import CompiledStateGraph

from ag_ui.core import Message as AGUIMessage

from agora_langgraph.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)
from agora_langgraph.common.schemas import ToolCall
from agora_langgraph.core.approval_logic import requires_human_approval
from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.adapters.session_metadata import SessionMetadataManager
from agora_langgraph.pipelines.moderator import ModerationPipeline

log = logging.getLogger(__name__)


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Sanitize tool parameters by removing non-JSON-serializable values.

    LangGraph/LangChain events may include internal objects like AsyncCallbackManager
    that cannot be serialized to JSON. This function filters them out.
    """
    sanitized = {}
    for key, value in params.items():
        try:
            json.dumps(value)
            sanitized[key] = value
        except (TypeError, ValueError):
            pass
    return sanitized


class Orchestrator:
    """Orchestration using LangGraph with AG-UI Protocol streaming and approval flow."""

    def __init__(
        self,
        graph: CompiledStateGraph,
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
        session_metadata: SessionMetadataManager | None = None,
    ):
        """Initialize orchestrator."""
        self.graph = graph
        self.moderator = moderator
        self.audit = audit_logger
        self.session_metadata = session_metadata
        self.pending_approvals: dict[str, asyncio.Future[bool]] = {}

    async def _handle_tool_approval_flow(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        thread_id: str,
        protocol_handler: Any,
    ) -> None:
        """Handle tool approval flow for high-risk operations."""
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
                thread_id, tool_name, risk_level, approval_id
            )

            await protocol_handler.send_tool_approval_request(
                tool_name=tool_name,
                tool_description=f"Tool call: {tool_name}",
                parameters=parameters,
                reasoning=reason or "Operation requires human approval",
                risk_level=risk_level,
                approval_id=approval_id,
            )

            try:
                approved = await future
                await self.audit.log_approval_response(thread_id, approval_id, approved)
                if not approved:
                    log.info(f"Tool {tool_name} rejected by user")
                    raise Exception("Tool execution rejected by user")
                log.info(f"Tool {tool_name} approved by user")
            finally:
                self.pending_approvals.pop(approval_id, None)

    def handle_approval_response(self, response: ToolApprovalResponsePayload) -> bool:
        """Process an approval response from the client.

        Returns True if the approval was handled, False if no matching pending approval.
        """
        approval_id = response.approval_id
        if approval_id in self.pending_approvals:
            future = self.pending_approvals[approval_id]
            if not future.done():
                future.set_result(response.approved)
            return True
        log.warning(f"Received approval for unknown ID: {approval_id}")
        return False

    async def process_message(
        self,
        agent_input: RunAgentInput,
        protocol_handler: Any | None = None,
    ) -> AGUIMessage:
        """Process a user message through the LangGraph pipeline using AG-UI Protocol.

        Args:
            agent_input: AG-UI RunAgentInput containing messages and context
            protocol_handler: Optional AG-UI Protocol handler for streaming

        Returns:
            Assistant response message
        """
        thread_id = agent_input.thread_id
        run_id = agent_input.run_id or str(uuid.uuid4())

        # Extract user message from input
        user_content = ""
        for msg in agent_input.messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        # Get user_id from top-level field
        user_id = agent_input.user_id

        # Create or update session metadata
        if self.session_metadata:
            try:
                log.info(f"Creating/updating session metadata: session_id={thread_id}, user_id={user_id}")
                await self.session_metadata.create_or_update_metadata(
                    session_id=thread_id,
                    user_id=user_id,
                    first_message=user_content,
                )
                log.info(f"Session metadata created/updated successfully for {thread_id}")
            except Exception as e:
                log.warning(f"Failed to update session metadata: {e}")

        # Validate input
        is_valid, error = await self.moderator.validate_input(user_content)
        if not is_valid:
            log.warning("Input validation failed: %s", error)
            return self._create_response_message(
                f"Input validation failed: {error}", str(uuid.uuid4())
            )

        await self.audit.log_message(
            session_id=thread_id,
            role="user",
            content=user_content,
            metadata=agent_input.context or {},
        )

        try:
            if protocol_handler:
                # Emit RUN_STARTED
                await protocol_handler.send_run_started(thread_id, run_id)

                # Send initial state snapshot
                await protocol_handler.send_state_snapshot(
                    {
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "current_agent": "general-agent",
                        "status": "processing",
                    }
                )

                await protocol_handler.send_step_started("routing")

            message_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": thread_id}}

            input_state = {
                "messages": [HumanMessage(content=user_content)],
                "session_id": thread_id,
                "current_agent": "general-agent",
                "pending_approval": None,
                "metadata": agent_input.context or {},
            }

            if protocol_handler:
                response_content, active_agent_id = await self._stream_response(
                    input_state,
                    config,
                    thread_id,
                    run_id,
                    message_id,
                    protocol_handler,
                )
            else:
                response_content, active_agent_id = await self._run_blocking(
                    input_state, config
                )

            # Validate output
            is_valid, error = await self.moderator.validate_output(response_content)
            if not is_valid:
                log.warning("Output validation failed: %s", error)
                response_content = "I apologize, but I cannot provide that response."

            await self.audit.log_message(
                session_id=thread_id,
                role="assistant",
                content=response_content,
                metadata={"agent_id": active_agent_id},
            )

            # Increment message count for successful response
            if self.session_metadata:
                try:
                    await self.session_metadata.increment_message_count(thread_id)
                except Exception as e:
                    log.warning(f"Failed to increment message count: {e}")

            if protocol_handler and protocol_handler.is_connected:
                # Send final state snapshot before finishing
                await protocol_handler.send_state_snapshot(
                    {
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "current_agent": active_agent_id,
                        "status": "completed",
                    }
                )
                # Emit RUN_FINISHED
                await protocol_handler.send_run_finished(thread_id, run_id)

            return self._create_response_message(response_content, message_id)

        except Exception as e:
            if str(e) == "Tool execution rejected by user":
                log.info("Action cancelled by user")
                if protocol_handler and protocol_handler.is_connected:
                    await protocol_handler.send_run_finished(thread_id, run_id)
                return self._create_response_message(
                    "I have cancelled the action as requested.", str(uuid.uuid4())
                )

            log.error("Error processing message: %s", e, exc_info=True)
            if protocol_handler and protocol_handler.is_connected:
                # Use official RUN_ERROR event for errors
                await protocol_handler.send_run_error(
                    message=f"Error processing message: {str(e)}",
                    code="processing_error",
                )
                await protocol_handler.send_run_finished(thread_id, run_id)
            return self._create_response_message(
                "I apologize, but I encountered an error processing your request.",
                str(uuid.uuid4()),
            )

    def _create_response_message(self, content: str, message_id: str) -> AGUIMessage:
        """Create an AG-UI AssistantMessage response."""
        from ag_ui.core import AssistantMessage

        return AssistantMessage(
            id=message_id,
            role="assistant",
            content=content,
        )

    async def _run_blocking(
        self,
        input_state: dict[str, Any],
        config: dict[str, Any],
    ) -> tuple[str, str]:
        """Run graph in blocking mode without streaming."""
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
        thread_id: str,
        run_id: str,
        message_id: str,
        protocol_handler: Any,
    ) -> tuple[str, str]:
        """Stream graph response using astream_events with AG-UI Protocol."""
        full_response: list[str] = []
        current_agent_id = "general-agent"
        current_step: str | None = "routing"
        active_tool_calls: dict[str, str] = {}
        message_started = False

        await protocol_handler.send_step_finished("routing")
        await protocol_handler.send_step_started("thinking")
        current_step = "thinking"

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
                        # Start message on first content
                        if not message_started:
                            await protocol_handler.send_text_message_start(
                                message_id, "assistant"
                            )
                            message_started = True

                        await protocol_handler.send_text_message_content(
                            message_id, content
                        )

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_run_id = event.get("run_id", str(uuid.uuid4()))
                raw_input = event.get("data", {}).get("input", {})
                tool_input = (
                    _sanitize_params(raw_input) if isinstance(raw_input, dict) else {}
                )

                active_tool_calls[tool_run_id] = tool_name
                log.info(f"Tool started: {tool_name} (run_id: {tool_run_id})")

                # Finish current step before starting tool execution
                if current_step and current_step != "executing_tools":
                    await protocol_handler.send_step_finished(current_step)

                await protocol_handler.send_step_started("executing_tools")
                current_step = "executing_tools"

                # Handle approval flow
                await self._handle_tool_approval_flow(
                    tool_name, tool_input, thread_id, protocol_handler
                )

                if protocol_handler.is_connected:
                    await protocol_handler.send_tool_call_start(
                        tool_call_id=tool_run_id,
                        tool_call_name=tool_name,
                        parent_message_id=message_id,
                    )
                    # Send tool arguments
                    if tool_input:
                        await protocol_handler.send_tool_call_args(
                            tool_call_id=tool_run_id,
                            args_json=json.dumps(tool_input),
                        )

            elif kind == "on_tool_end":
                tool_run_id = event.get("run_id", "")
                tool_name = active_tool_calls.pop(tool_run_id, "unknown")
                output = event.get("data", {}).get("output", "")

                log.info(f"Tool completed: {tool_name} (run_id: {tool_run_id})")

                if protocol_handler.is_connected:
                    # Send TOOL_CALL_END to signal end of streaming
                    await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
                    # Send TOOL_CALL_RESULT with the actual result
                    result_str = str(output)[:500] if output else ""
                    if result_str:
                        await protocol_handler.send_tool_call_result(
                            message_id=f"tool-result-{tool_run_id}",
                            tool_call_id=tool_run_id,
                            content=result_str,
                        )

                    # Finish executing_tools step and return to thinking
                    await protocol_handler.send_step_finished("executing_tools")
                    await protocol_handler.send_step_started("thinking")
                    current_step = "thinking"

            elif kind == "on_tool_error":
                tool_run_id = event.get("run_id", "")
                tool_name = active_tool_calls.pop(tool_run_id, "unknown")
                error = event.get("data", {}).get("error", "Unknown error")

                log.error(f"Tool error: {tool_name} - {error}")

                if protocol_handler.is_connected:
                    # Send TOOL_CALL_END (no result event for errors)
                    await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)

                    # Finish executing_tools step and return to thinking
                    await protocol_handler.send_step_finished("executing_tools")
                    await protocol_handler.send_step_started("thinking")
                    current_step = "thinking"

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "current_agent" in output:
                    new_agent = output["current_agent"]
                    if new_agent != current_agent_id:
                        log.info(f"Agent changed: {current_agent_id} → {new_agent}")
                        await self.audit.log_handoff(
                            thread_id, current_agent_id, new_agent
                        )
                        current_agent_id = new_agent

                        if protocol_handler.is_connected:
                            # Properly finish current step before starting new one
                            if current_step:
                                await protocol_handler.send_step_finished(current_step)
                            await protocol_handler.send_step_started("thinking")
                            current_step = "thinking"

                            # Send state delta for agent change
                            await protocol_handler.send_state_snapshot(
                                {
                                    "thread_id": thread_id,
                                    "run_id": run_id,
                                    "current_agent": current_agent_id,
                                    "status": "processing",
                                }
                            )

        # Finalize message and step
        if protocol_handler.is_connected:
            if message_started:
                await protocol_handler.send_text_message_end(message_id)
            if current_step:
                await protocol_handler.send_step_finished(current_step)

        return "".join(full_response), current_agent_id

    async def get_conversation_history(
        self, thread_id: str, include_tool_calls: bool = False
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session."""
        config = {"configurable": {"thread_id": thread_id}}

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
                        # Extract agent_id from additional_kwargs if present
                        agent_id = None
                        if hasattr(msg, "additional_kwargs"):
                            agent_id = msg.additional_kwargs.get("agent_id")

                        if msg.content:
                            history.append(
                                {
                                    "role": "assistant",
                                    "content": str(msg.content),
                                    "agent_id": agent_id,
                                }
                            )
                        if include_tool_calls and hasattr(msg, "tool_calls"):
                            for tc in msg.tool_calls or []:
                                history.append(
                                    {
                                        "role": "tool_call",
                                        "tool_call_id": tc.get("id", ""),
                                        "tool_name": tc.get("name", "unknown"),
                                        "content": str(tc.get("args", {})),
                                        "agent_id": agent_id,
                                    }
                                )
                    elif include_tool_calls and msg.type == "tool":
                        history.append(
                            {
                                "role": "tool",
                                "tool_call_id": getattr(msg, "tool_call_id", ""),
                                "tool_name": getattr(msg, "name", "unknown"),
                                "content": str(msg.content),
                            }
                        )

            return history
        except Exception as e:
            log.error(f"Error getting conversation history: {e}")
            return []
