"""Orchestrator using OpenAI Agents SDK with AG-UI Protocol streaming."""

from __future__ import annotations

import json
import logging
import uuid
import asyncio
from typing import Any

from ag_ui.core import Message as AGUIMessage, AssistantMessage

from agora_openai.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)
from agora_openai.common.schemas import ToolCall
from agora_openai.core.approval_logic import requires_human_approval
from agora_openai.core.agent_runner import AgentRunner
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.api.ag_ui_handler import AGUIProtocolHandler

log = logging.getLogger(__name__)


class Orchestrator:
    """Orchestration using OpenAI Agents SDK with AG-UI Protocol streaming."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
    ):
        """Initialize orchestrator with dependencies."""
        self.agent_runner = agent_runner
        self.moderator = moderator
        self.audit = audit_logger
        self.pending_approvals: dict[str, asyncio.Future[bool]] = {}

    async def _handle_tool_approval_flow(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        thread_id: str,
        protocol_handler: AGUIProtocolHandler,
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
        protocol_handler: AGUIProtocolHandler | None = None,
    ) -> AGUIMessage:
        """Process a user message through the Agent SDK pipeline using AG-UI Protocol.

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
                        "threadId": thread_id,
                        "runId": run_id,
                        "currentAgent": "general-agent",
                        "status": "processing",
                    }
                )

                await protocol_handler.send_step_started("routing")

            message_id = str(uuid.uuid4())
            current_step = "routing"
            message_started = False
            current_agent_id = "general-agent"

            if protocol_handler:
                await protocol_handler.send_step_finished("routing")
                await protocol_handler.send_step_started("thinking")
                current_step = "thinking"

                async def stream_callback(
                    chunk: str, agent_id: str | None = None
                ) -> None:
                    """Send each chunk as TEXT_MESSAGE_CONTENT event."""
                    nonlocal message_started, current_agent_id
                    if protocol_handler and protocol_handler.is_connected:
                        # Check for agent change
                        if agent_id and agent_id != current_agent_id:
                            log.info(
                                f"Agent changed during stream: {current_agent_id} → {agent_id}"
                            )
                            current_agent_id = agent_id
                            await protocol_handler.send_state_snapshot(
                                {
                                    "threadId": thread_id,
                                    "runId": run_id,
                                    "currentAgent": current_agent_id,
                                    "status": "processing",
                                }
                            )

                        if not message_started:
                            await protocol_handler.send_text_message_start(
                                message_id, "assistant"
                            )
                            message_started = True
                        await protocol_handler.send_text_message_content(
                            message_id, chunk
                        )

                async def tool_callback(
                    tool_call_id: str,
                    tool_name: str,
                    parameters: dict[str, Any],
                    status: str,
                    agent_id: str | None = None,
                    result: str | None = None,
                ) -> None:
                    """Send tool call notifications as AG-UI events."""
                    nonlocal current_step, current_agent_id

                    if not protocol_handler or not protocol_handler.is_connected:
                        return

                    # Check for agent change and send state snapshot
                    if agent_id and agent_id != current_agent_id:
                        log.info(f"Agent changed: {current_agent_id} → {agent_id}")
                        current_agent_id = agent_id
                        await protocol_handler.send_state_snapshot(
                            {
                                "threadId": thread_id,
                                "runId": run_id,
                                "currentAgent": current_agent_id,
                                "status": "processing",
                            }
                        )

                    if status == "started":
                        # Handle approval flow before emitting tool start
                        await self._handle_tool_approval_flow(
                            tool_name, parameters, thread_id, protocol_handler
                        )

                        # Transition to executing_tools step
                        if current_step != "executing_tools":
                            await protocol_handler.send_step_finished(current_step)
                            await protocol_handler.send_step_started("executing_tools")
                            current_step = "executing_tools"

                        await protocol_handler.send_tool_call_start(
                            tool_call_id=tool_call_id,
                            tool_call_name=tool_name,
                            parent_message_id=message_id,
                        )

                        if parameters:
                            await protocol_handler.send_tool_call_args(
                                tool_call_id=tool_call_id,
                                args_json=json.dumps(parameters),
                            )

                    elif status == "completed":
                        # Send TOOL_CALL_END first (signals end of streaming)
                        await protocol_handler.send_tool_call_end(
                            tool_call_id=tool_call_id
                        )

                        # Send TOOL_CALL_RESULT with the actual result content
                        if result:
                            await protocol_handler.send_tool_call_result(
                                message_id=f"tool-result-{tool_call_id}",
                                tool_call_id=tool_call_id,
                                content=result,
                            )

                        # Return to thinking step
                        if current_step == "executing_tools":
                            await protocol_handler.send_step_finished("executing_tools")
                            await protocol_handler.send_step_started("thinking")
                            current_step = "thinking"

                response_content, active_agent_id = await self.agent_runner.run_agent(
                    message=user_content,
                    session_id=thread_id,
                    stream_callback=stream_callback,
                    tool_callback=tool_callback,
                )

                # Finalize message and step
                if protocol_handler.is_connected:
                    if message_started:
                        await protocol_handler.send_text_message_end(message_id)
                    if current_step:
                        await protocol_handler.send_step_finished(current_step)
            else:
                response_content, active_agent_id = await self.agent_runner.run_agent(
                    message=user_content,
                    session_id=thread_id,
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

            if protocol_handler and protocol_handler.is_connected:
                # Send final state snapshot before finishing
                await protocol_handler.send_state_snapshot(
                    {
                        "threadId": thread_id,
                        "runId": run_id,
                        "currentAgent": active_agent_id,
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
        return AssistantMessage(
            id=message_id,
            role="assistant",
            content=content,
        )
