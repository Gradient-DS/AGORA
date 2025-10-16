from __future__ import annotations
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
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for HAI protocol."""
    await websocket.accept()
    
    handler = HAIProtocolHandler(websocket)
    orchestrator: Orchestrator = app.state.orchestrator
    
    log.info("WebSocket connection established")
    
    try:
        await handler.send_status("connected", "Connection established")
        
        while True:
            user_message = await handler.receive_message()
            
            if user_message is None:
                continue
            
            session_id = user_message.session_id
            
            await handler.send_status("routing", "Analyzing request...", session_id)
            
            response = await orchestrator.process_message(user_message, session_id)
            
            await handler.send_message(response)
            
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    except Exception as e:
        log.error("WebSocket error: %s", e, exc_info=True)
        try:
            await handler.send_error("internal_error", "Internal server error")
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "agora_openai.api.server:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )

