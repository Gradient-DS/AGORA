"""FastAPI server with WebSocket endpoint using AG-UI Protocol."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.adapters.checkpointer import create_checkpointer
from agora_langgraph.adapters.mcp_client import create_mcp_client_manager
from agora_langgraph.adapters.session_metadata import SessionMetadataManager
from agora_langgraph.adapters.user_manager import UserManager
from agora_langgraph.api.ag_ui_handler import AGUIProtocolHandler
from agora_langgraph.common.ag_ui_types import (
    RunAgentInput,
    ToolApprovalResponsePayload,
)
from agora_langgraph.config import get_settings, parse_mcp_servers
from agora_langgraph.core.agent_definitions import list_all_agents
from agora_langgraph.core.graph import build_agent_graph
from agora_langgraph.core.tools import set_user_manager
from agora_langgraph.logging_config import configure_logging
from agora_langgraph.pipelines.moderator import ModerationPipeline
from agora_langgraph.pipelines.orchestrator import Orchestrator

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

            # Set UserManager for settings tool
            set_user_manager(user_manager)

            orchestrator = Orchestrator(
                graph=compiled_graph,
                moderator=moderator,
                audit_logger=audit_logger,
                session_metadata=session_metadata,
                user_manager=user_manager,
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
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "agora-langgraph", "protocol": "ag-ui"}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "AGORA LangGraph Orchestration",
        "version": "2.0.0",
        "protocol": "AG-UI",
        "docs": "/docs",
        "websocket": "/ws",
    }


@app.get("/agents")
async def get_agents() -> dict[str, Any]:
    """Get list of active and inactive agents."""
    agents = list_all_agents()
    # Cast to Any to access AgentConfig-specific fields
    active_agents: list[Any] = agents["active"]
    return {
        "active_agents": [
            {
                "id": agent["id"],
                "name": agent["name"],
                "model": agent["model"],
                "description": agent["instructions"].split("\n\n")[0],
            }
            for agent in active_agents
        ],
        "inactive_agents": agents["inactive"],
    }


@app.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str, include_tools: bool = False
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
async def get_session_metadata(session_id: str) -> dict[str, Any]:
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
async def delete_session(session_id: str) -> dict[str, Any]:
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


class UpdateSessionRequest(BaseModel):
    """Request body for updating session metadata."""

    title: str | None = Field(None, description="New session title", max_length=200)


@app.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
) -> dict[str, Any]:
    """Update session metadata (e.g., rename session)."""
    session_metadata: SessionMetadataManager = app.state.session_metadata

    if request.title is not None:
        updated = await session_metadata.update_session_title(
            session_id, request.title
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True, "session": updated}

    raise HTTPException(status_code=400, detail="No update fields provided")


# ---------------------------------------------------------------------------
# USER MANAGEMENT ENDPOINTS
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    """Request body for creating a user."""

    email: str = Field(..., description="User's email address")
    name: str = Field(..., description="User's display name")
    role: str = Field("inspector", description="User's role (admin, inspector, viewer)")


@app.post("/users", status_code=201)
async def create_user(request: CreateUserRequest) -> dict[str, Any]:
    """Create a new user.

    Email must be unique across the system.
    """
    user_manager: UserManager = app.state.user_manager

    user = await user_manager.create_user(
        email=request.email, name=request.name, role=request.role
    )

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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
    """Get current user profile.

    Requires user_id query parameter for identification.
    """
    user_manager: UserManager = app.state.user_manager

    user = await user_manager.get_user(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""

    theme: str | None = None
    notifications_enabled: bool | None = None
    default_agent_id: str | None = None
    language: str | None = None
    spoken_text_type: str | None = None
    interaction_mode: str | None = None
    email_reports: bool | None = None


@app.get("/users/me/preferences")
async def get_current_user_preferences(
    user_id: str = Query(..., description="Current user ID"),
) -> dict[str, Any]:
    """Get current user's preferences."""
    user_manager: UserManager = app.state.user_manager
    user = await user_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    default_preferences = {
        "theme": "system",
        "notifications_enabled": True,
        "default_agent_id": "general-agent",
        "language": "nl-NL",
        "spoken_text_type": "summarize",
        "interaction_mode": "feedback",
        "email_reports": True,
    }
    # Use default if preferences is None or missing
    user_prefs = user.get("preferences")
    preferences = user_prefs if user_prefs else default_preferences
    return {"success": True, "preferences": preferences}


@app.put("/users/me/preferences")
async def update_current_user_preferences(
    request: UpdatePreferencesRequest,
    user_id: str = Query(..., description="Current user ID"),
) -> dict[str, Any]:
    """Update current user's preferences."""
    user_manager: UserManager = app.state.user_manager

    # Validate theme
    if request.theme is not None:
        if request.theme not in ("light", "dark", "system"):
            raise HTTPException(
                status_code=400, detail="theme must be 'light', 'dark', or 'system'"
            )

    # Validate spoken_text_type
    if request.spoken_text_type is not None:
        if request.spoken_text_type not in ("dictate", "summarize"):
            raise HTTPException(
                status_code=400,
                detail="spoken_text_type must be 'dictate' or 'summarize'",
            )

    # Validate interaction_mode
    if request.interaction_mode is not None:
        if request.interaction_mode not in ("feedback", "listen"):
            raise HTTPException(
                status_code=400,
                detail="interaction_mode must be 'feedback' or 'listen'",
            )

    # Get existing preferences to merge with
    user = await user_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    default_preferences = {
        "theme": "system",
        "notifications_enabled": True,
        "default_agent_id": "general-agent",
        "language": "nl-NL",
        "spoken_text_type": "summarize",
        "interaction_mode": "feedback",
        "email_reports": True,
    }
    existing_prefs = user.get("preferences")
    preferences = (existing_prefs if existing_prefs else default_preferences).copy()

    # Update only provided fields
    has_updates = False
    if request.theme is not None:
        preferences["theme"] = request.theme
        has_updates = True
    if request.notifications_enabled is not None:
        preferences["notifications_enabled"] = request.notifications_enabled
        has_updates = True
    if request.default_agent_id is not None:
        preferences["default_agent_id"] = request.default_agent_id
        has_updates = True
    if request.language is not None:
        preferences["language"] = request.language
        has_updates = True
    if request.spoken_text_type is not None:
        preferences["spoken_text_type"] = request.spoken_text_type
        has_updates = True
    if request.interaction_mode is not None:
        preferences["interaction_mode"] = request.interaction_mode
        has_updates = True
    if request.email_reports is not None:
        preferences["email_reports"] = request.email_reports
        has_updates = True

    if not has_updates:
        raise HTTPException(status_code=400, detail="No preferences provided")

    user = await user_manager.update_preferences(user_id, preferences)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "preferences": user.get("preferences"),
    }


@app.get("/users/{user_id}")
async def get_user(user_id: str) -> dict[str, Any]:
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
    role: str | None = Query(
        None, description="User's role (admin, inspector, viewer)"
    ),
) -> dict[str, Any]:
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
async def delete_user(user_id: str) -> dict[str, Any]:
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
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for AG-UI protocol."""
    await websocket.accept()

    handler = AGUIProtocolHandler(websocket)
    orchestrator: Orchestrator = app.state.orchestrator

    active_task = None

    try:
        while True:
            if not handler.is_connected:
                break

            try:
                message = await handler.receive_message()

                if message is None:
                    if not handler.is_connected:
                        break
                    continue

                if isinstance(message, RunAgentInput):
                    if active_task and not active_task.done():
                        active_task.cancel()
                        try:
                            await active_task
                        except asyncio.CancelledError:
                            pass

                    async def process_wrapper(agent_input: RunAgentInput) -> None:
                        try:
                            await orchestrator.process_message(agent_input, handler)
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            log.error("Error in processing task: %s", e, exc_info=True)
                            if handler.is_connected:
                                await handler.send_error("processing_error", str(e))

                    active_task = asyncio.create_task(process_wrapper(message))

                elif isinstance(message, ToolApprovalResponsePayload):
                    orchestrator.handle_approval_response(message)

            except WebSocketDisconnect:
                if active_task and not active_task.done():
                    active_task.cancel()
                handler.is_connected = False
                raise
            except Exception as e:
                log.error("Error processing message: %s", e, exc_info=True)

                if handler.is_connected:
                    try:
                        await handler.send_error(
                            "processing_error", f"Error processing message: {str(e)}"
                        )
                        if not handler.is_connected:
                            break
                    except Exception as send_err:
                        log.error("Failed to send error message: %s", send_err)
                        handler.is_connected = False
                        raise
                else:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("Fatal WebSocket error: %s", e, exc_info=True)
        try:
            await handler.send_error("internal_error", "Internal server error")
        except Exception:
            pass


def main() -> None:
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
