# GCP VM Deployment Implementation Plan

## Overview

Deploy the AGORA production stack to a GCP VM using the `docker-compose.production.yml` configuration created in the previous phase. This plan covers VM provisioning via gcloud CLI, Docker installation, firewall configuration, and deployment verification.

## Prerequisites

Before starting, ensure:
1. The production Docker Compose configuration is complete (`docker-compose.production.yml`, `Caddyfile`)
2. You have billing enabled on GCP project `agora-484112`
3. You have the gcloud CLI authenticated with appropriate permissions

## DNS Instructions (Manual - Do This First)

**You need to create an A record AFTER the VM is created** (once you have the static IP). The steps are:

1. Go to Cloud DNS in the GCP Console (in the project containing `gradient-testing.nl` zone)
2. Select the `gradient-testing` zone
3. Click "Add standard" record set
4. Configure:
   - **DNS name**: `agora` (this creates `agora.gradient-testing.nl`)
   - **Resource record type**: A
   - **TTL**: 300 (5 minutes, good for initial setup)
   - **IPv4 Address**: `<STATIC_IP>` (will be provided in Phase 1)
5. Click "Create"

**Verification**: After DNS propagation (usually 1-5 minutes):
```bash
dig agora.gradient-testing.nl +short
# Should return the static IP
```

---

## Current State Analysis

### GCP Project Status
- **Project**: `agora-484112`
- **Compute Engine API**: Not enabled (will be enabled in Phase 1)
- **Existing VMs**: None
- **Existing firewall rules**: None custom
- **Reserved IPs**: None

### Key Discoveries
- Using `e2-standard-4` (4 vCPUs, 16GB RAM) at ~$98/month for comfortable headroom
- Single domain architecture: `agora.gradient-testing.nl` serves both frontend and API
- Caddy handles automatic SSL via Let's Encrypt
- DNS zone is in a separate project (manual A record creation required)

## Desired End State

After this plan is complete:
1. VM `agora-production` running in `europe-west4-a` with static IP
2. Docker and Docker Compose v2 installed
3. Firewall allows HTTP (80) and HTTPS (443) from internet
4. AGORA repository cloned and configured
5. Production stack running with automatic HTTPS
6. DNS record pointing `agora.gradient-testing.nl` to the VM

### Verification
- `https://agora.gradient-testing.nl` loads the HAI frontend
- WebSocket connection works (chat functions)
- API requires authentication (returns 401 without key)

## What We're NOT Doing

- Automated DNS management (separate project)
- Container-Optimized OS (using Ubuntu for flexibility)
- Load balancing or auto-scaling (single VM)
- Managed database (using SQLite/Weaviate in containers)
- CI/CD pipeline (manual deployment for now)
- Monitoring/alerting setup (future enhancement)

---

## Phase 1: GCP Infrastructure Setup

### Overview
Enable Compute Engine API, reserve a static IP, and create the VM with appropriate firewall rules.

### Changes Required

#### 1. Enable Compute Engine API

```bash
gcloud services enable compute.googleapis.com --project=agora-484112
```

Wait for API to be enabled (~1-2 minutes).

#### 2. Reserve Static External IP

```bash
gcloud compute addresses create agora-production-ip \
  --project=agora-484112 \
  --region=europe-west4 \
  --description="Static IP for AGORA production"
```

Get the reserved IP:
```bash
gcloud compute addresses describe agora-production-ip \
  --project=agora-484112 \
  --region=europe-west4 \
  --format="value(address)"
```

**Save this IP** - you'll need it for DNS configuration.

#### 3. Create Firewall Rules

Allow HTTP and HTTPS traffic:

```bash
# Allow HTTP (for Let's Encrypt ACME challenge and redirect)
gcloud compute firewall-rules create agora-allow-http \
  --project=agora-484112 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:80 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=agora-web \
  --description="Allow HTTP for AGORA (Let's Encrypt and redirect)"

# Allow HTTPS
gcloud compute firewall-rules create agora-allow-https \
  --project=agora-484112 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=agora-web \
  --description="Allow HTTPS for AGORA production"
```

#### 4. Create VM Instance

```bash
gcloud compute instances create agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-balanced \
  --tags=agora-web \
  --address=agora-production-ip \
  --metadata=startup-script='#!/bin/bash
# Log startup
echo "AGORA VM startup script running at $(date)" >> /var/log/agora-startup.log

# Wait for apt to be available
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
  sleep 1
done

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add default user to docker group
usermod -aG docker $(ls /home | head -1)

# Install Docker Compose v2 plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

echo "Docker installation complete at $(date)" >> /var/log/agora-startup.log
' \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

### Success Criteria

#### Automated Verification:
- [x] Compute API enabled: `gcloud services list --project=agora-484112 --enabled --filter="name:compute" --format="value(name)"`
- [x] Static IP reserved: `gcloud compute addresses describe agora-production-ip --project=agora-484112 --region=europe-west4 --format="value(address)"`
- [x] Firewall rules created: `gcloud compute firewall-rules list --project=agora-484112 --filter="name~agora" --format="table(name,allowed)"`
- [x] VM running: `gcloud compute instances describe agora-production --project=agora-484112 --zone=europe-west4-a --format="value(status)"` returns `RUNNING`

#### Manual Verification:
- [ ] Note down the static IP for DNS configuration
- [ ] SSH access works: `gcloud compute ssh agora-production --project=agora-484112 --zone=europe-west4-a`

**Implementation Note**: After the VM is created, immediately create the DNS A record (see instructions at top of document). DNS propagation can take a few minutes, so do this before proceeding.

---

## Phase 2: VM Configuration

### Overview
SSH into the VM, verify Docker installation, and prepare for deployment.

### Changes Required

#### 1. SSH to VM

```bash
gcloud compute ssh agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a
```

#### 2. Verify Docker Installation

Wait for startup script to complete (check `/var/log/agora-startup.log`):

```bash
# Check startup script completion
cat /var/log/agora-startup.log

# Verify Docker
docker --version
docker compose version

# If docker compose not working yet, log out and back in for group membership
exit
# Then SSH again
```

#### 3. Clone Repository

```bash
# Create app directory
sudo mkdir -p /opt/agora
sudo chown $USER:$USER /opt/agora
cd /opt/agora

# Clone repository
git clone https://github.com/Gradient-DS/AGORA.git .

# Verify files exist
ls -la docker-compose.production.yml Caddyfile
```

#### 4. Create Production Environment File

```bash
cd /opt/agora

# Copy template
cp .env.production.example .env

# Edit with production values
nano .env
```

Required values to set in `.env`:
```bash
# Domain (must match DNS)
DOMAIN=agora.gradient-testing.nl

# API Keys
OPENAI_API_KEY=sk-...your-openai-key...

# Gateway authentication - START WITH FALSE for initial testing
# We'll enable this after verifying the UI works
GATEWAY_REQUIRE_AUTH=false

# API key for gateway (will be used when GATEWAY_REQUIRE_AUTH=true)
# Generate secure key: openssl rand -hex 32
GATEWAY_API_KEYS=your-secure-api-key-here

# Backend selection
DEFAULT_BACKEND=langgraph
VITE_BACKEND=langgraph

# Embedding provider (openai recommended for lower memory)
MCP_EMBEDDING_PROVIDER=openai
```

**Note**: We start with `GATEWAY_REQUIRE_AUTH=false` to test the UI without authentication. Once the frontend and chat work correctly, we'll enable authentication (see Phase 5).

### Success Criteria

#### Automated Verification (run on VM):
- [ ] Docker installed: `docker --version`
- [ ] Docker Compose installed: `docker compose version`
- [ ] Repository cloned: `ls /opt/agora/docker-compose.production.yml`
- [ ] Environment file exists: `ls /opt/agora/.env`

#### Manual Verification:
- [ ] `.env` file contains valid `OPENAI_API_KEY`
- [ ] `.env` file contains secure `API_KEYS` value
- [ ] `DOMAIN` matches your DNS record

**Implementation Note**: Make sure to securely store the API_KEYS value - you'll need it to authenticate with the API.

---

## Phase 3: Deploy Production Stack

### Overview
Start the production Docker Compose stack and verify all services are healthy.

### Changes Required

#### 1. Start Production Stack

```bash
cd /opt/agora

# Pull/build images and start in detached mode
docker compose -f docker-compose.production.yml up -d --build
```

This will take several minutes on first run as it builds all images.

#### 2. Monitor Startup

```bash
# Watch container status
docker compose -f docker-compose.production.yml ps

# Watch logs (Ctrl+C to exit)
docker compose -f docker-compose.production.yml logs -f

# Check Caddy specifically for SSL certificate
docker compose -f docker-compose.production.yml logs caddy
```

#### 3. Verify All Services Healthy

```bash
# Check all containers are running and healthy
docker compose -f docker-compose.production.yml ps

# Expected output: all services should show "healthy" or "running"
```

#### 4. Run Document Ingestion (One-Time)

```bash
# Populate Weaviate with regulation documents
docker compose -f docker-compose.production.yml --profile tools run --rm document-ingestion

# Verify ingestion
curl -s -X POST http://localhost:8080/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{Aggregate{RegulationChunk{meta{count}}}}"}' | jq
# Should return count > 0
```

### Success Criteria

#### Automated Verification (run on VM):
- [ ] All containers running: `docker compose -f docker-compose.production.yml ps --format "table {{.Service}}\t{{.Status}}" | grep -v "unhealthy\|Exit"`
- [ ] Caddy obtained certificate: `docker compose -f docker-compose.production.yml logs caddy 2>&1 | grep -i "certificate obtained"`
- [ ] API gateway healthy: `curl -s http://localhost:8000/health | jq`
- [ ] Weaviate healthy: `curl -s http://localhost:8080/v1/.well-known/ready`
- [ ] Documents ingested: `curl -s -X POST http://localhost:8080/v1/graphql -H "Content-Type: application/json" -d '{"query": "{Aggregate{RegulationChunk{meta{count}}}}"}' | jq '.data.Aggregate.RegulationChunk[0].meta.count'` returns > 0

#### Manual Verification:
- [ ] Caddy logs show successful HTTPS setup (no certificate errors)
- [ ] No services in restart loop (check `docker compose ps` multiple times)

**Implementation Note**: Certificate provisioning requires DNS to be correctly configured. If Caddy shows certificate errors, verify DNS is pointing to this VM's IP.

---

## Phase 4: External Verification (Without Auth)

### Overview
Verify the deployment is accessible from the internet and the UI functions correctly. Auth is disabled (`GATEWAY_REQUIRE_AUTH=false`) for this initial test.

### Changes Required

#### 1. Verify HTTPS Access (from local machine, not VM)

```bash
# Check HTTPS certificate
curl -v https://agora.gradient-testing.nl/caddy-health 2>&1 | grep -E "(SSL certificate|subject:|issuer:|HTTP)"

# Should show Let's Encrypt certificate and return 200
```

#### 2. Verify API Works (no auth required yet)

```bash
# Should return 200 (auth disabled)
curl -s -w "\nHTTP Status: %{http_code}\n" \
  https://agora.gradient-testing.nl/api/langgraph/health
```

#### 3. Verify Frontend Access

Open in browser: `https://agora.gradient-testing.nl`

- Frontend should load
- No certificate warnings
- Chat interface visible

#### 4. End-to-End Test

1. Open `https://agora.gradient-testing.nl` in browser
2. Start a new conversation
3. Send a message like "Hello, what can you help me with?"
4. Verify response streams back
5. Try a regulation question to test MCP integration

### Success Criteria

#### Automated Verification (from local machine):
- [ ] HTTPS works: `curl -sI https://agora.gradient-testing.nl | grep "HTTP/2 200"`
- [ ] Certificate valid: `curl -s https://agora.gradient-testing.nl/caddy-health` returns "OK"
- [ ] API accessible: `curl -s -o /dev/null -w "%{http_code}" https://agora.gradient-testing.nl/api/langgraph/health` returns `200`

#### Manual Verification:
- [ ] Frontend loads in browser without certificate warnings
- [ ] WebSocket connection establishes (check browser DevTools Network tab)
- [ ] Chat conversation works end-to-end
- [ ] Regulation search returns results
- [ ] Agent handoffs work (general → regulation → reporting)

**Implementation Note**: Once all tests pass, proceed to Phase 5 to enable authentication.

---

## Phase 5: Enable Authentication

### Overview
After verifying the UI works correctly, enable API authentication and test with API keys.

### Changes Required

#### 1. SSH to VM and Update Environment

```bash
gcloud compute ssh agora-production \
  --project=agora-484112 \
  --zone=europe-west4-a
```

```bash
cd /opt/agora

# Edit .env to enable auth
nano .env
# Change: GATEWAY_REQUIRE_AUTH=true
```

#### 2. Restart API Gateway

```bash
# Restart only the api-gateway to pick up the new env var
docker compose -f docker-compose.production.yml restart api-gateway

# Verify it's running
docker compose -f docker-compose.production.yml ps api-gateway
```

#### 3. Test Authentication (from local machine)

```bash
# Should return 401 (no API key)
curl -s -w "\nHTTP Status: %{http_code}\n" \
  https://agora.gradient-testing.nl/api/langgraph/health

# Should return 200 (with API key)
curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "X-API-Key: YOUR_API_KEY_FROM_ENV" \
  https://agora.gradient-testing.nl/api/langgraph/health
```

#### 4. Test WebSocket with Token

The frontend should still work because it passes the API key via WebSocket query parameter. Verify:

1. Open `https://agora.gradient-testing.nl` in browser
2. Open DevTools → Network tab → WS filter
3. Start a conversation
4. Verify WebSocket connects (should include `?token=...` in URL)

### Success Criteria

#### Automated Verification (from local machine):
- [ ] Auth required: `curl -s -o /dev/null -w "%{http_code}" https://agora.gradient-testing.nl/api/langgraph/health` returns `401`
- [ ] Auth works: `curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: YOUR_KEY" https://agora.gradient-testing.nl/api/langgraph/health` returns `200`

#### Manual Verification:
- [ ] Frontend still works with authentication enabled
- [ ] WebSocket connection includes token parameter
- [ ] Chat conversation works end-to-end with auth

**Implementation Note**: Store the API key securely. You'll need it for any external integrations or API testing.

---

## Troubleshooting

### DNS Issues

```bash
# Check DNS resolution
dig agora.gradient-testing.nl +short

# If empty, DNS hasn't propagated yet - wait and retry
# If wrong IP, update the A record
```

### Certificate Issues

```bash
# SSH to VM and check Caddy logs
docker compose -f docker-compose.production.yml logs caddy --tail=50

# Common issues:
# - DNS not pointing to VM (fix A record)
# - Port 80 blocked (check firewall rules)
# - Rate limited (wait and retry)
```

### Container Issues

```bash
# Check container status
docker compose -f docker-compose.production.yml ps

# Check specific service logs
docker compose -f docker-compose.production.yml logs <service-name> --tail=100

# Restart a specific service
docker compose -f docker-compose.production.yml restart <service-name>

# Full restart
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d
```

### Resource Issues

```bash
# Check disk space
df -h

# Check memory
free -h

# Check Docker resource usage
docker stats --no-stream
```

---

## Operational Notes

### Updating the Application

```bash
cd /opt/agora

# Pull latest code
git pull

# Rebuild and restart
docker compose -f docker-compose.production.yml up -d --build

# Or for zero-downtime (service by service)
docker compose -f docker-compose.production.yml up -d --build --no-deps <service>
```

### Viewing Logs

```bash
# All logs
docker compose -f docker-compose.production.yml logs -f

# Specific service
docker compose -f docker-compose.production.yml logs -f server-langgraph

# Last 100 lines
docker compose -f docker-compose.production.yml logs --tail=100
```

### Backup Volumes

```bash
# List volumes
docker volume ls | grep agora

# Backup Weaviate data
docker run --rm -v agora_weaviate_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/weaviate-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Cost Monitoring

- VM: ~$98/month (e2-standard-4)
- Static IP: ~$3/month (when attached to running VM)
- Disk: ~$5/month (50GB pd-balanced)
- Egress: Variable based on usage

**Total estimated**: ~$110-120/month base

---

## References

- Research document: `thoughts/shared/research/2026-01-12-gcp-backend-deployment-architecture.md`
- Production Caddy plan: `thoughts/shared/plans/2026-01-12-production-deployment-caddy.md`
- Docker Compose: `docker-compose.production.yml`
- Caddyfile: `Caddyfile`
- Environment template: `.env.production.example`
