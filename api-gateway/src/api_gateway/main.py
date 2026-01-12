"""AGORA API Gateway - FastAPI application."""

import logging

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .auth import verify_api_key_http, verify_api_key_websocket
from .config import Settings, get_settings
from .proxy import proxy_http, proxy_websocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="AGORA API Gateway",
    description="Routes requests to AGORA backend orchestrators",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Gateway health check."""
    return {"status": "healthy", "service": "api-gateway"}


@app.get("/gateway/backends")
async def list_backends(settings: Settings = Depends(get_settings)):
    """List available backends and default."""
    return {
        "backends": ["openai", "langgraph", "mock"],
        "default": settings.default_backend,
        "routes": {
            "openai": "/api/openai/*",
            "langgraph": "/api/langgraph/*",
            "mock": "/api/mock/*",
        },
    }


# WebSocket endpoints - handle auth manually (can't use Depends with APIKeyHeader)
@app.websocket("/ws")
async def websocket_default(websocket: WebSocket):
    """WebSocket proxy to default backend."""
    settings = get_settings()
    auth = verify_api_key_websocket(websocket, settings)
    if auth is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await proxy_websocket(websocket, "ws", settings)


@app.websocket("/api/{backend}/ws")
async def websocket_backend(websocket: WebSocket, backend: str):
    """WebSocket proxy to specific backend."""
    settings = get_settings()
    auth = verify_api_key_websocket(websocket, settings)
    if auth is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await proxy_websocket(websocket, f"api/{backend}/ws", settings)


# HTTP catch-all proxy
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_request(
    request: Request,
    path: str,
    auth: dict | None = Depends(verify_api_key_http),
    settings: Settings = Depends(get_settings),
):
    """Proxy HTTP requests to backend."""
    return await proxy_http(request, path, settings)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
