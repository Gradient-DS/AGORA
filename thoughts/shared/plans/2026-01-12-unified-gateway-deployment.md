# Unified Gateway Deployment Implementation Plan

## Overview

Deploy the AGORA stack with an API gateway from the start, combining Phase 1 (Local Full Stack) and Phase 2 (API Gateway + Authentication) from the research document. The frontend will use a feature flag environment variable (`VITE_BACKEND`) to select which backend orchestrator to use (langgraph, openai, or mock).

## Current State Analysis

### Existing Infrastructure
- **HAI Frontend**: Multi-stage Dockerfile with nginx serving static files, proxies `/ws` to `orchestrator:8000`
- **server-openai/server-langgraph**: Both have Dockerfiles, expose port 8000, identical AG-UI Protocol APIs
- **MCP Servers**: Comprehensive docker-compose.yml creating `agora-network`
- **Mock Server**: No Dockerfile exists, runs directly with `python mock_server.py`

### Key Discoveries
- HAI nginx.conf already expects a service named `orchestrator` at port 8000 (`HAI/nginx.conf:12`)
- Frontend uses `VITE_WS_URL` for WebSocket, derives HTTP URL from it (`HAI/src/lib/env.ts:4`)
- No backend selection logic exists in frontend - it's backend-agnostic
- MCP servers docker-compose creates the shared network (`mcp-servers/docker-compose.yml:66-68`)

## Desired End State

After this plan is complete:
1. Single `docker-compose up` starts the entire stack with API gateway
2. Frontend environment variable `VITE_BACKEND=langgraph|openai|mock` selects the backend
3. API Gateway authenticates requests with API key and routes to selected backend
4. All three backends (langgraph, openai, mock) run simultaneously, accessible via different paths
5. Local development works without authentication (optional API key)

### Verification
- Frontend at `http://localhost:3000` connects to selected backend
- WebSocket connection succeeds with API key header or query param
- Backend handoffs work correctly (general → regulation → reporting)
- MCP tool calls succeed

## What We're NOT Doing

- GCP deployment (separate future phase)
- SSL/TLS certificates (Caddy configuration for production)
- API key management UI (sqladmin)
- OpenAI embeddings migration (independent track)
- User authentication/authorization (just API key validation)

## Implementation Approach

The API gateway will handle:
1. **Path-based routing**: `/api/openai/*`, `/api/langgraph/*`, `/api/mock/*` route to respective backends
2. **Default backend**: Requests to `/ws` and `/` use the `DEFAULT_BACKEND` env var
3. **API key validation**: `X-API-Key` header or `token` query param (optional in local mode)
4. **WebSocket proxying**: Full duplex proxy with authentication

The frontend will:
1. Use `VITE_BACKEND` to determine which path to connect to
2. Build WebSocket URL as: `${base}/api/${backend}/ws` when backend is specified
3. Fall back to default `/ws` when no backend specified

---

## Phase 1: API Gateway Service

### Overview
Create the FastAPI-based API gateway that handles authentication and routing to backend services.

### Changes Required

#### 1. Create API Gateway Directory Structure

**Directory**: `api-gateway/`

```
api-gateway/
├── pyproject.toml
├── Dockerfile
└── src/
    └── api_gateway/
        ├── __init__.py
        ├── main.py          # FastAPI app with routing
        ├── auth.py          # API key validation
        ├── proxy.py         # HTTP and WebSocket proxy
        └── config.py        # Pydantic settings
```

#### 2. Gateway Configuration
**File**: `api-gateway/src/api_gateway/config.py`

```python
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """API Gateway configuration."""

    # Backend URLs
    openai_backend_url: str = Field(
        default="http://server-openai:8000",
        description="URL for server-openai backend"
    )
    langgraph_backend_url: str = Field(
        default="http://server-langgraph:8000",
        description="URL for server-langgraph backend"
    )
    mock_backend_url: str = Field(
        default="http://mock-server:8000",
        description="URL for mock server backend"
    )
    default_backend: str = Field(
        default="langgraph",
        description="Default backend when no path prefix specified"
    )

    # Authentication
    api_keys: str = Field(
        default="",
        description="Comma-separated API keys (empty = no auth required)"
    )
    require_auth: bool = Field(
        default=False,
        description="Whether to require API key authentication"
    )

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    model_config = {"env_prefix": "GATEWAY_"}


def get_settings() -> Settings:
    return Settings()
```

#### 3. Authentication Module
**File**: `api-gateway/src/api_gateway/auth.py`

```python
import secrets
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import APIKeyHeader

from .config import get_settings, Settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key_header_value: str | None = Depends(api_key_header),
    token: str | None = Query(None, description="API key as query param for WebSocket"),
    settings: Settings = Depends(get_settings),
) -> dict | None:
    """Verify API key from header or query parameter.

    Returns None if auth not required, raises 401 if invalid.
    """
    if not settings.require_auth:
        return {"name": "anonymous", "scopes": ["all"]}

    api_key = api_key_header_value or token

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key"
        )

    valid_keys = [k.strip() for k in settings.api_keys.split(",") if k.strip()]

    for valid_key in valid_keys:
        if secrets.compare_digest(api_key, valid_key):
            return {"name": "authenticated", "scopes": ["all"]}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key"
    )
```

#### 4. Proxy Module
**File**: `api-gateway/src/api_gateway/proxy.py`

```python
import asyncio
import logging
from typing import AsyncIterator

import httpx
from fastapi import Request, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse
from starlette.websockets import WebSocketState
import websockets

from .config import get_settings, Settings


logger = logging.getLogger(__name__)


BACKENDS = None


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
            remaining = path[len(prefix):] or "/"
            return backend_url, remaining

    # Use default backend
    return backends[settings.default_backend], path


async def proxy_http(
    request: Request,
    path: str,
    settings: Settings,
) -> StreamingResponse:
    """Proxy HTTP request to backend."""
    backend_url, target_path = resolve_backend(f"/{path}", settings)

    url = f"{backend_url}{target_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # Forward headers, excluding hop-by-hop headers
    excluded_headers = {"host", "connection", "keep-alive", "transfer-encoding"}
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in excluded_headers
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        proxy_req = client.build_request(
            method=request.method,
            url=url,
            headers=headers,
            content=await request.body(),
        )

        proxy_resp = await client.send(proxy_req, stream=True)

        async def stream_response() -> AsyncIterator[bytes]:
            async for chunk in proxy_resp.aiter_bytes():
                yield chunk
            await proxy_resp.aclose()

        # Filter response headers
        response_headers = {
            k: v for k, v in proxy_resp.headers.items()
            if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
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
        params = [p for p in websocket.url.query.split("&") if not p.startswith("token=")]
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
                return_exceptions=True
            )

    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=1011, reason=str(e))
```

#### 5. Main Application
**File**: `api-gateway/src/api_gateway/main.py`

```python
import logging

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .auth import verify_api_key
from .config import get_settings, Settings
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
        }
    }


# WebSocket endpoints
@app.websocket("/ws")
async def websocket_default(
    websocket: WebSocket,
    auth: dict | None = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
):
    """WebSocket proxy to default backend."""
    await proxy_websocket(websocket, "/ws", settings)


@app.websocket("/api/{backend}/ws")
async def websocket_backend(
    websocket: WebSocket,
    backend: str,
    auth: dict | None = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
):
    """WebSocket proxy to specific backend."""
    await proxy_websocket(websocket, f"/api/{backend}/ws", settings)


# HTTP catch-all proxy
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_request(
    request: Request,
    path: str,
    auth: dict | None = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
):
    """Proxy HTTP requests to backend."""
    return await proxy_http(request, path, settings)


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
```

#### 6. Package Configuration
**File**: `api-gateway/pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "api-gateway"
version = "0.1.0"
description = "AGORA API Gateway"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.32.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.27.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

#### 7. Gateway Dockerfile
**File**: `api-gateway/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["python", "-m", "api_gateway.main"]
```

### Success Criteria

#### Automated Verification:
- [x] Gateway builds: `docker build -t api-gateway ./api-gateway`
- [ ] Health check passes: `curl http://localhost:8000/health`
- [ ] Backend list works: `curl http://localhost:8000/gateway/backends`

#### Manual Verification:
- [ ] WebSocket proxy works (test with wscat or browser)
- [ ] HTTP proxy correctly forwards requests

---

## Phase 2: Mock Server Dockerfile

### Overview
Create Dockerfile for mock server to enable testing without LLM costs.

### Changes Required

#### 1. Mock Server Dockerfile
**File**: `docs/hai-contract/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn>=0.32.0 \
    pydantic>=2.0.0

COPY mock_server.py .
COPY schemas/ ./schemas/

# Create mock_documents directory for report files
RUN mkdir -p mock_documents

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "mock_server.py"]
```

### Success Criteria

#### Automated Verification:
- [x] Mock server builds: `docker build -t mock-server ./docs/hai-contract`
- [ ] Health check passes after container starts

---

## Phase 3: Frontend Backend Selection

### Overview
Add `VITE_BACKEND` environment variable to frontend for backend selection.

### Changes Required

#### 1. Update Environment Schema
**File**: `HAI/src/lib/env.ts`

Update the Zod schema to include backend selection:

```typescript
import { z } from 'zod';

const envSchema = z.object({
  VITE_WS_URL: z.string().url(),
  VITE_OPENAI_API_KEY: z.string().min(1),
  VITE_APP_NAME: z.string().default('AGORA HAI'),
  VITE_SESSION_TIMEOUT: z.string().transform(Number).default('3600000'),
  VITE_ELEVENLABS_API_KEY: z.string().optional().default(''),
  VITE_ELEVENLABS_VOICE_ID: z.string().optional().default('pNInz6obpgDQGcFmaJgB'),
  // New: Backend selection feature flag
  VITE_BACKEND: z.enum(['langgraph', 'openai', 'mock']).optional().default('langgraph'),
});

function validateEnv() {
  try {
    return envSchema.parse(import.meta.env);
  } catch (error) {
    console.error('Invalid environment configuration:', error);
    throw new Error('Failed to load environment configuration');
  }
}

export const env = validateEnv();

/**
 * Get the WebSocket URL for the selected backend.
 * If VITE_BACKEND is set, uses path-based routing: /api/{backend}/ws
 * Otherwise uses the default /ws endpoint.
 */
export function getWebSocketUrl(): string {
  const baseUrl = env.VITE_WS_URL.replace(/\/ws\/?$/, '');
  const backend = env.VITE_BACKEND;

  if (backend && backend !== 'langgraph') {
    // Use explicit backend path for non-default backends
    return `${baseUrl}/api/${backend}/ws`;
  }

  // Use default /ws endpoint (gateway will route to default backend)
  return env.VITE_WS_URL;
}

/**
 * Get the HTTP API base URL for the selected backend.
 */
export function getApiBaseUrl(): string {
  const wsUrl = getWebSocketUrl();
  return wsUrl
    .replace(/^ws:/, 'http:')
    .replace(/^wss:/, 'https:')
    .replace(/\/ws\/?$/, '');
}
```

#### 2. Update TypeScript Definitions
**File**: `HAI/src/env.d.ts`

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WS_URL: string;
  readonly VITE_OPENAI_API_KEY: string;
  readonly VITE_APP_NAME: string;
  readonly VITE_SESSION_TIMEOUT: string;
  readonly VITE_BACKEND?: 'langgraph' | 'openai' | 'mock';
  readonly VITE_ELEVENLABS_API_KEY?: string;
  readonly VITE_ELEVENLABS_VOICE_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

#### 3. Update WebSocket Client Usage
**File**: `HAI/src/hooks/useWebSocket.ts`

Update to use the new URL helper:

```typescript
import { getWebSocketUrl } from '@/lib/env';

// In getOrCreateClient function, change:
// url: env.VITE_WS_URL,
// to:
// url: getWebSocketUrl(),
```

#### 4. Update HTTP API URL Derivation
**File**: `HAI/src/lib/api/users.ts`

Update to use the new helper:

```typescript
import { getApiBaseUrl } from '@/lib/env';

function getBaseUrl(): string {
  return getApiBaseUrl();
}
```

**File**: `HAI/src/stores/useAgentStore.ts`

Update to use the new helper:

```typescript
import { getApiBaseUrl } from '@/lib/env';

// In loadAgentsFromAPI, change:
// const apiUrl = import.meta.env.VITE_WS_URL?.replace(...)
// to:
// const apiUrl = getApiBaseUrl();
```

#### 5. Update Environment Examples
**File**: `HAI/.env.example`

Add the new variable:

```env
# WebSocket URL - Point to your AGORA API Gateway
VITE_WS_URL=ws://localhost:8080/ws

# Backend Selection - Which orchestrator to use
# Options: langgraph (default), openai, mock
VITE_BACKEND=langgraph

# OpenAI API Key - Required for voice mode features
VITE_OPENAI_API_KEY=your_api_key_here

# ... rest of existing variables
```

### Success Criteria

#### Automated Verification:
- [x] TypeScript compiles: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Tests pass: `cd HAI && pnpm run test`

#### Manual Verification:
- [ ] Frontend connects to correct backend when `VITE_BACKEND=mock`
- [ ] Frontend connects to correct backend when `VITE_BACKEND=openai`
- [ ] Frontend uses default langgraph when `VITE_BACKEND` not set

---

## Phase 4: Unified Docker Compose

### Overview
Create the unified docker-compose that starts everything with the API gateway.

### Changes Required

#### 1. Root Docker Compose
**File**: `docker-compose.yml` (project root)

```yaml
version: "3.8"

services:
  # === API Gateway ===
  api-gateway:
    build: ./api-gateway
    ports:
      - "8080:8000"
    environment:
      - GATEWAY_OPENAI_BACKEND_URL=http://server-openai:8000
      - GATEWAY_LANGGRAPH_BACKEND_URL=http://server-langgraph:8000
      - GATEWAY_MOCK_BACKEND_URL=http://mock-server:8000
      - GATEWAY_DEFAULT_BACKEND=${DEFAULT_BACKEND:-langgraph}
      - GATEWAY_API_KEYS=${API_KEYS:-}
      - GATEWAY_REQUIRE_AUTH=${REQUIRE_AUTH:-false}
    depends_on:
      server-langgraph:
        condition: service_healthy
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 3s
      retries: 5

  # === Frontend ===
  hai:
    build:
      context: ./HAI
      args:
        - VITE_WS_URL=ws://localhost:8080/ws
        - VITE_BACKEND=${VITE_BACKEND:-langgraph}
        - VITE_OPENAI_API_KEY=${VITE_OPENAI_API_KEY:-}
        - VITE_APP_NAME=${VITE_APP_NAME:-AGORA HAI}
    ports:
      - "3000:80"
    depends_on:
      - api-gateway
    networks:
      - agora-network

  # === Orchestrators ===
  server-openai:
    build: ./server-openai
    environment:
      - APP_OPENAI_API_KEY=${OPENAI_API_KEY}
      - APP_MCP_SERVERS=regulation=http://regulation-analysis:8000,reporting=http://reporting:8000,history=http://inspection-history:8000
      - APP_HOST=0.0.0.0
      - APP_PORT=8000
    depends_on:
      regulation-analysis:
        condition: service_healthy
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 5

  server-langgraph:
    build: ./server-langgraph
    environment:
      - LANGGRAPH_OPENAI_API_KEY=${OPENAI_API_KEY}
      - LANGGRAPH_OPENAI_BASE_URL=${LANGGRAPH_OPENAI_BASE_URL:-https://api.openai.com/v1}
      - LANGGRAPH_OPENAI_MODEL=${LANGGRAPH_OPENAI_MODEL:-gpt-4o}
      - LANGGRAPH_MCP_SERVERS=regulation=http://regulation-analysis:8000,reporting=http://reporting:8000,history=http://inspection-history:8000
    volumes:
      - langgraph_sessions:/app/sessions
    depends_on:
      regulation-analysis:
        condition: service_healthy
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 5

  mock-server:
    build: ./docs/hai-contract
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      timeout: 3s
      retries: 5

  # === MCP Servers ===
  regulation-analysis:
    build:
      context: ./mcp-servers
      dockerfile: ./regulation-analysis/Dockerfile
    environment:
      - MCP_WEAVIATE_URL=http://weaviate:8080
      - MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
      - MCP_EMBEDDING_DEVICE=cpu
      - MCP_OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      weaviate:
        condition: service_healthy
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  reporting:
    build: ./mcp-servers/reporting
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - reporting_storage:/app/storage
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 3s
      retries: 5

  inspection-history:
    build: ./mcp-servers/inspection-history
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 3s
      retries: 5

  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.27.0
    environment:
      - QUERY_DEFAULTS_LIMIT=25
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
      - DEFAULT_VECTORIZER_MODULE=none
    volumes:
      - weaviate_data:/var/lib/weaviate
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "wget", "--spider", "http://localhost:8080/v1/.well-known/ready"]
      interval: 10s
      timeout: 3s
      retries: 10

networks:
  agora-network:
    driver: bridge

volumes:
  weaviate_data:
  reporting_storage:
  langgraph_sessions:
```

#### 2. Environment Template
**File**: `.env.example` (project root)

```bash
# === Required ===
OPENAI_API_KEY=sk-...

# === Backend Selection ===
# Default backend for API gateway (langgraph, openai, mock)
DEFAULT_BACKEND=langgraph

# Frontend backend selection (langgraph, openai, mock)
VITE_BACKEND=langgraph

# === Optional: LangGraph LLM Configuration ===
# Use alternative OpenAI-compatible provider
# LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
# LANGGRAPH_OPENAI_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo

# === Optional: Authentication ===
# Comma-separated API keys (empty = no auth required)
# API_KEYS=key1,key2,key3
# REQUIRE_AUTH=true

# === Optional: Frontend ===
VITE_OPENAI_API_KEY=${OPENAI_API_KEY}
VITE_APP_NAME=AGORA HAI
```

#### 3. Update HAI Dockerfile for Build Args
**File**: `HAI/Dockerfile`

Update to accept build args for environment variables:

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# Build arguments for environment variables
ARG VITE_WS_URL=ws://localhost:8080/ws
ARG VITE_BACKEND=langgraph
ARG VITE_OPENAI_API_KEY=
ARG VITE_APP_NAME=AGORA HAI
ARG VITE_SESSION_TIMEOUT=3600000

# Set as environment variables for build
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_BACKEND=$VITE_BACKEND
ENV VITE_OPENAI_API_KEY=$VITE_OPENAI_API_KEY
ENV VITE_APP_NAME=$VITE_APP_NAME
ENV VITE_SESSION_TIMEOUT=$VITE_SESSION_TIMEOUT

RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Update nginx.conf to proxy to api-gateway instead of orchestrator
COPY nginx.gateway.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

#### 4. Gateway-aware Nginx Config
**File**: `HAI/nginx.gateway.conf`

```nginx
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy all /ws and /api requests to the API gateway
    location ~ ^/(ws|api)/ {
        proxy_pass http://api-gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
    }

    # Also proxy root /ws for backwards compatibility
    location = /ws {
        proxy_pass http://api-gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    gzip_comp_level 6;
    gzip_min_length 1000;

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Success Criteria

#### Automated Verification:
- [ ] All services build: `docker-compose build`
- [ ] All services start: `docker-compose up -d`
- [ ] All health checks pass: `docker-compose ps` shows all healthy
- [ ] Gateway responds: `curl http://localhost:8080/health`
- [ ] Frontend loads: `curl http://localhost:3000`

#### Manual Verification:
- [ ] Frontend at http://localhost:3000 loads correctly
- [ ] Chat conversation works end-to-end
- [ ] Agent handoffs work (general → regulation → reporting)
- [ ] MCP tool calls succeed (regulation search, report generation)
- [ ] Switching `VITE_BACKEND=mock` uses mock server responses

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding.

---

## Testing Strategy

### Unit Tests
- API Gateway: Test routing logic, auth middleware
- Frontend: Test `getWebSocketUrl()` with different `VITE_BACKEND` values

### Integration Tests
- WebSocket proxy: Verify bidirectional message flow
- HTTP proxy: Verify all methods (GET, POST, PUT, DELETE) work

### Manual Testing Steps
1. Start stack with `docker-compose up`
2. Open http://localhost:3000
3. Send a chat message and verify response
4. Trigger a regulation search (mention "HACCP")
5. Request a report and verify generation
6. Change `VITE_BACKEND=mock`, rebuild, verify mock responses
7. Change `VITE_BACKEND=openai`, rebuild, verify openai backend used

## Quick Start

After implementation:

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env and add OPENAI_API_KEY

# 2. Start everything
docker-compose up --build

# 3. Access
open http://localhost:3000

# 4. Test different backends
docker-compose down
VITE_BACKEND=mock docker-compose up --build  # Uses mock server
```

## References

- Research document: `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md`
- HAI nginx config: `HAI/nginx.conf`
- MCP docker-compose: `mcp-servers/docker-compose.yml`
- Frontend env validation: `HAI/src/lib/env.ts`
