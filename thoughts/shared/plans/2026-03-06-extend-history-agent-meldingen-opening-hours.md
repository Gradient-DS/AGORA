# Extend History-Agent with Opening Hours and Meldingen Tools

## Overview

Extend the inspection-history MCP server with opening hours data in `check_company_exists` and a new `get_company_meldingen` tool for consumer complaints. Update history-agent instructions in both orchestrators.

## Current State Analysis

- **MCP server**: `mcp-servers/inspection-history/server.py` — single-file FastMCP app with 2 active tools (`check_company_exists`, `get_inspection_history`) and 4 commented-out tools
- **Demo data**: 4 companies in `DEMO_INSPECTIONS` dict (Restaurant Bella Rosa, SpeelgoedPlaza, Slagerij de Boer, Cafe Het Bruine Paard)
- **Agent instructions**: Defined in both `server-openai/.../agent_definitions.py:198-254` and `server-langgraph/.../agent_definitions.py:191-242`
- **MCP mapping**: Both orchestrators map `history-agent` → `["history"]` via `AGENT_MCP_MAPPING`
- **Auto-discovery**: Both orchestrators auto-discover MCP tools at startup — no registry changes needed

### Key Discoveries:
- `check_company_exists` returns `exists: True` for ALL valid addresses, even unknown ones (`server.py:237-243`)
- Langgraph history-agent has no handoffs (`agent_definitions.py:240`), openai version hands off to all agents (`agent_definitions.py:253`)
- `DUTCH_MESSAGES` dict exists for localized messages (`server.py:14-22`)

## Desired End State

1. `check_company_exists` returns `opening_hours` for known companies, `null` for unknown
2. New `get_company_meldingen` tool returns consumer complaints for a company
3. History-agent instructions mention opening hours and meldingen in both orchestrators
4. All existing tests still pass

### Verification:
- MCP server starts without errors
- `check_company_exists` response includes `opening_hours` field
- `get_company_meldingen` returns correct mock data for known companies
- Both orchestrator agent instructions reference the new capabilities

## What We're NOT Doing

- NOT renaming `check_company_exists` (avoid breaking changes)
- NOT re-enabling the 4 commented-out tools (separate effort)
- NOT adding date range filtering to meldingen (keep it simple)
- NOT modifying `AGENT_MCP_MAPPING` (auto-discovery handles new tools)
- NOT changing frontend, graph routing, or handoff logic

## Implementation Approach

All changes are additive mock data and a new tool in a single file, plus instruction text updates in two files. No structural changes needed.

---

## Phase 1: Opening Hours in `check_company_exists`

### Overview
Add opening hours data to each company in `DEMO_INSPECTIONS` and include it in the `check_company_exists` response.

### Changes Required:

#### 1. Add `opening_hours` to demo companies
**File**: `mcp-servers/inspection-history/server.py`
**Location**: Each company record in `DEMO_INSPECTIONS` (lines 47-190)

Add an `opening_hours` field to each of the 4 company records. Use varied but realistic schedules:

```python
# Restaurant Bella Rosa (2511AA-123)
"opening_hours": {
    "maandag": "Gesloten",
    "dinsdag": "11:00-22:00",
    "woensdag": "11:00-22:00",
    "donderdag": "11:00-22:00",
    "vrijdag": "11:00-23:00",
    "zaterdag": "12:00-23:00",
    "zondag": "12:00-21:00"
}

# SpeelgoedPlaza Den Haag (2521DJ-45)
"opening_hours": {
    "maandag": "10:00-18:00",
    "dinsdag": "10:00-18:00",
    "woensdag": "10:00-18:00",
    "donderdag": "10:00-21:00",
    "vrijdag": "10:00-18:00",
    "zaterdag": "10:00-17:00",
    "zondag": "12:00-17:00"
}

# Slagerij de Boer (9711NX-8)
"opening_hours": {
    "maandag": "08:00-18:00",
    "dinsdag": "08:00-18:00",
    "woensdag": "08:00-13:00",
    "donderdag": "08:00-18:00",
    "vrijdag": "08:00-18:00",
    "zaterdag": "08:00-16:00",
    "zondag": "Gesloten"
}

# Cafe Het Bruine Paard (1012AB-67)
"opening_hours": {
    "maandag": "16:00-01:00",
    "dinsdag": "16:00-01:00",
    "woensdag": "16:00-01:00",
    "donderdag": "16:00-01:00",
    "vrijdag": "16:00-03:00",
    "zaterdag": "14:00-03:00",
    "zondag": "14:00-01:00"
}
```

#### 2. Include `opening_hours` in `check_company_exists` response
**File**: `mcp-servers/inspection-history/server.py`
**Location**: `check_company_exists` function (lines 197-243)

For known companies (line 225-235), add:
```python
"opening_hours": company["opening_hours"],
```

For unknown addresses (line 237-243), add:
```python
"opening_hours": None,
```

### Success Criteria:

#### Automated Verification:
- [ ] MCP server starts without errors: `cd mcp-servers && docker-compose up --build inspection-history`
- [ ] Health check passes: `curl http://localhost:5005/health`
- [ ] `check_company_exists` for known address returns `opening_hours` dict
- [ ] `check_company_exists` for unknown address returns `opening_hours: null`

#### Manual Verification:
- [ ] Opening hours appear in chat when inspector looks up a known company

---

## Phase 2: New `get_company_meldingen` Tool

### Overview
Add mock meldingen data and a new tool to query consumer complaints by company address.

### Changes Required:

#### 1. Add `DEMO_MELDINGEN` data structure
**File**: `mcp-servers/inspection-history/server.py`
**Location**: After `DEMO_INSPECTIONS` (after line 190), before the tools section

```python
DEMO_MELDINGEN = {
    "2511AA-123": [  # Restaurant Bella Rosa - 2 meldingen
        {
            "melding_id": "MLD-2025-001234",
            "datum": "2025-11-15",
            "categorie": "onhygienische_bereiding",
            "subcategorie": "vuile_bereidingsruimte",
            "omschrijving": "Klacht over vieze keuken en ongedierte gezien bij het restaurant.",
            "product_omschrijving": None,
            "status": "in_behandeling",
            "bron": "consumentenklacht"
        },
        {
            "melding_id": "MLD-2025-001890",
            "datum": "2025-08-03",
            "categorie": "misleidende_informatie",
            "subcategorie": "geen_allergeninformatie",
            "omschrijving": "Geen allergeninformatie beschikbaar op de menukaart ondanks herhaaldelijk vragen.",
            "product_omschrijving": None,
            "status": "afgehandeld",
            "bron": "consumentenklacht"
        },
    ],
    "2521DJ-45": [  # SpeelgoedPlaza - 1 melding
        {
            "melding_id": "MLD-2025-002456",
            "datum": "2025-09-22",
            "categorie": "onjuiste_etikettering",
            "subcategorie": "ontbrekende_ingredienten",
            "omschrijving": "Speelgoedverf zonder ingrediëntenvermelding op de verpakking, potentieel giftige stoffen.",
            "product_omschrijving": "KinderVerf Set 12 kleuren",
            "status": "doorgestuurd",
            "bron": "consumentenklacht"
        },
    ],
    "9711NX-8": [  # Slagerij de Boer - 3 meldingen
        {
            "melding_id": "MLD-2025-003789",
            "datum": "2025-12-01",
            "categorie": "productproblemen",
            "subcategorie": "vreemde_geur_smaak",
            "omschrijving": "Rookworst had vreemde geur en smaak, vermoeden van bederf.",
            "product_omschrijving": "Rookworst huisgemaakt",
            "status": "in_behandeling",
            "bron": "consumentenklacht"
        },
        {
            "melding_id": "MLD-2025-003012",
            "datum": "2025-10-18",
            "categorie": "verlopen_producten",
            "subcategorie": "over_datum",
            "omschrijving": "Gehaktballen met verlopen houdbaarheidsdatum aangetroffen in de vitrine.",
            "product_omschrijving": "Gehaktballen huisgemaakt",
            "status": "afgehandeld",
            "bron": "consumentenklacht"
        },
        {
            "melding_id": "MLD-2025-002567",
            "datum": "2025-07-14",
            "categorie": "onhygienische_bereiding",
            "subcategorie": "ongedierte",
            "omschrijving": "Vliegen gespot in de vitrine bij de vleesproducten.",
            "product_omschrijving": None,
            "status": "afgehandeld",
            "bron": "consumentenklacht"
        },
    ],
    # 1012AB-67 (Cafe Het Bruine Paard) - no meldingen (clean record)
}
```

#### 2. Update `DUTCH_MESSAGES`
**File**: `mcp-servers/inspection-history/server.py`
**Location**: `DUTCH_MESSAGES` dict (lines 14-22)

Add:
```python
"no_meldingen": "Geen meldingen gevonden voor dit bedrijf.",
```

#### 3. Add `get_company_meldingen` tool
**File**: `mcp-servers/inspection-history/server.py`
**Location**: After `check_company_exists` (after line 243), before the inspection history tools section

```python
@mcp.tool()
async def get_company_meldingen(
    postal_code: str,
    house_number: str,
    categorie: str | None = None,
    limit: int = 10,
) -> dict:
    """Haal meldingen op uit het meldingensysteem voor een bedrijf.

    Controleer of er consumentenklachten of meldingen zijn binnengekomen
    over dit bedrijf op basis van postcode en huisnummer.

    Categorieën: productproblemen, onjuiste_etikettering, verlopen_producten,
    onhygienische_bereiding, misleidende_informatie

    Args:
        postal_code: Nederlandse postcode (bijv. '2511 AA')
        house_number: Huisnummer (bijv. '123')
        categorie: Optioneel filter op categorie
        limit: Maximum aantal meldingen om te retourneren (standaard 10)

    Returns:
        dict met meldingen en bedrijfsgegevens
    """
    logger.info(f"Fetching meldingen for address: {postal_code} {house_number}")

    error = validate_address(postal_code, house_number)
    if error:
        return {
            "status": "error",
            "error": error,
            "postal_code": postal_code,
            "house_number": house_number,
        }

    key = make_lookup_key(postal_code, house_number)
    meldingen = DEMO_MELDINGEN.get(key, [])

    # Get company name from DEMO_INSPECTIONS if available
    company_data = DEMO_INSPECTIONS.get(key)
    company_name = company_data["company_name"] if company_data else None

    if not meldingen:
        return {
            "status": "success",
            "postal_code": postal_code,
            "house_number": house_number,
            "company_name": company_name,
            "message": DUTCH_MESSAGES["no_meldingen"],
            "total_meldingen": 0,
            "meldingen": [],
        }

    # Filter by category if provided
    if categorie:
        meldingen = [m for m in meldingen if m["categorie"] == categorie]

    # Sort by date (newest first) and limit
    meldingen = sorted(meldingen, key=lambda m: m["datum"], reverse=True)[:limit]

    return {
        "status": "success",
        "postal_code": postal_code,
        "house_number": house_number,
        "company_name": company_name,
        "total_meldingen": len(meldingen),
        "meldingen": meldingen,
    }
```

### Success Criteria:

#### Automated Verification:
- [ ] MCP server starts without errors
- [ ] `get_company_meldingen` appears in tool list: `curl http://localhost:5005/mcp/tools | jq`
- [ ] Returns 2 meldingen for `2511AA-123` (Bella Rosa)
- [ ] Returns 0 meldingen for `1012AB-67` (Cafe Het Bruine Paard)
- [ ] Category filter works correctly

#### Manual Verification:
- [ ] Inspector can ask about meldingen for a company in the chat

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Update Agent Instructions (Both Orchestrators)

### Overview
Update history-agent instructions in both server-openai and server-langgraph to document opening hours in `check_company_exists` and the new `get_company_meldingen` tool.

### Changes Required:

#### 1. server-openai agent instructions
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`
**Location**: history-agent instructions (lines 201-248)

Add to the `YOUR CAPABILITIES` section (after line 217):
```python
"- Opening hours are included in the check_company_exists response\n\n"
```

Add to the `INSPECTION HISTORY` section (after line 222):
```python
"- Check consumer complaints via get_company_meldingen\n"
```

Add to the `WORKFLOW` section (after line 238, as step 4, shifting existing 4 to 5):
```python
"4. When checking consumer complaints:\n"
"   - Call get_company_meldingen (optionally filter by categorie)\n"
```

Add to the `FORMAT` section (line 248):
```python
"Bedrijfsgegevens → Openingstijden → Meldingen → Historisch Overzicht → Overtredingen → Follow-up Status"
```

#### 2. server-langgraph agent instructions
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
**Location**: history-agent instructions (lines 194-235)

Apply the same changes as server-openai:

Add to `YOUR FOCUS` section (after line 212):
```python
"- Opening hours (included in check_company_exists response)\n"
"- Consumer complaints from the meldingen system\n"
```

Add to `TOOL USAGE` section (after line 221, as new item 3, shifting existing 3 to 4):
```python
"3. When checking consumer complaints:\n"
"   - Call get_company_meldingen (optionally filter by categorie)\n"
```

Add to `FORMAT` section (line 235):
```python
"Bedrijfsgegevens → Openingstijden → Meldingen → Historisch Overzicht → Overtredingen → Follow-up Status"
```

### Success Criteria:

#### Automated Verification:
- [ ] Both orchestrators start without import errors
- [ ] `python -c "from agora_openai.core.agent_definitions import AGENT_CONFIGS; print('OK')"` succeeds
- [ ] `python -c "from agora_langgraph.core.agent_definitions import AGENT_CONFIGS; print('OK')"` succeeds

#### Manual Verification:
- [ ] History-agent mentions opening hours when looking up a known company
- [ ] History-agent uses `get_company_meldingen` when asked about complaints
- [ ] Both orchestrators behave identically

---

## Testing Strategy

### Manual Testing Steps:
1. Start MCP servers: `cd mcp-servers && docker-compose up --build`
2. Start an orchestrator and the frontend
3. Ask: "Zoek bedrijf op postcode 2511 AA nummer 123" — verify opening hours appear
4. Ask: "Zijn er meldingen over dit bedrijf?" — verify 2 meldingen for Bella Rosa
5. Ask: "Zoek bedrijf op postcode 1012 AB nummer 67" — verify no meldingen for Cafe
6. Test with unknown address — verify graceful handling

## References

- Research: `thoughts/shared/research/2026-03-06-extend-history-agent-meldingen-opening-hours.md`
- MCP server: `mcp-servers/inspection-history/server.py`
- Agent definitions (openai): `server-openai/src/agora_openai/core/agent_definitions.py:198-254`
- Agent definitions (langgraph): `server-langgraph/src/agora_langgraph/core/agent_definitions.py:191-242`
- MCP mapping (openai): `server-openai/src/agora_openai/core/agent_runner.py:34-39`
- MCP mapping (langgraph): `server-langgraph/src/agora_langgraph/core/tools.py:273-278`
