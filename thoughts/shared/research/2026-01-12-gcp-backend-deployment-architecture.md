---
date: 2026-01-12T14:30:00+01:00
researcher: Claude
git_commit: 8e824d28ccfcec5186ad10f79c5540896c1caac6
branch: feat/parallel-spoken
repository: AGORA
topic: "GCP Backend Deployment with API Gateway and Multi-Backend Routing"
tags: [research, deployment, gcp, api-gateway, infrastructure, authentication, local-development]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
last_updated_note: "Revised implementation order: local-first approach with frontend testing before GCP deployment"
---

# Research: GCP Backend Deployment with API Gateway and Multi-Backend Routing

**Date**: 2026-01-12T14:30:00+01:00
**Researcher**: Claude
**Git Commit**: 8e824d28ccfcec5186ad10f79c5540896c1caac6
**Branch**: feat/parallel-spoken
**Repository**: AGORA

## Research Question

How to host the AGORA backend on Google Cloud with:
1. API token authentication over HTTPS
2. A facade/gateway routing to different backends (server-openai, server-langgraph, mock server)
3. LangGraph server with option to use OpenAI or alternative models (e.g., gpt-oss-120b)
4. MCP servers running on the same VM
5. GCP instance type recommendations

## Summary

**Recommended Architecture:**
- Single GCP VM (N2D-Standard-16, ~$493/month) running all services via Docker Compose
- Traefik or nginx as reverse proxy with SSL termination and WebSocket support
- FastAPI-based API gateway with API key authentication middleware
- Path-based routing to backend variants (`/api/openai`, `/api/langgraph`, `/api/mock`)
- Environment variable configuration for LLM provider switching

**Key Findings:**
- The codebase already supports alternative LLM providers via `LANGGRAPH_OPENAI_BASE_URL`
- No authentication currently exists; API key middleware must be added
- All services are containerized and can run on a single VM
- Total resource requirement: ~12-24GB RAM, 7-13 vCPUs

## Detailed Findings

### Current Architecture Analysis

#### Backend Servers Overview

| Server | Port | Configuration Prefix | Purpose |
|--------|------|---------------------|---------|
| server-openai | 8000 | `OPENAI_AGENTS_` | OpenAI Agents SDK orchestrator |
| server-langgraph | 8000 | `LANGGRAPH_` | LangGraph orchestrator (supports any OpenAI-compatible API) |
| mock_server | 8000 | N/A | Demo/testing without real LLM calls |

**Key Files:**
- `server-openai/src/agora_openai/api/server.py:566-574` - Entry point
- `server-langgraph/src/agora_langgraph/api/server.py:567-579` - Entry point
- `docs/hai-contract/mock_server.py:1497-1501` - Entry point

#### MCP Servers

| Server | Internal Port | External Port | Dependencies |
|--------|---------------|---------------|--------------|
| regulation-analysis | 8000 | 5002 | Weaviate, PyTorch/Transformers |
| reporting | 8000 | 5003 | OpenAI API (for conversation analysis) |
| inspection-history | 8000 | 5005 | None (demo data) |
| Weaviate | 8080 | 8080 | None |

**Docker Compose:** `mcp-servers/docker-compose.yml`

### Authentication Requirements

#### Current State: No Authentication

The codebase currently has **no API authentication**:
- All CORS is set to `allow_origins=["*"]` (`server-openai/src/agora_openai/api/server.py:96-102`)
- User identification via query parameter `user_id` only
- No security middleware on any endpoint

#### Recommended: FastAPI API Key Middleware

```python
# api_gateway/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
import secrets
import os

API_KEYS = {
    os.getenv("API_KEY_HAI"): {"name": "HAI Frontend", "scopes": ["all"]},
    os.getenv("API_KEY_ADMIN"): {"name": "Admin", "scopes": ["all"]},
}

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing API Key")

    for valid_key, metadata in API_KEYS.items():
        if valid_key and secrets.compare_digest(api_key, valid_key):
            return metadata

    raise HTTPException(status_code=401, detail="Invalid API Key")
```

**WebSocket Authentication Options:**
1. Query parameter token: `wss://api.example.com/ws?token=<api-key>`
2. `Sec-WebSocket-Protocol` header workaround for browsers

### API Gateway Architecture

#### Option 1: Traefik (Recommended for Docker deployments)

```yaml
# docker-compose.gateway.yml
version: "3.8"

services:
  traefik:
    image: traefik:v3.0
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=your@email.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    networks:
      - agora-network

  api-gateway:
    build: ./api-gateway
    environment:
      - API_KEY_HAI=${API_KEY_HAI}
      - OPENAI_BACKEND_URL=http://server-openai:8000
      - LANGGRAPH_BACKEND_URL=http://server-langgraph:8000
      - MOCK_BACKEND_URL=http://mock-server:8000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.gateway.rule=Host(`api.yourdomain.com`)"
      - "traefik.http.routers.gateway.entrypoints=websecure"
      - "traefik.http.routers.gateway.tls.certresolver=letsencrypt"

  server-openai:
    build: ./server-openai
    labels:
      - "traefik.enable=false"  # Only accessible via gateway
    networks:
      - agora-network

  server-langgraph:
    build: ./server-langgraph
    environment:
      - LANGGRAPH_OPENAI_BASE_URL=${LANGGRAPH_OPENAI_BASE_URL:-https://api.openai.com/v1}
      - LANGGRAPH_OPENAI_API_KEY=${LANGGRAPH_OPENAI_API_KEY}
      - LANGGRAPH_OPENAI_MODEL=${LANGGRAPH_OPENAI_MODEL:-gpt-4o}
    labels:
      - "traefik.enable=false"
    networks:
      - agora-network

  mock-server:
    build:
      context: ./docs/hai-contract
      dockerfile: Dockerfile.mock  # Needs to be created
    labels:
      - "traefik.enable=false"
    networks:
      - agora-network
```

#### Option 2: nginx (Production-grade)

```nginx
# nginx.conf
upstream server_openai { server server-openai:8000; }
upstream server_langgraph { server server-langgraph:8000; }
upstream mock_server { server mock-server:8000; }

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    # API Gateway handles auth - forward to FastAPI gateway
    location / {
        proxy_pass http://api-gateway:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket - critical configuration
    location /ws {
        proxy_pass http://api-gateway:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_read_timeout 86400s;
    }
}
```

### Gateway Routing Logic

```python
# api_gateway/main.py
from fastapi import FastAPI, Request, Depends, WebSocket
from starlette.responses import StreamingResponse
import httpx
import os

from auth import verify_api_key

BACKENDS = {
    "openai": os.getenv("OPENAI_BACKEND_URL", "http://server-openai:8000"),
    "langgraph": os.getenv("LANGGRAPH_BACKEND_URL", "http://server-langgraph:8000"),
    "mock": os.getenv("MOCK_BACKEND_URL", "http://mock-server:8000"),
}

DEFAULT_BACKEND = os.getenv("DEFAULT_BACKEND", "langgraph")

app = FastAPI(title="AGORA API Gateway")
http_client = httpx.AsyncClient(timeout=120.0)

def get_backend_url(path: str) -> tuple[str, str]:
    """Extract backend from path prefix and return (backend_url, remaining_path)."""
    for backend_name, backend_url in BACKENDS.items():
        prefix = f"/api/{backend_name}"
        if path.startswith(prefix):
            remaining = path[len(prefix):] or "/"
            return backend_url, remaining
    # Default backend
    return BACKENDS[DEFAULT_BACKEND], path

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str, auth: dict = Depends(verify_api_key)):
    backend_url, target_path = get_backend_url(f"/{path}")

    url = f"{backend_url}{target_path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "connection")}

    proxy_req = http_client.build_request(
        request.method, url, headers=headers, content=await request.body()
    )
    proxy_resp = await http_client.send(proxy_req, stream=True)

    return StreamingResponse(
        proxy_resp.aiter_raw(),
        status_code=proxy_resp.status_code,
        headers=dict(proxy_resp.headers)
    )

@app.websocket("/ws")
async def websocket_proxy(websocket: WebSocket, backend: str = DEFAULT_BACKEND):
    # WebSocket proxy implementation with authentication
    # Use fastapi-proxy-lib for production
    pass
```

### LLM Provider Configuration

#### Server-LangGraph Already Supports Alternative Providers

The existing configuration in `server-langgraph/src/agora_langgraph/config.py:21-26`:

```python
openai_api_key: SecretStr = Field(description="OpenAI-compatible API key")
openai_base_url: str = Field(
    default="https://api.openai.com/v1",
    description="Base URL for OpenAI-compatible API",
)
openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
```

#### Configuration for Different Providers

| Provider | Base URL | Model Example |
|----------|----------|---------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Together.ai | `https://api.together.ai/v1` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenRouter | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct` |
| vLLM (self-hosted) | `http://localhost:8000/v1` | `meta-llama/Llama-3.3-70B-Instruct` |

**Environment Variables:**
```bash
# For Together.ai with Llama 3.3 70B
LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
LANGGRAPH_OPENAI_API_KEY=your_together_api_key
LANGGRAPH_OPENAI_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo
```

#### Recommended Models for Agentic Applications

| Model | Provider | Strengths | Cost |
|-------|----------|-----------|------|
| DeepSeek-V3 | Together.ai | Best reasoning, tool-use | $1.25/M tokens |
| Llama 3.3 70B | Together.ai, Groq | Balanced cost/performance | ~$0.80/M tokens |
| Qwen 2.5 72B | Together.ai | Excellent structured output | ~$1.00/M tokens |

### GCP Instance Recommendations

#### Workload Analysis

| Service | Memory | CPU |
|---------|--------|-----|
| 3 FastAPI Orchestrators | 3-6GB | 1.5-3 vCPUs |
| 2 Regular MCP Servers | 1-2GB | 1 vCPU |
| 1 PyTorch/Embeddings MCP | 2-4GB | 2-4 vCPUs |
| Weaviate | 4-8GB | 2-4 vCPUs |
| Docker/OS Overhead | 2-4GB | 1-2 vCPUs |
| **Total** | **12-24GB** | **7-13 vCPUs** |

#### Recommended Instance Types

| Instance | vCPUs | RAM | Monthly Cost | Use Case |
|----------|-------|-----|--------------|----------|
| **N2D-Standard-16** | 16 | 64GB | ~$493 | **Recommended for production** |
| N2-Standard-16 | 16 | 64GB | ~$567 | Intel-optimized workloads |
| E2-Standard-8 | 8 | 32GB | ~$196 | Development/staging |
| C3-Standard-8 | 8 | 32GB | ~$350 | High single-thread performance |

#### Cost Optimization

| Pricing Model | N2D-Standard-16 | Savings |
|--------------|-----------------|---------|
| On-Demand | ~$493/month | - |
| Sustained Use (100%) | ~$345/month | 30% |
| 1-Year Commitment | ~$310/month | 37% |
| 3-Year Commitment | ~$212/month | 57% |

#### Container-Optimized OS Recommended

- Pre-installed Docker
- Security-hardened, minimal attack surface
- Automatic weekly security updates
- No package manager (prevents drift)

### Deployment Configuration

#### Unified Docker Compose

```yaml
# docker-compose.production.yml
version: "3.8"

services:
  # === Reverse Proxy ===
  traefik:
    image: traefik:v3.0
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    command:
      - "--providers.docker=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.le.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.le.acme.email=${LETSENCRYPT_EMAIL}"
      - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
    networks:
      - agora-network

  # === API Gateway ===
  api-gateway:
    build: ./api-gateway
    environment:
      - API_KEY_HAI=${API_KEY_HAI}
      - DEFAULT_BACKEND=${DEFAULT_BACKEND:-langgraph}
      - OPENAI_BACKEND_URL=http://server-openai:8000
      - LANGGRAPH_BACKEND_URL=http://server-langgraph:8000
      - MOCK_BACKEND_URL=http://mock-server:8000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`${API_DOMAIN}`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls.certresolver=le"
    networks:
      - agora-network

  # === Orchestrators ===
  server-openai:
    build: ./server-openai
    environment:
      - OPENAI_AGENTS_OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_AGENTS_MCP_SERVERS=regulation=http://mcp-regulation:8000,reporting=http://mcp-reporting:8000,history=http://mcp-history:8000
    networks:
      - agora-network

  server-langgraph:
    build: ./server-langgraph
    environment:
      - LANGGRAPH_OPENAI_API_KEY=${LANGGRAPH_OPENAI_API_KEY}
      - LANGGRAPH_OPENAI_BASE_URL=${LANGGRAPH_OPENAI_BASE_URL:-https://api.openai.com/v1}
      - LANGGRAPH_OPENAI_MODEL=${LANGGRAPH_OPENAI_MODEL:-gpt-4o}
      - LANGGRAPH_MCP_SERVERS=regulation=http://mcp-regulation:8000,reporting=http://mcp-reporting:8000,history=http://mcp-history:8000
    networks:
      - agora-network

  mock-server:
    build:
      context: ./docs/hai-contract
      dockerfile: Dockerfile.mock
    networks:
      - agora-network

  # === MCP Servers ===
  mcp-regulation:
    build: ./mcp-servers/regulation-analysis
    environment:
      - MCP_WEAVIATE_URL=http://weaviate:8080
      - MCP_OPENAI_API_KEY=${MCP_OPENAI_API_KEY}
    depends_on:
      weaviate:
        condition: service_healthy
    networks:
      - agora-network

  mcp-reporting:
    build: ./mcp-servers/reporting
    environment:
      - OPENAI_API_KEY=${MCP_OPENAI_API_KEY}
    volumes:
      - reporting_storage:/app/storage
    networks:
      - agora-network

  mcp-history:
    build: ./mcp-servers/inspection-history
    networks:
      - agora-network

  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.27.0
    environment:
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
    volumes:
      - weaviate_data:/var/lib/weaviate
    healthcheck:
      test: ["CMD", "wget", "--spider", "http://localhost:8080/v1/.well-known/ready"]
      interval: 10s
      timeout: 3s
      retries: 10
    networks:
      - agora-network

networks:
  agora-network:
    driver: bridge

volumes:
  weaviate_data:
  reporting_storage:
  letsencrypt:
```

#### Environment File

```bash
# .env.production
API_DOMAIN=api.yourdomain.com
LETSENCRYPT_EMAIL=admin@yourdomain.com

# API Keys for gateway
API_KEY_HAI=your-secure-api-key-for-frontend

# Default backend (openai, langgraph, or mock)
DEFAULT_BACKEND=langgraph

# OpenAI API (for server-openai and MCP servers)
OPENAI_API_KEY=sk-...
MCP_OPENAI_API_KEY=sk-...

# LangGraph configuration (for alternative providers)
LANGGRAPH_OPENAI_API_KEY=sk-...
LANGGRAPH_OPENAI_BASE_URL=https://api.openai.com/v1
LANGGRAPH_OPENAI_MODEL=gpt-4o

# Alternative: Together.ai with Llama 3.3
# LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
# LANGGRAPH_OPENAI_API_KEY=your_together_key
# LANGGRAPH_OPENAI_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo
```

## Code References

- `server-openai/src/agora_openai/api/server.py:96-102` - CORS middleware (needs auth)
- `server-openai/src/agora_openai/config.py:20-46` - Settings with env prefix
- `server-langgraph/src/agora_langgraph/config.py:21-26` - OpenAI-compatible base_url config
- `server-langgraph/src/agora_langgraph/core/agents.py:31-53` - LLM instantiation with base_url
- `mcp-servers/docker-compose.yml` - MCP server orchestration
- `docs/hai-contract/mock_server.py:1497-1501` - Mock server entry point

## Architecture Insights

### Multi-Backend Routing Pattern

The facade pattern allows switching backends without frontend changes:
- `/api/openai/...` → server-openai (proprietary, OpenAI Agents SDK)
- `/api/langgraph/...` → server-langgraph (open-source, any LLM provider)
- `/api/mock/...` → mock server (demo/testing)

The gateway handles:
1. API key validation
2. Path-based routing
3. WebSocket proxy with authentication
4. Header forwarding

### LLM Provider Flexibility

Server-langgraph is designed for provider independence:
- `ChatOpenAI` with configurable `base_url` supports any OpenAI-compatible API
- Per-agent model override via `agent_definitions.py`
- LLM instances cached to avoid recreation

## Open Questions

1. **WebSocket Proxy Implementation**: The API gateway needs a robust WebSocket proxy with authentication. Consider using `fastapi-proxy-lib` or implementing a custom solution.

2. **API Key Management**: How should API keys be provisioned and rotated? Consider adding a key management endpoint or using GCP Secret Manager.

3. **Monitoring**: Should we add OpenTelemetry export to GCP Cloud Monitoring?

4. **Mock Server Dockerfile**: The mock server needs a Dockerfile to be added at `docs/hai-contract/Dockerfile.mock`.

5. **Database Persistence**: Session databases (`sessions.db`) need volume mounts for persistence across container restarts.

6. **gpt-oss-120b**: This model name appears to be referenced as a Groq model. Need to verify availability and correct model name at Groq console.

---

## Follow-up Research: Revised Estimates and Implementation Topics

### Corrected Resource Estimates

The original estimates were overly conservative. Based on actual FastAPI/Python memory footprints and user feedback (running on 32GB laptop with <20% utilization):

**With OpenAI Embeddings (Recommended):**

| Service | Realistic Memory | CPU |
|---------|-----------------|-----|
| 3 FastAPI Orchestrators | ~300MB each = 900MB | 0.5 vCPU each |
| 3 Lightweight MCP Servers | ~150MB each = 450MB | 0.25 vCPU each |
| Weaviate (small dataset) | ~1GB | 1 vCPU |
| Caddy | ~50MB | 0.1 vCPU |
| Docker/OS Overhead | ~500MB | 0.5 vCPU |
| **Total** | **~3GB realistic, 4GB comfortable** | **~3-4 vCPUs** |

**With Local Embeddings (sentence-transformers):**

| Service | Realistic Memory | CPU |
|---------|-----------------|-----|
| 3 FastAPI Orchestrators | ~300MB each = 900MB | 0.5 vCPU each |
| 2 Lightweight MCP Servers | ~150MB each = 300MB | 0.25 vCPU each |
| 1 PyTorch/Embeddings MCP | ~800MB (nomic-embed model) | 1-2 vCPUs |
| Weaviate (small dataset) | ~1GB | 1 vCPU |
| Caddy | ~50MB | 0.1 vCPU |
| Docker/OS Overhead | ~500MB | 0.5 vCPU |
| **Total** | **~4GB realistic, 6GB comfortable** | **~4-5 vCPUs** |

### OpenAI Embeddings: Impact Analysis

**Current Implementation:**
- Uses `nomic-ai/nomic-embed-text-v1.5` via sentence-transformers
- Requires PyTorch, Transformers, einops (~800MB memory)
- Embeddings generated locally for both ingestion and queries

**Key Files:**
- `mcp-servers/document-ingestion/embeddings/embedder.py` - Core embedding class
- `mcp-servers/regulation-analysis/server.py:29-47` - Query-time embedding
- `mcp-servers/document-ingestion/ingest.py` - Document ingestion pipeline

**Switching to OpenAI Embeddings:**

| Aspect | Local (nomic-embed) | OpenAI (text-embedding-3-small) |
|--------|---------------------|--------------------------------|
| Memory | ~800MB | ~50MB (just httpx client) |
| Dependencies | PyTorch, Transformers, sentence-transformers | openai SDK |
| Cost | Free (compute) | ~$0.02/1M tokens |
| Latency | ~50ms local | ~100-200ms API call |
| Dimensions | 768 | 1536 (or 512 with dimension param) |

**Required Changes:**
1. **Embedder class** - Add OpenAI provider option controlled by `MCP_EMBEDDING_PROVIDER=openai|local`
2. **Re-ingest documents** - Must use same embeddings for documents and queries
3. **Weaviate schema** - May need to update vector dimensions (768 → 1536)
4. **Docker images** - Remove PyTorch from regulation-analysis Dockerfile

**Cost Estimate for OpenAI Embeddings:**
- 1000 regulation documents × ~500 tokens each = 500K tokens ingestion = ~$0.01
- 1000 queries/month × ~20 tokens each = 20K tokens = ~$0.0004/month
- **Negligible cost** compared to infrastructure savings

### Revised GCP Instance Recommendations

| Instance | vCPUs | RAM | Monthly Cost | Recommendation |
|----------|-------|-----|--------------|----------------|
| **e2-small** | 2 | 2GB | ~$13/month | With OpenAI embeddings, minimum viable |
| **e2-standard-2** | 2 | 8GB | ~$49/month | **Recommended with OpenAI embeddings** |
| e2-standard-4 | 4 | 16GB | ~$98/month | Comfortable headroom, with or without local embeddings |

**Recommendation with OpenAI Embeddings: e2-standard-2 (~$49/month)**
- 8GB is plenty for ~3-4GB realistic usage
- 2 vCPUs handles the workload well
- Standard Ubuntu 22.04 LTS

### Reverse Proxy: Caddy (Recommended)

Caddy is simpler than Traefik with automatic HTTPS out of the box:

```
# Caddyfile
api.yourdomain.com {
    # API Gateway handles auth and routing
    reverse_proxy api-gateway:8000
}
```

**Why Caddy over Traefik:**
- Zero-config automatic HTTPS (Let's Encrypt)
- Simple Caddyfile syntax (vs Traefik labels)
- WebSocket support works out of the box
- Lower maintenance overhead

---

## Implementation Topics (Local-First Approach)

**Revised Strategy:** Test the complete stack locally before any cloud deployment. This enables:
- Full end-to-end testing on developer machines
- Validation of Docker Compose configuration before cloud deployment
- Frontend development with real backend (not just mock server)
- Iterative debugging without cloud deployment cycles

### Existing Docker Infrastructure

The codebase already has extensive Docker containerization:

| Component | Dockerfile | docker-compose.yml | Port |
|-----------|------------|-------------------|------|
| HAI Frontend | `HAI/Dockerfile` | `HAI/docker-compose.yml` | 3000→80 |
| server-openai | `server-openai/Dockerfile` | `server-openai/docker-compose.yml` | 8000 |
| server-langgraph | `server-langgraph/Dockerfile` | `server-langgraph/docker-compose.yml` | 8000 |
| regulation-analysis | `mcp-servers/regulation-analysis/Dockerfile` | `mcp-servers/docker-compose.yml` | 5002→8000 |
| reporting | `mcp-servers/reporting/Dockerfile` | `mcp-servers/docker-compose.yml` | 5003→8000 |
| inspection-history | `mcp-servers/inspection-history/Dockerfile` | `mcp-servers/docker-compose.yml` | 5005→8000 |
| Weaviate | External image | `mcp-servers/docker-compose.yml` | 8080 |

All services use a shared `agora-network` (bridge driver).

**Key Finding:** HAI's `nginx.conf` already proxies `/ws` to `http://orchestrator:8000`, expecting a service named `orchestrator`.

---

## Phase 1: Local Full Stack (Unified Docker Compose)

**Goal:** Run the entire stack locally with a single `docker-compose up`

### Topic 1A: Unified Local Docker Compose
**Scope:** Create a single docker-compose that starts all services for local development
**Deliverables:**
- `docker-compose.local.yml` at project root
- Combines all existing service definitions
- Frontend built and served via nginx (production-like)
- All backends + MCP servers running
- Environment file template `.env.local.example`

**Why This First:**
- Validates existing Dockerfiles work together
- Enables full E2E testing locally
- Frontend team can develop against real backend
- No authentication needed yet (local network)

**docker-compose.local.yml:**
```yaml
version: "3.8"

services:
  # === Frontend ===
  hai:
    build: ./HAI
    ports:
      - "3000:80"
    depends_on:
      - orchestrator
    networks:
      - agora-network

  # === Orchestrator (choose one via COMPOSE_PROFILES) ===
  orchestrator:
    build: ./server-langgraph  # or server-openai
    ports:
      - "8000:8000"
    environment:
      - LANGGRAPH_OPENAI_API_KEY=${OPENAI_API_KEY}
      - LANGGRAPH_OPENAI_BASE_URL=${LANGGRAPH_OPENAI_BASE_URL:-https://api.openai.com/v1}
      - LANGGRAPH_OPENAI_MODEL=${LANGGRAPH_OPENAI_MODEL:-gpt-4o}
      - LANGGRAPH_MCP_SERVERS=regulation=http://regulation-analysis:8000,reporting=http://reporting:8000,history=http://inspection-history:8000
    volumes:
      - ./sessions.db:/app/sessions.db
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 5
    depends_on:
      regulation-analysis:
        condition: service_healthy
    networks:
      - agora-network

  # === MCP Servers ===
  regulation-analysis:
    build:
      context: ./mcp-servers
      dockerfile: ./regulation-analysis/Dockerfile
    ports:
      - "5002:8000"
    environment:
      - MCP_WEAVIATE_URL=http://weaviate:8080
      - MCP_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
      - MCP_EMBEDDING_DEVICE=cpu
      - MCP_OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      weaviate:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - agora-network

  reporting:
    build: ./mcp-servers/reporting
    ports:
      - "5003:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - reporting_storage:/app/storage
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - agora-network

  inspection-history:
    build: ./mcp-servers/inspection-history
    ports:
      - "5005:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - agora-network

  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.27.0
    ports:
      - "8080:8080"
    environment:
      - QUERY_DEFAULTS_LIMIT=25
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
      - DEFAULT_VECTORIZER_MODULE=none
    volumes:
      - weaviate_data:/var/lib/weaviate
    healthcheck:
      test: ["CMD", "wget", "--spider", "http://localhost:8080/v1/.well-known/ready"]
      interval: 10s
      timeout: 3s
      retries: 10
    networks:
      - agora-network

networks:
  agora-network:
    driver: bridge

volumes:
  weaviate_data:
  reporting_storage:
```

**.env.local.example:**
```bash
# Required
OPENAI_API_KEY=sk-...

# Optional: LangGraph LLM configuration
LANGGRAPH_OPENAI_BASE_URL=https://api.openai.com/v1
LANGGRAPH_OPENAI_MODEL=gpt-4o
```

**Usage:**
```bash
# Start everything
cp .env.local.example .env
docker-compose -f docker-compose.local.yml up --build

# Access
# Frontend: http://localhost:3000
# Backend WebSocket: ws://localhost:8000/ws
# Backend REST: http://localhost:8000

# Run with OpenAI backend instead
docker-compose -f docker-compose.local.yml up --build \
  -e ORCHESTRATOR_IMAGE=./server-openai
```

**Dependencies:** None (uses existing Dockerfiles)

---

### Topic 1B: Frontend Development Mode
**Scope:** Enable frontend hot-reload development against Dockerized backend
**Deliverables:**
- Instructions for running HAI dev server with Docker backend
- Update `.env.local` to point to Docker services

**Setup:**
```bash
# Terminal 1: Start backend services only
docker-compose -f docker-compose.local.yml up --build \
  regulation-analysis reporting inspection-history weaviate orchestrator

# Terminal 2: Run frontend dev server
cd HAI
cp .env.example .env.local
# .env.local should have: VITE_WS_URL=ws://localhost:8000/ws
pnpm run dev
```

**Frontend connects to:**
- WebSocket: `ws://localhost:8000/ws` (Vite proxy handles this)
- REST API: Derived from WebSocket URL → `http://localhost:8000`

---

## Phase 2: API Gateway + Authentication (Local)

**Goal:** Add authentication layer that can be tested locally before cloud deployment

### Topic 2A: API Gateway Service
**Scope:** Create FastAPI gateway with API key authentication
**Deliverables:**
- `api-gateway/` directory with FastAPI app
- API key validation middleware
- HTTP proxy to backend services
- WebSocket proxy with auth (query param token)
- Dockerfile
- Health check endpoint

**Key Files:**
```
api-gateway/
├── pyproject.toml
├── Dockerfile
├── src/
│   └── api_gateway/
│       ├── __init__.py
│       ├── main.py          # FastAPI app
│       ├── auth.py          # API key validation
│       ├── proxy.py         # HTTP/WS proxy
│       └── config.py        # Pydantic settings
```

**Gateway Routing:**
- `/api/openai/*` → `http://server-openai:8000/*`
- `/api/langgraph/*` → `http://server-langgraph:8000/*`
- `/api/mock/*` → `http://mock-server:8000/*`
- `/ws` → WebSocket proxy to default backend
- `/*` → Default backend (configurable)

**Local Testing:**
```bash
# Add gateway to docker-compose
docker-compose -f docker-compose.local.yml -f docker-compose.gateway.yml up

# Test with API key
curl -H "X-API-Key: test-key-123" http://localhost:8080/health
```

### Topic 2B: API Key Management
**Scope:** Simple API key CRUD for local/production use
**Deliverables:**
- SQLite-based key storage (portable)
- Argon2 hashing for keys
- Admin endpoints protected by master key
- sqladmin UI at `/admin`

**Database Schema:**
```python
class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36))
    prefix = Column(String(8), index=True)
    secret_hash = Column(String(255))
    name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime, nullable=True)
    scopes = Column(String(255))
```

---

## Phase 3: Production Docker Compose

**Goal:** Production-ready configuration with SSL and all services

### Topic 3: Production Docker Compose
**Scope:** Extend local compose with production features
**Deliverables:**
- `docker-compose.production.yml`
- Caddy for SSL termination
- HAI built as static files
- Mock server Dockerfile

**Key Differences from Local:**
| Aspect | Local | Production |
|--------|-------|------------|
| SSL | None (HTTP only) | Caddy + Let's Encrypt |
| Frontend | Port 3000 | Via Caddy on 443 |
| API Gateway | Optional | Required (authentication) |
| Ports exposed | All (debugging) | Only 80/443 |

**Caddyfile:**
```
{$FRONTEND_DOMAIN} {
    root * /srv/hai
    file_server
    try_files {path} /index.html
}

{$API_DOMAIN} {
    reverse_proxy api-gateway:8000
}
```

---

## Phase 4: GCP Deployment

**Goal:** Deploy validated stack to GCP

### Topic 4: GCP VM Setup
**Scope:** Provision and configure GCP VM
**Deliverables:**
- VM creation (e2-standard-2 with OpenAI embeddings, or e2-standard-4 with local)
- Docker + Docker Compose installed
- Firewall rules (80, 443)
- Clone repo and run docker-compose

**Steps:**
1. Create VM (Ubuntu 22.04 LTS)
2. Install Docker + Docker Compose
3. Clone AGORA repository
4. Copy `.env.production` with secrets
5. Run `docker-compose -f docker-compose.production.yml up -d`
6. Configure DNS A records

### Topic 5: DNS Configuration
**Scope:** Configure domains for frontend and API
**Deliverables:**
- A records for both subdomains
- Caddy automatic SSL provisioning

**Domains:**
- `agora.gradient-testing.nl` → HAI Frontend
- `agora-api.gradient-testing.nl` → API Gateway

---

## Revised Implementation Order

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT TRACK                                 │
│                                                                         │
│  Phase 1: Local Full Stack                                              │
│  ├─ Topic 1A: Unified docker-compose.local.yml  ← START HERE            │
│                                                                         │
│           ↓                                                             │
│  Phase 2: API Gateway (Local)                                           │
│  ├─ Topic 2A: API Gateway service                                       │
│  └─ Topic 2B: API key management                                        │
│           ↓                                                             │
│  Phase 3: Production Config                                             │
│  └─ Topic 3: docker-compose.production.yml + Caddy                      │
│           ↓                                                             │
│  Phase 4: Cloud Deployment                                              │
│  ├─ Topic 4: GCP VM setup                                               │
│  └─ Topic 5: DNS configuration                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     INDEPENDENT TRACK (parallel)                         │
│                                                                         │
│  Topic A: OpenAI Embeddings Migration                                   │
│           → Reduces memory, enables smaller VMs                         │
│                                                                         │
│  Topic B: Multi-LLM Provider Support                                    │
│           → Documentation + optional enhancements                       │
│                                                                         │
│  Topic C: Mock Server Containerization                                  │
│           → Enables cost-free testing                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

**What Changed:**
- Frontend testing moved FIRST (Phase 1)
- GCP deployment moved LAST (Phase 4)
- Each phase can be tested independently
- Phase 1 uses existing Dockerfiles, no new code needed
- Independent topics (A, B, C) can be worked on anytime in parallel

### Topic Dependencies

```
Topic 1A (Local Compose) ← No dependencies, uses existing Dockerfiles
    ↓
Topic 1B (Frontend Dev) ← Depends on 1A
    ↓
Topic 2A (Gateway Service) ← Can develop in parallel with 1A/1B
    ↓
Topic 2B (Key Management) ← Depends on 2A
    ↓
Topic 3 (Production Compose) ← Depends on 1A + 2A
    ↓
Topic 4 (GCP VM) ← Depends on 3
    ↓
Topic 5 (DNS) ← Depends on 4
```

### Effort Estimates

**Deployment Track:**

| Topic | Complexity | Notes |
|-------|------------|-------|
| Topic 1A: Local Compose | Low | Combine existing docker-compose files |
| Topic 1B: Frontend Dev | Trivial | Documentation only |
| Topic 2A: API Gateway | Medium | New FastAPI service + WebSocket proxy |
| Topic 2B: Key Management | Low-Medium | SQLite + sqladmin integration |
| Topic 3: Production Compose | Low | Add Caddy, adjust ports |
| Topic 4: GCP VM | Low | Standard VM setup |
| Topic 5: DNS | Trivial | A records only |

**Independent Track (can run in parallel):**

| Topic | Complexity | Notes |
|-------|------------|-------|
| Topic A: OpenAI Embeddings | Low-Medium | Modify embedder class, re-ingest docs |
| Topic B: Multi-LLM Support | Low-Medium | Mostly docs, optional enhancements |
| Topic C: Mock Server Docker | Low | Simple Dockerfile |

---

## Independent Topics (No Deployment Dependencies)

These topics can be worked on in parallel with any deployment phase.

---

### Topic A: OpenAI Embeddings Migration

**Scope:** Switch from local sentence-transformers to OpenAI embeddings API

**Why This Matters:**
- Reduces regulation-analysis container memory from ~800MB to ~100MB
- Removes PyTorch/Transformers dependencies (faster builds, smaller images)
- Enables running on smaller/cheaper VMs
- Simplifies Dockerfile significantly

**Current Implementation:**
- Uses `nomic-ai/nomic-embed-text-v1.5` via sentence-transformers
- Requires PyTorch, Transformers, einops
- Embeddings generated locally for both ingestion and queries
- Vector dimensions: 768

**Key Files:**
- `mcp-servers/document-ingestion/embeddings/embedder.py` - Core embedding class
- `mcp-servers/regulation-analysis/server.py:29-47` - Query-time embedding
- `mcp-servers/document-ingestion/ingest.py` - Document ingestion pipeline
- `mcp-servers/regulation-analysis/Dockerfile` - Contains PyTorch deps
- `mcp-servers/regulation-analysis/requirements.txt`

**Deliverables:**
1. Update `embedder.py` to support OpenAI provider:
   ```python
   class Embedder:
       def __init__(self, provider: str = "local"):
           self.provider = provider
           if provider == "openai":
               self.client = openai.OpenAI()
           else:
               self.model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5")

       def embed(self, texts: list[str]) -> list[list[float]]:
           if self.provider == "openai":
               response = self.client.embeddings.create(
                   model="text-embedding-3-small",
                   input=texts,
                   dimensions=768  # Match existing for compatibility
               )
               return [e.embedding for e in response.data]
           else:
               return self.model.encode(texts).tolist()
   ```

2. Add environment variable `MCP_EMBEDDING_PROVIDER=openai|local`

3. Update Weaviate schema (or use `dimensions=768` param to match existing)

4. Simplify `regulation-analysis/Dockerfile`:
   ```dockerfile
   # Remove these lines when using OpenAI embeddings:
   # RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
   # RUN pip install sentence-transformers transformers einops
   ```

5. Update `requirements.txt` - add `openai`, conditionally remove torch deps

6. Re-run ingestion script with OpenAI embeddings:
   ```bash
   MCP_EMBEDDING_PROVIDER=openai python -m document_ingestion.ingest
   ```

7. Test query performance and verify results match

**Cost Analysis:**
| Operation | Tokens | Cost (text-embedding-3-small) |
|-----------|--------|-------------------------------|
| 1000 documents × 500 tokens | 500K | ~$0.01 |
| 1000 queries/month × 20 tokens | 20K | ~$0.0004/month |

**Dependencies:** None - can be done independently

**Complexity:** Low-Medium

---

### Topic B: Multi-LLM Provider Support

**Scope:** Document, test, and enhance alternative LLM provider support for server-langgraph

**Why This Matters:**
- Reduce costs with open-source models (Llama, DeepSeek, Qwen)
- Avoid vendor lock-in
- Enable air-gapped deployments with vLLM
- Different models for different use cases (speed vs quality)

**Current Implementation:**
Server-langgraph already supports any OpenAI-compatible API via configuration:

```python
# server-langgraph/src/agora_langgraph/config.py:21-26
openai_api_key: SecretStr = Field(description="OpenAI-compatible API key")
openai_base_url: str = Field(
    default="https://api.openai.com/v1",
    description="Base URL for OpenAI-compatible API",
)
openai_model: str = Field(default="gpt-4o", description="Default OpenAI model")
```

**Key Files:**
- `server-langgraph/src/agora_langgraph/config.py` - Settings
- `server-langgraph/src/agora_langgraph/core/agents.py:31-53` - LLM instantiation
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py` - Per-agent model config

**Deliverables:**

1. **Provider Configuration Documentation:**

   | Provider | Base URL | API Key Source | Notes |
   |----------|----------|----------------|-------|
   | OpenAI | `https://api.openai.com/v1` | OpenAI dashboard | Default |
   | Together.ai | `https://api.together.ai/v1` | together.ai | Best OSS model selection |
   | Groq | `https://api.groq.com/openai/v1` | groq.com | Fastest inference |
   | OpenRouter | `https://openrouter.ai/api/v1` | openrouter.ai | Model aggregator |
   | Fireworks | `https://api.fireworks.ai/inference/v1` | fireworks.ai | Fast, good pricing |
   | vLLM (self-hosted) | `http://localhost:8000/v1` | N/A | Air-gapped deployments |

2. **Recommended Models for Agentic Use:**

   | Model | Provider | Tool Calling | Structured Output | Cost/1M tokens |
   |-------|----------|--------------|-------------------|----------------|
   | GPT-4o | OpenAI | Excellent | Excellent | $5.00 |
   | GPT-4o-mini | OpenAI | Good | Good | $0.15 |
   | DeepSeek-V3 | Together | Excellent | Excellent | $1.25 |
   | Llama 3.3 70B | Together/Groq | Good | Good | $0.80 |
   | Qwen 2.5 72B | Together | Good | Excellent | $1.00 |

3. **Environment Configuration Examples:**

   ```bash
   # .env.together - Together.ai with DeepSeek-V3
   LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
   LANGGRAPH_OPENAI_API_KEY=your_together_key
   LANGGRAPH_OPENAI_MODEL=deepseek-ai/DeepSeek-V3

   # .env.groq - Groq with Llama 3.3 (fastest)
   LANGGRAPH_OPENAI_BASE_URL=https://api.groq.com/openai/v1
   LANGGRAPH_OPENAI_API_KEY=your_groq_key
   LANGGRAPH_OPENAI_MODEL=llama-3.3-70b-versatile

   # .env.local-vllm - Self-hosted vLLM
   LANGGRAPH_OPENAI_BASE_URL=http://localhost:8000/v1
   LANGGRAPH_OPENAI_API_KEY=not-needed
   LANGGRAPH_OPENAI_MODEL=meta-llama/Llama-3.3-70B-Instruct
   ```

4. **Test Script for Provider Validation:**
   ```python
   # scripts/test_llm_provider.py
   import asyncio
   from agora_langgraph.config import get_settings
   from langchain_openai import ChatOpenAI

   async def test_provider():
       settings = get_settings()
       llm = ChatOpenAI(
           api_key=settings.openai_api_key.get_secret_value(),
           base_url=settings.openai_base_url,
           model=settings.openai_model,
       )

       # Test basic completion
       response = await llm.ainvoke("Say 'Hello from AGORA'")
       print(f"Basic: {response.content}")

       # Test tool calling
       response = await llm.ainvoke(
           "What is 2+2?",
           tools=[{"type": "function", "function": {"name": "calculator", ...}}]
       )
       print(f"Tools: {response.tool_calls}")

   asyncio.run(test_provider())
   ```

5. **Per-Agent Model Override (Enhancement):**
   ```python
   # agent_definitions.py - Allow different models per agent
   AGENT_DEFINITIONS = {
       "general-agent": {
           "model": None,  # Use default
           ...
       },
       "regulation-agent": {
           "model": "gpt-4o",  # Force GPT-4o for complex reasoning
           ...
       },
       "reporting-agent": {
           "model": "gpt-4o-mini",  # Cheaper for report generation
           ...
       },
   }
   ```

6. **Cost Tracking (Optional Enhancement):**
   - Log token usage per request
   - Aggregate by agent/model
   - Export to monitoring

**Dependencies:** None - server-langgraph already supports this

**Complexity:** Low (documentation) to Medium (enhancements)

---

### Topic C: Mock Server Containerization

**Scope:** Create Dockerfile for mock server to enable full local testing without LLM costs

**Why This Matters:**
- Test frontend without OpenAI API costs
- CI/CD pipeline testing
- Demo environments
- Offline development

**Current State:**
- Mock server exists at `docs/hai-contract/mock_server.py`
- No Dockerfile exists
- Runs directly with `python mock_server.py`

**Deliverables:**

1. **Create `docs/hai-contract/Dockerfile.mock`:**
   ```dockerfile
   FROM python:3.11-slim

   WORKDIR /app

   # Install dependencies
   RUN pip install --no-cache-dir \
       fastapi \
       uvicorn \
       websockets \
       pydantic

   COPY mock_server.py .
   COPY schemas/ ./schemas/

   EXPOSE 8000

   HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
       CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

   CMD ["python", "mock_server.py"]
   ```

2. **Add mock server to docker-compose.local.yml:**
   ```yaml
   mock-server:
     build:
       context: ./docs/hai-contract
       dockerfile: Dockerfile.mock
     ports:
       - "8001:8000"  # Different port to avoid conflict
     networks:
       - agora-network
   ```

3. **Usage:**
   ```bash
   # Run with mock backend
   docker-compose -f docker-compose.local.yml up mock-server hai

   # Frontend .env.local for mock
   VITE_WS_URL=ws://localhost:8001/ws
   ```

**Dependencies:** None

**Complexity:** Low

---

## Quick Start (After Topic 1A)

```bash
# 1. Clone and configure
git clone <repo>
cd AGORA
cp .env.local.example .env

# 2. Add your OpenAI API key to .env
echo "OPENAI_API_KEY=sk-..." >> .env

# 3. Start everything
docker-compose -f docker-compose.local.yml up --build

# 4. Access
open http://localhost:3000  # Frontend
# WebSocket: ws://localhost:8000/ws
# MCP Health: http://localhost:5002/health
```

---

## GCP Instance Recommendations (Unchanged)

| Instance | vCPUs | RAM | Monthly Cost | Use Case |
|----------|-------|-----|--------------|----------|
| **e2-standard-2** | 2 | 8GB | ~$49/month | **Recommended with OpenAI embeddings** |
| e2-standard-4 | 4 | 16GB | ~$98/month | With local embeddings |

**Domain Configuration:**

| Domain | Service |
|--------|---------|
| `agora.gradient-testing.nl` | HAI Frontend |
| `agora-api.gradient-testing.nl` | API Gateway |
