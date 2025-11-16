from __future__ import annotations
import base64
import json
import logging
from typing import Any
from fastapi import WebSocket
from agora_openai.adapters.realtime_client import OpenAIRealtimeClient
from agora_openai.adapters.mcp_client import MCPToolClient

log = logging.getLogger(__name__)


class VoiceSessionHandler:
    """Handle voice session between client and OpenAI Realtime API with tool support."""

    def __init__(
        self,
        client_ws: WebSocket,
        realtime_client: OpenAIRealtimeClient,
        mcp_client: MCPToolClient,
    ):
        self.client_ws = client_ws
        self.realtime_client = realtime_client
        self.mcp_client = mcp_client
        self.is_active = False
        self.session_id: str | None = None
        self.pending_tool_calls: dict[str, dict[str, Any]] = {}

    async def start(
        self, 
        session_id: str, 
        instructions: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> None:
        """Start voice session."""
        self.session_id = session_id
        self.is_active = True

        log.info(f"Starting voice session: {session_id}")

        default_instructions = """You are a helpful AI assistant in the AGORA system.
You are engaging in a voice conversation with the user.
Be conversational, friendly, and concise in your responses.
You have access to specialized tools for compliance checking, risk analysis, reporting, and regulatory information.
When the user needs these capabilities, use the available tools to help them.
Always explain what you're doing when using tools."""

        # Get available tools from MCP client
        tools = self.mcp_client.tool_definitions if self.mcp_client.tool_definitions else []
        
        log.info(f"Registering {len(tools)} tools for voice session")

        session_config = {
            "modalities": ["text", "audio"],
            "instructions": instructions or default_instructions,
            "voice": "alloy",
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
            },
            "temperature": 0.8,
            "tools": tools,  # Register MCP tools
            "tool_choice": "auto",  # Let AI decide when to use tools
        }

        self.realtime_client.on_message(self._handle_openai_message)
        
        log.info("Connecting to OpenAI Realtime API...")
        try:
            await self.realtime_client.connect(session_config)
        except Exception as e:
            log.error(f"Failed to connect to OpenAI Realtime API: {e}")
            await self._send_error("connection_error", f"Failed to connect: {str(e)}")
            self.is_active = False
            return

        if conversation_history:
            log.info(f"Loading {len(conversation_history)} previous messages into voice context")
            for msg in conversation_history:
                await self.realtime_client.send_conversation_item(
                    role=msg.get("role", "user"),
                    text=msg.get("content", "")
                )

        await self._send_to_client(
            {"type": "session.started", "session_id": session_id}
        )

        log.info(f"Voice session started successfully: {session_id}")

    async def stop(self) -> None:
        """Stop voice session."""
        self.is_active = False
        await self.realtime_client.disconnect()
        log.info(f"Voice session stopped: {self.session_id}")

    async def handle_client_message(self, message: dict[str, Any]) -> None:
        """Handle message from client."""
        msg_type = message.get("type")

        if msg_type == "audio.data":
            await self._handle_audio_data(message)
        elif msg_type == "audio.commit":
            await self.realtime_client.commit_audio_buffer()
        elif msg_type == "text.message":
            await self._handle_text_message(message)
        elif msg_type == "response.cancel":
            await self.realtime_client.cancel_response()
        else:
            log.warning(f"Unknown client message type: {msg_type}")

    async def _handle_audio_data(self, message: dict[str, Any]) -> None:
        """Handle audio data from client."""
        audio_base64 = message.get("audio")
        if not audio_base64:
            log.warning("Received audio.data message without audio field")
            return

        try:
            audio_bytes = base64.b64decode(audio_base64)
            await self.realtime_client.send_audio(audio_bytes)
        except Exception as e:
            log.error(f"Error processing audio data: {e}", exc_info=True)
            await self._send_error("audio_processing_error", str(e))

    async def _handle_text_message(self, message: dict[str, Any]) -> None:
        """Handle text message from client."""
        text = message.get("text")
        if text:
            await self.realtime_client.send_text(text)

    async def _handle_openai_message(self, event: dict[str, Any]) -> None:
        """Handle message from OpenAI Realtime API."""
        event_type = event.get("type")

        if event_type == "error":
            await self._send_error(
                "openai_error", event.get("error", {}).get("message", "Unknown error")
            )
            return

        if event_type == "session.created":
            log.info("OpenAI session created")
            return

        if event_type == "session.updated":
            log.info("OpenAI session updated")
            return

        if event_type == "input_audio_buffer.speech_started":
            await self._send_to_client({"type": "speech.started"})

        elif event_type == "input_audio_buffer.speech_stopped":
            await self._send_to_client({"type": "speech.stopped"})

        elif event_type == "input_audio_buffer.committed":
            await self._send_to_client({"type": "audio.committed"})

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "")
            await self._send_to_client(
                {"type": "transcript.user", "text": transcript}
            )

        elif event_type == "response.audio.delta":
            audio_base64 = event.get("delta")
            if audio_base64:
                await self._send_to_client(
                    {"type": "audio.response", "audio": audio_base64}
                )

        elif event_type == "response.audio_transcript.delta":
            text_delta = event.get("delta", "")
            await self._send_to_client(
                {"type": "transcript.delta", "text": text_delta}
            )

        elif event_type == "response.function_call_arguments.done":
            # Function call completed, execute the tool
            call_id = event.get("call_id")
            name = event.get("name")
            arguments = event.get("arguments")
            
            log.info(f"Function call requested: {name} with call_id: {call_id}")
            
            await self._send_to_client({
                "type": "tool.executing",
                "tool_name": name,
                "call_id": call_id,
            })
            
            # Execute tool via MCP client
            try:
                result = await self.mcp_client.execute_tool(name, json.loads(arguments))
                log.info(f"Tool {name} executed successfully")
                
                # Send result back to Realtime API
                await self.realtime_client.send_function_result(call_id, result)
                
                await self._send_to_client({
                    "type": "tool.completed",
                    "tool_name": name,
                    "call_id": call_id,
                })
                
            except Exception as e:
                log.error(f"Error executing tool {name}: {e}", exc_info=True)
                error_result = {"error": str(e)}
                await self.realtime_client.send_function_result(call_id, error_result)
                
                await self._send_to_client({
                    "type": "tool.failed",
                    "tool_name": name,
                    "call_id": call_id,
                    "error": str(e),
                })

        elif event_type == "response.done":
            response = event.get("response", {})
            status = response.get("status")
            if status == "completed":
                await self._send_to_client({"type": "response.completed"})
            elif status == "cancelled":
                await self._send_to_client({"type": "response.cancelled"})
            elif status == "failed":
                await self._send_to_client(
                    {
                        "type": "response.failed",
                        "error": response.get("status_details", {}).get("error"),
                    }
                )

        elif event_type == "response.output_item.done":
            item = event.get("item", {})
            if item.get("type") == "message":
                content = item.get("content", [])
                for content_part in content:
                    if content_part.get("type") == "text":
                        text = content_part.get("text", "")
                        await self._send_to_client(
                            {"type": "transcript.assistant", "text": text}
                        )

        elif event_type == "rate_limits.updated":
            log.debug(f"Rate limits updated: {event.get('rate_limits')}")

        else:
            log.debug(f"Unhandled event type: {event_type}")

    async def _send_to_client(self, message: dict[str, Any]) -> None:
        """Send message to client WebSocket."""
        try:
            await self.client_ws.send_text(json.dumps(message))
        except Exception as e:
            log.error(f"Error sending to client: {e}", exc_info=True)
            self.is_active = False

    async def _send_error(self, error_code: str, message: str) -> None:
        """Send error to client."""
        await self._send_to_client(
            {"type": "error", "error_code": error_code, "message": message}
        )

