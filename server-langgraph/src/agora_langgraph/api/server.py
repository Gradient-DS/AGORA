"""FastAPI server with WebSocket endpoint using AG-UI Protocol."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agora_langgraph.config import get_settings, parse_mcp_servers
from agora_langgraph.logging_config import configure_logging
from agora_langgraph.core.agent_definitions import list_all_agents
from agora_langgraph.core.graph import build_agent_graph
from agora_langgraph.adapters.mcp_client import create_mcp_client_manager
from agora_langgraph.adapters.checkpointer import create_checkpointer
from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.adapters.session_metadata import SessionMetadataManager
from agora_langgraph.adapters.user_manager import UserManager
from agora_langgraph.pipelines.moderator import ModerationPipeline
from agora_langgraph.pipelines.orchestrator import Orchestrator
from agora_langgraph.api.ag_ui_handler import AGUIProtocolHandler
from agora_langgraph.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize LangGraph agents on startup."""
    settings = get_settings()

    configure_logging(settings.log_level)
    log.info("Starting AGORA LangGraph Server (AG-UI Protocol)")

    os.environ["OPENAI_API_KEY"] = settings.openai_api_key.get_secret_value()
    log.info("Configured OpenAI API key")

    mcp_servers = parse_mcp_servers(settings.mcp_servers)
    log.info("MCP Servers configured: %s", list(mcp_servers.keys()))

    async with create_mcp_client_manager(mcp_servers) as mcp_manager:
        mcp_tools_by_server = mcp_manager.get_tools_by_server()
        log.info("Loaded MCP tools from %d servers", len(mcp_tools_by_server))

        graph = build_agent_graph(mcp_tools_by_server)

        async with create_checkpointer(settings.sessions_db_path) as checkpointer:
            compiled_graph = graph.compile(checkpointer=checkpointer)
            log.info("LangGraph compiled with checkpointer")

            moderator = ModerationPipeline(enabled=settings.guardrails_enabled)
            audit_logger = AuditLogger(otel_endpoint=settings.otel_endpoint)

            session_metadata = SessionMetadataManager(db_path=settings.sessions_db_path)
            await session_metadata.initialize()

            user_manager = UserManager(db_path=settings.sessions_db_path)
            await user_manager.initialize()

            orchestrator = Orchestrator(
                graph=compiled_graph,
                moderator=moderator,
                audit_logger=audit_logger,
                session_metadata=session_metadata,
            )

            app.state.orchestrator = orchestrator
            app.state.mcp_manager = mcp_manager
            app.state.checkpointer = checkpointer
            app.state.session_metadata = session_metadata
            app.state.user_manager = user_manager

            yield

            await session_metadata.close()
            await user_manager.close()

    log.info("Shutting down AGORA LangGraph Server")


app = FastAPI(
    title="AGORA LangGraph Orchestration",
    description="LangGraph orchestration for AGORA multi-agent system using AG-UI Protocol",
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
    return {"status": "healthy", "service": "agora-langgraph", "protocol": "ag-ui"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AGORA LangGraph Orchestration",
        "version": "2.0.0",
        "protocol": "AG-UI",
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


# ---------------------------------------------------------------------------
# USER MANAGEMENT ENDPOINTS
# ---------------------------------------------------------------------------


@app.post("/users", status_code=201)
async def create_user(
    email: str = Query(..., description="User's email address"),
    name: str = Query(..., description="User's display name"),
    role: str = Query("inspector", description="User's role (admin, inspector, viewer)"),
):
    """Create a new user.

    Email must be unique across the system.
    """
    user_manager: UserManager = app.state.user_manager

    user = await user_manager.create_user(email=email, name=name, role=role)

    if not user:
        raise HTTPException(status_code=409, detail="Email already exists")

    return {
        "success": True,
        "user": user,
    }


@app.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=100, description="Max users to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List all users, ordered by creation date (most recent first)."""
    user_manager: UserManager = app.state.user_manager

    users, total_count = await user_manager.list_users(limit=limit, offset=offset)

    return {
        "success": True,
        "users": users,
        "totalCount": total_count,
    }


@app.get("/users/me")
async def get_current_user(
    user_id: str = Query(..., description="Current user ID"),
):
    """Get current user profile.

    Requires user_id query parameter for identification.
    """
    user_manager: UserManager = app.state.user_manager

    user = await user_manager.get_user(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@app.put("/users/me/preferences")
async def update_current_user_preferences(
    user_id: str = Query(..., description="Current user ID"),
    theme: str | None = Query(None, description="Theme preference (light, dark, system)"),
    notifications_enabled: bool | None = Query(None, description="Enable notifications"),
    default_agent_id: str | None = Query(None, description="Default agent ID"),
    language: str | None = Query(None, description="Language preference"),
):
    """Update current user's preferences."""
    user_manager: UserManager = app.state.user_manager

    # Build preferences dict from provided values
    preferences = {}
    if theme is not None:
        preferences["theme"] = theme
    if notifications_enabled is not None:
        preferences["notifications_enabled"] = notifications_enabled
    if default_agent_id is not None:
        preferences["default_agent_id"] = default_agent_id
    if language is not None:
        preferences["language"] = language

    if not preferences:
        raise HTTPException(status_code=400, detail="No preferences provided")

    user = await user_manager.update_preferences(user_id, preferences)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "preferences": user.get("preferences"),
    }


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user profile by ID."""
    user_manager: UserManager = app.state.user_manager

    user = await user_manager.get_user(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "user": user,
    }


@app.put("/users/{user_id}")
async def update_user(
    user_id: str,
    name: str | None = Query(None, description="User's display name"),
    role: str | None = Query(None, description="User's role (admin, inspector, viewer)"),
):
    """Update user profile.

    Partial updates are supported - only provided fields will be updated.
    """
    user_manager: UserManager = app.state.user_manager

    user = await user_manager.update_user(user_id, name=name, role=role)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "user": user,
    }


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """Delete a user and all associated sessions.

    This operation cascades to delete all sessions owned by the user.
    """
    user_manager: UserManager = app.state.user_manager

    deleted, sessions_count = await user_manager.delete_user(user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "message": "User and associated sessions deleted",
        "deletedSessionsCount": sessions_count,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for AG-UI protocol."""
    await websocket.accept()

    handler = AGUIProtocolHandler(websocket)
    orchestrator: Orchestrator = app.state.orchestrator

    log.info("=" * 80)
    log.info(
        "WebSocket connection ESTABLISHED from %s (AG-UI Protocol)", websocket.client
    )
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
                    run_id = message.run_id or str(uuid.uuid4())
                    log.info(
                        f"Processing AG-UI run for thread: {thread_id}, run: {run_id}"
                    )

                    if active_task and not active_task.done():
                        log.info(
                            "New run received while processing previous one. Cancelling previous."
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
                                f"Got response from orchestrator: role={resp.role}, has_content={bool(resp.content)}"
                            )
                            log.info(
                                f"Response sent successfully for thread: {agent_input.thread_id}"
                            )
                        except asyncio.CancelledError:
                            log.info("Processing cancelled")
                        except Exception as e:
                            log.error("Error in processing task: %s", e, exc_info=True)
                            if handler.is_connected:
                                await handler.send_error("processing_error", str(e))

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
                        await handler.send_error(
                            "processing_error", f"Error processing message: {str(e)}"
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


def main():
    """Run the server."""
    settings = get_settings()
    uvicorn.run(
        "agora_langgraph.api.server:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
