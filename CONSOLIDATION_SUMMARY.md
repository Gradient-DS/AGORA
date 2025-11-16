# KVK + Inspection History Consolidation

## Summary

Successfully consolidated the separate `kvk-lookup` MCP server into `inspection-history`, creating a unified **Company Information & Inspection History** server.

## Changes Made

### 1. ✅ Updated Inspection History Server
**File:** `mcp-servers/inspection-history/server.py`
- Renamed to "Company Information & Inspection History"
- Added `httpx` import for HTTP requests
- Added `KVK_BASE_URL` constant
- Added two new KVK tools:
  - `check_company_exists(kvk_number)` - Verify company exists
  - `get_company_basic_info(kvk_number)` - Get company info (NO NAME for privacy)

**Result:** 7 total tools (2 company + 5 history)

### 2. ✅ Removed KVK Server from Docker
**File:** `mcp-servers/docker-compose.yml`
- Removed `kvk-lookup` service entirely
- Kept only 3 servers:
  - `regulation-analysis` (port 5002)
  - `reporting` (port 5003)
  - `inspection-history` (port 5005)

### 3. ✅ Updated Backend Configuration  
**File:** `server-openai/docker-compose.yml`
- Updated `APP_MCP_SERVERS` to remove `kvk-lookup`
- New value: `regulation-analysis=http://regulation-analysis:8000,reporting=http://reporting:8000,inspection-history=http://inspection-history:8000`

### 4. ✅ Removed kvk-agent
**File:** `server-openai/src/agora_openai/core/agent_definitions.py`
- Removed entire `kvk-agent` definition
- Updated `history-agent` to "Company Information & Inspection History Specialist"
- Added company tools to history-agent instructions:
  - `check_company_exists`
  - `get_company_basic_info`
- Updated general-agent workflows to use new tool names

### 5. ✅ Updated Routing Logic
**File:** `server-openai/src/agora_openai/core/routing_logic.py`
- Removed `"kvk-agent"` from `Literal` type
- Consolidated kvk-agent responsibilities into `history-agent` description
- **New routing:**
  - `general-agent` - Default for most queries
  - `regulation-agent` - Regulation searches
  - `reporting-agent` - Report generation
  - `history-agent` - **Company info + inspection history**

### 6. ✅ Updated Documentation
**File:** `mcp-servers/README.md`
- Updated overview to show 3 servers (not 4)
- Consolidated tool list under "Company Information & Inspection History"
- Updated all configuration examples
- Updated port numbers throughout

### 7. ✅ Added "Nieuwe Inspectie" Button
**File:** `HAI/src/components/layout/Header.tsx`
- Added button to clear session and start fresh conversation
- Prevents OpenAI thread memory from carrying over between demos

## Architecture Benefits

### Before (4 servers, 5 agents)
```
kvk-lookup (port 5004) → kvk-agent
inspection-history (port 5005) → history-agent
regulation-analysis (port 5002) → regulation-agent  
reporting (port 5003) → reporting-agent
general-agent (coordinator)
```

### After (3 servers, 4 agents)
```
inspection-history (port 5005) → history-agent
  ├── Company tools (KVK API)
  └── History tools (demo data)
regulation-analysis (port 5002) → regulation-agent
reporting (port 5003) → reporting-agent
general-agent (coordinator)
```

## Key Improvements

1. **Simpler Architecture** - One less server to manage and monitor
2. **Logical Grouping** - Company info and history naturally belong together
3. **Privacy by Design** - KVK tools explicitly do NOT return company names
4. **Better Agent Flow** - history-agent can provide complete company context
5. **Easier Demo** - "Nieuwe Inspectie" button for fresh conversations

## Privacy Feature

The consolidated KVK tools intentionally **exclude company names** from responses:

```python
# get_company_basic_info returns:
{
    "kvk_number": "12345678",
    "start_date": "2015-06-20",
    "active": True,
    "legal_form": "BV",
    "postal_region": "Amsterdam",
    "sbi_codes": [{"code": "4765", "type": "main"}]
    # NO "name" field!
}
```

This allows demos with real KVK numbers without revealing actual company names to the AI model or in logs.

## Testing

To test the consolidated server:

```bash
# Start all services
cd mcp-servers
docker-compose up --build

# Test company existence
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_company_exists",
    "arguments": {"kvk_number": "12345678"}
  }'

# Test company info (no name returned)
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_company_basic_info",
    "arguments": {"kvk_number": "12345678"}
  }'

# Test inspection history
curl -X POST http://localhost:5005/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "get_inspection_history",
    "arguments": {"kvk_number": "12345678"}
  }'
```

## Next Steps

1. Update your local `.env` file:
   ```bash
   APP_MCP_SERVERS=regulation-analysis=http://localhost:5002,reporting=http://localhost:5003,inspection-history=http://localhost:5005
   ```

2. Rebuild and restart services:
   ```bash
   cd mcp-servers && docker-compose down
   docker-compose up --build
   ```

3. Restart backend:
   ```bash
   cd server-openai
   python -m agora_openai.api.server
   ```

4. Test with frontend - use "Nieuwe Inspectie" button between demos!

## Migration Notes

- **No breaking changes** for existing demo scenarios
- Tool names are backward compatible (still have all history tools)
- Added 2 new tools accessible to all agents via general-agent
- KVK data structure unchanged (just removed name field)

