# Production Deployment with Caddy Implementation Plan

## Overview

Create a production-ready deployment configuration using Caddy for automatic HTTPS and single-domain path-based routing. This extends the existing local development stack (`docker-compose.yml`) with production hardening: SSL termination, required authentication, and minimal port exposure.

## Current State Analysis

### Existing Infrastructure
- **Local Docker Compose** (`docker-compose.yml`): Full stack with API gateway, HAI, orchestrators, MCP servers
- **API Gateway** (`api-gateway/`): FastAPI with optional auth (`REQUIRE_AUTH` flag)
- **HAI Frontend** (`HAI/`): Multi-stage build, nginx serves static files and proxies to api-gateway
- **Environment Config** (`.env.example`): Template for local development

### Key Discoveries
- HAI nginx already proxies `/ws` and `/api/*` to `api-gateway:8000` (`HAI/nginx.gateway.conf:14-39`)
- API Gateway auth is controlled by `GATEWAY_REQUIRE_AUTH` env var (`api-gateway/src/api_gateway/config.py:17-20`)
- All services use `agora-network` bridge network for internal communication
- Frontend build args bake `VITE_WS_URL` at build time (`HAI/Dockerfile:7`)

## Desired End State

After this plan is complete:
1. Single `docker-compose -f docker-compose.production.yml up` deploys production stack
2. Caddy handles SSL termination with automatic Let's Encrypt certificates
3. Single domain (`agora.gradient-testing.nl`) serves both frontend and API via path-based routing
4. API authentication is required by default (`REQUIRE_AUTH=true`)
5. Only ports 80 and 443 are exposed to the internet
6. All internal service communication remains on Docker network

### Architecture

```
Internet (HTTPS:443)
    │
    ▼
┌─────────┐
│  Caddy  │ ← SSL termination, Let's Encrypt
└────┬────┘
     │
     ├─── /* ──────────► HAI (nginx:80)
     │                      │
     │                      ├─── /ws, /api/* → api-gateway:8000
     │                      └─── static files
     │
     └─── (internal only)
              │
              ▼
         ┌──────────────┐
         │ API Gateway  │
         └──────┬───────┘
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
server-    server-      mock-
openai     langgraph    server
    │           │
    └─────┬─────┘
          ▼
    ┌─────────────┐
    │ MCP Servers │
    └─────────────┘
```

### Verification
- HTTPS works: `curl https://agora.gradient-testing.nl/health`
- Frontend loads: Browser opens `https://agora.gradient-testing.nl`
- WebSocket connects: Chat conversation works end-to-end
- Auth required: `curl https://agora.gradient-testing.nl/api/langgraph/health` returns 401 without API key
- Auth works: Same request with `X-API-Key` header returns 200

## What We're NOT Doing

- GCP VM provisioning (that's Phase 4 in the research doc)
- DNS configuration (manual step, documented only)
- API key management UI (future enhancement)
- OpenAI embeddings migration (independent track)
- Multi-domain setup (using single domain with path routing)
- Custom SSL certificates (using Let's Encrypt)

## Implementation Approach

1. Create production Docker Compose that extends the local setup
2. Add Caddy service for SSL termination
3. Configure Caddy with single domain and path-based routing
4. Set production defaults (auth required, proper timeouts)
5. Create production environment template

---

## Phase 1: Caddyfile Configuration

### Overview
Create the Caddy configuration for automatic HTTPS with Let's Encrypt and reverse proxy routing.

### Changes Required

#### 1. Create Caddyfile
**File**: `Caddyfile`

```caddyfile
# AGORA Production Caddyfile
# Single domain with path-based routing
# All traffic goes through HAI nginx, which proxies /ws and /api/* to api-gateway

{$DOMAIN:localhost} {
    # Enable compression
    encode gzip

    # Reverse proxy everything to HAI nginx
    # HAI nginx handles:
    # - Static file serving for frontend
    # - Proxying /ws and /api/* to api-gateway
    reverse_proxy hai:80 {
        # WebSocket support
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}

        # Flush immediately for streaming responses
        flush_interval -1
    }

    # Health check endpoint for load balancers/monitoring
    handle /caddy-health {
        respond "OK" 200
    }

    # Security headers
    header {
        # Prevent clickjacking
        X-Frame-Options "SAMEORIGIN"
        # Prevent MIME type sniffing
        X-Content-Type-Options "nosniff"
        # XSS protection
        X-XSS-Protection "1; mode=block"
        # Referrer policy
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    # Logging
    log {
        output stdout
        format json
        level INFO
    }
}
```

### Success Criteria

#### Automated Verification:
- [x] Caddyfile syntax is valid: `docker run --rm -v $(pwd)/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile`

---

## Phase 2: Production Docker Compose

### Overview
Create the production Docker Compose configuration with Caddy, authentication enabled, and minimal port exposure.

### Changes Required

#### 1. Create Production Docker Compose
**File**: `docker-compose.production.yml`

```yaml
# Production deployment with Caddy SSL termination
# Usage: docker-compose -f docker-compose.production.yml up -d

services:
  # === Reverse Proxy (SSL Termination) ===
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"  # HTTP/3 (QUIC)
    environment:
      - DOMAIN=${DOMAIN:-localhost}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      hai:
        condition: service_started
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost/caddy-health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # === API Gateway ===
  api-gateway:
    build: ./api-gateway
    restart: unless-stopped
    environment:
      - GATEWAY_OPENAI_BACKEND_URL=http://server-openai:8000
      - GATEWAY_LANGGRAPH_BACKEND_URL=http://server-langgraph:8000
      - GATEWAY_MOCK_BACKEND_URL=http://mock-server:8000
      - GATEWAY_DEFAULT_BACKEND=${DEFAULT_BACKEND:-langgraph}
      - GATEWAY_API_KEYS=${API_KEYS}
      - GATEWAY_REQUIRE_AUTH=true
    depends_on:
      server-langgraph:
        condition: service_healthy
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3

  # === Frontend ===
  hai:
    build:
      context: ./HAI
      args:
        # Production: WebSocket URL is relative (same domain)
        - VITE_WS_URL=wss://${DOMAIN:-localhost}/ws
        - VITE_BACKEND=${VITE_BACKEND:-langgraph}
        - VITE_APP_NAME=${VITE_APP_NAME:-AGORA HAI}
        - VITE_SESSION_TIMEOUT=3600000
    restart: unless-stopped
    depends_on:
      - api-gateway
    networks:
      - agora-network

  # === Orchestrators ===
  server-openai:
    build: ./server-openai
    restart: unless-stopped
    environment:
      - OPENAI_AGENTS_OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_AGENTS_MCP_SERVERS=regulation=http://regulation-analysis:8000,reporting=http://reporting:8000,history=http://inspection-history:8000
      - OPENAI_AGENTS_HOST=0.0.0.0
      - OPENAI_AGENTS_PORT=8000
    depends_on:
      regulation-analysis:
        condition: service_healthy
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  server-langgraph:
    build: ./server-langgraph
    restart: unless-stopped
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
      interval: 30s
      timeout: 10s
      retries: 3

  mock-server:
    build: ./docs/hai-contract
    restart: unless-stopped
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  # === MCP Servers ===
  regulation-analysis:
    build:
      context: ./mcp-servers
      dockerfile: ./regulation-analysis/Dockerfile
    restart: unless-stopped
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
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  reporting:
    build: ./mcp-servers/reporting
    restart: unless-stopped
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - reporting_storage:/app/storage
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3

  inspection-history:
    build: ./mcp-servers/inspection-history
    restart: unless-stopped
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]
      interval: 30s
      timeout: 10s
      retries: 3

  weaviate:
    image: cr.weaviate.io/semitechnologies/weaviate:1.27.0
    restart: unless-stopped
    environment:
      - QUERY_DEFAULTS_LIMIT=25
      - AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true
      - PERSISTENCE_DATA_PATH=/var/lib/weaviate
      - DEFAULT_VECTORIZER_MODULE=none
      - CLUSTER_HOSTNAME=weaviate
      - RAFT_BOOTSTRAP_EXPECT=1
      - RAFT_JOIN=weaviate:8300
    volumes:
      - weaviate_data:/var/lib/weaviate
    networks:
      - agora-network
    healthcheck:
      test: ["CMD", "wget", "--spider", "http://localhost:8080/v1/.well-known/ready"]
      interval: 30s
      timeout: 10s
      retries: 5

  # === One-off: Document Ingestion ===
  # Run with: docker-compose -f docker-compose.production.yml run --rm document-ingestion
  # This populates Weaviate with regulation documents (required for regulation-analysis MCP)
  document-ingestion:
    build:
      context: ./mcp-servers
      dockerfile: ./document-ingestion/Dockerfile
    environment:
      - MCP_OPENAI_API_KEY=${OPENAI_API_KEY}
      - MCP_WEAVIATE_URL=http://weaviate:8080
      - MCP_EMBEDDING_PROVIDER=${MCP_EMBEDDING_PROVIDER:-openai}
      - MCP_INPUT_DIR=/app/input/SPEC Agent
    volumes:
      # Mount input PDFs (regulation documents)
      - ./mcp-servers/input:/app/input:ro
      # Persist intermediate outputs for debugging
      - ./mcp-servers/document-ingestion/output:/app/output
    depends_on:
      weaviate:
        condition: service_healthy
    networks:
      - agora-network
    profiles:
      - tools  # Only runs when explicitly requested

networks:
  agora-network:
    driver: bridge

volumes:
  caddy_data:
  caddy_config:
  weaviate_data:
  reporting_storage:
  langgraph_sessions:
```

#### 2. Create Production Environment Template
**File**: `.env.production.example`

```bash
# ============================================================
# AGORA Production Environment Configuration
# ============================================================
# Copy this to .env and fill in the values before deploying

# ============================================================
# Required: Domain Configuration
# ============================================================
# Your domain name (must have DNS A record pointing to server IP)
DOMAIN=agora.gradient-testing.nl

# ============================================================
# Required: API Keys
# ============================================================
# OpenAI API key for LLM and embeddings
OPENAI_API_KEY=sk-...

# API keys for gateway authentication (comma-separated)
# Generate secure keys: openssl rand -hex 32
API_KEYS=your-secure-api-key-here

# ============================================================
# Backend Selection
# ============================================================
# Default backend for API gateway (langgraph, openai, mock)
DEFAULT_BACKEND=langgraph

# Frontend backend selection (should match DEFAULT_BACKEND)
VITE_BACKEND=langgraph

# ============================================================
# Optional: LangGraph LLM Configuration
# ============================================================
# Use alternative OpenAI-compatible provider
# LANGGRAPH_OPENAI_BASE_URL=https://api.together.ai/v1
# LANGGRAPH_OPENAI_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo

# ============================================================
# Optional: Document Ingestion
# ============================================================
# Embedding provider for document ingestion (openai or local)
# 'openai' uses text-embedding-3-small (recommended, faster, less memory)
# 'local' uses sentence-transformers (no API costs but requires ~800MB RAM)
MCP_EMBEDDING_PROVIDER=openai

# ============================================================
# Optional: Frontend Customization
# ============================================================
VITE_APP_NAME=AGORA HAI
```

### Success Criteria

#### Automated Verification:
- [x] Docker Compose config is valid: `docker-compose -f docker-compose.production.yml config`
- [ ] All images build: `docker-compose -f docker-compose.production.yml build`
- [ ] Services start: `docker-compose -f docker-compose.production.yml up -d`
- [ ] All containers healthy: `docker-compose -f docker-compose.production.yml ps`

#### Manual Verification:
- [ ] HTTPS certificate obtained automatically (check Caddy logs)
- [ ] Frontend accessible at `https://{DOMAIN}`
- [ ] WebSocket connection works (chat conversation)
- [ ] API returns 401 without API key
- [ ] API works with valid API key header

**Implementation Note**: After completing this phase, test locally with `DOMAIN=localhost` before deploying to production.

---

## Phase 3: HAI nginx Configuration Update

### Overview
Update HAI's nginx configuration to properly handle the production setup where Caddy terminates SSL.

### Changes Required

#### 1. Update nginx.gateway.conf for X-Forwarded headers
**File**: `HAI/nginx.gateway.conf`

Add trusted proxy configuration to properly handle headers from Caddy:

```nginx
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # Use Docker's internal DNS resolver for dynamic upstream resolution
    resolver 127.0.0.11 valid=10s;

    # Trust X-Forwarded-* headers from Caddy
    set_real_ip_from 10.0.0.0/8;
    set_real_ip_from 172.16.0.0/12;
    set_real_ip_from 192.168.0.0/16;
    real_ip_header X-Forwarded-For;
    real_ip_recursive on;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy all /ws and /api requests to the API gateway
    location ~ ^/(ws|api)/ {
        set $upstream http://api-gateway:8000;
        proxy_pass $upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # Also proxy root /ws for backwards compatibility
    location = /ws {
        set $upstream http://api-gateway:8000;
        proxy_pass $upstream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
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
- [x] nginx config syntax valid: `docker run --rm -v $(pwd)/HAI/nginx.gateway.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine nginx -t`

---

## Testing Strategy

### Local Testing (before production deployment)

1. **Test with localhost domain:**
   ```bash
   # Create .env from production template
   cp .env.production.example .env
   # Edit .env: set DOMAIN=localhost, add OPENAI_API_KEY and API_KEYS

   # Start production stack
   docker-compose -f docker-compose.production.yml up --build

   # Test (Caddy will use self-signed cert for localhost)
   curl -k https://localhost/health
   curl -k -H "X-API-Key: your-api-key" https://localhost/api/langgraph/health
   ```

2. **Test authentication:**
   ```bash
   # Should return 401
   curl -k https://localhost/api/langgraph/health

   # Should return 200
   curl -k -H "X-API-Key: your-api-key" https://localhost/api/langgraph/health
   ```

3. **Test WebSocket:**
   ```bash
   # Use wscat or browser DevTools
   # Should fail without token
   wscat -c "wss://localhost/ws" --no-check

   # Should connect with token
   wscat -c "wss://localhost/ws?token=your-api-key" --no-check
   ```

4. **Run Document Ingestion (for full testing):**
   ```bash
   # Run document ingestion to populate Weaviate
   docker-compose -f docker-compose.production.yml --profile tools run --rm document-ingestion

   # Verify ingestion succeeded
   curl -X POST http://localhost:8080/v1/graphql \
     -H "Content-Type: application/json" \
     -d '{"query": "{Aggregate{RegulationChunk{meta{count}}}}"}'
   ```

### Production Deployment Steps

1. **Prerequisites:**
   - GCP VM provisioned (e2-standard-2 recommended)
   - Docker and Docker Compose installed
   - DNS A record pointing `agora.gradient-testing.nl` to VM IP
   - Firewall allows ports 80 and 443

2. **Deploy:**
   ```bash
   # SSH to VM
   ssh user@vm-ip

   # Clone repository
   git clone https://github.com/Gradient-DS/AGORA.git
   cd AGORA

   # Create production environment
   cp .env.production.example .env
   # Edit .env with production values

   # Generate API key
   echo "API_KEYS=$(openssl rand -hex 32)" >> .env

   # Start stack
   docker-compose -f docker-compose.production.yml up -d --build

   # Check logs
   docker-compose -f docker-compose.production.yml logs -f caddy
   ```

3. **Run Document Ingestion (one-time setup):**
   ```bash
   # Wait for Weaviate to be healthy
   docker-compose -f docker-compose.production.yml ps weaviate

   # Run document ingestion to populate Weaviate with regulation documents
   # This parses PDFs, generates embeddings, and uploads to Weaviate
   docker-compose -f docker-compose.production.yml --profile tools run --rm document-ingestion

   # Verify documents were ingested
   curl -X POST http://localhost:8080/v1/graphql \
     -H "Content-Type: application/json" \
     -d '{"query": "{Aggregate{RegulationChunk{meta{count}}}}"}'
   # Should return count > 0
   ```

   **Note**: Document ingestion only needs to be run once, or when adding new regulation documents. The data persists in the `weaviate_data` volume.

4. **Verify:**
   ```bash
   # Check SSL certificate
   curl -v https://agora.gradient-testing.nl/health

   # Check all services healthy
   docker-compose -f docker-compose.production.yml ps
   ```

### Manual Testing Checklist
- [ ] HTTPS works without certificate warnings
- [ ] Frontend loads and displays correctly
- [ ] Chat conversation works end-to-end
- [ ] Agent handoffs work (general → regulation → reporting)
- [ ] MCP tool calls succeed
- [ ] Regulation search returns results (requires document ingestion)
- [ ] API requires authentication (returns 401 without key)
- [ ] API works with X-API-Key header
- [ ] WebSocket works with token query param

## Performance Considerations

- **Caddy caching**: Consider adding cache headers for static assets
- **Connection pooling**: Caddy handles this automatically
- **Health check intervals**: Set to 30s in production (vs 10s in dev) to reduce load
- **Restart policy**: All services set to `unless-stopped` for automatic recovery

## Security Considerations

- **API keys**: Generated with `openssl rand -hex 32` for sufficient entropy
- **No secrets in Docker images**: All secrets via environment variables
- **Internal network**: Backend services not exposed to internet
- **Security headers**: Added via Caddy (X-Frame-Options, X-Content-Type-Options, etc.)
- **HTTPS only**: Caddy automatically redirects HTTP to HTTPS

## Rollback Plan

If issues occur:
```bash
# Stop production stack
docker-compose -f docker-compose.production.yml down

# Fall back to local stack (for debugging)
docker-compose up -d

# Check logs for issues
docker-compose -f docker-compose.production.yml logs --tail=100
```

## References

- Research document: `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md`
- Unified gateway plan: `thoughts/shared/plans/2026-01-12-unified-gateway-deployment.md`
- Caddy documentation: https://caddyserver.com/docs/
- HAI nginx config: `HAI/nginx.gateway.conf`
- API gateway auth: `api-gateway/src/api_gateway/auth.py`
- Document ingestion: `mcp-servers/document-ingestion/README.md`
- Document ingestion Dockerfile: `mcp-servers/document-ingestion/Dockerfile`
