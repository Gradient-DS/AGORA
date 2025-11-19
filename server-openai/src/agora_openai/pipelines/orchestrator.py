from __future__ import annotations
import logging
import uuid
import asyncio
from agora_openai.common.hai_types import UserMessage, AssistantMessage
from agora_openai.common.schemas import ToolCall
from agora_openai.core.approval_logic import requires_human_approval
from agora_openai.core.agent_runner import AgentRunner
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.api.hai_protocol import HAIProtocolHandler

log = logging.getLogger(__name__)


class Orchestrator:
    """Orchestration using Agent SDK with handoffs."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
    ):
        self.agent_runner = agent_runner
        self.moderator = moderator
        self.audit = audit_logger
        self.pending_approvals: dict[str, asyncio.Future[bool]] = {}

    async def _handle_tool_approval_flow(
        self,
        tool_name: str,
        parameters: dict,
        session_id: str,
        protocol_handler: HAIProtocolHandler,
    ) -> None:
        """Handle tool approval flow logic."""
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
                session_id=session_id,
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

    async def process_message(
        self,
        message: UserMessage,
        session_id: str,
        protocol_handler: HAIProtocolHandler | None = None,
    ) -> AssistantMessage:
        """Process message with Agent SDK handoffs.

        If protocol_handler is provided, responses will be streamed in real-time.
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
            current_agent_id = {"value": None}

            if protocol_handler:

                async def stream_callback(
                    chunk: str, agent_id: str | None = None
                ) -> None:
                    """Send each chunk via protocol handler."""
                    if agent_id:
                        current_agent_id["value"] = agent_id
                    if protocol_handler and protocol_handler.is_connected:
                        await protocol_handler.send_assistant_message_chunk(
                            content=chunk,
                            session_id=session_id,
                            agent_id=current_agent_id["value"],
                            message_id=message_id,
                            is_final=False,
                        )

                async def tool_callback(
                    tool_call_id: str,
                    tool_name: str,
                    parameters: dict,
                    status: str,
                    agent_id: str | None = None,
                ) -> None:
                    """Send tool call notifications via protocol handler."""
                    if agent_id:
                        current_agent_id["value"] = agent_id
                    if protocol_handler and protocol_handler.is_connected:
                        if status == "started":
                            await self._handle_tool_approval_flow(
                                tool_name, parameters, session_id, protocol_handler
                            )

                        await protocol_handler.send_tool_call(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            parameters=parameters,
                            session_id=session_id,
                            status=status,
                            agent_id=current_agent_id["value"],
                        )

                response_content, active_agent_id = await self.agent_runner.run_agent(
                    message=message.content,
                    session_id=session_id,
                    stream_callback=stream_callback,
                    tool_callback=tool_callback,
                )

                if protocol_handler and protocol_handler.is_connected:
                    await protocol_handler.send_assistant_message_chunk(
                        content="",
                        session_id=session_id,
                        agent_id=active_agent_id,
                        message_id=message_id,
                        is_final=True,
                    )
            else:
                response_content, active_agent_id = await self.agent_runner.run_agent(
                    message=message.content,
                    session_id=session_id,
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
