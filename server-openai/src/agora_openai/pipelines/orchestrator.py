from __future__ import annotations
import logging
import uuid
from common.hai_types import UserMessage, AssistantMessage
from agora_openai.core.routing_logic import AgentSelection
from agora_openai.adapters.openai_assistants import OpenAIAssistantsClient
from agora_openai.adapters.mcp_client import MCPToolClient
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.api.hai_protocol import HAIProtocolHandler

log = logging.getLogger(__name__)


class Orchestrator:
    """Minimal orchestration - OpenAI handles complexity."""
    
    def __init__(
        self,
        openai_client: OpenAIAssistantsClient,
        mcp_client: MCPToolClient,
        moderator: ModerationPipeline,
        audit_logger: AuditLogger,
    ):
        self.openai = openai_client
        self.mcp = mcp_client
        self.moderator = moderator
        self.audit = audit_logger
        self.threads: dict[str, str] = {}
    
    async def process_message(
        self,
        message: UserMessage,
        session_id: str,
        protocol_handler: HAIProtocolHandler | None = None,
    ) -> AssistantMessage:
        """Process message with OpenAI-native features.
        
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
        
        if session_id not in self.threads:
            self.threads[session_id] = await self.openai.create_thread({
                "session_id": session_id,
            })
        thread_id = self.threads[session_id]
        
        try:
            routing = await self.openai.route_with_structured_output(
                message=message.content,
                context={"session_id": session_id},
                response_model=AgentSelection,
            )
            
            log.info(
                "Routed to %s (confidence: %.2f): %s",
                routing.selected_agent,
                routing.confidence,
                routing.reasoning,
            )
            
            await self.openai.send_message(thread_id, message.content)
            
            assistant_id = self.openai.assistants[routing.selected_agent]
            
            if protocol_handler:
                message_id = str(uuid.uuid4())
                
                # Wrapper to inject protocol handler and session into tool executor
                async def tool_executor_with_notification(tool_name: str, parameters: dict) -> dict:
                    return await self._execute_tool_with_notification(
                        tool_name, parameters, protocol_handler, session_id
                    )
                
                async def stream_callback(chunk: str) -> None:
                    """Send each chunk via protocol handler."""
                    if protocol_handler and protocol_handler.is_connected:
                        await protocol_handler.send_assistant_message_chunk(
                            content=chunk,
                            session_id=session_id,
                            agent_id=routing.selected_agent,
                            message_id=message_id,
                            is_final=False,
                        )
                
                response_content = await self.openai.run_assistant_with_tools_streaming(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    tool_executor=tool_executor_with_notification,
                    stream_callback=stream_callback,
                )
                
                if protocol_handler and protocol_handler.is_connected:
                    await protocol_handler.send_assistant_message_chunk(
                        content="",
                        session_id=session_id,
                        agent_id=routing.selected_agent,
                        message_id=message_id,
                        is_final=True,
                    )
            else:
                response_content = await self.openai.run_assistant_with_tools(
                    thread_id=thread_id,
                    assistant_id=assistant_id,
                    tool_executor=self._execute_tool_with_logging,
                )
            
            is_valid, error = await self.moderator.validate_output(response_content)
            if not is_valid:
                log.warning("Output validation failed: %s", error)
                response_content = "I apologize, but I cannot provide that response."
            
            assistant_message = AssistantMessage(
                content=response_content,
                session_id=session_id,
                agent_id=routing.selected_agent,
            )
            
            await self.audit.log_message(
                session_id=session_id,
                role="assistant",
                content=response_content,
                metadata={"agent_id": routing.selected_agent},
            )
            
            return assistant_message
            
        except Exception as e:
            log.error("Error processing message: %s", e, exc_info=True)
            return AssistantMessage(
                content="I apologize, but I encountered an error processing your request.",
                session_id=session_id,
            )
    
    async def _execute_tool_with_logging(
        self,
        tool_name: str,
        parameters: dict,
    ) -> dict:
        """Execute tool and log the execution."""
        log.info("Executing tool: %s", tool_name)
        
        result = await self.mcp.execute_tool(tool_name, parameters)
        
        session_id = "unknown"
        await self.audit.log_tool_execution(
            tool_name=tool_name,
            parameters=parameters,
            result=result,
            session_id=session_id,
        )
        
        return result
    
    async def _execute_tool_with_notification(
        self,
        tool_name: str,
        parameters: dict,
        protocol_handler: HAIProtocolHandler | None,
        session_id: str,
    ) -> dict:
        """Execute tool with WebSocket notifications."""
        # Send "started" notification
        if protocol_handler and protocol_handler.is_connected:
            from common.hai_types import ToolCallMessage
            await protocol_handler.send_message(ToolCallMessage(
                tool_name=tool_name,
                parameters=parameters,
                session_id=session_id,
                status="started"
            ))
        
        # Execute the tool
        try:
            # Special handling for extract_inspection_data - inject conversation history
            if tool_name == "extract_inspection_data":
                thread_id = self.threads.get(session_id)
                if thread_id:
                    try:
                        conversation_history = await self.openai.get_thread_messages(thread_id)
                        parameters["conversation_history"] = conversation_history
                        log.info(f"Injected {len(conversation_history)} messages into extract_inspection_data")
                    except Exception as e:
                        log.warning(f"Failed to retrieve conversation history: {e}")
            
            result = await self.mcp.execute_tool(tool_name, parameters)
            
            # Send "completed" notification
            if protocol_handler and protocol_handler.is_connected:
                from common.hai_types import ToolCallMessage
                result_summary = str(result)[:100] if result else "Success"
                await protocol_handler.send_message(ToolCallMessage(
                    tool_name=tool_name,
                    parameters=parameters,
                    session_id=session_id,
                    status="completed",
                    result=result_summary
                ))
            
            # Log for audit
            await self.audit.log_tool_execution(
                tool_name=tool_name,
                parameters=parameters,
                result=result,
                session_id=session_id,
            )
            
            return result
            
        except Exception as e:
            log.error("Tool execution failed: %s", e)
            
            # Send "failed" notification
            if protocol_handler and protocol_handler.is_connected:
                from common.hai_types import ToolCallMessage
                await protocol_handler.send_message(ToolCallMessage(
                    tool_name=tool_name,
                    parameters=parameters,
                    session_id=session_id,
                    status="failed",
                    result=str(e)[:100]
                ))
            
            raise

