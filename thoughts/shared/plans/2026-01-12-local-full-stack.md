# Local Full Stack Implementation Plan

## Overview

Create a unified Docker Compose configuration that starts the entire AGORA stack locally with a single command. This enables full end-to-end testing on developer machines, validates Docker configurations before cloud deployment, and allows frontend development against a real backend.

## Current State Analysis

### Existing Docker Infrastructure

The codebase has separate docker-compose files for each service:

| Component | docker-compose | Network | Issue |
|-----------|----------------|---------|-------|
| HAI | `HAI/docker-compose.yml` | agora-network (external) | Expects `orchestrator` service |
| server-langgraph | `server-langgraph/docker-compose.yml` | default (none!) | **Not on agora-network** |
| server-openai | `server-openai/docker-compose.yml` | agora-network (external) | OK |
| MCP Servers | `mcp-servers/docker-compose.yml` | agora-network (creates it) | OK |

### Key Discoveries

1. **HAI nginx.conf** (`HAI/nginx.conf:12`) proxies `/ws` to `http://orchestrator:8000` - expects a service named `orchestrator`
2. **Network ownership**: `mcp-servers/docker-compose.yml:101-104` creates the `agora-network`
3. **server-langgraph missing network**: Its docker-compose doesn't join agora-network at all
4. **Environment prefix inconsistency**: Pydantic configs use `LANGGRAPH_*` but some docker-compose files use `APP_*`
5. **All services have health endpoints**: Can use for `depends_on` with `condition: service_healthy`

### Health Endpoints (All on port 8000 internally)

| Service | Endpoint | Implementation |
|---------|----------|----------------|
| server-openai | `/health` | `server-openai/src/agora_openai/api/server.py:106-109` |
| server-langgraph | `/health` | `server-langgraph/src/agora_langgraph/api/server.py:107-110` |
| regulation-analysis | `/health` | `mcp-servers/regulation-analysis/server.py:256-264` |
| reporting | `/health` | `mcp-servers/reporting/server.py:401-409` |
| inspection-history | `/health` | `mcp-servers/inspection-history/server.py:521-532` |

## Desired End State

After implementation:
1. Run `docker compose -f docker-compose.local.yml up --build` from project root
2. Frontend available at `http://localhost:3000`
3. Backend WebSocket at `ws://localhost:8000/ws`
4. All MCP servers running and accessible
5. Full E2E testing possible without any additional setup

### Verification

```bash
# Start everything
docker compose -f docker-compose.local.yml up --build

# Verify services
curl http://localhost:8000/health  # orchestrator
curl http://localhost:5002/health  # regulation-analysis
curl http://localhost:5003/health  # reporting
curl http://localhost:5005/health  # inspection-history

# Frontend should load and connect via WebSocket
open http://localhost:3000
```

## What We're NOT Doing

- **No API Gateway/Authentication**: That's Phase 2
- **No SSL/HTTPS**: Local development only
- **No Mock Server Docker**: That's Independent Topic C
- **No Cloud Deployment**: That's Phase 4
- **No changes to existing Dockerfiles**: Reuse what exists

---

## Phase 1: Create Unified Docker Compose

### Overview

Create `docker-compose.local.yml` at project root that combines all services into a single orchestrated stack.

### Changes Required

#### 1. Create docker-compose.local.yml

**File**: `/Users/lexlubbers/Code/AGORA/docker-compose.local.yml` (new file)

```yaml
# Unified local development stack for AGORA
# Usage: docker compose -f docker-compose.local.yml up --build
#
# Services:
#   - hai: Frontend (http://localhost:3000)
#   - orchestrator: Backend WebSocket server (ws://localhost:8000/ws)
#   - regulation-analysis: MCP server (http://localhost:5002)
#   - reporting: MCP server (http://localhost:5003)
#   - inspection-history: MCP server (http://localhost:5005)
#   - weaviate: Vector database (http://localhost:8080)

services:
  # ============================================================
  # Frontend
  # ============================================================
  hai:
    build: ./HAI
    ports:
      - "3000:80"
    environment:
      - NODE_ENV=production
    depends_on:
      orchestrator:
        condition: service_healthy
    networks:
      - agora-network
    restart: unless-stopped

  # ============================================================
  # Orchestrator (LangGraph backend)
  # Named 'orchestrator' to match HAI nginx.conf proxy config
  # ============================================================
  orchestrator:
    build: ./server-langgraph
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      LANGGRAPH_OPENAI_API_KEY: ${OPENAI_API_KEY}
      LANGGRAPH_OPENAI_BASE_URL: ${LANGGRAPH_OPENAI_BASE_URL:-https://api.openai.com/v1}
      LANGGRAPH_OPENAI_MODEL: ${LANGGRAPH_OPENAI_MODEL:-gpt-4o}
      LANGGRAPH_MCP_SERVERS: "regulation=http://regulation-analysis:8000,reporting=http://reporting:8000,history=http://inspection-history:8000"
      LANGGRAPH_HOST: "0.0.0.0"
      LANGGRAPH_PORT: "8000"
      LANGGRAPH_LOG_LEVEL: ${LOG_LEVEL:-INFO}
    volumes:
      - sessions_data:/app/sessions.db
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    depends_on:
      regulation-analysis:
        condition: service_healthy
      reporting:
        condition: service_healthy
      inspection-history:
        condition: service_healthy
    networks:
      - agora-network
    restart: unless-stopped

  # ============================================================
  # MCP Servers
  # ============================================================
  regulation-analysis:
    build:
      context: ./mcp-servers
      dockerfile: ./regulation-analysis/Dockerfile
    ports:
      - "5002:8000"
    env_file:
      - .env
    environment:
      MCP_WEAVIATE_URL: "http://weaviate:8080"
      MCP_EMBEDDING_MODEL: "nomic-ai/nomic-embed-text-v1.5"
      MCP_EMBEDDING_DEVICE: "cpu"
      MCP_OPENAI_API_KEY: ${OPENAI_API_KEY}
    depends_on:
      weaviate:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - agora-network
    restart: unless-stopped

  reporting:
    build:
      context: ./mcp-servers/reporting
      dockerfile: Dockerfile
    ports:
      - "5003:8000"
    env_file:
      - .env
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - reporting_storage:/app/storage
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - agora-network
    restart: unless-stopped

  inspection-history:
    build:
      context: ./mcp-servers/inspection-history
      dockerfile: Dockerfile
    ports:
      - "5005:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - agora-network
    restart: unless-stopped

  # ============================================================
  # Infrastructure
  # ============================================================
  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.27.0
    ports:
      - "8080:8080"
      - "50051:50051"
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
      PERSISTENCE_DATA_PATH: '/var/lib/weaviate'
      DEFAULT_VECTORIZER_MODULE: 'none'
      ENABLE_MODULES: ''
      CLUSTER_HOSTNAME: 'node1'
    volumes:
      - weaviate_data:/var/lib/weaviate
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=3", "--spider", "http://localhost:8080/v1/.well-known/ready"]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 10s
    networks:
      - agora-network
    restart: unless-stopped

networks:
  agora-network:
    driver: bridge
    name: agora-network

volumes:
  weaviate_data:
  reporting_storage:
  sessions_data:
```

#### 2. Create Environment Template

**File**: `/Users/lexlubbers/Code/AGORA/.env.local.example` (new file)

```bash
# AGORA Local Development Environment
# Copy to .env and fill in your API key
#
# Usage:
#   cp .env.local.example .env
#   # Edit .env with your OpenAI API key
#   docker compose -f docker-compose.local.yml up --build

# ============================================================
# Required
# ============================================================

# OpenAI API key - used by orchestrator and MCP servers
OPENAI_API_KEY=sk-your-api-key-here

# ============================================================
# Optional: LLM Provider Configuration
# ============================================================

# For alternative OpenAI-compatible providers (Together.ai, Groq, etc.)
# LANGGRAPH_OPENAI_BASE_URL=https://api.openai.com/v1
# LANGGRAPH_OPENAI_MODEL=gpt-4o

# Examples:
# Together.ai with DeepSeek-V3:
#   LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
#   LANGGRAPH_OPENAI_MODEL=deepseek-ai/DeepSeek-V3
#
# Groq with Llama 3.3 (fastest):
#   LANGGRAPH_OPENAI_BASE_URL=https://api.groq.com/openai/v1
#   LANGGRAPH_OPENAI_MODEL=llama-3.3-70b-versatile

# ============================================================
# Optional: Development Settings
# ============================================================

# Log level: DEBUG, INFO, WARNING, ERROR
# LOG_LEVEL=INFO
```

### Success Criteria

#### Automated Verification

```bash
# 1. Environment setup
cp .env.local.example .env
# Edit .env with real OPENAI_API_KEY

# 2. Build and start all services
docker compose -f docker-compose.local.yml up --build -d

# 3. Wait for services to be healthy (up to 2 minutes)
docker compose -f docker-compose.local.yml ps

# 4. Health checks pass
curl -s http://localhost:8000/health | grep -q "healthy"
curl -s http://localhost:5002/health | grep -q "healthy"
curl -s http://localhost:5003/health | grep -q "healthy"
curl -s http://localhost:5005/health | grep -q "healthy"
curl -s http://localhost:8080/v1/.well-known/ready | grep -q "true"

# 5. Frontend serves
curl -s http://localhost:3000 | grep -q "AGORA"
```

- [ ] `docker compose -f docker-compose.local.yml config` validates without errors
- [ ] `docker compose -f docker-compose.local.yml build` completes successfully
- [ ] All services reach healthy state within 2 minutes
- [ ] All health endpoints return 200

#### Manual Verification

- [ ] Open `http://localhost:3000` in browser - HAI frontend loads
- [ ] WebSocket connects successfully (check browser DevTools Network tab)
- [ ] Send a test message - orchestrator responds via AG-UI Protocol
- [ ] Tool calls to MCP servers work (e.g., regulation search)

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Frontend Development Mode Documentation

### Overview

Document how to run the HAI frontend in development mode (with hot-reload) against the Dockerized backend services.

### Changes Required

#### 1. Update HAI README with Local Dev Instructions

**File**: `/Users/lexlubbers/Code/AGORA/HAI/README.md`

Add the following section:

```markdown
## Development with Docker Backend

Run the frontend with hot-reload against the full Docker backend stack:

### Option 1: Full Stack with Built Frontend

Start everything including a production build of the frontend:

```bash
# From project root
docker compose -f docker-compose.local.yml up --build
# Frontend: http://localhost:3000
```

### Option 2: Dev Server with Docker Backend

Run the frontend dev server while backend runs in Docker:

```bash
# Terminal 1: Start backend services only (from project root)
docker compose -f docker-compose.local.yml up --build \
  orchestrator regulation-analysis reporting inspection-history weaviate

# Terminal 2: Run frontend dev server (from HAI directory)
cd HAI
cp .env.example .env.local
# Ensure .env.local has: VITE_WS_URL=ws://localhost:8000/ws
pnpm run dev
# Frontend with hot-reload: http://localhost:5173
```

### Environment Configuration

For local development against Docker backend, your `HAI/.env.local` should contain:

```bash
VITE_WS_URL=ws://localhost:8000/ws
VITE_APP_NAME=AGORA HAI (Dev)
```

The WebSocket URL points to the Docker orchestrator service which proxies to the LangGraph backend.
```

#### 2. Ensure HAI .env.example is Correct

**File**: `/Users/lexlubbers/Code/AGORA/HAI/.env.example`

Verify it contains (should already be correct based on research):

```bash
VITE_WS_URL=ws://localhost:8000/ws
```

### Success Criteria

#### Automated Verification

- [ ] `HAI/README.md` contains "Development with Docker Backend" section
- [ ] `HAI/.env.example` contains `VITE_WS_URL=ws://localhost:8000/ws`

#### Manual Verification

- [ ] Start backend services with Docker (Terminal 1)
- [ ] Run `pnpm run dev` in HAI directory (Terminal 2)
- [ ] Open `http://localhost:5173` - frontend loads with hot-reload
- [ ] Make a CSS change - browser updates without refresh
- [ ] Send a message - backend responds correctly

---

## Testing Strategy

### Integration Tests

1. **Full Stack Startup**
   - All 6 services start successfully
   - Health checks pass for all services
   - Services communicate via Docker network

2. **End-to-End Flow**
   - Frontend connects to orchestrator via WebSocket
   - User message triggers LLM response
   - Tool calls route to correct MCP server
   - Response streams back to frontend

### Manual Testing Steps

1. Start full stack: `docker compose -f docker-compose.local.yml up --build`
2. Open `http://localhost:3000`
3. Select/create a user
4. Start a conversation: "Hello, I'm an inspector checking a restaurant"
5. Verify agent responds with relevant information
6. Ask a regulation question to trigger MCP tool call
7. Verify tool results appear in conversation

---

## Alternative: OpenAI Backend

To use the OpenAI Agents SDK backend instead of LangGraph, modify docker-compose.local.yml:

```yaml
orchestrator:
  build: ./server-openai  # Change from server-langgraph
  environment:
    OPENAI_AGENTS_OPENAI_API_KEY: ${OPENAI_API_KEY}
    OPENAI_AGENTS_OPENAI_MODEL: ${OPENAI_MODEL:-gpt-4o}
    OPENAI_AGENTS_MCP_SERVERS: "regulation=http://regulation-analysis:8000,reporting=http://reporting:8000,history=http://inspection-history:8000"
```

Note: The environment prefix changes from `LANGGRAPH_` to `OPENAI_AGENTS_` to match the Pydantic settings in `server-openai/src/agora_openai/config.py`.

---

## References

- Research document: `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md`
- HAI nginx configuration: `HAI/nginx.conf`
- Existing MCP docker-compose: `mcp-servers/docker-compose.yml`
- Environment templates: `.env.example`, `HAI/.env.example`
