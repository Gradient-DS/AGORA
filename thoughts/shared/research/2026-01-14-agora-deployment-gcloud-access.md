---
date: 2026-01-14T10:30:00+01:00
researcher: Claude
git_commit: 69c02f4e8f1fd6bcbb5b48f5bccfa2fb2aac56f0
branch: main
repository: AGORA
topic: "AGORA Deployment Architecture and GCloud CLI Access"
tags: [research, deployment, gcp, gcloud, infrastructure, docker]
status: complete
last_updated: 2026-01-14
last_updated_by: Claude
---

# Research: AGORA Deployment Architecture and GCloud CLI Access

**Date**: 2026-01-14T10:30:00+01:00
**Researcher**: Claude
**Git Commit**: 69c02f4e8f1fd6bcbb5b48f5bccfa2fb2aac56f0
**Branch**: main
**Repository**: AGORA

## Research Question

How is AGORA currently deployed, and how can it be accessed via Google Cloud CLI?

## Summary

AGORA is deployed on a **single GCP VM** (`agora-production`) in project `agora-484112`, running all services via Docker Compose with Caddy as the reverse proxy for SSL termination.

**Quick Access Commands:**
```bash
# SSH to production VM
gcloud compute ssh agora-production --project=agora-484112 --zone=europe-west4-a

# View container status
docker compose -f docker-compose.production.yml ps

# View logs
docker compose -f docker-compose.production.yml logs -f
```

**Production URL:** `https://agora.gradient-testing.nl`

## Detailed Findings

### Current Deployment Architecture

```
Internet
    ↓ HTTPS (443)
Caddy (SSL Termination, Let's Encrypt)
    ↓
HAI Frontend (nginx serving React app)
    ↓ /ws, /api/*
API Gateway (FastAPI)
    ├─→ server-langgraph (default orchestrator)
    ├─→ server-openai (alternative orchestrator)
    └─→ mock-server (testing)
    ↓ MCP calls
MCP Servers
    ├── regulation-analysis (Weaviate + embeddings)
    ├── reporting
    └── inspection-history
```

### GCP Infrastructure Details

| Resource | Value |
|----------|-------|
| **Project ID** | `agora-484112` |
| **VM Name** | `agora-production` |
| **Zone** | `europe-west4-a` |
| **Machine Type** | `e2-standard-4` (4 vCPUs, 16GB RAM) |
| **OS** | Ubuntu 22.04 LTS |
| **Static IP** | `agora-production-ip` |
| **Domain** | `agora.gradient-testing.nl` |
| **Monthly Cost** | ~$110-120 (VM + IP + disk) |

### Docker Compose Services

The production stack (`docker-compose.production.yml`) runs 10 services:

| Service | Port | Purpose |
|---------|------|---------|
| `caddy` | 80, 443 | SSL termination, reverse proxy |
| `hai` | 80 (internal) | Frontend (React + nginx) |
| `api-gateway` | 8000 (internal) | Auth + routing to backends |
| `server-langgraph` | 8000 (internal) | Default orchestrator |
| `server-openai` | 8000 (internal) | Alternative orchestrator |
| `mock-server` | 8000 (internal) | Testing backend |
| `regulation-analysis` | 8000 (internal) | MCP: regulation search |
| `reporting` | 8000 (internal) | MCP: report generation |
| `inspection-history` | 8000 (internal) | MCP: inspection data |
| `weaviate` | 8080 (internal) | Vector database |

## GCloud CLI Access Guide

### Prerequisites

1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
2. Authenticate: `gcloud auth login`
3. Set project: `gcloud config set project agora-484112`

### Common Operations

#### SSH to Production VM

```bash
# Standard SSH
gcloud compute ssh agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a

# SSH with port forwarding (for local access to services)
gcloud compute ssh agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a \
  -- -L 8080:localhost:8080
```

#### Check VM Status

```bash
# View VM status
gcloud compute instances describe agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a \
  --format="table(name,status,networkInterfaces[0].accessConfigs[0].natIP)"

# List all VMs in project
gcloud compute instances list --project=agora-484112
```

#### Start/Stop VM

```bash
# Stop VM (saves cost but loses SSL certificate cache)
gcloud compute instances stop agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a

# Start VM
gcloud compute instances start agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a
```

#### View Logs (Serial Console)

```bash
# View boot logs
gcloud compute instances get-serial-port-output agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a
```

#### Get External IP

```bash
# Get static IP address
gcloud compute addresses describe agora-production-ip \
  --project=agora-484112 \
  --region=europe-west4 \
  --format="value(address)"
```

### On-VM Docker Operations

After SSH'ing to the VM:

```bash
cd /opt/agora

# View all container status
docker compose -f docker-compose.production.yml ps

# View logs (all services)
docker compose -f docker-compose.production.yml logs -f

# View logs (specific service)
docker compose -f docker-compose.production.yml logs -f server-langgraph

# Restart a service
docker compose -f docker-compose.production.yml restart api-gateway

# Full restart
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d

# Update deployment (pull new code and rebuild)
git pull
docker compose -f docker-compose.production.yml up -d --build

# Check resource usage
docker stats --no-stream
```

### Health Checks

```bash
# From local machine (external)
curl -s https://agora.gradient-testing.nl/caddy-health
curl -s https://agora.gradient-testing.nl/api/langgraph/health

# From VM (internal)
curl -s http://localhost:8000/health   # api-gateway
curl -s http://localhost:8080/v1/.well-known/ready  # weaviate
```

### Firewall Rules

```bash
# List AGORA firewall rules
gcloud compute firewall-rules list \
  --project=agora-484112 \
  --filter="name~agora"
```

Current rules:
- `agora-allow-http` - TCP:80 from 0.0.0.0/0 (Let's Encrypt + redirect)
- `agora-allow-https` - TCP:443 from 0.0.0.0/0 (production traffic)

## Code References

- `docker-compose.production.yml` - Production Docker Compose configuration
- `docker-compose.yml` - Local development configuration
- `Caddyfile` - Caddy reverse proxy configuration
- `.env.production.example` - Production environment template
- `thoughts/shared/plans/2026-01-12-gcp-vm-deployment.md` - Detailed deployment plan
- `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md` - Architecture research

## Architecture Insights

### Single-Domain Architecture

AGORA uses a single domain (`agora.gradient-testing.nl`) with path-based routing:
- `/` - Frontend (HAI React app)
- `/ws` - WebSocket connection to orchestrator
- `/api/*` - REST API endpoints
- `/caddy-health` - Health check endpoint

This simplifies SSL management and CORS configuration.

### Authentication

The API gateway supports optional API key authentication:
- Controlled by `GATEWAY_REQUIRE_AUTH` environment variable
- API keys passed via `X-API-Key` header or WebSocket query parameter
- Currently disabled for testing (`GATEWAY_REQUIRE_AUTH=false`)

### Backend Switching

The orchestrator can be switched without frontend changes:
- `DEFAULT_BACKEND=langgraph` - LangGraph (default, supports any OpenAI-compatible API)
- `DEFAULT_BACKEND=openai` - OpenAI Agents SDK
- `DEFAULT_BACKEND=mock` - Mock server for testing

## Operational Notes

### Updating the Application

```bash
# SSH to VM
gcloud compute ssh agora-production --project=agora-484112 --zone=europe-west4-a

# Update
cd /opt/agora
git pull
docker compose -f docker-compose.production.yml up -d --build
```

### Viewing Production Logs

```bash
# SSH and view logs
gcloud compute ssh agora-production --project=agora-484112 --zone=europe-west4-a \
  --command="cd /opt/agora && docker compose -f docker-compose.production.yml logs --tail=100"
```

### Backup Weaviate Data

```bash
# On VM
docker run --rm \
  -v agora_weaviate_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/weaviate-backup-$(date +%Y%m%d).tar.gz -C /data .
```

## Open Questions

1. **Monitoring**: No external monitoring configured yet (GCP Cloud Monitoring integration pending)
2. **CI/CD**: Manual deployment only - no automated pipeline
3. **Backup Strategy**: Volume backups not automated
4. **Scaling**: Single VM only - no auto-scaling or load balancing

## Related Research

- `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md` - Detailed deployment architecture analysis
- `thoughts/shared/plans/2026-01-12-gcp-vm-deployment.md` - Step-by-step deployment plan
- `thoughts/shared/plans/2026-01-12-production-deployment-caddy.md` - Caddy configuration plan
