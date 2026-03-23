"""Orchestrator using LangGraph with astream_events for AG-UI Protocol streaming."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
from ag_ui.core import Message as AGUIMessage
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.adapters.session_metadata import SessionMetadataManager
from agora_langgraph.adapters.user_manager import UserManager
from agora_langgraph.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)
from agora_langgraph.common.message_utils import extract_text
from agora_langgraph.config import get_settings
from agora_langgraph.core.tool_display_names import (
    get_tool_display_name,
    get_tool_spoken_description,
)
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

    SESSION_IMAGES_DIR = Path("session_images")

    def __init__(
        self,
        graph: CompiledStateGraph[Any],
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
        session_metadata: SessionMetadataManager | None = None,
        user_manager: UserManager | None = None,
        reporting_url: str | None = None,
    ):
        """Initialize orchestrator."""
        self.graph = graph
        self.moderator = moderator
        self.audit = audit_logger
        self.session_metadata = session_metadata
        self.user_manager = user_manager
        self.reporting_url = reporting_url
        # Context for resuming after interrupt-based approval
        self._pending_approval_context: dict[str, Any] | None = None
        # Agent ID being resumed (set before calling _stream_response with Command)
        self._resuming_agent_id: str | None = None

    def _save_session_images(
        self,
        session_id: str,
        image_parts: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Save uploaded images to disk. Returns list of {filename, mime_type}."""
        images_dir = self.SESSION_IMAGES_DIR / session_id
        images_dir.mkdir(parents=True, exist_ok=True)

        saved: list[dict[str, str]] = []
        for img in image_parts:
            data_url = img.get("data", "")
            mime_type = img.get("mimeType", "image/jpeg")

            if "," not in data_url:
                continue
            _, b64_data = data_url.split(",", 1)

            try:
                image_bytes = base64.b64decode(b64_data)
            except Exception:
                log.warning("Failed to decode image base64 data")
                continue

            # Deterministic filename from content hash
            content_hash = hashlib.md5(image_bytes).hexdigest()[:12]
            ext = "jpg" if "jpeg" in mime_type else mime_type.split("/")[-1]
            filename = f"{content_hash}.{ext}"
            file_path = images_dir / filename

            if not file_path.exists():
                file_path.write_bytes(image_bytes)
                log.info(
                    f"Saved session image {filename} for session {session_id} ({len(image_bytes)} bytes)"
                )

            saved.append({"filename": filename, "mime_type": mime_type})

        return saved

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

        # Extract user messages — always text-only for the LLM
        user_text_parts: list[str] = []
        image_parts: list[dict[str, Any]] = []
        for msg in agent_input.messages:
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                if isinstance(raw_content, list):
                    # Multimodal content array — extract text and image parts separately
                    text_parts = [
                        part["text"]
                        for part in raw_content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    image_parts = [
                        part
                        for part in raw_content
                        if isinstance(part, dict) and part.get("type") == "binary"
                    ]
                    user_text_parts.append("\n".join(text_parts))
                else:
                    user_text_parts.append(raw_content)

        # Text-only content for both LLM and logging
        user_content = "\n".join(user_text_parts)

        # Auto-forward images to reporting MCP server for PDF evidence
        if image_parts and self.reporting_url:
            asyncio.create_task(
                self._forward_images_to_reporting(
                    session_id=thread_id,
                    image_parts=image_parts,
                    caption=user_content,
                )
            )

        # Save images to disk for chat history persistence
        saved_images: list[dict[str, str]] = []
        if image_parts:
            saved_images = self._save_session_images(thread_id, image_parts)

        # Generate AI descriptions for images in the background
        if image_parts and self.reporting_url:
            asyncio.create_task(
                self._describe_and_update_images(
                    session_id=thread_id,
                    image_parts=image_parts,
                )
            )

        # Image-only message — no LLM invocation needed
        if not user_content.strip() and image_parts:
            log.info(f"Image-only message for session {thread_id}, skipping LLM")
            if protocol_handler:
                run_id = agent_input.run_id or str(uuid.uuid4())
                await protocol_handler.send_run_started(thread_id, run_id)
                await protocol_handler.send_run_finished(thread_id, run_id)
            return self._create_response_message("", str(uuid.uuid4()))

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
            metadata={},
        )

        try:
            if protocol_handler:
                # Emit RUN_STARTED
                await protocol_handler.send_run_started(thread_id, run_id)

                # Note: Initial state snapshot will be sent after we determine current_agent

                await protocol_handler.send_step_started("routing")

            message_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": thread_id}}

            # Include user_id in metadata so agents can access it
            metadata: dict[str, Any] = {"user_id": user_id}

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
                # Resume interrupted graph with user's response (clarification flow)
                graph_input: dict[str, Any] | Command = Command(resume=user_content)
                self._resuming_agent_id = (
                    existing_state.values.get("current_agent", "general-agent")
                    if existing_state and existing_state.values
                    else "general-agent"
                )
                log.info(
                    f"[DEBUG] RESUMING interrupted graph with: {user_content[:100]}..."
                )
            elif is_existing_thread:
                # Existing thread - only send new message
                # interaction_mode is persisted in checkpointed state
                human_msg = HumanMessage(content=user_content)
                if saved_images:
                    human_msg.additional_kwargs["image_refs"] = saved_images
                graph_input = {
                    "messages": [human_msg],
                    "metadata": metadata,
                }
            else:
                # NEW session - always start in feedback mode
                human_msg = HumanMessage(content=user_content)
                if saved_images:
                    human_msg.additional_kwargs["image_refs"] = saved_images
                graph_input = {
                    "messages": [human_msg],
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
                # For interrupted flows, use the agent from persisted state
                initial_agent = (
                    self._resuming_agent_id if is_interrupted else "general-agent"
                )
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

            self._resuming_agent_id = None

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

    async def resume_with_approval(
        self,
        response: ToolApprovalResponsePayload,
        protocol_handler: Any,
    ) -> AGUIMessage | None:
        """Resume an interrupted graph with an approval decision.

        Called when a ToolApprovalResponsePayload arrives via WebSocket.
        Resumes the graph with Command(resume={"approved": ..., "feedback": ...}).
        """
        ctx = self._pending_approval_context
        if not ctx or ctx["approval_id"] != response.approval_id:
            log.warning(f"No matching pending approval for ID: {response.approval_id}")
            return None

        self._pending_approval_context = None

        thread_id = ctx["thread_id"]
        run_id = ctx["run_id"]
        message_id = ctx["message_id"]
        user_id = ctx["user_id"]
        interaction_mode = ctx["interaction_mode"]
        config = {"configurable": {"thread_id": thread_id}}

        await self.audit.log_approval_response(
            thread_id, response.approval_id, response.approved
        )

        if not response.approved:
            log.info(f"Tool rejected by user (approval_id: {response.approval_id})")
        else:
            log.info(f"Tool approved by user (approval_id: {response.approval_id})")

        # Determine the agent we're resuming into from persisted state
        try:
            existing_state = await self.graph.aget_state(config)  # type: ignore[arg-type]
            self._resuming_agent_id = (
                existing_state.values.get("current_agent", "general-agent")
                if existing_state and existing_state.values
                else "general-agent"
            )
        except Exception:
            self._resuming_agent_id = "general-agent"

        graph_input: Command = Command(
            resume={
                "approved": response.approved,
                "feedback": response.feedback,
            }
        )

        try:
            if protocol_handler:
                await protocol_handler.send_run_started(thread_id, run_id)
                await protocol_handler.send_step_started("routing")
                await protocol_handler.send_state_snapshot(
                    {
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "current_agent": self._resuming_agent_id,
                        "status": "processing",
                    }
                )

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

                if protocol_handler.is_connected:
                    await protocol_handler.send_state_snapshot(
                        {
                            "thread_id": thread_id,
                            "run_id": run_id,
                            "current_agent": active_agent_id,
                            "status": "completed",
                        }
                    )
                    await protocol_handler.send_run_finished(thread_id, run_id)

                self._resuming_agent_id = None
                return self._create_response_message(response_content, message_id)

        except Exception as e:
            self._resuming_agent_id = None
            log.error("Error resuming after approval: %s", e, exc_info=True)
            if protocol_handler and protocol_handler.is_connected:
                await protocol_handler.send_run_error(
                    message=f"Error resuming after approval: {str(e)}",
                    code="processing_error",
                )
                await protocol_handler.send_run_finished(thread_id, run_id)

        return None

    async def _forward_images_to_reporting(
        self,
        session_id: str,
        image_parts: list[dict[str, Any]],
        caption: str,
    ) -> None:
        """Forward uploaded images to the reporting MCP server for PDF evidence."""
        url = f"{self.reporting_url}/reports/{session_id}/images"
        caption = caption.strip() if caption else "Bewijsfoto"

        async with httpx.AsyncClient(timeout=10.0) as client:
            for img in image_parts:
                try:
                    resp = await client.post(
                        url,
                        json={
                            "image_data": img.get("data", ""),
                            "caption": caption,
                            "mime_type": img.get("mimeType", "image/jpeg"),
                        },
                    )
                    if resp.status_code == 201:
                        log.info(
                            f"Forwarded evidence image to reporting server for session {session_id}"
                        )
                    elif resp.status_code == 409:
                        log.info(
                            f"Image limit reached for session {session_id}, skipping remaining"
                        )
                        break
                    else:
                        log.warning(
                            f"Failed to forward image: {resp.status_code} {resp.text}"
                        )
                except Exception as e:
                    log.warning(f"Failed to forward evidence image: {e}")

    async def _describe_and_update_images(
        self,
        session_id: str,
        image_parts: list[dict[str, Any]],
    ) -> None:
        """Generate AI descriptions for images and update reporting server."""
        from langchain_openai import ChatOpenAI

        settings = get_settings()
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
            max_completion_tokens=300,
        )

        for i, img in enumerate(image_parts):
            data_url = img.get("data", "")
            if not data_url:
                continue

            try:
                response = await llm.ainvoke(
                    [
                        HumanMessage(
                            content=[
                                {
                                    "type": "text",
                                    "text": (
                                        "Beschrijf deze foto kort in het Nederlands (max 2 zinnen). "
                                        "Dit is een inspectie-foto gemaakt door een NVWA-inspecteur. "
                                        "Focus op wat zichtbaar is dat relevant kan zijn voor "
                                        "voedselveiligheid of compliance."
                                    ),
                                },
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ]
                        )
                    ]
                )
                description = (
                    response.content
                    if isinstance(response.content, str)
                    else str(response.content)
                )

                # Update the reporting MCP server with the description
                if self.reporting_url:
                    url = f"{self.reporting_url}/reports/{session_id}/images/{i}/description"
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.patch(
                            url, json={"description": description}
                        )
                        if resp.status_code == 200:
                            log.info(
                                f"Updated image {i} description for session {session_id}"
                            )
                        else:
                            log.warning(
                                f"Failed to update image description: {resp.status_code}"
                            )
            except Exception as e:
                log.warning(f"Failed to describe image {i}: {e}")

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
                response_content = extract_text(msg.content)
                break

        agent_id = result.get("current_agent", "general-agent")
        return response_content, agent_id

    @staticmethod
    def _build_spoken_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
        """Build filtered message list for spoken generation.

        Prior completed turns: only HumanMessages + final AI responses
        Current turn: only HumanMessages + agent's final AIMessage
        No tool results — the agent's response already incorporates them.
        """
        last_final_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage) and messages[i].additional_kwargs.get(
                "is_final_response"
            ):
                last_final_idx = i
                break

        filtered: list[BaseMessage] = []

        # Prior turns: only HumanMessages + final responses
        if last_final_idx >= 0:
            for msg in messages[: last_final_idx + 1]:
                if isinstance(msg, HumanMessage):
                    filtered.append(msg)
                elif isinstance(msg, AIMessage) and msg.additional_kwargs.get(
                    "is_final_response"
                ):
                    filtered.append(msg)

        # Current turn: only HumanMessages + agent's final AIMessage
        for msg in messages[last_final_idx + 1 :]:
            if isinstance(msg, HumanMessage):
                filtered.append(msg)
            elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                filtered.append(msg)

        return filtered

    async def _generate_spoken(
        self,
        agent_id: str,
        messages: list[BaseMessage],
        message_id: str,
        protocol_handler: Any,
        written_text: str = "",
    ) -> str:
        """Generate spoken text and stream to client.

        Runs sequentially after the graph ends. Receives the completed written
        response so the spoken LLM can summarize it. Uses empty callbacks config
        to isolate from any active LangGraph streaming context.
        """
        from agora_langgraph.core.agent_definitions import get_spoken_prompt
        from agora_langgraph.core.agents import get_llm_for_spoken

        spoken_prompt = get_spoken_prompt(agent_id)
        if not spoken_prompt:
            log.warning(f"No spoken prompt for {agent_id}, skipping spoken generation")
            return ""

        llm = get_llm_for_spoken()
        full_messages: list[BaseMessage] = [
            SystemMessage(content=spoken_prompt)
        ] + list(messages)

        # Append the written response so the spoken LLM can summarize it
        if written_text:
            full_messages.append(AIMessage(content=written_text))

        spoken_parts: list[str] = []
        spoken_started = False

        try:
            # Pass empty callbacks to prevent leaking into graph's streaming context
            async for chunk in llm.astream(full_messages, config={"callbacks": []}):
                if hasattr(chunk, "content") and chunk.content:
                    content = extract_text(chunk.content)
                    if not content:
                        continue

                    if not spoken_started and protocol_handler.is_connected:
                        await protocol_handler.send_spoken_text_start(
                            message_id, "assistant"
                        )
                        spoken_started = True

                    spoken_parts.append(content)
                    if protocol_handler.is_connected:
                        await protocol_handler.send_spoken_text_content(
                            message_id, content
                        )
        except Exception as e:
            log.error(f"Spoken generation failed: {e}", exc_info=True)

        return "".join(spoken_parts)

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

        The agent's response is streamed directly as written text. Spoken text
        is generated after the graph ends via _generate_spoken.

        Dual-channel streaming controlled by user's spoken_text_type preference:
        - 'summarize': Spoken generated after graph ends (speech-optimized)
        - 'dictate': Duplicates written to both channels
        """
        full_response: list[str] = []
        # Handle both normal input and Command resume
        is_resuming_from_interrupt = isinstance(graph_input, Command)
        resumed_tool_handled = (
            False  # Track if we've skipped the resumed tool's start event
        )
        if is_resuming_from_interrupt:
            current_agent_id = self._resuming_agent_id or "general-agent"
        else:
            current_agent_id = graph_input.get("current_agent", "general-agent")
        current_step: str | None = "routing"
        active_tool_calls: dict[str, str] = {}
        message_started = False
        spoken_message_started = False
        # Track whether the current agent invocation is making tool calls.
        # If it is, we must not stream the text (it's intermediate, not the final answer).
        agent_streaming_active = False

        # Agent node names — we stream written text directly from these
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
                    content = extract_text(chunk.content)
                    if not content:
                        continue

                    if node_name in agent_nodes:
                        # Stream agent's response directly as written text.
                        # Skip chunks that are part of tool call generation.
                        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                            agent_streaming_active = False
                            continue
                        if (
                            hasattr(chunk, "tool_call_chunks")
                            and chunk.tool_call_chunks
                        ):
                            agent_streaming_active = False
                            continue

                        agent_streaming_active = True
                        full_response.append(content)

                        if protocol_handler.is_connected:
                            if not message_started:
                                log.info(
                                    f"Starting text streams (spoken_mode={spoken_mode})"
                                )
                                await protocol_handler.send_text_message_start(
                                    message_id, "assistant"
                                )
                                message_started = True
                                # In dictate mode: start spoken channel eagerly
                                # (spoken duplicates written chunks)
                                # In summarize mode: spoken starts after written completes
                                if (
                                    spoken_mode == "dictate"
                                    and not spoken_message_started
                                ):
                                    await protocol_handler.send_spoken_text_start(
                                        message_id, "assistant"
                                    )
                                    spoken_message_started = True

                            await protocol_handler.send_text_message_content(
                                message_id, content
                            )

                            # In dictate mode: also send written to spoken channel
                            if spoken_mode == "dictate":
                                await protocol_handler.send_spoken_text_content(
                                    message_id, content
                                )

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_run_id = event.get("run_id", str(uuid.uuid4()))
                raw_input: Any = event.get("data", {}).get("input", {})
                tool_input = (
                    _sanitize_params(raw_input) if isinstance(raw_input, dict) else {}
                )

                # When resuming from interrupt, skip TOOL_CALL_START for the first tool
                # (events were already sent during interrupt handling in the previous stream)
                if is_resuming_from_interrupt and not resumed_tool_handled:
                    log.info(
                        f"Skipping TOOL_CALL_START for resumed tool: "
                        f"{tool_name} ({tool_run_id})"
                    )
                    resumed_tool_handled = True
                    # Still track it so we can skip TOOL_CALL_END/RESULT too
                    active_tool_calls[tool_run_id] = f"_resumed_{tool_name}"
                    continue

                active_tool_calls[tool_run_id] = tool_name
                log.info(f"on_tool_start: {tool_name} (run_id: {tool_run_id})")

                # Finish current step before starting tool execution
                if current_step and current_step != "executing_tools":
                    await protocol_handler.send_step_finished(current_step)

                await protocol_handler.send_step_started("executing_tools")
                current_step = "executing_tools"

                if protocol_handler.is_connected:
                    log.info(
                        f"[DEBUG] Sending TOOL_CALL_START: {tool_name} ({tool_run_id})"
                    )
                    await protocol_handler.send_tool_call_start(
                        tool_call_id=tool_run_id,
                        tool_call_name=tool_name,
                        tool_display_name=get_tool_display_name(tool_name),
                        tool_description=get_tool_spoken_description(tool_name),
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
                log.info(
                    f"[DEBUG] active_tool_calls before pop: {list(active_tool_calls.keys())}"
                )
                tool_name = active_tool_calls.pop(tool_run_id, None)
                output = event.get("data", {}).get("output", "")
                log.info(
                    f"[DEBUG] on_tool_end: tool_name={tool_name}, output_len={len(str(output)) if output else 0}"
                )

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
                    log.info(
                        f"[DEBUG] Skipping TOOL_CALL_END/RESULT for resumed tool: {tool_name} ({tool_run_id})"
                    )
                    continue

                log.info(f"[DEBUG] Tool completed: {tool_name} (run_id: {tool_run_id})")

                if protocol_handler.is_connected:
                    # Send TOOL_CALL_END to signal end of streaming
                    log.info(f"[DEBUG] Sending TOOL_CALL_END for {tool_run_id}")
                    await protocol_handler.send_tool_call_end(tool_call_id=tool_run_id)
                    # Send TOOL_CALL_RESULT with the actual result
                    # Always send TOOL_CALL_RESULT so frontend marks tool as completed
                    result_str = str(output)[:500] if output else ""
                    log.info(
                        f"[DEBUG] Sending TOOL_CALL_RESULT for {tool_run_id}, content_len={len(result_str)}"
                    )
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
                    log.info(
                        f"[DEBUG] Tool interrupted (not error): {tool_name} (run_id: {tool_run_id})"
                    )
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
        log.info(
            f"Stream completed, checking for interrupt. "
            f"active_tool_calls: {list(active_tool_calls.keys())}"
        )
        try:
            final_state = await self.graph.aget_state(config)  # type: ignore[arg-type]
            log.info(f"final_state.next: {final_state.next if final_state else 'None'}")

            # Check if update_user_settings was called with interaction_mode in THIS turn
            if final_state and final_state.values:
                messages = final_state.values.get("messages", [])
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
                        break

            if final_state and final_state.next:
                # Graph was interrupted - extract payload to determine type
                log.info(
                    f"Graph interrupted at node(s): {final_state.next}, "
                    f"thread: {thread_id}"
                )

                interrupt_value = None
                if final_state.tasks:
                    for task in final_state.tasks:
                        if hasattr(task, "interrupts") and task.interrupts:
                            interrupt_value = task.interrupts[0].value
                            log.info(f"Interrupt payload: {interrupt_value}")
                            break

                interrupt_type = (
                    interrupt_value.get("type")
                    if isinstance(interrupt_value, dict)
                    else None
                )

                # Close any active tool calls that were interrupted
                if active_tool_calls and protocol_handler.is_connected:
                    for tool_run_id, tool_name in list(active_tool_calls.items()):
                        log.info(
                            f"Closing interrupted tool call: {tool_name} ({tool_run_id})"
                        )
                        await protocol_handler.send_tool_call_end(
                            tool_call_id=tool_run_id
                        )
                        if interrupt_type == "clarification_request":
                            result_content = (
                                interrupt_value.get("display_text", "")
                                if isinstance(interrupt_value, dict)
                                else ""
                            ) or "Clarification requested"
                        elif interrupt_type == "tool_approval_request":
                            result_content = "Wachten op goedkeuring..."
                        else:
                            result_content = "Wachten op invoer..."
                        await protocol_handler.send_tool_call_result(
                            message_id=f"tool-result-{tool_run_id}",
                            tool_call_id=tool_run_id,
                            content=result_content,
                        )
                    active_tool_calls.clear()

                if interrupt_type == "tool_approval_request":
                    # Send approval request to frontend and store context for resumption
                    approval_id = str(uuid.uuid4())
                    i_tool_name = interrupt_value.get("tool_name", "unknown")
                    i_risk_level = interrupt_value.get("risk_level", "high")

                    self._pending_approval_context = {
                        "approval_id": approval_id,
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "message_id": message_id,
                        "user_id": user_id,
                        "interaction_mode": interaction_mode,
                    }

                    await self.audit.log_approval_request(
                        thread_id, i_tool_name, i_risk_level, approval_id
                    )

                    if protocol_handler.is_connected:
                        await protocol_handler.send_tool_approval_request(
                            tool_name=i_tool_name,
                            tool_description=get_tool_spoken_description(i_tool_name)
                            or f"Tool call: {i_tool_name}",
                            parameters=interrupt_value.get("parameters", {}),
                            reasoning=interrupt_value.get("reason")
                            or "Operation requires human approval",
                            risk_level=i_risk_level,
                            approval_id=approval_id,
                            tool_display_name=get_tool_display_name(i_tool_name),
                        )
                    log.info(
                        f"Sent approval request for {i_tool_name} "
                        f"(approval_id: {approval_id})"
                    )

                elif interrupt_type == "clarification_request":
                    # Send clarification questions as text message
                    if isinstance(interrupt_value, dict):
                        display_text = interrupt_value.get("display_text", "")
                        if display_text and protocol_handler.is_connected:
                            clarification_message = (
                                "Om het rapport te kunnen voltooien heb ik nog "
                                "enkele gegevens nodig:\n\n" + display_text
                            )

                            if not message_started:
                                await protocol_handler.send_text_message_start(
                                    message_id, "assistant"
                                )
                                await protocol_handler.send_spoken_text_start(
                                    message_id, "assistant"
                                )
                                message_started = True
                                spoken_message_started = True

                            await protocol_handler.send_text_message_content(
                                message_id, clarification_message
                            )
                            # Strip numbered list formatting for
                            # natural TTS pronunciation
                            spoken_clarification = re.sub(
                                r"\d+\.\s*", "", clarification_message
                            )
                            spoken_clarification = re.sub(
                                r"\n+", " ", spoken_clarification
                            )
                            await protocol_handler.send_spoken_text_content(
                                message_id, spoken_clarification
                            )
                            full_response.append(clarification_message)
                            log.info(
                                f"Sent clarification questions to user: "
                                f"{len(clarification_message)} chars"
                            )

        except Exception as e:
            log.error(f"Failed to check interrupt state: {e}", exc_info=True)

        # Handle listen mode responses (final_written set but no streaming happened)
        # Skip when graph is interrupted — final_written may contain stale data
        # from a previous turn
        graph_was_interrupted = final_state and final_state.next
        listen_mode_response = False
        try:
            if final_state and final_state.values and not graph_was_interrupted:
                final_written = final_state.values.get("final_written", "")
                final_spoken = final_state.values.get("final_spoken", "")
                final_interaction_mode = final_state.values.get("interaction_mode")

                # If we have final_written but didn't stream (listen mode), send it now
                if final_written and not message_started:
                    listen_mode_response = True
                    await protocol_handler.send_text_message_start(
                        message_id, "assistant"
                    )
                    await protocol_handler.send_text_message_content(
                        message_id, final_written
                    )
                    message_started = True
                    full_response.append(final_written)

                    # Also send spoken if present (from graph state, e.g. wake word handler)
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
                if (
                    final_interaction_mode
                    and final_interaction_mode != interaction_mode
                ):
                    log.info(
                        f"interaction_mode changed to '{final_interaction_mode}' "
                        f"(persisted in session state)"
                    )
        except Exception as e:
            log.warning(f"Failed to handle listen mode response: {e}")

        # Close written text channel and step BEFORE awaiting spoken
        # so the frontend can finalize the written message immediately
        if protocol_handler.is_connected:
            if message_started:
                await protocol_handler.send_text_message_end(message_id)
            # In dictate mode, spoken was already streamed alongside written
            if spoken_mode == "dictate" and spoken_message_started:
                await protocol_handler.send_spoken_text_end(message_id)
            if current_step:
                await protocol_handler.send_step_finished(current_step)

        # Generate spoken text sequentially from the completed written response
        spoken_content = ""
        if (
            spoken_mode == "summarize"
            and not graph_was_interrupted
            and not listen_mode_response
            and message_started
        ):
            try:
                written_text = "".join(full_response)
                state_messages = (
                    final_state.values.get("messages", [])
                    if final_state and final_state.values
                    else []
                )
                if state_messages:
                    spoken_messages = self._build_spoken_messages(state_messages)
                    spoken_content = await self._generate_spoken(
                        agent_id=current_agent_id,
                        messages=spoken_messages,
                        message_id=message_id,
                        protocol_handler=protocol_handler,
                        written_text=written_text,
                    )
                    spoken_message_started = spoken_message_started or bool(
                        spoken_content
                    )
            except Exception as e:
                log.warning(f"Failed to generate spoken text: {e}", exc_info=True)

        # Persist spoken_text on the AIMessage in graph state for history
        if spoken_content and final_state and not graph_was_interrupted:
            try:
                state_messages = (
                    final_state.values.get("messages", []) if final_state.values else []
                )
                for msg in reversed(state_messages):
                    if isinstance(msg, AIMessage) and msg.additional_kwargs.get(
                        "is_final_response"
                    ):
                        updated_kwargs = {**msg.additional_kwargs}
                        updated_kwargs["spoken_text"] = spoken_content
                        updated_msg = AIMessage(
                            content=msg.content,
                            id=msg.id,
                            additional_kwargs=updated_kwargs,
                        )
                        await self.graph.aupdate_state(
                            config,
                            {"messages": [updated_msg]},
                        )
                        break
            except Exception as e:
                log.warning(
                    f"Failed to update spoken_text in state: {e}", exc_info=True
                )

        # Close spoken channel after generation (summarize mode + listen mode with final_spoken)
        if protocol_handler.is_connected:
            if spoken_message_started and spoken_mode != "dictate":
                await protocol_handler.send_spoken_text_end(message_id)

        written_chars = len("".join(full_response))
        log.info(
            f"Response complete: written={written_chars} chars, "
            f"spoken_mode={spoken_mode}"
        )

        return "".join(full_response), current_agent_id

    async def get_conversation_history(
        self, thread_id: str, include_tool_calls: bool = False
    ) -> list[dict[str, Any]]:
        """Get conversation history for a session.

        Filters out consecutive AI messages without tool calls,
        keeping only the last one in each sequence (the finalized version).
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
                        content_text = extract_text(msg.content)

                        # Check for image refs in metadata (new approach)
                        image_attachment = None
                        image_refs = (
                            msg.additional_kwargs.get("image_refs", [])
                            if hasattr(msg, "additional_kwargs")
                            else []
                        )
                        if image_refs:
                            ref = image_refs[0]
                            filename = ref.get("filename", "")
                            mime_type = ref.get("mime_type", "image/jpeg")
                            file_path = self.SESSION_IMAGES_DIR / thread_id / filename
                            if file_path.exists():
                                image_attachment = {
                                    "url": f"/sessions/{thread_id}/images/{filename}",
                                    "mimeType": mime_type,
                                }

                        # Fallback: legacy multimodal messages (backward compat)
                        if not image_attachment and isinstance(msg.content, list):
                            for part in msg.content:
                                if (
                                    isinstance(part, dict)
                                    and part.get("type") == "image_url"
                                ):
                                    data_url = part.get("image_url", {}).get("url", "")
                                    mime_type = "image/jpeg"
                                    if data_url.startswith("data:"):
                                        mime_header = data_url.split(",")[0]
                                        if "image/" in mime_header:
                                            mime_type = mime_header.split(":", 1)[
                                                1
                                            ].split(";")[0]
                                    if "," in data_url:
                                        _, b64_data = data_url.split(",", 1)
                                        try:
                                            image_bytes = base64.b64decode(b64_data)
                                            content_hash = hashlib.md5(
                                                image_bytes
                                            ).hexdigest()[:12]
                                            ext = (
                                                "jpg"
                                                if "jpeg" in mime_type
                                                else mime_type.split("/")[-1]
                                            )
                                            filename = f"{content_hash}.{ext}"
                                            file_path = (
                                                self.SESSION_IMAGES_DIR
                                                / thread_id
                                                / filename
                                            )
                                            if file_path.exists():
                                                image_attachment = {
                                                    "url": f"/sessions/{thread_id}/images/{filename}",
                                                    "mimeType": mime_type,
                                                }
                                        except Exception:
                                            pass
                                    break

                        entry: dict[str, Any] = {
                            "role": "user",
                            "content": content_text,
                        }
                        if image_attachment:
                            entry["image_attachment"] = image_attachment
                        history.append(entry)
                    elif msg.type == "ai":
                        # Extract agent_id and spoken_text from additional_kwargs if present
                        agent_id = None
                        spoken_text = None
                        if hasattr(msg, "additional_kwargs"):
                            agent_id = msg.additional_kwargs.get("agent_id")
                            spoken_text = msg.additional_kwargs.get("spoken_text")

                        has_tool_calls = bool(getattr(msg, "tool_calls", None))

                        if has_tool_calls:
                            # AI message with tool calls - always include
                            prev_was_ai_without_tools = False
                            if msg.content:
                                history.append(
                                    {
                                        "role": "assistant",
                                        "content": extract_text(msg.content),
                                        "agent_id": agent_id or "",
                                        "spoken_text": spoken_text,
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
                                        "content": extract_text(msg.content),
                                        "agent_id": agent_id or "",
                                        "spoken_text": spoken_text,
                                    }
                                else:
                                    history.append(
                                        {
                                            "role": "assistant",
                                            "content": extract_text(msg.content),
                                            "agent_id": agent_id or "",
                                            "spoken_text": spoken_text,
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
                                "content": extract_text(msg.content),
                            }
                        )

            return history
        except Exception as e:
            log.error(f"Error getting conversation history: {e}")
            return []
