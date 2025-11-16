# KVK Lookup MCP Server

FastMCP-based Model Context Protocol server for querying Dutch Chamber of Commerce (KVK) company information.

## Overview

This MCP server provides tools to interact with the official KVK Open Data API to retrieve basic company information, verify company existence, check activity status, and get business classifications.

**Port**: 5004 (mapped from container port 8000)

## Available Tools

### 1. check_company_exists
Check if a company exists in the KVK register.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number

**Returns:**
- `exists` (boolean): Whether the company was found
- `active` (boolean): Whether company is active (if found)
- `legal_form` (string): Legal form code (e.g., "BV", "VOF")
- `country` (string): Country code (e.g., "NL")

**Use Case:** Quick validation before proceeding with detailed lookups.

**Example:**
```bash
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_company_exists",
    "arguments": {"kvk_number": "59581883"}
  }'
```

### 2. get_company_info
Get comprehensive company information.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number

**Returns:**
- `kvk_number` (string): The queried KVK number
- `start_date` (string): Company registration start date (YYYYMMDD)
- `active` (boolean): Active status
- `legal_form` (string): Legal form code
- `postal_region` (integer): First two digits of postal code
- `country` (string): Country code
- `insolvency_status` (string): Bankruptcy/debt status if applicable
- `activities` (array): List of business activities with SBI codes

**Use Case:** Get full company profile for compliance checks and reporting.

**Example:**
```bash
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_info",
    "arguments": {"kvk_number": "59581883"}
  }'
```

### 3. check_company_active
Check if a company is actively operating.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number

**Returns:**
- `active` (boolean): Whether company is registered as active
- `has_insolvency` (boolean): Whether company has insolvency status
- `insolvency_type` (string): Type of insolvency if applicable
- `warning` (string): Warning message if company is inactive

**Use Case:** Quick status check for supplier validation or partner verification.

**Example:**
```bash
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_company_active",
    "arguments": {"kvk_number": "59581883"}
  }'
```

### 4. get_company_activities
Get business activities classified by SBI codes.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number

**Returns:**
- `primary_activities` (array): Main business activities
- `secondary_activities` (array): Secondary business activities
- `total_activities` (integer): Total number of registered activities

Each activity contains:
- `sbi_code` (string): SBI classification code (max 6 digits)
- `type` (string): "Hoofdactiviteit" or "Nevenactiviteit"

**Use Case:** Determine business sector for regulatory compliance and risk assessment.

**Example:**
```bash
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_activities",
    "arguments": {"kvk_number": "59581883"}
  }'
```

## SBI Code Reference

SBI (Standard Business Classification) codes classify business activities:
- 5630: Cafés
- 5610: Restaurants
- 5621: Event catering
- 1071: Bakeries
- 1039: Other fruit and vegetable processing

See [CBS SBI codes](https://www.cbs.nl/nl-nl/onze-diensten/methoden/classificaties/activiteiten/sbi-2008-standaard-bedrijfsindeling-2008) for full classification.

## API Details

**Base URL:** https://opendata.kvk.nl/api/v1/hvds

**Authentication:** None required (open data API)

**Rate Limiting:** Subject to KVK API limits (check official documentation)

## Development

### Local Testing

```bash
cd mcp-servers/kvk-lookup

# Install dependencies
pip install -r requirements.txt

# Run server
python server.py

# Server starts on http://localhost:8000
```

### Testing Tools

```bash
# Health check
curl http://localhost:5004/health

# List all tools
curl http://localhost:5004/mcp/tools | jq

# Server info
curl http://localhost:5004/mcp/resources

# Test tool execution
curl -X POST http://localhost:5004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_company_exists",
    "arguments": {"kvk_number": "12345678"}
  }' | jq
```

## Docker Deployment

### Build and Run

```bash
cd mcp-servers

# Build kvk-lookup service
docker-compose build kvk-lookup

# Run kvk-lookup service
docker-compose up kvk-lookup

# Run all MCP servers
docker-compose up
```

### Health Checks

```bash
# Check Docker health status
docker-compose ps

# View logs
docker-compose logs kvk-lookup

# Check health endpoint
curl http://localhost:5004/health
```

## Integration with AGORA

Add KVK Lookup server to the orchestrator configuration:

```bash
# In server-openai/.env
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,kvk-lookup=http://localhost:5004
```

The orchestrator will automatically discover and register all KVK Lookup tools.

## Use Cases in AGORA

### 1. Inspector Workflow
When an inspector enters a company KVK number during an inspection:
- **Check existence** to validate the number
- **Get company info** to auto-fill company details
- **Get activities** to determine applicable regulations (e.g., food handling for SBI 5630)

### 2. Compliance Verification
During report generation:
- **Check active status** to flag inactive companies
- **Get insolvency status** for risk assessment
- **Verify activities** match inspection type

### 3. Voice Mode Integration
All tools execute in <3s for voice-compatible interaction:
```
Inspector: "Check company 59581883"
Agent: [calls check_company_exists] "Company found, active, registered as BV..."
```

## Error Handling

All tools return structured responses:

**Success:**
```json
{
  "status": "success",
  "kvk_number": "59581883",
  "active": true,
  ...
}
```

**Error:**
```json
{
  "status": "error",
  "error": "Human-readable error message",
  "code": "ERROR_CODE"
}
```

**Error Codes:**
- `INVALID_FORMAT`: KVK number is not 8 digits
- `NOT_FOUND`: Company not found in register
- `API_ERROR`: KVK API returned error
- `TIMEOUT`: Request timed out
- `INTERNAL_ERROR`: Unexpected server error

## Performance

- **Tool execution:** <1s typical, <3s guaranteed (voice compatible)
- **Timeout:** 10s for external API calls
- **Caching:** None (real-time data from KVK)

## Security

- **Input validation:** KVK numbers validated as 8-digit strings
- **Non-root user:** Container runs as user ID 1000
- **No authentication required:** Public API (no keys needed)
- **Read-only access:** Only queries data, no modifications

## Monitoring

All tool executions are logged:

```python
logger.info(f"Checking existence for KVK number: {kvk_number}")
logger.error(f"Error checking KVK number {kvk_number}: {e}")
```

View logs:
```bash
docker-compose logs -f kvk-lookup
```

## Troubleshooting

### Server won't start
```bash
# Check if port is in use
lsof -i :5004

# Check logs
docker-compose logs kvk-lookup

# Test dependencies
pip install -r requirements.txt
python -c "from fastmcp import FastMCP; print('OK')"
```

### KVK API not responding
```bash
# Test KVK API directly
curl https://opendata.kvk.nl/api/v1/hvds/basisbedrijfsgegevens/kvknummer/59581883

# Check network connectivity from container
docker-compose exec kvk-lookup curl -I https://opendata.kvk.nl
```

### Tools not discovered
```bash
# List registered tools
curl http://localhost:5004/mcp/tools | jq

# Verify tool registration in logs
docker-compose logs kvk-lookup | grep -i "tool"
```

## References

- [KVK Open Data API Documentation](https://developers.kvk.nl/nl/documentation/open-dataset-basis-bedrijfsgegevens-api)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Server Guidelines](.cursor/04-mcp-servers.mdc)

## Version

**Version:** 1.0.0  
**Last Updated:** 2025-11-16  
**API Version:** KVK Open Data v1.1.0

