---
date: 2026-03-06T12:00:00+01:00
researcher: Claude
git_commit: ae92e0e
branch: feat/tool-description
repository: AGORA
topic: "Extend history-agent with opening hours and meldingen tools"
tags: [research, codebase, inspection-history, mcp-server, meldingen, opening-hours]
status: complete
last_updated: 2026-03-06
last_updated_by: Claude
---

# Research: Extend History-Agent with Opening Hours and Meldingen Tools

**Date**: 2026-03-06
**Git Commit**: ae92e0e
**Branch**: feat/tool-description
**Repository**: AGORA

## Research Question

How to extend the inspection-history MCP server (company information agent) with:
1. Opening hours combined into the existing `check_company_exists` tool
2. A new tool to check "meldingen" (consumer complaints) from "het meldingensysteem"

## Summary

The inspection-history MCP server is a single-file FastMCP app (`mcp-servers/inspection-history/server.py`) with 2 active tools (`check_company_exists`, `get_inspection_history`) and 4 commented-out tools. It serves mock data from an in-memory `DEMO_INSPECTIONS` dict keyed by postal code + house number. The history-agent in both orchestrators is mapped exclusively to the `history` MCP server via `AGENT_MCP_MAPPING`. Changes require updates in 3 places: the MCP server, and both orchestrator agent definitions.

## Detailed Findings

### 1. Current `check_company_exists` Tool (to extend with opening hours)

**File**: `mcp-servers/inspection-history/server.py:197-243`

Current behavior:
- Takes `postal_code` and `house_number` parameters
- Validates address format, looks up in `DEMO_INSPECTIONS`
- Returns: `exists`, `company_name`, `postal_code`, `house_number`, `street`, `city`, `active`
- Note: Currently returns `exists: True` for ALL valid address formats, even unknown ones (lines 237-243)

**Proposed changes for opening hours**:
- Add `opening_hours` field to each company record in `DEMO_INSPECTIONS`
- Include `opening_hours` in the `check_company_exists` response
- Consider renaming to `get_company_info` since it now returns richer data
- For unknown addresses, return generic/null opening hours

**Mock data structure for opening hours**:
```python
"opening_hours": {
    "maandag": "09:00-17:00",
    "dinsdag": "09:00-17:00",
    "woensdag": "09:00-17:00",
    "donderdag": "09:00-17:00",
    "vrijdag": "09:00-17:00",
    "zaterdag": "10:00-16:00",
    "zondag": "Gesloten"
}
```

### 2. New Meldingen Tool

No existing tool or data structure for meldingen/complaints. This needs to be created from scratch.

**Consumer complaint categories** (from NVWA/Consumentenbond forms):
- Product issues: wrong taste/smell, foreign objects
- Incorrect labelling: missing allergen/ingredient info
- Expired products
- Unclean premises: pests, dirty prep areas, unhygienic preparation
- Misleading information: e.g. chicken sold as turkey, no allergen info available

**Consumer complaint data fields**:
- Detailed product description
- Type number
- Batch number
- Barcode
- Category (from above)

**Proposed mock data structure**:
```python
DEMO_MELDINGEN = {
    "2511AA-123": [  # Restaurant Bella Rosa
        {
            "melding_id": "MLD-2025-001234",
            "datum": "2025-11-15",
            "categorie": "onhygienische_bereiding",
            "subcategorie": "vuile_bereidingsruimte",
            "omschrijving": "Klacht over vieze keuken en ongedierte gezien bij het restaurant.",
            "product_omschrijving": None,
            "type_nummer": None,
            "batch_nummer": None,
            "barcode": None,
            "status": "in_behandeling",
            "bron": "consumentenklacht"
        },
    ],
}
```

**Proposed tool**:
```python
@mcp.tool()
async def get_company_meldingen(
    postal_code: str,
    house_number: str,
    categorie: str | None = None,
    limit: int = 10
) -> dict:
    """Haal meldingen op uit het meldingensysteem voor een bedrijf op basis van postcode en huisnummer.

    Controleer of er consumentenklachten of meldingen zijn binnengekomen over dit bedrijf.
    """
```

### 3. Files That Need Changes

#### MCP Server (inspection-history)
- `mcp-servers/inspection-history/server.py`:
  - Add `opening_hours` to `DEMO_INSPECTIONS` company records
  - Add `opening_hours` to `check_company_exists` response
  - Add `DEMO_MELDINGEN` data structure
  - Add `get_company_meldingen` tool
  - Update `DUTCH_MESSAGES` with meldingen-related messages

#### Agent Definitions (both orchestrators)
- `server-openai/src/agora_openai/core/agent_definitions.py:198-254`:
  - Update history-agent instructions to mention opening hours in `check_company_exists` response
  - Add `get_company_meldingen` to the TOOL USAGE / WORKFLOW section
  - Update FORMAT section to include Meldingen
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:191-242`:
  - Same instruction updates as server-openai

#### No changes needed in:
- `AGENT_MCP_MAPPING` (already maps history-agent → history server)
- Orchestrator tool discovery (auto-discovers tools from MCP servers)
- Graph routing / handoff logic
- Frontend (tools are displayed generically)

### 4. Current Agent Instructions (history-agent)

Both orchestrators define nearly identical instructions at:
- **server-openai**: `server-openai/src/agora_openai/core/agent_definitions.py:201-248`
- **server-langgraph**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:194-235`

The workflow section currently lists:
1. `check_company_exists` → verify company
2. `get_inspection_history` → full details
3. `get_company_violations` → filter by severity
4. `check_repeat_violation` → specific categories
5. `get_follow_up_status` → follow-up actions

Should add:
- Opening hours info is now part of `check_company_exists` response
- `get_company_meldingen` for checking consumer complaints

### 5. Mock Data: 4 Demo Companies

| Key | Company | City | Suggested meldingen scenario |
|-----|---------|------|------------------------------|
| `2511AA-123` | Restaurant Bella Rosa | Den Haag | 2 meldingen (unclean premises, misleading info) |
| `2521DJ-45` | SpeelgoedPlaza Den Haag | Den Haag | 1 melding (incorrect labelling) |
| `9711NX-8` | Slagerij de Boer | Groningen | 3 meldingen (product issues, expired, unclean) |
| `1012AB-67` | Cafe Het Bruine Paard | Amsterdam | 0 meldingen (clean record) |

## Code References

- `mcp-servers/inspection-history/server.py:197-243` - Current `check_company_exists` tool
- `mcp-servers/inspection-history/server.py:251-301` - Current `get_inspection_history` tool
- `mcp-servers/inspection-history/server.py:46-190` - `DEMO_INSPECTIONS` mock data
- `server-openai/src/agora_openai/core/agent_definitions.py:198-254` - History-agent config (openai)
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:191-242` - History-agent config (langgraph)
- `server-openai/src/agora_openai/core/agent_runner.py:34-39` - AGENT_MCP_MAPPING (openai)
- `server-langgraph/src/agora_langgraph/core/tools.py:273-278` - AGENT_MCP_MAPPING (langgraph)

## Architecture Insights

1. **Auto-discovery**: Both orchestrators auto-discover MCP tools at startup. Adding a new tool to the MCP server automatically makes it available — no registry updates needed.
2. **Agent instructions matter**: The LLM needs to know about tools in its system prompt to use them effectively. Both orchestrator agent definitions must be updated.
3. **Single-file server**: The entire inspection-history server is one file, making extension straightforward.
4. **Handoff detection**: In server-openai, `_detect_handoff_target` (agent_runner.py:358-374) triggers on tool names containing "company" or "history". A tool named `get_company_meldingen` would match the "company" pattern automatically.
5. **Both orchestrators**: Per CLAUDE.md guidelines, changes must be implemented identically in both server-openai and server-langgraph.

## Historical Context (from thoughts/)

- `thoughts/shared/plans/2026-02-22-kvk-to-postal-code-migration.md` - Previous migration from KVK numbers to postal code + house number lookup (already completed)
- `thoughts/shared/research/2026-02-22-kvk-to-postal-code-migration.md` - Research for that migration
- No existing documents about meldingen or opening hours features

## Open Questions

1. Should `check_company_exists` be renamed (e.g., `get_company_info`) now that it returns richer data including opening hours?
2. Should meldingen data be a separate dict (`DEMO_MELDINGEN`) or nested inside `DEMO_INSPECTIONS` company records?
3. What status values should meldingen have? (e.g., `in_behandeling`, `afgehandeld`, `doorgestuurd`)
4. Should the 4 commented-out tools (`get_company_violations`, `check_repeat_violation`, `get_follow_up_status`, `search_inspections_by_inspector`) be re-enabled as part of this work?
5. Should `get_company_meldingen` include a date range filter parameter?
