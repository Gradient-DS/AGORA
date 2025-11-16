# AGORA Setup Guide

Complete setup instructions for running the AGORA OpenAI orchestration with MCP servers.

## Overview

The system consists of:
- **OpenAI Orchestrator** - Main server using OpenAI Assistants API
- **2 MCP Servers** - Specialized tools for compliance operations

## Quick Start

### 1. Start MCP Servers

```bash
cd mcp-servers
docker-compose up --build -d
```

This starts 2 MCP servers with HTTP transport on:
- http://localhost:5002 - Regulation Analysis
- http://localhost:5003 - Reporting

Verify they're running:
```bash
curl http://localhost:5002/health
curl http://localhost:5002/tools | jq
```

### 2. Configure OpenAI Server

Create `.env` in `server-openai/`:
```bash
APP_OPENAI_API_KEY=sk-your-actual-key-here
APP_OPENAI_MODEL=gpt-4o
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003
APP_GUARDRAILS_ENABLED=true
APP_OTEL_ENDPOINT=http://localhost:4317
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
```

### 3. Install and Run OpenAI Server

```bash
cd server-openai
pip install -e .
python -m agora_openai.api.server
```

Server will start on http://localhost:8000

You should see:
```
Starting AGORA OpenAI Orchestration Server
Discovered tools from 2 servers
Created assistant regulation-agent: asst_xxxxx
Created assistant reporting-agent: asst_xxxxx
Initialized 2 assistants
```

### 4. Test the System

Save as `test_client.py`:
```python
import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        # Send message
        message = {
            "type": "user_message",
            "content": "What are the FDA food safety regulations for temperature control?",
            "session_id": "test-123"
        }
        await ws.send(json.dumps(message))
        
        # Receive responses
        async for response in ws:
            data = json.loads(response)
            print(f"\n{data['type']}: {data.get('content', data.get('status'))}")
            
            if data['type'] == 'assistant_message':
                break

asyncio.run(test())
```

Run it:
```bash
python test_client.py
```

## Architecture

```
┌─────────────────────────────────────────┐
│     HAI (WebSocket Client)              │
│         ws://localhost:8000/ws          │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│   OpenAI Orchestrator (FastAPI)        │
│   - Intelligent routing                 │
│   - OpenAI Assistants API               │
│   - Moderation & validation             │
│   http://localhost:8000                 │
└────┬─────────────────────────┬──────────┘
     │                         │
     ▼                         ▼
┌─────────────────────────────────────────┐
│        MCP Servers (HTTP)               │
│  5002: Regulation Analysis              │
│  5003: Reporting                        │
└─────────────────────────────────────────┘
```

## Development Modes

### Mode 1: All Local (No Docker)

**MCP Servers:**
```bash
cd mcp-servers/regulation-analysis
pip install -r requirements.txt
python server.py  # Runs on port 8000
```

**OpenAI Server:**
```bash
cd server-openai
pip install -e .
APP_MCP_SERVERS=regulation-analysis=http://localhost:8000
python -m agora_openai.api.server
```

### Mode 2: MCP in Docker, Orchestrator Local (Recommended for Dev)

**MCP Servers:**
```bash
cd mcp-servers
docker-compose up --build
```

**OpenAI Server:**
```bash
cd server-openai
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003
python -m agora_openai.api.server
```

### Mode 3: All in Docker (Production)

Update `server-openai/.env`:
```bash
APP_MCP_SERVERS=regulation-analysis=http://regulation-analysis:8000,reporting=http://reporting:8000
```

Run both:
```bash
# Start MCP servers
cd mcp-servers
docker-compose up -d

# Start orchestrator
cd ../server-openai
docker-compose up
```

## Testing MCP Servers Directly

### Health Check
```bash
curl http://localhost:5002/health
```

### List Tools
```bash
curl http://localhost:5002/tools | jq
```

### Execute Tool
```bash
curl -X POST http://localhost:5002/tools/semantic_search_regulations \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"query": "HACCP temperature control", "top_k": 5}}' | jq
```

### Test Report Generation
```bash
curl -X POST http://localhost:5003/tools/start_inspection_report \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"session_id": "test-123", "inspector_name": "John Doe", "inspection_date": "2024-01-15"}}' | jq
```

## Troubleshooting

### MCP Servers Not Discovered

**Check if servers are running:**
```bash
docker-compose ps
```

**Test connectivity:**
```bash
curl http://localhost:5002/tools
```

**Check logs:**
```bash
docker-compose logs regulation-analysis
```

### OpenAI Server Can't Start

**Missing API key:**
```bash
# Verify .env file has APP_OPENAI_API_KEY
cat .env | grep OPENAI_API_KEY
```

**Port already in use:**
```bash
lsof -i :8000
# Kill the process or change APP_PORT
```

### Tools Not Working

**Check MCP client logs in orchestrator:**
```bash
# Should see "Discovered X tools from Y servers"
# Look for "Executing MCP tool: tool_name"
```

**Test tool directly:**
```bash
curl -X POST http://localhost:5002/tools/semantic_search_regulations \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"query": "food safety", "top_k": 3}}'
```

## Key Files

### Configuration
- `server-openai/.env` - OpenAI server config
- `mcp-servers/docker-compose.yml` - MCP servers deployment
- `server-openai/docker-compose.yml` - OpenAI server deployment

### Documentation
- `server-openai/README.md` - OpenAI server overview
- `server-openai/QUICKSTART.md` - 5-minute setup guide
- `server-openai/ARCHITECTURE.md` - Design details
- `server-openai/DEVELOPMENT.md` - Developer guide
- `mcp-servers/README.md` - MCP servers guide

### Source Code
- `server-openai/src/agora_openai/` - OpenAI server implementation
- `mcp-servers/*/server.py` - MCP server implementations

## What Changed?

The MCP servers have been **migrated from stdio to HTTP transport** using FastMCP:

**Before:**
- Stdio communication (stdin/stdout)
- Required `stdin_open: true` and `tty: true` in Docker
- Couldn't be accessed over HTTP
- Complex integration

**After:**
- HTTP REST API
- Standard endpoints (`/health`, `/tools`, `/tools/{name}`)
- Can be called from anywhere
- Simple curl-based testing
- Better for distributed systems

## Next Steps

1. **Build HAI (Frontend)** - WebSocket client connecting to `/ws`
2. **Add Authentication** - Protect HTTP endpoints
3. **Monitoring** - Add Prometheus metrics
4. **Production Deployment** - Deploy to cloud infrastructure

## Support

See individual READMEs for detailed information:
- [OpenAI Server README](server-openai/README.md)
- [MCP Servers README](mcp-servers/README.md)
