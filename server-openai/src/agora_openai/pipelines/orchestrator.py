"""Orchestrator using OpenAI Agents SDK with AG-UI Protocol streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from ag_ui.core import AssistantMessage
from ag_ui.core import Message as AGUIMessage

from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.adapters.session_metadata import SessionMetadataManager
from agora_openai.adapters.user_manager import UserManager
from agora_openai.api.ag_ui_handler import AGUIProtocolHandler
from agora_openai.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)
from agora_openai.common.schemas import ToolCall
from agora_openai.config import get_settings
from agora_openai.core.agent_definitions import get_spoken_prompt
from agora_openai.core.agent_runner import AgentRunner
from agora_openai.core.approval_logic import requires_human_approval
from agora_openai.pipelines.moderator import ModerationPipeline

log = logging.getLogger(__name__)


class Orchestrator:
    """Orchestration using OpenAI Agents SDK with AG-UI Protocol streaming."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
        session_metadata: SessionMetadataManager | None = None,
        user_manager: UserManager | None = None,
    ):
        """Initialize orchestrator with dependencies."""
        self.agent_runner = agent_runner
        self.moderator = moderator
        self.audit = audit_logger
        self.session_metadata = session_metadata
        self.user_manager = user_manager
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

        # Get user_id from top-level field
        user_id = agent_input.user_id

        # Create or update session metadata
        if self.session_metadata:
            try:
                settings = get_settings()
                await self.session_metadata.create_or_update_metadata(
                    session_id=thread_id,
                    user_id=user_id,
                    first_message=user_content,
                    api_key=settings.openai_api_key.get_secret_value(),
                )
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
            spoken_message_started = False
            current_agent_id = "general-agent"

            # Fetch user preference for spoken response mode
            spoken_mode = "summarize"  # default
            if self.user_manager:
                try:
                    user = await self.user_manager.get_user(user_id)
                    if user:
                        prefs = user.get("preferences", {})
                        if prefs:
                            spoken_mode = prefs.get("spoken_text_type", "summarize")
                except Exception as e:
                    log.warning(f"Failed to fetch user preferences: {e}, using default")

            # Parallel spoken task state (only used in 'summarize' mode)
            spoken_task: asyncio.Task[None] | None = None
            spoken_queue: asyncio.Queue[str | None] = asyncio.Queue()

            # Timing state for debug logging
            stream_start_time: float = time.time()
            written_first_token_time: float = 0.0
            spoken_first_token_time: float = 0.0
            written_end_time: float = 0.0
            spoken_end_time: float = 0.0
            written_first_token_received = False
            spoken_first_token_received = False

            if protocol_handler:
                await protocol_handler.send_step_finished("routing")
                await protocol_handler.send_step_started("thinking")
                current_step = "thinking"

                async def generate_spoken_parallel() -> None:
                    """Generate spoken response in TRUE PARALLEL (summarize mode).

                    Uses the same conversation context but a spoken-specific prompt
                    that produces shorter, TTS-friendly summary responses.
                    """
                    nonlocal spoken_first_token_time, spoken_first_token_received
                    nonlocal spoken_end_time
                    try:
                        spoken_prompt = get_spoken_prompt(current_agent_id)
                        if not spoken_prompt:
                            log.warning(
                                f"No spoken prompt for agent {current_agent_id}"
                            )
                            await protocol_handler.send_spoken_text_error(
                                message_id,
                                "prompt_not_found",
                                f"No spoken prompt defined for agent: {current_agent_id}",
                            )
                            return

                        from openai import AsyncOpenAI

                        settings = get_settings()
                        client = AsyncOpenAI(
                            api_key=settings.openai_api_key.get_secret_value()
                        )

                        # Use same conversation context as written stream
                        conversation = [
                            {"role": m.get("role"), "content": m.get("content")}
                            for m in agent_input.messages
                        ]
                        spoken_messages = [
                            {"role": "system", "content": spoken_prompt}
                        ] + conversation

                        stream = await client.chat.completions.create(
                            model=settings.openai_model,
                            messages=spoken_messages,
                            stream=True,
                        )

                        async for chunk in stream:
                            if chunk.choices and chunk.choices[0].delta.content:
                                # Track first token timing
                                if not spoken_first_token_received:
                                    spoken_first_token_time = time.time()
                                    spoken_first_token_received = True
                                    elapsed = (
                                        spoken_first_token_time - stream_start_time
                                    )
                                    log.info(
                                        f"[TIMING] Spoken first token received at "
                                        f"+{elapsed:.3f}s from stream start"
                                    )
                                await spoken_queue.put(chunk.choices[0].delta.content)

                        # Mark spoken stream end
                        spoken_end_time = time.time()
                        elapsed = spoken_end_time - stream_start_time
                        log.info(
                            f"[TIMING] Spoken stream finished at "
                            f"+{elapsed:.3f}s from stream start"
                        )

                    except Exception as e:
                        error_msg = str(e)
                        log.error(f"Error generating spoken response: {error_msg}")
                        if protocol_handler.is_connected:
                            await protocol_handler.send_spoken_text_error(
                                message_id, "generation_failed", error_msg
                            )
                    finally:
                        await spoken_queue.put(None)

                async def stream_spoken_to_frontend() -> None:
                    """Stream spoken chunks to frontend as they arrive."""
                    nonlocal spoken_message_started
                    while True:
                        chunk = await spoken_queue.get()
                        if chunk is None:
                            # Send spoken_text_end immediately when spoken stream finishes
                            if protocol_handler.is_connected and spoken_message_started:
                                await protocol_handler.send_spoken_text_end(message_id)
                                spoken_message_started = False  # Mark as ended
                            break
                        if protocol_handler.is_connected:
                            await protocol_handler.send_spoken_text_content(
                                message_id, chunk
                            )

                log.info(f"[TIMING] Stream started (mode: {spoken_mode})")

                async def stream_callback(
                    chunk: str, agent_id: str | None = None
                ) -> None:
                    """Send each chunk to written channel, handle spoken based on mode."""
                    nonlocal message_started, current_agent_id, spoken_task
                    nonlocal spoken_message_started
                    nonlocal written_first_token_time, written_first_token_received
                    if protocol_handler and protocol_handler.is_connected:
                        # Track written first token timing
                        if not written_first_token_received:
                            written_first_token_time = time.time()
                            written_first_token_received = True
                            elapsed = written_first_token_time - stream_start_time
                            log.info(
                                f"[TIMING] Written first token received at "
                                f"+{elapsed:.3f}s from stream start"
                            )

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

                        # Start BOTH channels on first content
                        if not message_started:
                            await protocol_handler.send_text_message_start(
                                message_id, "assistant"
                            )
                            await protocol_handler.send_spoken_text_start(
                                message_id, "assistant"
                            )
                            message_started = True
                            spoken_message_started = True

                            # In 'summarize' mode: start parallel LLM call for spoken
                            if spoken_mode == "summarize":
                                spoken_task = asyncio.create_task(
                                    generate_spoken_parallel()
                                )
                                asyncio.create_task(stream_spoken_to_frontend())

                        # Send written content
                        await protocol_handler.send_text_message_content(
                            message_id, chunk
                        )

                        # In 'dictate' mode: duplicate content to spoken channel
                        if spoken_mode == "dictate":
                            await protocol_handler.send_spoken_text_content(
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

                        # Record full tool call data for history retrieval
                        if self.session_metadata and agent_id:
                            try:
                                await self.session_metadata.record_tool_call_agent(
                                    tool_call_id=tool_call_id,
                                    session_id=thread_id,
                                    agent_id=agent_id,
                                    tool_name=tool_name,
                                    parameters=(
                                        json.dumps(parameters) if parameters else None
                                    ),
                                )
                            except Exception as e:
                                log.warning(f"Failed to record tool call: {e}")

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
                        # Store tool call result for history retrieval
                        if self.session_metadata and result:
                            try:
                                await self.session_metadata.update_tool_call_result(
                                    tool_call_id=tool_call_id,
                                    result=result,
                                )
                            except Exception as e:
                                log.warning(f"Failed to store tool call result: {e}")

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

                # Include user_id context for settings tool
                # This allows the general-agent to use update_user_settings
                message_with_context = user_content
                if user_id:
                    message_with_context = (
                        f"[SYSTEM CONTEXT: user_id={user_id}]\n\n{user_content}"
                    )

                response_content, active_agent_id = await self.agent_runner.run_agent(
                    message=message_with_context,
                    session_id=thread_id,
                    stream_callback=stream_callback,
                    tool_callback=tool_callback,
                )

                # Mark written stream end
                written_end_time = time.time()
                written_elapsed = written_end_time - stream_start_time
                log.info(
                    f"[TIMING] Written stream finished at "
                    f"+{written_elapsed:.3f}s from stream start"
                )

                # Wait for spoken task to complete (only in 'summarize' mode)
                if spoken_task:
                    try:
                        await spoken_task
                    except Exception as e:
                        log.error(f"Spoken task failed: {e}")

                # Log timing summary
                if written_first_token_received and spoken_first_token_received:
                    first_token_diff = (
                        spoken_first_token_time - written_first_token_time
                    )
                    log.info(
                        f"[TIMING] First token difference: spoken was "
                        f"{first_token_diff:+.3f}s vs written"
                    )
                if written_end_time > 0 and spoken_end_time > 0:
                    end_diff = spoken_end_time - written_end_time
                    log.info(
                        f"[TIMING] Stream end difference: spoken was "
                        f"{end_diff:+.3f}s vs written"
                    )
                log.info(
                    f"[TIMING] Summary - Written: "
                    f"first={written_first_token_time - stream_start_time:.3f}s, "
                    f"end={written_end_time - stream_start_time:.3f}s | "
                    f"Spoken: first={spoken_first_token_time - stream_start_time:.3f}s, "
                    f"end={spoken_end_time - stream_start_time:.3f}s"
                )

                # Finalize BOTH channels
                if protocol_handler.is_connected:
                    if message_started:
                        await protocol_handler.send_text_message_end(message_id)
                    if spoken_message_started:
                        await protocol_handler.send_spoken_text_end(message_id)
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

    async def get_conversation_history(
        self, thread_id: str, include_tool_calls: bool = False
    ) -> list[dict[str, Any]]:
        """Get conversation history with tool calls and agent_id tracking.

        Retrieves the conversation history from the agent runner and enriches
        it with full tool call data from storage.

        Args:
            thread_id: Session/thread identifier
            include_tool_calls: If True, includes tool calls and results

        Returns:
            List of conversation items with role, content, and agent_id
        """
        # Get full tool call data from storage
        stored_tool_calls: list[dict[str, Any]] = []
        if self.session_metadata and include_tool_calls:
            try:
                stored_tool_calls = (
                    await self.session_metadata.get_tool_calls_for_session(thread_id)
                )
            except Exception as e:
                log.warning(f"Failed to get tool calls: {e}")

        return await self.agent_runner.get_conversation_history(
            session_id=thread_id,
            include_tool_calls=include_tool_calls,
            stored_tool_calls=stored_tool_calls,
        )

    def _create_response_message(self, content: str, message_id: str) -> AGUIMessage:
        """Create an AG-UI AssistantMessage response."""
        return AssistantMessage(
            id=message_id,
            role="assistant",
            content=content,
        )
