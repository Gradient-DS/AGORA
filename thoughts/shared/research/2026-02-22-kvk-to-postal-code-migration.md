---
date: 2026-02-22T12:00:00+01:00
researcher: claude
git_commit: ac8982c58a640949daafc8331ab97bda483e9e44
branch: main
repository: AGORA
topic: "Migrating from KVK numbers to postal code + house number for company lookup"
tags: [research, codebase, inspection-history, mcp-servers, agent-definitions, demo]
status: complete
last_updated: 2026-02-22
last_updated_by: claude
---

# Research: Migrating from KVK Numbers to Postal Code + House Number Lookup

**Date**: 2026-02-22T12:00:00+01:00
**Researcher**: claude
**Git Commit**: ac8982c58a640949daafc8331ab97bda483e9e44
**Branch**: main
**Repository**: AGORA

## Research Question

What would it take to change the company lookup mechanism from KVK numbers (8-digit Chamber of Commerce identifiers) to postal codes + house numbers (e.g., "2628 BA, number 15") for demo purposes? All data will remain mocked.

## Summary

The change is **moderate in scope but straightforward**. KVK numbers are deeply embedded in the inspection-history MCP server and both orchestrator agent definitions, but the frontend (HAI) is completely KVK-agnostic and requires no changes. The core work involves:

1. **1 MCP server file** to refactor (data model + 2 active tools + 4 disabled tools)
2. **2 agent definition files** to update (prompts/triggers in both orchestrators)
3. **2 tool display name files** to update
4. **1 transfer tool docstring** to update (LangGraph)
5. **Several documentation files** to update (READMEs, DEMO_SCENARIOS, mock server, benchmark)

No database migrations, no API contract changes, no frontend changes needed.

## Detailed Findings

### Component 1: Inspection History MCP Server (PRIMARY CHANGE)

**File**: `mcp-servers/inspection-history/server.py`

This is the main file that needs refactoring. All changes are in this single ~560-line file.

#### A. Data Model — `DEMO_INSPECTIONS` dictionary (lines 30-163)

Currently keyed by KVK number string. Each entry has a `kvk_number` field. Must change to:
- New key format: e.g., `"2511AA-123"` (postal code + house number, no spaces)
- Replace `kvk_number` field with `postal_code` and `house_number` fields
- Add a `street` field for display purposes (optional but nice for demo)

**Current structure** (4 companies):
```python
DEMO_INSPECTIONS = {
    "92251854": {
        "company_name": "Restaurant Bella Rosa",
        "kvk_number": "92251854",
        "inspections": [...]
    },
    ...
}
```

**Proposed structure**:
```python
DEMO_INSPECTIONS = {
    "2511AA-123": {
        "company_name": "Restaurant Bella Rosa",
        "postal_code": "2511 AA",
        "house_number": "123",
        "street": "Haagweg",
        "city": "Den Haag",
        "inspections": [...]
    },
    ...
}
```

#### B. `check_company_exists` tool (lines 170-236)

- Rename to `check_address_exists` or `check_location_exists`
- Change parameter from `kvk_number: str` to `postal_code: str, house_number: str`
- Update validation from "8 digits" to Dutch postal code format (`NNNN AA`)
- Update lookup key construction
- Remove `KVK_BASE_URL` constant (line 14-15) and dead KVK API code (lines 199-236)

#### C. `get_inspection_history` tool (lines 244-281)

- Change parameter from `kvk_number: str` to `postal_code: str, house_number: str`
- Update validation and lookup logic
- Update return value to include address fields instead of `kvk_number`

#### D. Disabled tools (lines 284-518)

Four tools have `@mcp.tool()` commented out but still contain `kvk_number` parameters:
- `get_company_violations` (line 284)
- `check_repeat_violation` (line 342)
- `get_follow_up_status` (line 413)
- `search_inspections_by_inspector` (line 481) — iterates all entries, returns `kvk_number` in results

These should be updated for consistency even though they're disabled.

#### E. Constants and messages (lines 14-26)

- Remove `KVK_BASE_URL` (line 14-15)
- Update `DUTCH_MESSAGES["invalid_kvk"]` → `"invalid_address"` with new format message
- Update `DUTCH_MESSAGES["not_found"]` message text

#### F. Health/info resource (lines 535-552)

- Update `demo_kvk_numbers` key at line 551 to `demo_addresses` or similar

### Component 2: Server-OpenAI Agent Definitions

**File**: `server-openai/src/agora_openai/core/agent_definitions.py`

#### A. general-agent instructions

- **Line 34-35**: Change triggers from `"KVK numbers, company lookups"` to `"postcodes, adressen, company lookups"`
- **Line 35**: Change trigger words from `"'bedrijf', 'KVK', 'geschiedenis'"` to `"'bedrijf', 'postcode', 'adres', 'geschiedenis'"`
- **Line 43**: Change `"inspector mentions KVK or company name"` to `"inspector mentions address/postcode or company name"`
- **Line 53**: Change example from `"Start inspectie bij Bakkerij Jansen KVK 12345678"` to `"Start inspectie bij Bakkerij Jansen, postcode 2511 AA nummer 123"`

#### B. history-agent instructions

- **Lines 212-214**: Change capabilities from `"Check if company exists in KVK register"` to `"Check if company exists at address"`
- **Lines 228-230**: Change workflow from `"When inspector provides KVK number"` to `"When inspector provides postal code and house number"`
- Update tool references from `check_company_exists` to new tool name

#### C. Spoken text prompts

- **Lines 267, 318**: Remove `"'KVK' → 'Kamer van Koophandel'"` expansion rule

### Component 3: Server-LangGraph Agent Definitions (MIRROR)

**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`

Identical changes as server-openai:
- **Lines 35, 47, 59**: Update triggers and routing keywords
- **Lines 211-213**: Update workflow instructions
- **Lines 255, 269-271, 318**: Update spoken text prompts

### Component 4: Transfer Tool Docstring (LangGraph only)

**File**: `server-langgraph/src/agora_langgraph/core/tools.py`

- **Lines 32-33**: Change `transfer_to_history` docstring from `"Company information or KVK numbers"` to `"Company information, addresses, or postal codes"`

### Component 5: Tool Display Names (Both Orchestrators)

**Files**:
- `server-openai/src/agora_openai/core/tool_display_names.py`
- `server-langgraph/src/agora_langgraph/core/tool_display_names.py`

- **Line 15**: Change `"search_kvk": "Zoeken in het KVK"` to new tool display name
- **Line 8**: Update `"check_company_exists"` display name if tool is renamed
- Add display name for new tool name(s)

### Component 6: Handoff Detection (Server-OpenAI)

**File**: `server-openai/src/agora_openai/core/agent_runner.py`

- **Lines 355-356**: The `_detect_handoff_target` method checks for `"company"` or `"history"` substrings in tool names to route to `history-agent`. If tools are renamed, ensure new names still match (they likely will if they contain `"company"` or `"address"`).

### Components Requiring NO Changes

#### HAI Frontend — NO CHANGES
The frontend is completely KVK-agnostic. It renders tool calls generically via `ToolCallCard.tsx` and `ToolCallReference.tsx`. KVK data flows through as opaque `TOOL_CALL_ARGS`/`TOOL_CALL_RESULT` AG-UI events.

#### Reporting MCP Server — NO CHANGES (optional)
The reporting server uses a generic `company_id` field (`mcp-servers/reporting/models/hap_schema.py:97`) and `company_address` field (line 99). These are not validated as KVK numbers. The orchestrator can simply pass the postal code as `company_id` or leave it null.

#### Regulation Analysis MCP Server — NO CHANGES
Zero KVK references.

### Documentation Updates (Low Priority)

These are non-functional but should be updated for consistency:

| File | What to update |
|---|---|
| `DEMO_SCENARIOS.md` | Demo prompts, KVK references throughout (lines 12, 32, 93, 108-121, 267-286, 345-346, 438-477, 537-541) |
| `docs/hai-contract/mock_server.py` | `DEMO_COMPANY` dict (line 68-72), conversation examples, tool call simulations |
| `benchmark/benchmark.py` | Test scenario prompt (line 151-158) and expected tool names |
| `README.md` | Demo instructions (line 77), project description (line 16) |
| `server-openai/README.md` | Agent description (line 82), test example (line 137) |
| `mcp-servers/README.md` | Server description (line 11), tool parameters (lines 179-186) |
| `mcp-servers/inspection-history/README.md` | KVK references throughout (lines 7, 48-70, 124) |
| `docs/hai-contract/HAI_API_CONTRACT.md` | Tool call example (lines 156-159) |

## Proposed New Lookup Key Design

For the postal code + house number lookup, a reasonable approach:

```python
def make_lookup_key(postal_code: str, house_number: str) -> str:
    """Create a normalized lookup key from postal code and house number."""
    # Normalize: remove spaces from postal code, lowercase
    normalized_pc = postal_code.replace(" ", "").upper()
    return f"{normalized_pc}-{house_number}"
```

Example demo data:
| Lookup Key | Postal Code | House Nr | Company | City |
|---|---|---|---|---|
| `2511AA-123` | 2511 AA | 123 | Restaurant Bella Rosa | Den Haag |
| `2521DJ-45` | 2521 DJ | 45 | SpeelgoedPlaza Den Haag | Den Haag |
| `9711NX-8` | 9711 NX | 8 | Slagerij de Boer | Groningen |
| `1012AB-67` | 1012 AB | 67 | Cafe Het Bruine Paard | Amsterdam |

## Effort Estimate

| Category | Files | Complexity |
|---|---|---|
| MCP server (core logic) | 1 file | Medium — data model + 6 tool signatures + validation |
| Agent definitions | 2 files | Low — text prompt updates |
| Tool display names | 2 files | Trivial — string changes |
| Transfer tool docstring | 1 file | Trivial |
| Documentation | ~8 files | Low — find/replace + context updates |
| **Total** | **~14 files** | **A few hours of work** |

## Code References

- `mcp-servers/inspection-history/server.py:30-163` — DEMO_INSPECTIONS data (main refactor target)
- `mcp-servers/inspection-history/server.py:170-236` — check_company_exists tool
- `mcp-servers/inspection-history/server.py:244-281` — get_inspection_history tool
- `mcp-servers/inspection-history/server.py:14-15` — KVK_BASE_URL constant to remove
- `mcp-servers/inspection-history/server.py:18-26` — DUTCH_MESSAGES to update
- `server-openai/src/agora_openai/core/agent_definitions.py:33-55` — general-agent KVK triggers
- `server-openai/src/agora_openai/core/agent_definitions.py:212-230` — history-agent KVK workflow
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:35-59` — general-agent KVK triggers
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:210-213` — history-agent KVK workflow
- `server-langgraph/src/agora_langgraph/core/tools.py:28-38` — transfer_to_history docstring
- `server-openai/src/agora_openai/core/tool_display_names.py:15` — search_kvk display name
- `server-langgraph/src/agora_langgraph/core/tool_display_names.py:15` — search_kvk display name

## Architecture Insights

- The KVK lookup is entirely self-contained within the inspection-history MCP server — there is no separate KVK service despite references in older docs
- The real KVK API call code (`httpx` client to `opendata.kvk.nl`) is already dead code (unreachable after an early return) — removing it simplifies the migration
- The frontend's generic tool rendering means UI changes are unnecessary
- The reporting server's `company_id` field is decoupled from the inspection-history server — no coordination needed
- Both orchestrators must be updated identically per project convention

## Open Questions

1. **Tool naming**: Should `check_company_exists` be renamed (e.g., `check_address_exists`) or keep the same name with different parameters?
2. **Postal code validation**: How strict should validation be? (Dutch format: 4 digits + 2 letters, e.g., "2628 BA")
3. **Disabled tools**: Should the 4 disabled tools also be updated now, or left as-is since they're commented out?
4. **Demo scenario prompts**: What should the new demo prompt look like? E.g., "Start inspectie bij Restaurant Bella Rosa, postcode 2511 AA nummer 123"
