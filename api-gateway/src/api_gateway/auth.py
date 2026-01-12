"""API key authentication module."""

import secrets

from fastapi import Depends, HTTPException, Query, Request, WebSocket, status
from fastapi.security import APIKeyHeader

from .config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key_http(
    api_key_header_value: str | None = Depends(api_key_header),
    token: str | None = Query(None, description="API key as query param"),
    settings: Settings = Depends(get_settings),
) -> dict | None:
    """Verify API key for HTTP requests.

    Returns client info if auth not required or key is valid.
    Raises 401 if auth required and key is invalid.
    """
    if not settings.require_auth:
        return {"name": "anonymous", "scopes": ["all"]}

    api_key = api_key_header_value or token

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
        )

    valid_keys = [k.strip() for k in settings.api_keys.split(",") if k.strip()]

    for valid_key in valid_keys:
        if secrets.compare_digest(api_key, valid_key):
            return {"name": "authenticated", "scopes": ["all"]}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key",
    )


def verify_api_key_websocket(
    websocket: WebSocket,
    settings: Settings,
) -> dict | None:
    """Verify API key for WebSocket connections.

    Extracts token from query params or headers.
    Returns client info if auth not required or key is valid.
    Returns None if auth required and key is invalid (caller should close connection).
    """
    if not settings.require_auth:
        return {"name": "anonymous", "scopes": ["all"]}

    # Try query param first, then header
    token = websocket.query_params.get("token")
    if not token:
        token = websocket.headers.get("x-api-key")

    if token is None:
        return None

    valid_keys = [k.strip() for k in settings.api_keys.split(",") if k.strip()]

    for valid_key in valid_keys:
        if secrets.compare_digest(token, valid_key):
            return {"name": "authenticated", "scopes": ["all"]}

    return None
