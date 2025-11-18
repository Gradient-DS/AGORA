# Inspection History MCP Server

Mock inspection history database for AGORA demo. Provides access to historical inspection data including violations, follow-ups, and repeat offenses.

## Overview

This MCP server provides a simulated inspection history database with realistic demo data for testing AGORA v1.0 scenarios. It integrates with the KVK Lookup server to provide complete company profiles.

**Port**: 5005 (mapped from container port 8000)

## Available Tools

### 1. get_inspection_history
Get complete inspection history for a company.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number
- `limit` (integer, optional): Maximum inspections to return (default: 10)

**Returns:**
- List of inspections with dates, inspectors, findings, and violations
- Overall scores and inspection types
- Notes from inspectors

**Use Case:** Answer "Zijn er eerdere overtredingen bekend?" type questions

**Example:**
```bash
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "59581883"}
  }'
```

### 2. get_company_violations
Get all violations across all inspections for a company.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number
- `limit` (integer, optional): Maximum violations to return (default: 10)
- `severity` (string, optional): Filter by severity: "warning", "serious", "minor"

**Returns:**
- List of violations with inspection context
- Severity levels and categories
- Resolution status and follow-up requirements

**Use Case:** Identify patterns of non-compliance

**Example:**
```bash
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_violations",
    "arguments": {
      "kvk_number": "87654321",
      "severity": "warning"
    }
  }'
```

### 3. check_repeat_violation
Check if a violation category has occurred before.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number
- `violation_category` (string, required): Category to check

**Common Categories:**
- `hygiene_measures`
- `food_labeling`
- `product_labeling`
- `temperature_control`
- `pest_control`
- `allergen_information`

**Returns:**
- Boolean indicating if this is a repeat
- Details of previous occurrences
- Enforcement recommendations (escalation advice)
- Unresolved violation counts

**Use Case:** Determine enforcement escalation for repeat offenders

**Example:**
```bash
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_repeat_violation",
    "arguments": {
      "kvk_number": "59581883",
      "violation_category": "hygiene_measures"
    }
  }'
```

### 4. get_follow_up_status
Get status of follow-up actions required from previous inspections.

**Parameters:**
- `kvk_number` (string, required): 8-digit KVK number
- `inspection_id` (string, optional): Specific inspection to check

**Returns:**
- List of pending follow-ups
- Overdue status calculation
- Resolution notes
- Follow-up dates

**Use Case:** Track compliance with corrective actions

**Example:**
```bash
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_follow_up_status",
    "arguments": {"kvk_number": "87654321"}
  }'
```

### 5. search_inspections_by_inspector
Search inspections conducted by a specific inspector.

**Parameters:**
- `inspector_name` (string, required): Inspector name (partial match)
- `limit` (integer, optional): Maximum results (default: 20)

**Returns:**
- List of inspections by that inspector
- Sorted by date (newest first)
- Includes violation counts and overall scores

**Use Case:** Review inspector workload and find similar cases

**Example:**
```bash
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "search_inspections_by_inspector",
    "arguments": {"inspector_name": "Kees Bakker"}
  }'
```

## Demo Data

The server includes realistic demo data for 4 companies matching the AGORA v1.0 scenarios:

### 1. Restaurant Bella Rosa (KVK: 59581883)
**Scenario:** Koen's horeca inspection
- **History:** 2 inspections (2020, 2022)
- **Violations:** Hygiene measures warning in 2022 (unresolved)
- **Key Feature:** Repeat violation ready for escalation

### 2. SpeelgoedPlaza Den Haag (KVK: 12345678)
**Scenario:** Fatima's product safety inspection
- **History:** 1 inspection (2023)
- **Violations:** Product labeling warning (resolved)
- **Key Feature:** Shows good compliance after warning

### 3. Slagerij de Boer (KVK: 87654321)
**Scenario:** Jan's butcher shop inspection
- **History:** 2 inspections (2019, 2021)
- **Violations:** Food labeling warning in 2021 (unresolved, overdue follow-up)
- **Key Feature:** Repeat offender with overdue follow-up

### 4. Café Het Bruine Paard (KVK: 11223344)
**Additional demo data**
- **History:** 1 inspection (2024)
- **Violations:** None
- **Key Feature:** Clean record for contrast

## Integration with KVK Lookup

This server is designed to work seamlessly with the KVK Lookup server:

**Typical Workflow:**
1. Inspector starts inspection: "Start inspectie bij Restaurant Bella Rosa"
2. **KVK Lookup** provides:
   - Company name, legal form, SBI codes
   - Active status and registration date
3. **Inspection History** provides:
   - Previous inspection dates and findings
   - Historical violations and patterns
   - Follow-up status
4. **Regulation Analysis** provides:
   - Applicable regulations based on SBI codes
   - Specific articles for violations
5. **Reporting** generates final report combining all sources

## Voice Mode Integration

All tools execute in <1s for voice-compatible interaction:

```
Inspector: "Check geschiedenis van bedrijf 59581883"
Agent: [calls get_inspection_history + get_company_violations]
       "Restaurant Bella Rosa heeft 2 eerdere inspecties. 
        In mei 2022 was er een waarschuwing voor onvoldoende 
        hygiënemaatregelen, deze is nog niet opgelost..."
```

## Development

### Local Testing

```bash
cd mcp-servers/inspection-history

# Install dependencies
pip install -r requirements.txt

# Run server
python server.py

# Server starts on http://localhost:8000
```

### Testing Tools

```bash
# Health check
curl http://localhost:5005/health

# List all tools
curl http://localhost:5005/mcp/tools | jq

# Server info (shows demo KVK numbers)
curl http://localhost:5005/mcp/resources

# Test inspection history
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "59581883"}
  }' | jq
```

## Docker Deployment

### Build and Run

```bash
cd mcp-servers

# Build inspection-history service
docker-compose build inspection-history

# Run inspection-history service
docker-compose up inspection-history

# Run all MCP servers
docker-compose up
```

### Health Checks

```bash
# Check Docker health status
docker-compose ps

# View logs
docker-compose logs inspection-history

# Check health endpoint
curl http://localhost:5005/health
```

## Integration with AGORA

Add Inspection History server to the orchestrator configuration:

```bash
# In server-openai/.env
APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,kvk-lookup=http://localhost:5004,inspection-history=http://localhost:5005
```

The orchestrator will automatically discover and register all inspection history tools.

## Use Cases in AGORA

### 1. Scenario Testing (All Personas)
Each inspector scenario requires historical data:
- **Koen:** "Zijn er eerdere overtredingen bekend?"
- **Fatima:** "Zijn er eerder onveilige producten aangetroffen?"
- **Jan:** "Wat is er eerder geconstateerd?"

### 2. Repeat Violation Detection
Automatically identify patterns:
```
Inspector dictates: "Ongeëtiketteerde producten in koeling"
Agent: [calls check_repeat_violation]
       "WAARSCHUWING: Dit is een herhaalde overtreding. 
        In november 2021 was er een soortgelijk probleem..."
```

### 3. Enforcement Escalation
Determine appropriate action level:
```
if is_repeat and not resolved:
    enforcement_level = "immediate_action"
    suggest_follow_up = "higher_penalty"
```

### 4. Inspector Context
Provide complete picture at inspection start:
```
Agent combines:
- KVK: Active BV, horeca (SBI 5630)
- History: 2 inspections, 1 unresolved warning
- Regulations: Hygiënecode Horeca applies
→ "Dit bedrijf heeft 1 openstaande waarschuwing uit 2022..."
```

## Error Handling

All tools return structured responses:

**Success:**
```json
{
  "status": "success",
  "kvk_number": "59581883",
  "company_name": "Restaurant Bella Rosa",
  "inspections": [...]
}
```

**Not Found:**
```json
{
  "status": "not_found",
  "kvk_number": "99999999",
  "message": "No inspection history found. This may be a first inspection.",
  "inspections": []
}
```

**Error:**
```json
{
  "status": "error",
  "error": "Invalid KVK number format. Must be 8 digits.",
  "kvk_number": "123"
}
```

## Performance

- **Tool execution:** <500ms (in-memory dict lookup)
- **No external dependencies:** Pure Python, no database calls
- **Voice compatible:** All responses <1s

## Data Structure

Each inspection contains:
```python
{
    "inspection_id": "INS-2022-001234",
    "date": "2022-05-15",
    "inspector": "Jan Pietersen",
    "inspection_type": "hygiene_routine",
    "overall_score": "voldoende_met_opmerkingen",
    "violations": [
        {
            "violation_id": "VIO-2022-001234-01",
            "category": "hygiene_measures",
            "severity": "warning",
            "description": "Onvoldoende hygiënemaatregelen",
            "regulation": "Hygiënecode Horeca artikel 4.2",
            "resolved": False,
            "follow_up_required": True,
            "follow_up_date": "2022-08-15"
        }
    ]
}
```

## Future: Real Database Integration

When connecting to real NVWA database:
1. Replace `DEMO_INSPECTIONS` dict with database queries
2. Add authentication/authorization
3. Add caching layer for performance
4. Keep same tool interface (no changes to agents needed)

## Monitoring

All tool executions are logged:

```python
logger.info(f"Getting inspection history for KVK: {kvk_number}")
logger.info(f"Checking repeat violation: {violation_category}")
```

View logs:
```bash
docker-compose logs -f inspection-history
```

## Security

- **Input validation:** KVK numbers validated as 8-digit strings
- **Non-root user:** Container runs as user ID 1000
- **Read-only data:** Demo data is immutable
- **No external calls:** All data in-memory

## Version

**Version:** 1.0.0  
**Last Updated:** 2025-11-16  
**Status:** Demo/Mock Data

## References

- [AGORA Personas & Scenarios](../../PERSONAS_AND_SCENARIOS.md)
- [Gap Analysis](../../GAP_ANALYSIS_SUMMARY.md)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [MCP Server Guidelines](../../.cursor/04-mcp-servers.mdc)

