# AGORA MCP Servers

Model Context Protocol (MCP) servers for AGORA's compliance platform using the **FastMCP** framework with HTTP transport for OpenAI integration.

## Overview

Five specialized MCP servers providing tools for compliance operations:

1. **Company Compliance** (port 5001) - Company profiles and inspection history
2. **Regulation Analysis** (port 5002) - Regulatory lookups and document analysis
3. **Reporting** (port 5003) - Inspection report generation
4. **Risk Enforcement** (port 5004) - Risk scoring and enforcement flagging
5. **Utilities** (port 5005) - Translation, date formatting, and utilities

## Quick Start

### 1. Build and Run with Docker Compose

```bash
cd mcp-servers

# On macOS, use legacy builder for faster builds
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

docker-compose up --build
```

This will start all 5 MCP servers:

- http://localhost:5001 - Company Compliance
- http://localhost:5002 - Regulation Analysis
- http://localhost:5003 - Reporting
- http://localhost:5004 - Risk Enforcement
- http://localhost:5005 - Utilities

### 2. Configure OpenAI Orchestrator

Add to your `.env` file:

```bash
APP_MCP_SERVERS=company-compliance=http://localhost:5001,regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,risk-enforcement=http://localhost:5004,utilities=http://localhost:5005
```

### 3. Test the Servers

Check health status:

```bash
# Test health endpoint (HTTP)
curl http://localhost:5001/health

# Check container health
docker-compose ps

# View logs
docker-compose logs company-compliance
```

Each server exposes:
- **HTTP MCP endpoints** for tool execution and resource access
- **`/health` HTTP endpoint** for health checks and monitoring
- **`server://info` resource** for server capabilities

Test MCP endpoints:
```bash
# List available tools
curl http://localhost:5001/mcp/tools

# Call a tool
curl -X POST http://localhost:5001/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_profile",
    "arguments": {"company_id": "C001"}
  }'
```

## Architecture

Each server runs independently using the **FastMCP** framework with **HTTP transport** for OpenAI integration:

- ✅ **HTTP Transport** - Compatible with OpenAI Responses API and standard HTTP clients
- ✅ **Automatic tool registration** - Use `@mcp.tool` decorator
- ✅ **Custom HTTP routes** - Add endpoints like `/health` with `@mcp.custom_route`
- ✅ **Type-safe parameters** - Full Python type hints
- ✅ **Resource endpoints** - Expose data via `@mcp.resource()`
- ✅ **Built-in server** - Single `mcp.run()` call starts everything

## Development

### Run Locally (without Docker)

```bash
cd mcp-servers/company-compliance
pip install -r requirements.txt
python server.py
```

Server will start with http transport on the default port.

### Project Structure

```
mcp-servers/
├── company-compliance/
│   ├── server.py          # FastMCP server
│   ├── requirements.txt   # Dependencies
│   └── Dockerfile
├── regulation-analysis/
│   ├── server.py
│   ├── requirements.txt
│   └── Dockerfile
├── reporting/
│   ├── server.py
│   ├── requirements.txt
│   └── Dockerfile
├── risk-enforcement/
│   ├── server.py
│   ├── requirements.txt
│   └── Dockerfile
├── utilities/
│   ├── server.py
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml
```

## Available Tools

### Company Compliance

- `get_company_profile(company_id)` - Get company info
- `fetch_inspection_history(company_id, limit)` - Get inspection records

### Regulation Analysis

- `lookup_regulation_articles(domain, keywords)` - Search regulations
- `analyze_document(document_uri, analysis_type)` - Analyze documents

### Reporting

- `generate_inspection_report(company_id, inspection_data, history, notes)` - Generate reports

### Risk Enforcement

- `calculate_risk_score(history, business_activities, region)` - Calculate risk
- `flag_for_enforcement(company_id, violation_id, severity, justification)` - Flag violations

### Utilities

- `translate_text(text, target_language)` - Translate text
- `format_date(date_str, format_type)` - Format dates
- `calculate_due_date(start_date, days)` - Calculate due dates

## FastMCP Implementation

Each server follows the FastMCP reference architecture:

```python
import logging
from datetime import datetime
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Server Name")

@mcp.tool
async def my_tool(param: str) -> dict:
    """Tool description."""
    return {"result": "value"}

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "healthy"}, status_code=200)

@mcp.resource("server://info")
def server_info() -> str:
    """Server capabilities."""
    return '{"name": "Server Name", "version": "1.0.0"}'

if __name__ == "__main__":
    logger.info("Starting server on http://0.0.0.0:8000")
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```

### Key Features

- **HTTP Transport**: Standard HTTP for OpenAI integration and tool execution
- **Health Endpoints**: HTTP `/health` endpoint for Docker health checks
- **Resource Endpoints**: `server://info` for server capabilities
- **Logging**: Structured logging for monitoring
- **Type Safety**: Full type hints for parameters and return values
- **Non-root User**: Runs as non-root user in Docker for security
- **Pinned Dependencies**: requirements.txt with pinned versions

### OpenAI Integration

These servers use HTTP transport, making them compatible with OpenAI's Responses API:

```python
# In your OpenAI orchestrator
mcp_servers = {
    "company-compliance": "http://localhost:5001",
    "regulation-analysis": "http://localhost:5002",
    "reporting": "http://localhost:5003",
    "risk-enforcement": "http://localhost:5004",
    "utilities": "http://localhost:5005"
}

# The MCP client can call tools via HTTP
# Example: GET http://localhost:5001/mcp/tools (list tools)
# Example: POST http://localhost:5001/mcp/tools/call (execute tool)
```

## Troubleshooting

**Slow Docker builds on macOS (exporting to OCI format taking minutes):**
```bash
# Use legacy builder instead of BuildKit
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0
docker-compose up --build

# Or add to your shell profile (~/.zshrc or ~/.bash_profile):
echo 'export DOCKER_BUILDKIT=0' >> ~/.zshrc
echo 'export COMPOSE_DOCKER_CLI_BUILD=0' >> ~/.zshrc
```

**Ports already in use:**
```bash
# Check what's using the ports
lsof -i :5001-5005

# Stop containers
docker-compose down
```

**Can't connect from orchestrator:**
- Check health: `curl http://localhost:5001/health`
- Verify containers are healthy: `docker-compose ps` (should show "healthy")
- Check server logs: `docker-compose logs company-compliance`
- Check network: `docker network inspect agora-network`
- Verify ports are exposed: `docker-compose ps | grep ":500"`

**Health checks failing:**
- Check if server is starting: `docker-compose logs company-compliance`
- Verify httpx is installed: Check requirements.txt
- Increase start_period in docker-compose.yml if server needs more time

**Tools not discovered:**
- Check server logs for errors: `docker-compose logs company-compliance`
- Verify decorators use `@mcp.tool` (without parentheses)
- Ensure server runs `mcp.run(transport="http", host="0.0.0.0", port=8000)`
- Test tools endpoint: `curl http://localhost:5001/mcp/tools`
- Test server info: Query `server://info` resource

## Production Deployment

For production:

1. **Use environment variables** for server URLs:
   ```bash
   APP_MCP_SERVERS=company-compliance=http://mcp-company-compliance:8000,regulation-analysis=http://mcp-regulation-analysis:8000,...
   ```

2. **Remove port mappings** for servers that don't need external access (only keep internal Docker networking)

3. **Add authentication** at the application level

4. **Add rate limiting** to prevent abuse

5. **Monitor with health checks** at `/health`

6. **Scale servers** as needed:
   ```bash
   docker-compose up --scale company-compliance=3
   ```

## References

- [FastMCP Framework](https://github.com/jlowin/fastmcp)
- [MCP Specification](https://modelcontextprotocol.io)
- [Model Context Protocol](https://github.com/modelcontextprotocol)
