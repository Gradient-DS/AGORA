from __future__ import annotations
import logging
from common.hai_types import UserMessage, AssistantMessage
from agora_openai.core.routing_logic import AgentSelection
from agora_openai.adapters.openai_assistants import OpenAIAssistantsClient
from agora_openai.adapters.mcp_client import MCPToolClient
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline

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
    ) -> AssistantMessage:
        """Process message with OpenAI-native features."""
        
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
        result = await self.mcp.execute_tool(tool_name, parameters)
        
        session_id = "unknown"
        await self.audit.log_tool_execution(
            tool_name=tool_name,
            parameters=parameters,
            result=result,
            session_id=session_id,
        )
        
        return result

