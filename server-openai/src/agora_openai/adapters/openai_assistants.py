from __future__ import annotations
from typing import Any, Callable
import logging
import asyncio
import json
from openai import AsyncOpenAI
from agora_openai.core.routing_logic import ROUTING_SYSTEM_PROMPT

log = logging.getLogger(__name__)


class OpenAIAssistantsClient:
    """Wrapper for OpenAI Assistants API - leverages native features."""
    
    def __init__(self, api_key: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.assistants: dict[str, str] = {}
    
    async def initialize_assistant(
        self,
        agent_id: str,
        name: str,
        instructions: str,
        model: str,
        tools: list[dict[str, Any]],
        temperature: float = 0.7,
    ) -> str:
        """Create OpenAI Assistant. Returns assistant_id."""
        assistant = await self.client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            temperature=temperature,
        )
        
        self.assistants[agent_id] = assistant.id
        log.info("Created assistant %s: %s", agent_id, assistant.id)
        return assistant.id
    
    async def create_thread(self, metadata: dict[str, Any] | None = None) -> str:
        """Create conversation thread. Returns thread_id."""
        thread = await self.client.beta.threads.create(metadata=metadata or {})
        log.info("Created thread: %s", thread.id)
        return thread.id
    
    async def send_message(self, thread_id: str, content: str) -> None:
        """Add user message to thread."""
        await self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )
    
    async def run_assistant_with_tools(
        self,
        thread_id: str,
        assistant_id: str,
        tool_executor: Callable[[str, dict[str, Any]], Any],
    ) -> str:
        """Run assistant with automatic tool execution loop.
        
        OpenAI handles the loop automatically!
        """
        run = await self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
        )
        
        while True:
            await asyncio.sleep(0.5)
            
            run = await self.client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id,
            )
            
            log.info("Run %s status: %s", run.id, run.status)
            
            if run.status == "completed":
                break
            
            elif run.status == "requires_action":
                tool_outputs = await self._execute_required_tools(
                    run,
                    tool_executor,
                )
                
                await self.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                )
            
            elif run.status in ["failed", "cancelled", "expired"]:
                error_msg = str(run.last_error) if run.last_error else run.status
                raise Exception(f"Run {run.status}: {error_msg}")
        
        messages = await self.client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=1,
        )
        
        message_content = messages.data[0].content[0]
        if hasattr(message_content, "text"):
            return message_content.text.value
        return str(message_content)
    
    async def run_assistant_with_tools_streaming(
        self,
        thread_id: str,
        assistant_id: str,
        tool_executor: Callable[[str, dict[str, Any]], Any],
        stream_callback: Callable[[str], Any],
    ) -> str:
        """Run assistant with streaming support using OpenAI's stream API.
        
        Streams text chunks via callback and handles tool calls during streaming.
        When tool calls are required, the stream ends and we need to handle them separately.
        """
        full_response = []
        run_id = None
        
        try:
            async with self.client.beta.threads.runs.stream(
                thread_id=thread_id,
                assistant_id=assistant_id,
            ) as stream:
                async for event in stream:
                    log.debug("Stream event: %s", event.event)
                    
                    if event.event == "thread.run.created":
                        run_id = event.data.id
                    
                    elif event.event == "thread.message.delta":
                        if hasattr(event.data, "delta") and hasattr(event.data.delta, "content"):
                            for content_block in event.data.delta.content:
                                if hasattr(content_block, "text") and hasattr(content_block.text, "value"):
                                    chunk = content_block.text.value
                                    full_response.append(chunk)
                                    await stream_callback(chunk)
                    
                    elif event.event == "thread.run.requires_action":
                        log.info("Stream paused for tool execution")
                        run = event.data
                        run_id = run.id
                        break
                    
                    elif event.event == "thread.run.failed":
                        error_msg = str(event.data.last_error) if event.data.last_error else "Unknown error"
                        raise Exception(f"Run failed: {error_msg}")
                    
                    elif event.event == "thread.run.cancelled":
                        raise Exception("Run was cancelled")
                    
                    elif event.event == "thread.run.expired":
                        raise Exception("Run expired")
        
        except Exception as e:
            if "requires_action" not in str(e):
                raise
        
        if run_id:
            run = await self.client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id,
            )
            
            if run.status == "requires_action":
                tool_outputs = await self._execute_required_tools(
                    run,
                    tool_executor,
                )
                
                async with self.client.beta.threads.runs.submit_tool_outputs_stream(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                ) as stream:
                    async for event in stream:
                        log.debug("Post-tool stream event: %s", event.event)
                        
                        if event.event == "thread.message.delta":
                            if hasattr(event.data, "delta") and hasattr(event.data.delta, "content"):
                                for content_block in event.data.delta.content:
                                    if hasattr(content_block, "text") and hasattr(content_block.text, "value"):
                                        chunk = content_block.text.value
                                        full_response.append(chunk)
                                        await stream_callback(chunk)
                        
                        elif event.event == "thread.run.failed":
                            error_msg = str(event.data.last_error) if event.data.last_error else "Unknown error"
                            raise Exception(f"Run failed: {error_msg}")
                        
                        elif event.event == "thread.run.cancelled":
                            raise Exception("Run was cancelled")
                        
                        elif event.event == "thread.run.expired":
                            raise Exception("Run expired")
        
        return "".join(full_response)
    
    async def _execute_required_tools(
        self,
        run: Any,
        tool_executor: Callable[[str, dict[str, Any]], Any],
    ) -> list[dict[str, str]]:
        """Execute tools that OpenAI requests."""
        tool_outputs = []
        
        if not run.required_action or not run.required_action.submit_tool_outputs:
            return tool_outputs
        
        for tool_call in run.required_action.submit_tool_outputs.tool_calls:
            try:
                args = json.loads(tool_call.function.arguments)
                result = await tool_executor(tool_call.function.name, args)
                
                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(result),
                })
            except Exception as e:
                log.error("Tool execution failed: %s", e, exc_info=True)
                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps({"error": str(e)}),
                })
        
        return tool_outputs
    
    async def route_with_structured_output(
        self,
        message: str,
        context: dict[str, Any],
        response_model: type,
    ) -> Any:
        """Use structured outputs for intelligent routing.
        
        Guaranteed schema compliance!
        """
        response = await self.client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
                {"role": "user", "content": f"Request: {message}\n\nContext: {context}"},
            ],
            response_format=response_model,
        )
        
        return response.choices[0].message.parsed

