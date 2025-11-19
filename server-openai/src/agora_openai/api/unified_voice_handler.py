# NOTE: This file is not used yet, but is a placeholder for future voice handling.
# TODO: Implement voice handling using STT and TTS with async text gen for both.


from __future__ import annotations
import base64
import json
import logging
from typing import Any
import numpy as np
from fastapi import WebSocket
from agents.voice import (
    AudioInput,
    SingleAgentVoiceWorkflow,
    VoicePipeline,
    VoicePipelineConfig,
    TTSModelSettings,
)
from agora_openai.core.agent_runner import AgentRegistry

log = logging.getLogger(__name__)

AUDIO_CONFIG = {
    "samplerate": 24000,
    "channels": 1,
    "dtype": "int16",
    "blocksize": 2400,
}


TTS_SETTINGS_BY_AGENT = {
    "general-agent": TTSModelSettings(
        instructions=(
            "Personality: Friendly, helpful, and professional NVWA assistant\n"
            "Tone: Warm and welcoming, like a knowledgeable colleague\n"
            "Pronunciation: Clear and natural Dutch pronunciation\n"
            "Tempo: Moderate pace with natural pauses\n"
            "Emotion: Approachable and supportive"
        )
    ),
    "history-agent": TTSModelSettings(
        instructions=(
            "Personality: Detail-oriented company information specialist\n"
            "Tone: Professional and thorough, conveying expertise in inspection history\n"
            "Pronunciation: Clear articulation of company names, KVK numbers, and dates\n"
            "Tempo: Steady pace with emphasis on key data points\n"
            "Emotion: Confident and analytical when discussing historical patterns"
        )
    ),
    "regulation-agent": TTSModelSettings(
        instructions=(
            "Personality: Expert regulatory compliance advisor\n"
            "Tone: Authoritative yet approachable, making complex regulations understandable\n"
            "Pronunciation: Clear emphasis on regulation names and compliance terms\n"
            "Tempo: Moderate pace with pauses after important regulatory points\n"
            "Emotion: Serious but reassuring, emphasizing safety and compliance"
        )
    ),
    "reporting-agent": TTSModelSettings(
        instructions=(
            "Personality: Thorough documentation specialist\n"
            "Tone: Methodical and precise, ensuring accuracy in reporting\n"
            "Pronunciation: Clear articulation of inspection findings and action items\n"
            "Tempo: Steady pace with natural pauses between sections\n"
            "Emotion: Professional and systematic, conveying completeness"
        )
    ),
}


def get_tts_settings_for_agent(agent_id: str) -> TTSModelSettings:
    """Get TTS settings for a specific agent, with fallback to general agent."""
    return TTS_SETTINGS_BY_AGENT.get(agent_id, TTS_SETTINGS_BY_AGENT["general-agent"])


class UnifiedVoiceHandler:
    """Unified voice handler using Agents SDK VoicePipeline for both text and voice."""

    def __init__(
        self,
        client_ws: WebSocket,
        agent_registry: AgentRegistry,
    ):
        self.client_ws = client_ws
        self.agent_registry = agent_registry
        self.is_active = False
        self.session_id: str | None = None
        self.current_agent_id: str = "general-agent"
        self.pipeline: VoicePipeline | None = None

    async def start(
        self,
        session_id: str,
        agent_id: str = "general-agent",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> None:
        """Start unified voice session with Agent SDK pipeline."""
        self.session_id = session_id
        self.current_agent_id = agent_id
        self.is_active = True

        log.info(f"Starting unified voice session: {session_id} with agent: {agent_id}")

        agent = self.agent_registry.get_agent(agent_id)
        if not agent:
            log.error(f"Agent {agent_id} not found, using general-agent")
            agent = self.agent_registry.get_entry_agent()
            self.current_agent_id = "general-agent"

        tts_settings = get_tts_settings_for_agent(self.current_agent_id)

        voice_config = VoicePipelineConfig(
            tts_settings=tts_settings,
        )

        self.pipeline = VoicePipeline(
            workflow=SingleAgentVoiceWorkflow(agent),
            config=voice_config,
        )

        await self._send_to_client(
            {"type": "session.started", "session_id": session_id, "agent_id": agent_id}
        )

        log.info(f"Unified voice session started successfully: {session_id}")

    async def stop(self) -> None:
        """Stop voice session."""
        self.is_active = False
        self.pipeline = None
        log.info(f"Unified voice session stopped: {self.session_id}")

    async def handle_client_message(self, message: dict[str, Any]) -> None:
        """Handle message from client."""
        msg_type = message.get("type")

        if msg_type == "audio.data":
            await self._handle_audio_data(message)
        elif msg_type == "text.message":
            await self._handle_text_message(message)
        else:
            log.warning(f"Unknown client message type: {msg_type}")

    async def _process_pipeline_result(self, result: Any) -> None:
        """Process streaming results from the voice pipeline."""
        transcript_parts = []

        async for event in result.stream():
            if event.type == "voice_stream_event_audio":
                audio_chunk_base64 = base64.b64encode(event.data).decode("utf-8")
                await self._send_to_client(
                    {"type": "audio.response", "audio": audio_chunk_base64}
                )
            elif event.type == "voice_stream_event_transcript":
                transcript_parts.append(event.text)
                await self._send_to_client(
                    {"type": "transcript.delta", "text": event.text}
                )
            elif event.type == "voice_stream_event_tool_call":
                await self._send_to_client(
                    {
                        "type": "tool.executing",
                        "tool_name": event.name,
                        "call_id": (
                            str(event.call_id) if hasattr(event, "call_id") else None
                        ),
                    }
                )
            elif event.type == "voice_stream_event_tool_result":
                await self._send_to_client(
                    {
                        "type": "tool.completed",
                        "tool_name": (
                            event.name if hasattr(event, "name") else "unknown"
                        ),
                        "call_id": (
                            str(event.call_id) if hasattr(event, "call_id") else None
                        ),
                    }
                )

        full_transcript = "".join(transcript_parts)
        if full_transcript:
            await self._send_to_client(
                {"type": "transcript.assistant", "text": full_transcript}
            )

        await self._send_to_client({"type": "response.completed"})

    async def _handle_audio_data(self, message: dict[str, Any]) -> None:
        """Handle audio data from client using VoicePipeline."""
        audio_base64 = message.get("audio")
        if not audio_base64:
            log.warning("Received audio.data message without audio field")
            return

        try:
            await self._send_to_client({"type": "speech.started"})

            audio_bytes = base64.b64decode(audio_base64)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

            if not self.pipeline:
                log.error("Pipeline not initialized")
                await self._send_error(
                    "pipeline_error", "Voice pipeline not initialized"
                )
                return

            audio_input = AudioInput(buffer=audio_array)

            log.info("Processing audio with VoicePipeline...")
            result = await self.pipeline.run(audio_input)
            await self._process_pipeline_result(result)

        except Exception as e:
            log.error(f"Error processing audio data: {e}", exc_info=True)
            await self._send_error("audio_processing_error", str(e))

    async def _handle_text_message(self, message: dict[str, Any]) -> None:
        """Handle text message from client (for testing voice mode with text)."""
        text = message.get("text")
        if not text:
            return

        try:
            await self._send_to_client({"type": "speech.started"})

            if not self.pipeline:
                log.error("Pipeline not initialized")
                await self._send_error(
                    "pipeline_error", "Voice pipeline not initialized"
                )
                return

            empty_audio = np.zeros(AUDIO_CONFIG["samplerate"], dtype=np.int16)
            audio_input = AudioInput(buffer=empty_audio)

            log.info(f"Processing text message via pipeline: {text}")
            # TODO: Check if pipeline.run supports text input directly
            result = await self.pipeline.run(audio_input)
            await self._process_pipeline_result(result)

        except Exception as e:
            log.error(f"Error processing text message: {e}", exc_info=True)
            await self._send_error("text_processing_error", str(e))

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
