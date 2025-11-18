from __future__ import annotations
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from agora_openai.config import get_settings, parse_mcp_servers
from agora_openai.logging_config import configure_logging
from agora_openai.core.agent_definitions import AGENT_CONFIGS, list_all_agents
from agora_openai.core.agent_runner import AgentRegistry, AgentRunner
from agora_openai.adapters.mcp_tools import MCPToolRegistry
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.pipelines.orchestrator import Orchestrator
from agora_openai.api.hai_protocol import HAIProtocolHandler
from agora_openai.api.unified_voice_handler import UnifiedVoiceHandler

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize Agent SDK agents on startup."""
    settings = get_settings()
    
    configure_logging(settings.log_level)
    log.info("Starting AGORA Agent SDK Server")
    
    # Set OPENAI_API_KEY for Agents SDK
    import os
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key.get_secret_value()
    log.info("Configured OpenAI API key for Agents SDK")
    
    mcp_servers = parse_mcp_servers(settings.mcp_servers)
    log.info("MCP Servers configured: %s", mcp_servers)
    
    mcp_tool_registry = MCPToolRegistry(mcp_servers)
    
    await mcp_tool_registry.discover_and_register_tools()
    log.info("Discovered and registered MCP servers")
    
    agent_registry = AgentRegistry(mcp_tool_registry)
    
    for agent_config in AGENT_CONFIGS:
        agent_registry.register_agent(agent_config)
    
    agent_registry.configure_handoffs()
    log.info("Configured agent handoffs")
    
    agent_runner = AgentRunner(agent_registry)
    
    moderator = ModerationPipeline(enabled=settings.guardrails_enabled)
    audit_logger = AuditLogger(otel_endpoint=settings.otel_endpoint)
    
    orchestrator = Orchestrator(
        agent_runner=agent_runner,
        moderator=moderator,
        audit_logger=audit_logger,
    )
    
    app.state.orchestrator = orchestrator
    app.state.agent_registry = agent_registry
    app.state.mcp_tool_registry = mcp_tool_registry
    
    yield
    
    log.info("Shutting down AGORA Agent SDK Server")
    await mcp_tool_registry.disconnect_all()


app = FastAPI(
    title="AGORA Agent SDK Orchestration",
    description="Agent SDK orchestration for AGORA multi-agent system",
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
    return {"status": "healthy", "service": "agora-agents"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AGORA Agent SDK Orchestration",
        "version": "1.0.0",
        "docs": "/docs",
        "websocket": "/ws",
        "voice_websocket": "/ws/voice",
    }


@app.get("/agents")
async def get_agents():
    """Get list of active and inactive agents."""
    agents = list_all_agents()
    return {
        "active_agents": [
            {
                "id": agent["id"],
                "name": agent["name"],
                "model": agent["model"],
                "description": agent["instructions"].split("\n\n")[0],
            }
            for agent in agents["active"]
        ],
        "inactive_agents": agents["inactive"],
    }


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, include_tools: bool = False):
    """Get conversation history for a session.
    
    This endpoint is used by MCP servers (like reporting) to retrieve
    conversation history from the Agents SDK SQLite session storage.
    
    Args:
        session_id: Session identifier
        include_tools: If True, includes tool calls and results in the history
    
    Returns:
        Conversation history with user, assistant, and optionally tool messages
    """
    orchestrator: Orchestrator = app.state.orchestrator
    
    try:
        history = await orchestrator.agent_runner.get_conversation_history(
            session_id=session_id,
            include_tool_calls=include_tools
        )
        
        return {
            "success": True,
            "session_id": session_id,
            "history": history,
            "message_count": len(history),
        }
    except Exception as e:
        log.error(f"Error retrieving session history: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve history for session {session_id}"
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
    """WebSocket endpoint for unified voice mode using Agents SDK VoicePipeline."""
    await websocket.accept()
    
    log.info("=" * 80)
    log.info("Unified Voice WebSocket connection ESTABLISHED from %s", websocket.client)
    log.info("=" * 80)
    
    agent_registry: AgentRegistry = app.state.agent_registry
    
    handler = UnifiedVoiceHandler(websocket, agent_registry)
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "session.start":
                    session_id = message.get("session_id", "default")
                    agent_id = message.get("agent_id", "general-agent")
                    conversation_history = message.get("conversation_history", [])
                    await handler.start(session_id, agent_id, conversation_history)
                
                elif message.get("type") == "session.stop":
                    await handler.stop()
                    break
                
                elif handler.is_active:
                    await handler.handle_client_message(message)
                else:
                    log.warning("Received message but session not active")
                    
            except WebSocketDisconnect:
                log.info("Unified Voice WebSocket disconnected by client")
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
        log.info("Unified Voice WebSocket connection CLOSED")
        log.info("=" * 80)
    except Exception as e:
        log.error("=" * 80)
        log.error("FATAL Unified Voice WebSocket error - connection will close")
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
