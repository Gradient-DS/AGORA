from __future__ import annotations
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from agora_openai.config import get_settings, parse_mcp_servers
from agora_openai.logging_config import configure_logging
from agora_openai.core.agent_definitions import AGENT_CONFIGS
from agora_openai.adapters.openai_assistants import OpenAIAssistantsClient
from agora_openai.adapters.mcp_client import MCPToolClient
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.pipelines.orchestrator import Orchestrator
from agora_openai.api.hai_protocol import HAIProtocolHandler
from agora_openai.api.voice_handler import VoiceSessionHandler
from agora_openai.adapters.realtime_client import OpenAIRealtimeClient

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize OpenAI Assistants on startup."""
    settings = get_settings()
    
    configure_logging(settings.log_level)
    log.info("Starting AGORA OpenAI Orchestration Server")
    
    openai_client = OpenAIAssistantsClient(
        api_key=settings.openai_api_key.get_secret_value()
    )
    
    mcp_client = MCPToolClient(parse_mcp_servers(settings.mcp_servers))
    
    mcp_tools = await mcp_client.discover_tools()
    log.info("Discovered %d MCP tools", len(mcp_tools))
    
    for agent_config in AGENT_CONFIGS:
        builtin_tools = [
            {"type": tool_type}
            for tool_type in agent_config["tools"]
        ]
        all_tools = builtin_tools + mcp_tools
        
        await openai_client.initialize_assistant(
            agent_id=agent_config["id"],
            name=agent_config["name"],
            instructions=agent_config["instructions"],
            model=agent_config["model"],
            tools=all_tools,
            temperature=agent_config["temperature"],
        )
    
    log.info("Initialized %d assistants", len(AGENT_CONFIGS))
    
    moderator = ModerationPipeline(enabled=settings.guardrails_enabled)
    audit_logger = AuditLogger(otel_endpoint=settings.otel_endpoint)
    
    orchestrator = Orchestrator(
        openai_client=openai_client,
        mcp_client=mcp_client,
        moderator=moderator,
        audit_logger=audit_logger,
    )
    
    app.state.orchestrator = orchestrator
    
    yield
    
    log.info("Shutting down AGORA OpenAI Orchestration Server")


app = FastAPI(
    title="AGORA OpenAI Orchestration",
    description="OpenAI-native orchestration for AGORA multi-agent system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "agora-openai"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AGORA OpenAI Orchestration",
        "version": "1.0.0",
        "docs": "/docs",
        "websocket": "/ws",
        "voice_websocket": "/ws/voice",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for HAI protocol."""
    await websocket.accept()
    
    handler = HAIProtocolHandler(websocket)
    orchestrator: Orchestrator = app.state.orchestrator
    
    log.info("=" * 80)
    log.info("WebSocket connection ESTABLISHED from %s", websocket.client)
    log.info("=" * 80)
    
    try:
        while True:
            if not handler.is_connected:
                log.info("Handler reports connection is closed, exiting loop")
                break
                
            try:
                user_message = await handler.receive_message()
                
                if user_message is None:
                    if not handler.is_connected:
                        log.info("Connection closed during receive, exiting loop")
                        break
                    continue
                
                session_id = user_message.session_id
                log.info(f"Processing message for session: {session_id}")
                
                await handler.send_status("routing", "Analyzing request...", session_id)
                
                if not handler.is_connected:
                    log.info("Connection closed after status send, exiting loop")
                    break
                
                response = await orchestrator.process_message(user_message, session_id, handler)
                log.info(f"Got response from orchestrator: type={response.type}, has_content={bool(response.content)}")
                
                if not handler.is_connected:
                    log.info("Connection closed after response send, exiting loop")
                    break
                    
                log.info(f"Response sent successfully for session: {session_id}")
                
            except WebSocketDisconnect:
                log.info("WebSocket disconnected by client")
                handler.is_connected = False
                raise
            except Exception as e:
                log.error("=" * 80)
                log.error("ERROR PROCESSING MESSAGE")
                log.error("=" * 80)
                log.error("Error: %s", e, exc_info=True)
                log.error("=" * 80)
                
                if handler.is_connected:
                    try:
                        await handler.send_error("processing_error", f"Error processing message: {str(e)}")
                        if handler.is_connected:
                            log.info("Error message sent to client, connection maintained")
                        else:
                            log.info("Connection closed while sending error, exiting loop")
                            break
                    except Exception as send_err:
                        log.error("Failed to send error message: %s", send_err)
                        log.error("Connection will be closed")
                        handler.is_connected = False
                        raise
                else:
                    log.info("Connection already closed, cannot send error message")
                    break
            
    except WebSocketDisconnect:
        log.info("=" * 80)
        log.info("WebSocket connection CLOSED")
        log.info("=" * 80)
    except Exception as e:
        log.error("=" * 80)
        log.error("FATAL WebSocket error - connection will close")
        log.error("=" * 80)
        log.error("Fatal WebSocket error: %s", e, exc_info=True)
        log.error("=" * 80)
        try:
            await handler.send_error("internal_error", "Internal server error")
        except Exception:
            pass


@app.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for voice mode using OpenAI Realtime API with tool support."""
    await websocket.accept()
    
    settings = get_settings()
    
    log.info("=" * 80)
    log.info("Voice WebSocket connection ESTABLISHED from %s", websocket.client)
    log.info("=" * 80)
    
    realtime_client = OpenAIRealtimeClient(
        api_key=settings.openai_api_key.get_secret_value()
    )
    
    orchestrator: Orchestrator = app.state.orchestrator
    mcp_client = orchestrator.mcp
    
    handler = VoiceSessionHandler(websocket, realtime_client, mcp_client)
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "session.start":
                    session_id = message.get("session_id", "default")
                    instructions = message.get("instructions")
                    conversation_history = message.get("conversation_history", [])
                    await handler.start(session_id, instructions, conversation_history)
                
                elif message.get("type") == "session.stop":
                    await handler.stop()
                    break
                
                elif handler.is_active:
                    await handler.handle_client_message(message)
                else:
                    log.warning("Received message but session not active")
                    
            except WebSocketDisconnect:
                log.info("Voice WebSocket disconnected by client")
                break
            except json.JSONDecodeError as e:
                log.error("Invalid JSON received: %s", e)
            except Exception as e:
                log.error("Error processing voice message: %s", e, exc_info=True)
                try:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "error_code": "processing_error",
                                "message": str(e),
                            }
                        )
                    )
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        log.info("=" * 80)
        log.info("Voice WebSocket connection CLOSED")
        log.info("=" * 80)
    except Exception as e:
        log.error("=" * 80)
        log.error("FATAL Voice WebSocket error - connection will close")
        log.error("=" * 80)
        log.error("Fatal error: %s", e, exc_info=True)
    finally:
        if handler.is_active:
            await handler.stop()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "agora_openai.api.server:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )

