from __future__ import annotations
import logging
import os
import uvicorn
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from agora_openai.config import get_settings, parse_mcp_servers
from agora_openai.logging_config import configure_logging
from agora_openai.core.agent_definitions import AGENT_CONFIGS, list_all_agents
from agora_openai.core.agent_runner import AgentRegistry, AgentRunner
from agora_openai.adapters.mcp_tools import MCPToolRegistry
from agora_openai.adapters.audit_logger import AuditLogger
from agora_openai.adapters.session_metadata import SessionMetadataManager
from agora_openai.pipelines.moderator import ModerationPipeline
from agora_openai.pipelines.orchestrator import Orchestrator
from agora_openai.api.ag_ui_handler import AGUIProtocolHandler
from agora_openai.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize Agent SDK agents on startup."""
    settings = get_settings()

    configure_logging(settings.log_level)
    log.info("Starting AGORA Agent SDK Server (AG-UI Protocol)")

    # Set OPENAI_API_KEY for Agents SDK
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

    session_metadata = SessionMetadataManager(db_path="sessions.db")
    await session_metadata.initialize()

    orchestrator = Orchestrator(
        agent_runner=agent_runner,
        moderator=moderator,
        audit_logger=audit_logger,
        session_metadata=session_metadata,
    )

    app.state.orchestrator = orchestrator
    app.state.agent_registry = agent_registry
    app.state.mcp_tool_registry = mcp_tool_registry
    app.state.session_metadata = session_metadata

    yield

    log.info("Shutting down AGORA Agent SDK Server")
    await session_metadata.close()
    await mcp_tool_registry.disconnect_all()


app = FastAPI(
    title="AGORA Agent SDK Orchestration (AG-UI Protocol)",
    description="Agent SDK orchestration for AGORA multi-agent system using AG-UI Protocol",
    version="2.0.0",
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
    return {"status": "healthy", "service": "agora-agents", "protocol": "ag-ui"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AGORA Agent SDK Orchestration",
        "version": "2.0.0",
        "protocol": "AG-UI Protocol v2.1.1",
        "docs": "/docs",
        "websocket": "/ws",
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
    """Get conversation history for a session (thread).

    Args:
        session_id: Session/thread identifier
        include_tools: If True, includes tool calls and results in the history

    Returns:
        Conversation history with user, assistant, and optionally tool messages
    """
    orchestrator: Orchestrator = app.state.orchestrator

    try:
        history = await orchestrator.get_conversation_history(
            thread_id=session_id, include_tool_calls=include_tools
        )

        return {
            "success": True,
            "threadId": session_id,
            "history": history,
            "messageCount": len(history),
        }
    except Exception as e:
        log.error(f"Error retrieving session history: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to retrieve history for thread {session_id}",
        }


@app.get("/sessions")
async def list_sessions(
    user_id: str = Query(..., description="User/inspector persona ID"),
    limit: int = Query(50, ge=1, le=100, description="Max sessions to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List all sessions for a user, ordered by last activity."""
    session_metadata: SessionMetadataManager = app.state.session_metadata

    sessions, total_count = await session_metadata.list_sessions(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    return {
        "success": True,
        "sessions": sessions,
        "totalCount": total_count,
    }


@app.get("/sessions/{session_id}/metadata")
async def get_session_metadata(session_id: str):
    """Get session metadata by ID."""
    session_metadata: SessionMetadataManager = app.state.session_metadata

    session = await session_metadata.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "session": session,
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its metadata.

    Note: This deletes the metadata. Session conversation data
    deletion depends on the backend implementation.
    """
    session_metadata: SessionMetadataManager = app.state.session_metadata

    deleted = await session_metadata.delete_session(session_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "message": "Session deleted",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for AG-UI protocol communication."""
    await websocket.accept()

    handler = AGUIProtocolHandler(websocket)
    orchestrator: Orchestrator = app.state.orchestrator

    log.info("=" * 80)
    log.info("AG-UI WebSocket connection ESTABLISHED from %s", websocket.client)
    log.info("=" * 80)

    active_task = None

    try:
        while True:
            if not handler.is_connected:
                log.info("Handler reports connection is closed, exiting loop")
                break

            try:
                message = await handler.receive_message()

                if message is None:
                    if not handler.is_connected:
                        log.info("Connection closed during receive, exiting loop")
                        break
                    continue

                if isinstance(message, RunAgentInput):
                    thread_id = message.thread_id
                    log.info(f"Processing AG-UI RunAgentInput for thread: {thread_id}")

                    if active_task and not active_task.done():
                        log.info(
                            "New message received while processing previous one. Cancelling."
                        )
                        active_task.cancel()
                        try:
                            await active_task
                        except asyncio.CancelledError:
                            pass

                    async def process_wrapper(agent_input: RunAgentInput):
                        try:
                            resp = await orchestrator.process_message(
                                agent_input, handler
                            )
                            log.info(
                                f"Got response from orchestrator: role={resp.role}"
                            )
                            log.info(
                                f"Response sent successfully for thread: {agent_input.thread_id}"
                            )
                        except asyncio.CancelledError:
                            log.info("Processing cancelled")
                        except Exception as e:
                            log.error("Error in processing task: %s", e, exc_info=True)
                            if handler.is_connected:
                                await handler.send_run_error(
                                    message=str(e), code="processing_error"
                                )

                    active_task = asyncio.create_task(process_wrapper(message))

                elif isinstance(message, ToolApprovalResponsePayload):
                    log.info(
                        f"Received tool approval response: {message.approved} (id: {message.approval_id})"
                    )
                    orchestrator.handle_approval_response(message)

            except WebSocketDisconnect:
                log.info("WebSocket disconnected by client")
                if active_task and not active_task.done():
                    active_task.cancel()
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
                        await handler.send_run_error(
                            message=f"Error processing message: {str(e)}",
                            code="processing_error",
                        )
                        if handler.is_connected:
                            log.info(
                                "Error message sent to client, connection maintained"
                            )
                        else:
                            log.info(
                                "Connection closed while sending error, exiting loop"
                            )
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
        log.info("AG-UI WebSocket connection CLOSED")
        log.info("=" * 80)
    except Exception as e:
        log.error("=" * 80)
        log.error("FATAL WebSocket error - connection will close")
        log.error("=" * 80)
        log.error("Fatal WebSocket error: %s", e, exc_info=True)
        log.error("=" * 80)
        try:
            await handler.send_run_error(
                message="Internal server error", code="internal_error"
            )
        except Exception:
            pass


if __name__ == "__main__":

    settings = get_settings()
    uvicorn.run(
        "agora_openai.api.server:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
