"""FastAPI server with WebSocket endpoint - matching server-openai API."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agora_langgraph.config import get_settings, parse_mcp_servers
from agora_langgraph.logging_config import configure_logging
from agora_langgraph.core.agent_definitions import AGENT_CONFIGS, list_all_agents
from agora_langgraph.core.graph import build_agent_graph
from agora_langgraph.adapters.mcp_client import create_mcp_client_manager
from agora_langgraph.adapters.checkpointer import create_checkpointer
from agora_langgraph.adapters.audit_logger import AuditLogger
from agora_langgraph.pipelines.moderator import ModerationPipeline
from agora_langgraph.pipelines.orchestrator import Orchestrator
from agora_langgraph.api.hai_protocol import HAIProtocolHandler
from agora_langgraph.common.hai_types import UserMessage, ToolApprovalResponse

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize LangGraph agents on startup."""
    settings = get_settings()

    configure_logging(settings.log_level)
    log.info("Starting AGORA LangGraph Server")

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

            orchestrator = Orchestrator(
                graph=compiled_graph,
                moderator=moderator,
                audit_logger=audit_logger,
            )

            app.state.orchestrator = orchestrator
            app.state.mcp_manager = mcp_manager
            app.state.checkpointer = checkpointer

            yield

    log.info("Shutting down AGORA LangGraph Server")


app = FastAPI(
    title="AGORA LangGraph Orchestration",
    description="LangGraph orchestration for AGORA multi-agent system",
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
    return {"status": "healthy", "service": "agora-langgraph"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "AGORA LangGraph Orchestration",
        "version": "1.0.0",
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
    """Get conversation history for a session.

    Args:
        session_id: Session identifier
        include_tools: If True, includes tool calls and results in the history

    Returns:
        Conversation history with user, assistant, and optionally tool messages
    """
    orchestrator: Orchestrator = app.state.orchestrator

    try:
        history = await orchestrator.get_conversation_history(
            session_id=session_id, include_tool_calls=include_tools
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
            "message": f"Failed to retrieve history for session {session_id}",
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

                if isinstance(message, UserMessage):
                    session_id = message.session_id
                    log.info(f"Processing message for session: {session_id}")

                    if active_task and not active_task.done():
                        log.info(
                            "New user message received while processing previous one. Cancelling previous."
                        )
                        active_task.cancel()
                        try:
                            await active_task
                        except asyncio.CancelledError:
                            pass

                    async def process_wrapper(msg, sess_id):
                        try:
                            resp = await orchestrator.process_message(
                                msg, sess_id, handler
                            )
                            log.info(
                                f"Got response from orchestrator: type={resp.type}, has_content={bool(resp.content)}"
                            )
                            log.info(
                                f"Response sent successfully for session: {sess_id}"
                            )
                        except asyncio.CancelledError:
                            log.info("Processing cancelled")
                        except Exception as e:
                            log.error("Error in processing task: %s", e, exc_info=True)
                            if handler.is_connected:
                                await handler.send_error("processing_error", str(e))

                    active_task = asyncio.create_task(
                        process_wrapper(message, session_id)
                    )

                elif isinstance(message, ToolApprovalResponse):
                    log.info(
                        f"Received tool approval response: {message.approved} (id: {message.approval_id})"
                    )
                    if message.approval_id in orchestrator.pending_approvals:
                        future = orchestrator.pending_approvals[message.approval_id]
                        if not future.done():
                            future.set_result(message.approved)
                    else:
                        log.warning(
                            f"Received approval for unknown ID: {message.approval_id}"
                        )

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
