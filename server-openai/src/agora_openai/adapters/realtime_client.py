from __future__ import annotations
import asyncio
import base64
import json
import logging
from typing import Any, Callable, Awaitable
import websockets
from websockets.client import WebSocketClientProtocol

log = logging.getLogger(__name__)


class OpenAIRealtimeClient:
    """Client for OpenAI Realtime API with WebSocket communication."""

    def __init__(self, api_key: str, model: str = "gpt-4o-realtime-preview-2024-10-01"):
        self.api_key = api_key
        self.model = model
        self.ws: WebSocketClientProtocol | None = None
        self.is_connected = False
        self._message_handlers: list[Callable[[dict[str, Any]], Awaitable[None]]] = []

    async def connect(self, session_config: dict[str, Any] | None = None) -> None:
        """Connect to OpenAI Realtime API."""
        if self.is_connected:
            log.warning("Already connected to Realtime API")
            return

        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        log.info(f"Connecting to OpenAI Realtime API: {url}")
        log.debug(f"Using model: {self.model}")

        try:
            self.ws = await websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=20,
            )
            self.is_connected = True
            log.info("WebSocket connected to OpenAI Realtime API")

            asyncio.create_task(self._message_loop())

            await asyncio.sleep(0.5)

            if session_config:
                log.info("Updating session configuration")
                await self.update_session(session_config)

            log.info("OpenAI Realtime API fully initialized")

        except websockets.exceptions.InvalidStatusCode as e:
            log.error(f"Invalid status code from Realtime API: {e.status_code}")
            log.error(f"Headers: {e.headers}")
            raise
        except Exception as e:
            log.error(f"Failed to connect to Realtime API: {e}", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Disconnect from OpenAI Realtime API."""
        if self.ws:
            self.is_connected = False
            await self.ws.close()
            self.ws = None
            log.info("Disconnected from OpenAI Realtime API")

    async def update_session(self, config: dict[str, Any]) -> None:
        """Update session configuration."""
        await self._send_event("session.update", {"session": config})

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to OpenAI."""
        base64_audio = base64.b64encode(audio_data).decode("utf-8")
        await self._send_event("input_audio_buffer.append", {"audio": base64_audio})

    async def commit_audio_buffer(self) -> None:
        """Commit the audio buffer and trigger a response."""
        await self._send_event("input_audio_buffer.commit", {})

    async def create_response(self) -> None:
        """Request the model to generate a response."""
        await self._send_event("response.create", {})

    async def send_text(self, text: str, role: str = "user") -> None:
        """Send a text message (creates a conversation item)."""
        await self._send_event(
            "conversation.item.create",
            {
                "item": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                }
            },
        )
        await self.create_response()

    async def send_conversation_item(self, role: str, text: str) -> None:
        """Add a conversation item without triggering a response (for context loading)."""
        await self._send_event(
            "conversation.item.create",
            {
                "item": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                }
            },
        )

    async def send_function_result(self, call_id: str, result: dict[str, Any]) -> None:
        """Send function call result back to OpenAI."""
        await self._send_event(
            "conversation.item.create",
            {
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                }
            },
        )
        # Create a response after sending the function result
        await self.create_response()

    async def cancel_response(self) -> None:
        """Cancel the current response generation."""
        await self._send_event("response.cancel", {})

    def on_message(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Register a message handler."""
        self._message_handlers.append(handler)

    async def _send_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Send an event to OpenAI."""
        if not self.ws or not self.is_connected:
            log.warning(f"Cannot send event {event_type}, not connected")
            return

        event = {"type": event_type, **data}
        try:
            await self.ws.send(json.dumps(event))
            log.debug(f"Sent event: {event_type}")
        except websockets.exceptions.ConnectionClosed as e:
            log.error(f"Connection closed while sending {event_type}: {e}")
            self.is_connected = False
        except Exception as e:
            log.error(f"Error sending event {event_type}: {e}", exc_info=True)
            self.is_connected = False

    async def _message_loop(self) -> None:
        """Continuously receive messages from OpenAI."""
        if not self.ws:
            return

        log.info("Starting message loop for OpenAI Realtime API")
        try:
            async for message in self.ws:
                if not self.is_connected:
                    log.info("Connection marked as closed, exiting message loop")
                    break

                try:
                    data = json.loads(message)
                    event_type = data.get('type')
                    log.debug(f"Received event: {event_type}")

                    if event_type == "error":
                        log.error(f"Error from OpenAI: {data.get('error')}")

                    for handler in self._message_handlers:
                        try:
                            await handler(data)
                        except Exception as e:
                            log.error(f"Error in message handler: {e}", exc_info=True)

                except json.JSONDecodeError as e:
                    log.error(f"Invalid JSON from Realtime API: {e}")
                except Exception as e:
                    log.error(f"Error processing message: {e}", exc_info=True)

        except websockets.exceptions.ConnectionClosed as e:
            log.warning(f"Realtime API connection closed: code={e.code}, reason={e.reason}")
        except Exception as e:
            log.error(f"Error in message loop: {e}", exc_info=True)
        finally:
            self.is_connected = False
            log.info("Message loop ended")

