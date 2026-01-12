"""HTTP and WebSocket proxy module."""

import asyncio
import logging
from typing import AsyncIterator

import httpx
from fastapi import Request, WebSocket, WebSocketDisconnect
from starlette.requests import ClientDisconnect
from starlette.responses import Response, StreamingResponse
from starlette.websockets import WebSocketState
import websockets

from .config import Settings, get_settings

logger = logging.getLogger(__name__)


BACKENDS: dict[str, str] | None = None


def get_backends(settings: Settings) -> dict[str, str]:
    """Get backend URL mapping."""
    global BACKENDS
    if BACKENDS is None:
        BACKENDS = {
            "openai": settings.openai_backend_url,
            "langgraph": settings.langgraph_backend_url,
            "mock": settings.mock_backend_url,
        }
    return BACKENDS


def resolve_backend(path: str, settings: Settings) -> tuple[str, str]:
    """Resolve backend URL and remaining path from request path.

    Returns (backend_url, remaining_path)
    """
    backends = get_backends(settings)

    # Check for explicit backend prefix: /api/{backend}/...
    for backend_name, backend_url in backends.items():
        prefix = f"/api/{backend_name}"
        if path.startswith(prefix):
            remaining = path[len(prefix) :] or "/"
            return backend_url, remaining

    # Use default backend
    return backends[settings.default_backend], path


async def proxy_http(
    request: Request,
    path: str,
    settings: Settings,
) -> Response:
    """Proxy HTTP request to backend."""
    backend_url, target_path = resolve_backend(f"/{path}", settings)

    url = f"{backend_url}{target_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # Forward headers, excluding hop-by-hop headers
    excluded_headers = {"host", "connection", "keep-alive", "transfer-encoding"}
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in excluded_headers
    }

    try:
        body = await request.body()
    except ClientDisconnect:
        # Client disconnected before we could read the body - this is normal
        # (e.g., browser navigation, fetch cancellation, page refresh)
        logger.debug("Client disconnected before request body was read")
        return Response(status_code=499)  # Client Closed Request (nginx convention)

    async with httpx.AsyncClient(timeout=120.0) as client:
        proxy_req = client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=body,
        )

        proxy_resp = await client.send(proxy_req, stream=True)

        async def stream_response() -> AsyncIterator[bytes]:
            try:
                async for chunk in proxy_resp.aiter_bytes():
                    yield chunk
            except ClientDisconnect:
                logger.debug("Client disconnected during response streaming")
            finally:
                await proxy_resp.aclose()

        # Filter response headers
        response_headers = {
            k: v
            for k, v in proxy_resp.headers.items()
            if k.lower()
            not in {"content-encoding", "content-length", "transfer-encoding"}
        }

        return StreamingResponse(
            stream_response(),
            status_code=proxy_resp.status_code,
            headers=response_headers,
            media_type=proxy_resp.headers.get("content-type"),
        )


async def proxy_websocket(
    websocket: WebSocket,
    path: str,
    settings: Settings,
) -> None:
    """Proxy WebSocket connection to backend."""
    backend_url, target_path = resolve_backend(f"/{path}", settings)

    # Convert HTTP URL to WebSocket URL
    ws_url = backend_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}{target_path}"

    # Forward query params
    if websocket.url.query:
        # Remove token param (used for auth)
        params = [
            p for p in websocket.url.query.split("&") if not p.startswith("token=")
        ]
        if params:
            ws_url = f"{ws_url}?{'&'.join(params)}"

    await websocket.accept()

    try:
        async with websockets.connect(ws_url) as backend_ws:

            async def forward_to_backend():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await backend_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Client disconnected")
                except Exception as e:
                    logger.error(f"Error forwarding to backend: {e}")

            async def forward_to_client():
                try:
                    async for message in backend_ws:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Error forwarding to client: {e}")

            # Run both directions concurrently
            await asyncio.gather(
                forward_to_backend(),
                forward_to_client(),
                return_exceptions=True,
            )

    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason=str(e))
