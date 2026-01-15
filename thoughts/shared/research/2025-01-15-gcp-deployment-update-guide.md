---
date: 2025-01-15T16:00:00+01:00
researcher: Claude
branch: main
repository: AGORA
topic: "GCP Deployment Update Guide"
tags: [operations, deployment, gcp, docker, commands]
status: complete
---

# GCP Deployment Update Guide

Quick reference for updating the AGORA deployment on GCP.

## Quick Reference

### SSH to Production VM

```bash
gcloud compute ssh agora-production --project=agora-484112 --zone=europe-west4-a
```

### Update and Redeploy

```bash
# SSH to VM first, then:
cd /opt/agora
git pull
docker compose -f docker-compose.production.yml up -d --build
```

---

## Production Environment Details

| Property | Value |
|----------|-------|
| **Project ID** | `agora-484112` |
| **VM Name** | `agora-production` |
| **Zone** | `europe-west4-a` |
| **Domain** | `agora.gradient-testing.nl` |
| **App Directory** | `/opt/agora` |

---

## Common Operations

### Full Deployment Update

SSH to the VM and run:

```bash
cd /opt/agora

# Pull latest changes
git pull

# Rebuild and restart all services
docker compose -f docker-compose.production.yml up -d --build

# Watch startup logs
docker compose -f docker-compose.production.yml logs -f
```

### Update Specific Service Only

```bash
cd /opt/agora

# Rebuild and restart only one service (zero-downtime for others)
docker compose -f docker-compose.production.yml up -d --build --no-deps <service-name>

# Example: Update only the langgraph server
docker compose -f docker-compose.production.yml up -d --build --no-deps server-langgraph

# Example: Update only the frontend
docker compose -f docker-compose.production.yml up -d --build --no-deps hai
```

Available services:
- `caddy` - Reverse proxy / SSL
- `hai` - Frontend
- `api-gateway` - Authentication gateway
- `server-langgraph` - LangGraph orchestrator (default)
- `server-openai` - OpenAI Agents SDK orchestrator
- `mock-server` - Test backend
- `regulation-analysis` - MCP: regulation search
- `reporting` - MCP: report generation
- `inspection-history` - MCP: inspection data
- `weaviate` - Vector database

### Check Service Status

```bash
cd /opt/agora

# View all container status
docker compose -f docker-compose.production.yml ps

# Check resource usage
docker stats --no-stream
```

### View Logs

```bash
cd /opt/agora

# All services (follow)
docker compose -f docker-compose.production.yml logs -f

# Specific service
docker compose -f docker-compose.production.yml logs -f server-langgraph

# Last 100 lines of a service
docker compose -f docker-compose.production.yml logs --tail=100 api-gateway
```

### Restart Services

```bash
cd /opt/agora

# Restart single service
docker compose -f docker-compose.production.yml restart api-gateway

# Full restart (stop all, then start)
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d
```

---

## Health Checks

### From Local Machine (External)

```bash
# Basic health check
curl -s https://agora.gradient-testing.nl/caddy-health

# API health (requires auth if enabled)
curl -s https://agora.gradient-testing.nl/api/langgraph/health

# With API key
curl -s -H "X-API-Key: YOUR_KEY" https://agora.gradient-testing.nl/api/langgraph/health
```

### From VM (Internal)

```bash
# API Gateway
curl -s http://localhost:8000/health

# Weaviate
curl -s http://localhost:8080/v1/.well-known/ready

# MCP servers
curl -s http://localhost:5002/health  # regulation-analysis
curl -s http://localhost:5003/health  # reporting
curl -s http://localhost:5005/health  # inspection-history
```

---

## Environment Variables

Edit the production environment file:

```bash
cd /opt/agora
nano .env
```

Key variables:
- `OPENAI_API_KEY` - OpenAI API key
- `GATEWAY_REQUIRE_AUTH` - Enable/disable API authentication (`true`/`false`)
- `GATEWAY_API_KEYS` - Comma-separated API keys
- `DEFAULT_BACKEND` - Default orchestrator (`langgraph`, `openai`, `mock`)

After editing, restart the affected service:

```bash
docker compose -f docker-compose.production.yml restart api-gateway
```

---

## Troubleshooting

### Container Keeps Restarting

```bash
# Check container logs
docker compose -f docker-compose.production.yml logs <service-name> --tail=100

# Check if out of memory
docker stats --no-stream
free -h
```

### SSL Certificate Issues

```bash
# Check Caddy logs
docker compose -f docker-compose.production.yml logs caddy --tail=50

# Force certificate renewal (if needed)
docker compose -f docker-compose.production.yml restart caddy
```

### Disk Space

```bash
# Check disk usage
df -h

# Clean up Docker resources
docker system prune -f

# Remove unused images
docker image prune -a -f
```

### Git Pull Conflicts

```bash
cd /opt/agora

# Stash local changes
git stash

# Pull latest
git pull

# Re-apply local changes if needed
git stash pop
```

---

## Backup Operations

### Backup Weaviate Data

```bash
cd /opt/agora

docker run --rm \
  -v agora_weaviate_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/weaviate-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Backup SQLite Databases

```bash
cd /opt/agora

# Copy session databases
docker cp $(docker compose -f docker-compose.production.yml ps -q server-langgraph):/app/sessions.db ./sessions-langgraph-backup.db
```

---

## VM Operations

### Start/Stop VM (from local machine)

```bash
# Stop VM (saves cost, but containers will be down)
gcloud compute instances stop agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a

# Start VM
gcloud compute instances start agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a

# Check status
gcloud compute instances describe agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a \
  --format="table(name,status,networkInterfaces[0].accessConfigs[0].natIP)"
```

### View Boot Logs

```bash
gcloud compute instances get-serial-port-output agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a
```

---

## One-Liner Deployment Update

For quick updates when you know everything is fine:

```bash
gcloud compute ssh agora-production --project=agora-484112 --zone=europe-west4-a \
  --command="cd /opt/agora && git pull && docker compose -f docker-compose.production.yml up -d --build"
```

---

## References

- Full deployment plan: `thoughts/shared/plans/2026-01-12-gcp-vm-deployment.md`
- Architecture details: `thoughts/shared/research/2026-01-14-agora-deployment-gcloud-access.md`
- Production Docker Compose: `docker-compose.production.yml`
