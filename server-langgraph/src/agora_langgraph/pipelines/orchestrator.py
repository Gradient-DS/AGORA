"""Orchestrator using LangGraph with astream_events for AG-UI Protocol streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from ag_ui.core import Message as AGUIMessage
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.adapters.session_metadata import SessionMetadataManager
from agora_langgraph.adapters.user_manager import UserManager
from agora_langgraph.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)
from agora_langgraph.common.schemas import ToolCall
from agora_langgraph.config import get_settings
from agora_langgraph.core.approval_logic import requires_human_approval
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
        graph: CompiledStateGraph[Any],
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
        session_metadata: SessionMetadataManager | None = None,
        user_manager: UserManager | None = None,
    ):
        """Initialize orchestrator."""
        self.graph = graph
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
                settings = get_settings()
                log.info(
                    f"Creating/updating session metadata: session_id={thread_id}, user_id={user_id}"
                )
                await self.session_metadata.create_or_update_metadata(
                    session_id=thread_id,
                    user_id=user_id,
                    first_message=user_content,
                    api_key=settings.openai_api_key.get_secret_value(),
                    base_url=settings.openai_base_url,
                )
                log.info(
                    f"Session metadata created/updated successfully for {thread_id}"
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

                # Note: Initial state snapshot will be sent after we determine current_agent

                await protocol_handler.send_step_started("routing")

            message_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": thread_id}}

            # Include user_id and user context in metadata so agents can access it
            metadata = agent_input.context.copy() if agent_input.context else {}
            metadata["user_id"] = user_id

            # Fetch user email and preferences (NOT interaction_mode - that's session-level)
            if self.user_manager:
                try:
                    user = await self.user_manager.get_user(user_id)
                    if user:
                        metadata["user_email"] = user.get("email")
                        metadata["user_name"] = user.get("name")
                        prefs = user.get("preferences", {})
                        if prefs:
                            metadata["email_reports"] = prefs.get("email_reports", True)
                except Exception as e:
                    log.warning(f"Failed to fetch user info for metadata: {e}")

            # Check if thread exists and get its persisted state
            is_interrupted = False
            is_existing_thread = False
            interaction_mode = "feedback"  # Default for new sessions

            try:
                existing_state = await self.graph.aget_state(config)  # type: ignore[arg-type]
                # Check if this is truly an existing thread with messages
                # (not just an empty state object)
                if (
                    existing_state
                    and existing_state.values
                    and existing_state.values.get("messages")
                ):
                    is_existing_thread = True
                    # interaction_mode is session-level, read from checkpointed state only
                    interaction_mode = existing_state.values.get(
                        "interaction_mode", "feedback"
                    )
                    log.info(
                        f"Existing thread {thread_id}, "
                        f"interaction_mode={interaction_mode}"
                    )
                else:
                    log.info(f"New thread {thread_id}, will start in feedback mode")

                if existing_state and existing_state.next:
                    # Graph is interrupted - there are pending tasks waiting for resume
                    is_interrupted = True
                    log.info(
                        f"Thread {thread_id} is interrupted at {existing_state.next}, "
                        "will resume with user message"
                    )
            except Exception as e:
                log.warning(f"Failed to read persisted state: {e}")

            # Determine input for graph invocation
            if is_interrupted:
                # Resume interrupted graph with user's response
                graph_input: dict[str, Any] | Command = Command(resume=user_content)
                log.info(f"[DEBUG] RESUMING interrupted graph with: {user_content[:100]}...")
            elif is_existing_thread:
                # Existing thread - only send new message
                # interaction_mode is persisted in checkpointed state
                graph_input = {
                    "messages": [HumanMessage(content=user_content)],
                    "metadata": metadata,
                }
            else:
                # NEW session - always start in feedback mode
                graph_input = {
                    "messages": [HumanMessage(content=user_content)],
                    "session_id": thread_id,
                    "current_agent": "general-agent",
                    "pending_approval": None,
                    "metadata": metadata,
                    # Listen mode fields - new sessions always start in feedback mode
                    "interaction_mode": "feedback",
                    "message_buffer": [],
                    "buffer_context": "",
                }

            # Send initial state snapshot with correct current_agent
            if protocol_handler:
                # For normal invocations, always start at general-agent
                # For interrupted flows, we're resuming at reporting-agent
                initial_agent = "reporting-agent" if is_interrupted else "general-agent"
                await protocol_handler.send_state_snapshot(
                    {
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "current_agent": initial_agent,
                        "status": "processing",
                    }
                )

            if protocol_handler:
                response_content, active_agent_id = await self._stream_response(
                    graph_input,
                    config,
                    thread_id,
                    run_id,
                    message_id,
                    user_id,
                    protocol_handler,
                    interaction_mode,
                )
            else:
                response_content, active_agent_id = await self._run_blocking(
                    graph_input, config
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
        graph_input: dict[str, Any] | Command,
        config: dict[str, Any],
    ) -> tuple[str, str]:
        """Run graph in blocking mode without streaming."""
        result = await self.graph.ainvoke(graph_input, config=config)  # type: ignore[arg-type]

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
        graph_input: dict[str, Any] | Command,
        config: dict[str, Any],
        thread_id: str,
        run_id: str,
        message_id: str,
        user_id: str,
        protocol_handler: Any,
        interaction_mode: str = "feedback",
    ) -> tuple[str, str]:
        """Stream graph response using astream_events with AG-UI Protocol.

        The graph uses parallel generation nodes (generate_written, generate_spoken)
        via the Send API. Both run simultaneously with shared context but different
        prompts.

        Dual-channel streaming controlled by user's spoken_text_type preference:
        - 'summarize': Uses generate_spoken output (speech-optimized)
        - 'dictate': Ignores spoken stream, duplicates written to both channels
        """
        full_response: list[str] = []
        # Handle both normal input and Command resume
        is_resuming_from_interrupt = isinstance(graph_input, Command)
        resumed_tool_handled = False  # Track if we've skipped the resumed tool's start event
        if is_resuming_from_interrupt:
            current_agent_id = "reporting-agent"  # Resuming interrupted reporting flow
        else:
            current_agent_id = graph_input.get("current_agent", "general-agent")
        current_step: str | None = "routing"
        active_tool_calls: dict[str, str] = {}
        message_started = False
        spoken_message_started = False

        # Agent node names - we don't stream from these (ReAct loop)
        agent_nodes = {
            "general-agent",
            "regulation-agent",
            "reporting-agent",
            "history-agent",
        }

        await protocol_handler.send_step_finished("routing")
        await protocol_handler.send_step_started("thinking")
        current_step = "thinking"

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

        log.info(f"Spoken mode for user {user_id}: {spoken_mode}")

        async for event in self.graph.astream_events(
            graph_input, config=config, version="v2"  # type: ignore[arg-type]
        ):
            kind = event.get("event", "")
            metadata = event.get("metadata", {})
            node_name = metadata.get("langgraph_node", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content = str(chunk.content)

                    # Only stream from generator nodes, not agent nodes
                    # Agent nodes run during ReAct loop - their output is regenerated
                    if node_name in agent_nodes:
                        # Skip streaming from agent nodes (wasted call is filtered)
                        continue

                    if node_name == "generate_written":
                        # Accumulate for final response
                        full_response.append(content)

                        if protocol_handler.is_connected:
                            # Start both channels on first written content
                            if not message_started:
                                log.info(
                                    f"Starting text streams (spoken_mode={spoken_mode})"
                                )
                                await protocol_handler.send_text_message_start(
                                    message_id, "assistant"
                                )
                                await protocol_handler.send_spoken_text_start(
                                    message_id, "assistant"
                                )
                                message_started = True
                                spoken_message_started = True

                            # Send to written channel
                            await protocol_handler.send_text_message_content(
                                message_id, content
                            )

                            # In dictate mode: also send written to spoken channel
                            if spoken_mode == "dictate":
                                await protocol_handler.send_spoken_text_content(
                                    message_id, content
                                )

                    elif node_name == "generate_spoken":
                        # In summarize mode: send to spoken channel
                        if spoken_mode == "summarize" and protocol_handler.is_connected:
                            # Ensure spoken started (should be from written first chunk)
                            if not spoken_message_started:
                                await protocol_handler.send_spoken_text_start(
                                    message_id, "assistant"
                                )
                                spoken_message_started = True

                            await protocol_handler.send_spoken_text_content(
                                message_id, content
                            )
                        elif spoken_mode == "dictate":
                            # In dictate mode: ignore spoken stream (we duplicate written)
                            pass
            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_run_id = event.get("run_id", str(uuid.uuid4()))
                raw_input: Any = event.get("data", {}).get("input", {})
                tool_input = (
                    _sanitize_params(raw_input) if isinstance(raw_input, dict) else {}
                )

                # When resuming from interrupt, skip TOOL_CALL_START for the resumed tool
                # (we already sent events for it during interrupt handling in the previous stream)
                if is_resuming_from_interrupt and not resumed_tool_handled and tool_name == "request_clarification":
                    log.info(f"[DEBUG] Skipping TOOL_CALL_START for resumed tool: {tool_name} ({tool_run_id})")
                    resumed_tool_handled = True
                    # Still track it so we can skip TOOL_CALL_END/RESULT too
                    active_tool_calls[tool_run_id] = f"_resumed_{tool_name}"
                    continue

                active_tool_calls[tool_run_id] = tool_name
                log.info(f"[DEBUG] on_tool_start: {tool_name} (run_id: {tool_run_id})")
                log.info(f"[DEBUG] active_tool_calls after start: {list(active_tool_calls.keys())}")

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
                    log.info(f"[DEBUG] Sending TOOL_CALL_START: {tool_name} ({tool_run_id})")
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
                log.info(f"[DEBUG] on_tool_end received: run_id={tool_run_id}")
                log.info(f"[DEBUG] active_tool_calls before pop: {list(active_tool_calls.keys())}")
                tool_name = active_tool_calls.pop(tool_run_id, None)
                output = event.get("data", {}).get("output", "")
                log.info(f"[DEBUG] on_tool_end: tool_name={tool_name}, output_len={len(str(output)) if output else 0}")

                # Skip if tool wasn't started in this stream (e.g., resumed from interrupt)
                # Events were already sent when the interrupt was handled
                if tool_name is None:
                    log.info(
                        f"[DEBUG] Skipping on_tool_end for tool not in this stream "
                        f"(run_id: {tool_run_id}) - likely resumed from interrupt"
                    )
                    continue

                # Skip sending events for resumed tools (we already sent them during interrupt handling)
                if tool_name.startswith("_resumed_"):
                    log.info(f"[DEBUG] Skipping TOOL_CALL_END/RESULT for resumed tool: {tool_name} ({tool_run_id})")
                    continue

                log.info(f"[DEBUG] Tool completed: {tool_name} (run_id: {tool_run_id})")

                if protocol_handler.is_connected:
                    # Send TOOL_CALL_END to signal end of streaming
                    log.info(f"[DEBUG] Sending TOOL_CALL_END for {tool_run_id}")
                    await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
                    # Send TOOL_CALL_RESULT with the actual result
                    # Always send TOOL_CALL_RESULT so frontend marks tool as completed
                    result_str = str(output)[:500] if output else ""
                    log.info(f"[DEBUG] Sending TOOL_CALL_RESULT for {tool_run_id}, content_len={len(result_str)}")
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
                error = event.get("data", {}).get("error", "Unknown error")
                error_str = str(error)

                # Check if this is an interrupt (not a real error)
                # LangGraph reports interrupt() as a tool error
                is_interrupt = "Interrupt(" in error_str

                if is_interrupt:
                    # Don't pop from active_tool_calls - let interrupt handling close it
                    tool_name = active_tool_calls.get(tool_run_id)
                    log.info(f"[DEBUG] Tool interrupted (not error): {tool_name} (run_id: {tool_run_id})")
                    # Don't send any events here - interrupt handling will do it
                    continue

                tool_name = active_tool_calls.pop(tool_run_id, None)

                # Skip if tool wasn't started in this stream
                if tool_name is None:
                    log.info(
                        f"Skipping on_tool_error for tool not in this stream "
                        f"(run_id: {tool_run_id})"
                    )
                    continue

                log.error(f"Tool error: {tool_name} - {error}")

                if protocol_handler.is_connected:
                    # Send TOOL_CALL_END and TOOL_CALL_RESULT for errors
                    await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
                    await protocol_handler.send_tool_call_result(
                        message_id=f"tool-result-{tool_run_id}",
                        tool_call_id=tool_run_id,
                        content=f"Error: {error_str[:400]}",
                    )

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

        # After streaming completes, check if graph was interrupted
        # Get the final state to check for interrupts
        log.info(f"[DEBUG] Stream completed, checking for interrupt. active_tool_calls: {list(active_tool_calls.keys())}")
        try:
            final_state = await self.graph.aget_state(config)  # type: ignore[arg-type]
            log.info(f"[DEBUG] final_state.next: {final_state.next if final_state else 'None'}")

            # Check if update_user_settings was called with interaction_mode in THIS turn
            # Only check the most recent AIMessage to avoid re-applying old tool calls
            if final_state and final_state.values:
                messages = final_state.values.get("messages", [])
                # Find the most recent AIMessage with tool_calls (from this turn)
                for msg in reversed(messages):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            if tool_call.get("name") == "update_user_settings":
                                args = tool_call.get("args", {})
                                new_mode = args.get("interaction_mode")
                                if new_mode and new_mode in ("feedback", "listen"):
                                    log.info(
                                        f"Updating session interaction_mode to '{new_mode}' "
                                        f"via update_user_settings tool"
                                    )
                                    await self.graph.aupdate_state(
                                        config,
                                        {"interaction_mode": new_mode},
                                    )
                        break  # Only check the most recent AIMessage with tool calls
            if final_state and final_state.next:
                # Graph was interrupted - there are pending tasks
                log.info(
                    f"[DEBUG] Graph interrupted at node(s): {final_state.next}, "
                    f"thread: {thread_id}"
                )

                # Extract interrupt payload first (needed for tool result)
                interrupt_value = None
                if final_state.tasks:
                    for task in final_state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            interrupt_value = task.interrupts[0].value
                            log.info(f"[DEBUG] Interrupt payload: {interrupt_value}")
                            break

                # Close any active tool calls that were interrupted
                # (they never got TOOL_CALL_END because interrupt() paused execution)
                log.info(f"[DEBUG] About to close interrupted tool calls. active_tool_calls: {list(active_tool_calls.items())}, is_connected: {protocol_handler.is_connected}")
                if active_tool_calls and protocol_handler.is_connected:
                    for tool_run_id, tool_name in list(active_tool_calls.items()):
                        log.info(f"[DEBUG] Closing interrupted tool call: {tool_name} ({tool_run_id})")
                        await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
                        # Send TOOL_CALL_RESULT so frontend marks tool as completed
                        result_content = ""
                        if interrupt_value and isinstance(interrupt_value, dict):
                            result_content = interrupt_value.get("display_text", "")
                        log.info(f"[DEBUG] Sending TOOL_CALL_RESULT for interrupted tool {tool_run_id}")
                        await protocol_handler.send_tool_call_result(
                            message_id=f"tool-result-{tool_run_id}",
                            tool_call_id=tool_run_id,
                            content=result_content or "Clarification requested",
                        )
                    active_tool_calls.clear()
                else:
                    log.info(f"[DEBUG] NOT closing tool calls: active_tool_calls={bool(active_tool_calls)}, is_connected={protocol_handler.is_connected}")

                # Send clarification questions to user as text message
                if final_state.tasks:
                    for task in final_state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            interrupt_value = task.interrupts[0].value
                            log.info(f"Interrupt payload: {interrupt_value}")

                            # Send clarification questions as text message
                            if isinstance(interrupt_value, dict):
                                display_text = interrupt_value.get("display_text", "")
                                if display_text and protocol_handler.is_connected:
                                    # Format the questions nicely
                                    clarification_message = (
                                        "Om het rapport te kunnen voltooien heb ik nog "
                                        "enkele gegevens nodig:\n\n" + display_text
                                    )

                                    # Start message if not started
                                    if not message_started:
                                        await protocol_handler.send_text_message_start(
                                            message_id, "assistant"
                                        )
                                        await protocol_handler.send_spoken_text_start(
                                            message_id, "assistant"
                                        )
                                        message_started = True
                                        spoken_message_started = True

                                    # Send the questions
                                    await protocol_handler.send_text_message_content(
                                        message_id, clarification_message
                                    )
                                    await protocol_handler.send_spoken_text_content(
                                        message_id, clarification_message
                                    )
                                    full_response.append(clarification_message)
                                    log.info(
                                        f"Sent clarification questions to user: "
                                        f"{len(clarification_message)} chars"
                                    )
        except Exception as e:
            log.error(f"[DEBUG] Failed to check interrupt state: {e}", exc_info=True)

        # Handle listen mode responses (final_written set but no streaming happened)
        try:
            if final_state and final_state.values:
                final_written = final_state.values.get("final_written", "")
                final_spoken = final_state.values.get("final_spoken", "")
                final_interaction_mode = final_state.values.get("interaction_mode")

                # If we have final_written but didn't stream (listen mode), send it now
                if final_written and not message_started:
                    await protocol_handler.send_text_message_start(message_id, "assistant")
                    await protocol_handler.send_text_message_content(message_id, final_written)
                    message_started = True
                    full_response.append(final_written)

                    # Also send spoken if present
                    if final_spoken:
                        await protocol_handler.send_spoken_text_start(
                            message_id, "assistant"
                        )
                        await protocol_handler.send_spoken_text_content(
                            message_id, final_spoken
                        )
                        spoken_message_started = True

                    log.info(
                        f"Sent listen mode response: written={len(final_written)} chars"
                    )

                # Log interaction_mode change (per-session, persisted in graph state)
                if final_interaction_mode and final_interaction_mode != interaction_mode:
                    log.info(
                        f"interaction_mode changed to '{final_interaction_mode}' "
                        f"(persisted in session state)"
                    )
        except Exception as e:
            log.warning(f"Failed to handle listen mode response: {e}")

        written_chars = len("".join(full_response))
        spoken_source = (
            "duplicated from written" if spoken_mode == "dictate" else "generate_spoken"
        )
        log.info(
            f"Parallel generation complete: written={written_chars} chars, "
            f"spoken_mode={spoken_mode}, spoken_source={spoken_source}"
        )

        # Finalize BOTH channels
        if protocol_handler.is_connected:
            if message_started:
                await protocol_handler.send_text_message_end(message_id)
            if spoken_message_started:
                await protocol_handler.send_spoken_text_end(message_id)
            if current_step:
                await protocol_handler.send_step_finished(current_step)

        return "".join(full_response), current_agent_id

    async def get_conversation_history(
        self, thread_id: str, include_tool_calls: bool = False
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session.

        Note: Due to parallel generation architecture, the LangGraph checkpoint
        may contain duplicate AIMessages (agent's response + regenerated response).
        This method filters out consecutive AI messages without tool calls,
        keeping only the last one in each sequence (the final regenerated version).
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = await self.graph.aget_state(config)  # type: ignore[arg-type]
            if not state or not state.values:
                return []

            messages = state.values.get("messages", [])
            history = []

            # Track previous message type to filter consecutive AI messages
            prev_was_ai_without_tools = False

            for msg in messages:
                if hasattr(msg, "type"):
                    if msg.type == "human":
                        prev_was_ai_without_tools = False
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

                        has_tool_calls = bool(getattr(msg, "tool_calls", None))

                        if has_tool_calls:
                            # AI message with tool calls - always include
                            prev_was_ai_without_tools = False
                            if msg.content:
                                history.append(
                                    {
                                        "role": "assistant",
                                        "content": str(msg.content),
                                        "agent_id": agent_id or "",
                                    }
                                )
                            if include_tool_calls:
                                for tc in msg.tool_calls or []:
                                    history.append(
                                        {
                                            "role": "tool_call",
                                            "tool_call_id": tc.get("id", ""),
                                            "tool_name": tc.get("name", "unknown"),
                                            "content": str(tc.get("args", {})),
                                            "agent_id": agent_id or "",
                                        }
                                    )
                        else:
                            # AI message without tool calls
                            if msg.content:
                                if prev_was_ai_without_tools and history:
                                    # Replace the previous AI message (it was the
                                    # agent's "wasted" response before regeneration)
                                    history[-1] = {
                                        "role": "assistant",
                                        "content": str(msg.content),
                                        "agent_id": agent_id or "",
                                    }
                                else:
                                    history.append(
                                        {
                                            "role": "assistant",
                                            "content": str(msg.content),
                                            "agent_id": agent_id or "",
                                        }
                                    )
                            prev_was_ai_without_tools = True

                    elif include_tool_calls and msg.type == "tool":
                        prev_was_ai_without_tools = False
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
