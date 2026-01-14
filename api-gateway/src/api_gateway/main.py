"""AGORA API Gateway - FastAPI application."""

import logging

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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


@app.get("/gateway/elevenlabs/config")
async def get_elevenlabs_config(
    settings: Settings = Depends(get_settings),
    _auth: dict = Depends(verify_api_key_http),
):
    """Get ElevenLabs configuration (voice ID, whether voice is enabled)."""
    return {
        "enabled": bool(settings.elevenlabs_api_key),
        "voiceId": settings.elevenlabs_voice_id,
    }


@app.post("/gateway/elevenlabs/token")
async def get_elevenlabs_token(
    settings: Settings = Depends(get_settings),
    _auth: dict = Depends(verify_api_key_http),
):
    """Get a single-use token for ElevenLabs STT.

    The master API key stays server-side; client gets a scoped token.
    """
    if not settings.elevenlabs_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs not configured",
        )

    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe",
            headers={"xi-api-key": settings.elevenlabs_api_key},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"ElevenLabs token request failed: {response.text}",
            )

        return response.json()


@app.post("/gateway/elevenlabs/tts")
async def proxy_elevenlabs_tts(
    request: Request,
    settings: Settings = Depends(get_settings),
    _auth: dict = Depends(verify_api_key_http),
):
    """Proxy TTS requests to ElevenLabs, keeping API key server-side."""
    if not settings.elevenlabs_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs not configured",
        )

    import httpx

    body = await request.json()
    voice_id = body.pop("voice_id", settings.elevenlabs_voice_id)

    async def stream_tts():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_tts(),
        media_type="audio/mpeg",
    )


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
