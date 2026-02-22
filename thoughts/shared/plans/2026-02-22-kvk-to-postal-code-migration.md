# KVK to Postal Code + House Number Migration

## Overview

Migrate the company lookup mechanism from KVK numbers (8-digit Chamber of Commerce identifiers) to postal codes + house numbers (e.g., "2511 AA", number 123) for demo purposes. All data remains mocked. Tool names (`check_company_exists`, `get_inspection_history`) stay the same — only parameters change.

## Current State Analysis

- **MCP server** (`mcp-servers/inspection-history/server.py`): 4 demo companies keyed by KVK number, 2 active tools (`check_company_exists`, `get_inspection_history`), 4 disabled tools, dead KVK API code using `httpx`
- **Agent definitions**: Both orchestrators reference KVK in prompts/triggers/workflow instructions
- **Tool display names**: Both have a `search_kvk` entry (unused but present)
- **Transfer tool** (LangGraph): Docstring references "KVK numbers"
- **Handoff detection** (server-openai `agent_runner.py:347-363`): Checks for `"company"` or `"history"` in tool names — works fine without renaming

### Key Discoveries:
- `check_company_exists` always returns hardcoded success for valid 8-digit input (`server.py:193-198`) — all KVK API code is unreachable dead code
- `httpx` import is only used in dead code — can be removed
- Tool display names have `search_kvk` which appears to be a leftover from a removed tool
- The two orchestrator agent definition files are NOT identical — they have different prompt styles and structures, so each needs careful individual editing

## Desired End State

After this migration:
1. Inspector says "Start inspectie bij Restaurant Bella Rosa, postcode 2511 AA nummer 123" instead of providing a KVK number
2. The MCP tools accept `postal_code` + `house_number` parameters instead of `kvk_number`
3. Demo data is keyed by normalized postal code + house number (e.g., `"2511AA-123"`)
4. All agent prompts reference postcodes/addresses instead of KVK
5. All documentation is updated

### Verification:
- MCP server health check returns 200
- Agent definitions parse correctly (no syntax errors)
- Demo scenario prompts use new format
- `check_company_exists` validates Dutch postal code format (4 digits + 2 letters)
- `get_inspection_history` looks up by postal code + house number

## What We're NOT Doing

- Renaming tool functions (`check_company_exists` stays `check_company_exists`)
- Changing the frontend (HAI) — it's already KVK-agnostic
- Changing the reporting MCP server — uses generic `company_id`/`company_address` fields
- Changing the regulation analysis MCP server — zero KVK references
- Adding real postal code validation (we keep it simple for demo)
- Adding a real address lookup API

## Implementation Approach

Three phases: core MCP server refactor, agent prompt updates (both orchestrators + tools), and documentation updates. Each phase is independently testable.

## Demo Data

New demo companies with realistic Dutch addresses:

| Lookup Key | Postal Code | House Nr | Company | City | Street |
|---|---|---|---|---|---|
| `2511AA-123` | 2511 AA | 123 | Restaurant Bella Rosa | Den Haag | Haagweg |
| `2521DJ-45` | 2521 DJ | 45 | SpeelgoedPlaza Den Haag | Den Haag | Zuiderparklaan |
| `9711NX-8` | 9711 NX | 8 | Slagerij de Boer | Groningen | Brugstraat |
| `1012AB-67` | 1012 AB | 67 | Café Het Bruine Paard | Amsterdam | Damstraat |

---

## Phase 1: MCP Server Refactor

### Overview
Refactor `mcp-servers/inspection-history/server.py` to use postal code + house number instead of KVK numbers. This is the core functional change.

### Changes Required:

#### 1. Remove dead code and update constants
**File**: `mcp-servers/inspection-history/server.py`

Remove the `KVK_BASE_URL` constant (line 15), remove the `httpx` import (line 7), and update `DUTCH_MESSAGES`:

```python
# Remove line 7: import httpx
# Remove lines 14-15: KVK_BASE_URL = "https://opendata.kvk.nl/api/v1/hvds"

# Update DUTCH_MESSAGES (lines 18-26):
DUTCH_MESSAGES = {
    "invalid_address": "Ongeldig adresformaat. Postcode moet 4 cijfers en 2 letters zijn (bijv. '2511 AA'), huisnummer moet een getal zijn.",
    "not_found": "Geen bedrijf gevonden op dit adres. Dit kan een eerste inspectie zijn.",
    "no_violations": "Er zijn geen overtredingen gevonden voor dit bedrijf.",
    "repeat_warning": "⚠️ WAARSCHUWING: Dit is een herhaalde overtreding.",
    "escalation_advised": "ESCALATIE_GEADVISEERD",
    "immediate_action": "DIRECTE_ACTIE_VEREIST",
    "no_history": "Geen geschiedenis gevonden. Dit lijkt een eerste inspectie te zijn.",
}
```

#### 2. Add lookup key helper function
**File**: `mcp-servers/inspection-history/server.py`

Add after DUTCH_MESSAGES, before DEMO_INSPECTIONS:

```python
def make_lookup_key(postal_code: str, house_number: str) -> str:
    """Create a normalized lookup key from postal code and house number."""
    normalized_pc = postal_code.replace(" ", "").upper()
    return f"{normalized_pc}-{house_number}"


def validate_address(postal_code: str, house_number: str) -> str | None:
    """Validate Dutch postal code and house number format.

    Returns error message if invalid, None if valid.
    """
    import re
    normalized_pc = postal_code.replace(" ", "").upper()
    if not re.match(r"^\d{4}[A-Z]{2}$", normalized_pc):
        return DUTCH_MESSAGES["invalid_address"]
    if not house_number.strip().isdigit():
        return DUTCH_MESSAGES["invalid_address"]
    return None
```

#### 3. Update DEMO_INSPECTIONS data model
**File**: `mcp-servers/inspection-history/server.py` (lines 30-163)

Replace the entire `DEMO_INSPECTIONS` dictionary. Change keys from KVK numbers to postal code + house number format. Replace `kvk_number` field with `postal_code`, `house_number`, `street`, and `city` fields. Keep all inspection data identical.

```python
# Demo data using postal code + house number as lookup key
DEMO_INSPECTIONS = {
    "2511AA-123": {  # Koen scenario
        "company_name": "Restaurant Bella Rosa",
        "postal_code": "2511 AA",
        "house_number": "123",
        "street": "Haagweg",
        "city": "Den Haag",
        "inspections": [
            # ... same inspection data as current, unchanged ...
        ],
    },
    "2521DJ-45": {  # Fatima scenario
        "company_name": "SpeelgoedPlaza Den Haag",
        "postal_code": "2521 DJ",
        "house_number": "45",
        "street": "Zuiderparklaan",
        "city": "Den Haag",
        "inspections": [
            # ... same inspection data as current, unchanged ...
        ],
    },
    "9711NX-8": {  # Jan scenario
        "company_name": "Slagerij de Boer",
        "postal_code": "9711 NX",
        "house_number": "8",
        "street": "Brugstraat",
        "city": "Groningen",
        "inspections": [
            # ... same inspection data as current, unchanged ...
        ],
    },
    "1012AB-67": {  # Additional demo company for testing
        "company_name": "Café Het Bruine Paard",
        "postal_code": "1012 AB",
        "house_number": "67",
        "street": "Damstraat",
        "city": "Amsterdam",
        "inspections": [
            # ... same inspection data as current, unchanged ...
        ],
    },
}
```

#### 4. Refactor `check_company_exists` tool
**File**: `mcp-servers/inspection-history/server.py` (lines 170-236)

Replace the entire function. Change parameter from `kvk_number: str` to `postal_code: str, house_number: str`. Remove all dead KVK API code. Use new validation and lookup:

```python
@mcp.tool()
async def check_company_exists(postal_code: str, house_number: str) -> dict:
    """Controleer of een bedrijf bestaat op het opgegeven adres.

    Zoek een bedrijf op basis van postcode en huisnummer.
    Retourneert bedrijfsgegevens als het bedrijf is gevonden.

    Args:
        postal_code: Nederlandse postcode (bijv. '2511 AA')
        house_number: Huisnummer (bijv. '123')

    Returns:
        dict met status, bedrijfsnaam en adresgegevens
    """
    logger.info(f"Checking company at address: {postal_code} {house_number}")

    error = validate_address(postal_code, house_number)
    if error:
        return {
            "status": "error",
            "exists": False,
            "error": error,
            "code": "INVALID_FORMAT",
        }

    key = make_lookup_key(postal_code, house_number)
    company = DEMO_INSPECTIONS.get(key)

    if company:
        return {
            "status": "success",
            "exists": True,
            "postal_code": company["postal_code"],
            "house_number": company["house_number"],
            "street": company["street"],
            "city": company["city"],
            "company_name": company["company_name"],
            "active": True,
        }

    return {
        "status": "success",
        "exists": True,
        "postal_code": postal_code,
        "house_number": house_number,
        "active": True,
    }
```

Note: For addresses not in demo data, we still return `exists: True` (matching current behavior where any valid 8-digit KVK returns success).

#### 5. Refactor `get_inspection_history` tool
**File**: `mcp-servers/inspection-history/server.py` (lines 244-281)

Replace the function. Change parameter from `kvk_number: str` to `postal_code: str, house_number: str`:

```python
@mcp.tool()
async def get_inspection_history(postal_code: str, house_number: str, limit: int = 10) -> dict:
    """Haal inspectiegeschiedenis op voor een bedrijf op basis van adres.

    Retourneert een lijst van eerdere inspecties inclusief data, inspecteurs,
    bevindingen en overtredingen.

    Args:
        postal_code: Nederlandse postcode (bijv. '2511 AA')
        house_number: Huisnummer (bijv. '123')
        limit: Maximum aantal inspecties om te retourneren (standaard 10)

    Returns:
        dict met inspectiehistorie en bedrijfsgegevens
    """
    logger.info(f"Fetching inspection history for address: {postal_code} {house_number}")

    error = validate_address(postal_code, house_number)
    if error:
        return {
            "status": "error",
            "error": error,
            "postal_code": postal_code,
            "house_number": house_number,
        }

    key = make_lookup_key(postal_code, house_number)
    company_data = DEMO_INSPECTIONS.get(key)

    if not company_data:
        return {
            "status": "not_found",
            "postal_code": postal_code,
            "house_number": house_number,
            "message": DUTCH_MESSAGES["not_found"],
            "inspections": [],
        }

    inspections = company_data["inspections"][:limit]

    return {
        "status": "success",
        "postal_code": company_data["postal_code"],
        "house_number": company_data["house_number"],
        "street": company_data["street"],
        "city": company_data["city"],
        "company_name": company_data["company_name"],
        "total_inspections": len(company_data["inspections"]),
        "returned_inspections": len(inspections),
        "inspections": inspections,
    }
```

#### 6. Update 4 disabled tools
**File**: `mcp-servers/inspection-history/server.py` (lines 284-518)

Update all 4 disabled tools to use `postal_code: str, house_number: str` instead of `kvk_number: str`. For each:
- Change function signature parameter
- Update docstring
- Change lookup to use `make_lookup_key(postal_code, house_number)`
- Update return values to include address fields instead of `kvk_number`
- `search_inspections_by_inspector` (line 481): update the per-result dict to include `postal_code`/`house_number` instead of `kvk_number`

#### 7. Update health check and server info
**File**: `mcp-servers/inspection-history/server.py`

Update `server_info` resource (lines 535-552):
- Change `demo_kvk_numbers` key to `demo_addresses`
- Value should be list of formatted address strings like `"2511 AA 123 - Restaurant Bella Rosa"`

Update comment on line 29 from "Using KVK numbers that can be looked up via KVK Lookup MCP server" to "Demo data using postal code + house number as lookup key".

#### 8. Clean up imports
Remove `import httpx` (line 7) since it was only used in dead code. Keep `Optional` from typing since disabled tools still use it.

### Success Criteria:

#### Automated Verification:
- [ ] MCP server starts without import errors: `cd mcp-servers && docker-compose up inspection-history`
- [ ] Health check returns 200: `curl http://localhost:5005/health`
- [ ] Tool list shows updated parameters: `curl http://localhost:5005/mcp/tools | jq`
- [x] No Python syntax errors: `python -c "import ast; ast.parse(open('mcp-servers/inspection-history/server.py').read())"`

#### Manual Verification:
- [ ] `check_company_exists` with valid address returns company info
- [ ] `check_company_exists` with invalid format returns error
- [ ] `get_inspection_history` returns correct demo data for each address
- [ ] `get_inspection_history` for unknown address returns not_found

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Agent Definitions & Tool Config Updates

### Overview
Update both orchestrator agent definitions, tool display names, and the LangGraph transfer tool docstring to reference postal codes/addresses instead of KVK.

### Changes Required:

#### 1. Server-OpenAI Agent Definitions
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`

**general-agent instructions (lines 33-35, 43, 53):**
- Line 34: `"   - Use for: KVK numbers, company lookups, inspection history\n"` → `"   - Use for: Postal codes, addresses, company lookups, inspection history\n"`
- Line 35: `"   - Triggers: 'bedrijf', 'KVK', 'geschiedenis', 'start inspectie'\n"` → `"   - Triggers: 'bedrijf', 'postcode', 'adres', 'geschiedenis', 'start inspectie'\n"`
- Line 43: `"- If inspector mentions KVK or company name → handoff to history-agent\n"` → `"- If inspector mentions address, postcode or company name → handoff to history-agent\n"`
- Line 53: `"Q: 'Start inspectie bij Bakkerij Jansen KVK 12345678'\n"` → `"Q: 'Start inspectie bij Bakkerij Jansen, postcode 2511 AA nummer 123'\n"`

**history-agent instructions (lines 211-214, 228-229):**
- Lines 212-214: Replace:
  ```
  "COMPANY VERIFICATION:\n"
  "- Check if company exists in KVK register (check_company_exists)\n"
  "- Verify KVK numbers are valid (8 digits)\n\n"
  ```
  With:
  ```
  "COMPANY VERIFICATION:\n"
  "- Check if company exists at address (check_company_exists)\n"
  "- Verify postal code format (4 digits + 2 letters, e.g. '2511 AA')\n\n"
  ```
- Lines 228-229: Replace:
  ```
  "1. When inspector provides KVK number:\n"
  "   - First call check_company_exists to verify\n"
  ```
  With:
  ```
  "1. When inspector provides postal code and house number:\n"
  "   - First call check_company_exists with postal_code and house_number to verify\n"
  ```

**Spoken text prompts (lines 267, 273-274, 318):**
- Line 267: `"  * 'KVK' → 'Kamer van Koophandel'\n"` → remove this line (KVK is no longer used)
- Lines 273-274: Update example:
  ```
  "Vraag: 'Start inspectie bij Bakkerij Jansen KVK 12345678'\n"
  "Antwoord: 'Prima, ik zoek de bedrijfsgegevens voor Bakkerij Jansen "
  "bij de Kamer van Koophandel op.'"
  ```
  To:
  ```
  "Vraag: 'Start inspectie bij Bakkerij Jansen, postcode 2511 AA nummer 123'\n"
  "Antwoord: 'Prima, ik zoek de bedrijfsgegevens voor Bakkerij Jansen op.'"
  ```
- Line 318: `"  * 'KVK' → 'Kamer van Koophandel'\n\n"` → remove this line

#### 2. Server-LangGraph Agent Definitions
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`

**general-agent instructions (lines 35, 47, 59):**
- Line 35: `"- Bedrijfsinformatie en KVK-verificatie opzoeken\n"` → `"- Bedrijfsinformatie opzoeken op basis van postcode en huisnummer\n"`
- Line 47: `"   - ANY mention of: KVK, company name, bedrijf, geschiedenis, inspectiehistorie\n"` → `"   - ANY mention of: postcode, adres, company name, bedrijf, geschiedenis, inspectiehistorie\n"`
- Line 59: `"- Company/KVK mentioned? → transfer_to_history\n"` → `"- Company/address/postcode mentioned? → transfer_to_history\n"`

**history-agent instructions (lines 198, 211-213):**
- Line 198: `"1. FIRST: Call check_company_exists or get_inspection_history\n"` → `"1. FIRST: Call check_company_exists with postal_code and house_number, or get_inspection_history\n"`
- Lines 211-213: Replace:
  ```
  "TOOL USAGE:\n"
  "1. When inspector provides KVK number:\n"
  "   - Call check_company_exists to verify\n"
  "   - Call get_inspection_history for full details\n"
  ```
  With:
  ```
  "TOOL USAGE:\n"
  "1. When inspector provides postal code and house number:\n"
  "   - Call check_company_exists with postal_code and house_number to verify\n"
  "   - Call get_inspection_history for full details\n"
  ```

**Spoken text prompts (lines 255, 269-271, 318):**
- Line 255: `"  * 'KVK' → 'Kamer van Koophandel'\n"` → remove this line
- Lines 269-271: Update example:
  ```
  "Vraag: 'Start inspectie bij Bakkerij Jansen KVK 12345678'\n"
  "Antwoord: 'Prima, ik zoek de bedrijfsgegevens voor Bakkerij Jansen "
  "bij de Kamer van Koophandel op.'"
  ```
  To:
  ```
  "Vraag: 'Start inspectie bij Bakkerij Jansen, postcode 2511 AA nummer 123'\n"
  "Antwoord: 'Prima, ik zoek de bedrijfsgegevens voor Bakkerij Jansen op.'"
  ```
- Line 318: `"  * 'KVK' → 'Kamer van Koophandel'\n\n"` → remove this line

#### 3. LangGraph Transfer Tool Docstring
**File**: `server-langgraph/src/agora_langgraph/core/tools.py`

Lines 32-33: Change:
```python
    """Transfer the conversation to the Company and Inspection History Specialist.

    Use this when the user asks about:
    - Company information or KVK numbers
```
To:
```python
    """Transfer the conversation to the Company and Inspection History Specialist.

    Use this when the user asks about:
    - Company information, addresses, or postal codes
```

#### 4. Tool Display Names (both orchestrators)
**Files**:
- `server-openai/src/agora_openai/core/tool_display_names.py`
- `server-langgraph/src/agora_langgraph/core/tool_display_names.py`

In both files, remove the `search_kvk` entry (line 15):
```python
    "search_kvk": "Zoeken in het KVK",  # REMOVE THIS LINE
```

The `check_company_exists` display name "Controleren bedrijfsgegevens" is still accurate and needs no change.

### Success Criteria:

#### Automated Verification:
- [x] No Python syntax errors in agent definitions: `python -c "from agora_openai.core.agent_definitions import AGENT_CONFIGS; print('OK')"`
- [x] No Python syntax errors in LangGraph agent definitions: `python -c "from agora_langgraph.core.agent_definitions import AGENT_CONFIGS; print('OK')"`
- [ ] Type check passes for server-openai: `cd server-openai && mypy src/`
- [ ] Type check passes for server-langgraph: `cd server-langgraph && mypy src/`
- [x] No "KVK" or "kvk" references remain in agent_definitions.py (both): `grep -i kvk server-openai/src/agora_openai/core/agent_definitions.py server-langgraph/src/agora_langgraph/core/agent_definitions.py`

#### Manual Verification:
- [ ] Agent prompts read naturally in Dutch
- [ ] Handoff triggers mention postcode/adres instead of KVK
- [ ] Spoken text examples use new address format

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Documentation Updates

### Overview
Update all documentation files to reference postal codes/addresses instead of KVK numbers.

### Changes Required:

#### 1. DEMO_SCENARIOS.md
**File**: `DEMO_SCENARIOS.md` (~35 lines to update)

Key changes:
- Line 12: `"Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854"` → `"Start inspectie bij Restaurant Bella Rosa, postcode 2511 AA nummer 123"`
- Line 32: Similar update for SpeelgoedPlaza with `postcode 2521 DJ nummer 45`
- All `{"kvk_number": "..."}` argument blocks → `{"postal_code": "...", "house_number": "..."}`
- Line 93: Remove KVK Lookup health check (port 5004 service no longer exists)
- Lines 438-547: Update "Integration Flow" section header and content
- Line 537: Update "All demo KVK numbers" → "All demo addresses" with new address list

#### 2. Mock Server
**File**: `docs/hai-contract/mock_server.py` (~21 lines to update)

- Line 69: `"kvk_number": "92251854"` → `"postal_code": "2511 AA", "house_number": "123", "street": "Haagweg", "city": "Den Haag"`
- Lines 129, 138: Update `firstMessagePreview` strings
- Line 172: Update message content
- Line 176: Update bedrijfsgegevens display (remove KVK, add address)
- Lines 200, 213: Update tool call content from `kvk_number` to `postal_code`/`house_number`
- Line 278: `"Heeft u het KVK-nummer?"` → `"Wat is de postcode en het huisnummer?"`
- Line 492: Update agent description
- Line 772: Remove `text.replace("KVK", "Kamer van Koophandel")` TTS replacement
- Line 976: Update agent description
- Lines 1012-1241: Update all tool call simulations to use postal_code/house_number

#### 3. HAI API Contract
**File**: `docs/hai-contract/HAI_API_CONTRACT.md`

- Line 86: `"KVK-gegevens en inspectiehistorie"` → `"Bedrijfsinformatie en inspectiehistorie"`
- Line 158: Update tool call content from `kvk_number` to `postal_code`/`house_number`

#### 4. Root README
**File**: `README.md`

- Line 16: `"Geautomatiseerde bedrijfsverificatie (KVK) en inspectiegeschiedenis"` → `"Geautomatiseerde bedrijfsverificatie en inspectiegeschiedenis"`
- Line 77: `'Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854'` → `'Start inspectie bij Restaurant Bella Rosa, postcode 2511 AA nummer 123'`
- Line 166: `"inspection-history/   # KVK + inspectiedata"` → `"inspection-history/   # Bedrijfsverificatie + inspectiedata"`

#### 5. Server-OpenAI README
**File**: `server-openai/README.md`

- Line 82: `"Bedrijfsverificatie (KVK opzoeken)"` → `"Bedrijfsverificatie (adres opzoeken)"`
- Line 137: `"Start inspectie bij KVK 12345678"` → `"Start inspectie bij postcode 2511 AA nummer 123"`

#### 6. MCP Servers README
**File**: `mcp-servers/README.md`

- Line 11: Remove "KVK opzoeken en" from description
- Lines 180-186: Update tool parameter signatures from `kvk_number` to `postal_code, house_number`

#### 7. Inspection History README
**File**: `mcp-servers/inspection-history/README.md`

- Line 7: Remove KVK Lookup reference
- Lines 48-66: Update company headers from `(KVK: ...)` to `(Postcode: ... Nr: ...)`
- Line 124: Update validation description from KVK format to postal code format

#### 8. HAI Contract README
**File**: `docs/hai-contract/README.md`

- Line 140: Update demo prompt from KVK to postal code format

#### 9. Benchmark
**Files**: `benchmark/benchmark.py`, `benchmark/server_wrapper.py`

- `benchmark.py` line 152: Update prompt from KVK to postal code format
- `server_wrapper.py` line 74: Remove "KVK extracts" reference

### Success Criteria:

#### Automated Verification:
- [x] No "kvk" (case-insensitive) references in documentation: `grep -ri kvk DEMO_SCENARIOS.md README.md docs/ mcp-servers/README.md mcp-servers/inspection-history/README.md server-openai/README.md benchmark/`
- [x] Mock server has no syntax errors: `python -c "import ast; ast.parse(open('docs/hai-contract/mock_server.py').read())"`

#### Manual Verification:
- [ ] Demo scenarios read naturally with new address format
- [ ] Mock server simulations use consistent postal code + house number data
- [ ] All READMEs accurately describe the new address-based lookup

---

## Testing Strategy

### Unit Tests:
- Verify `make_lookup_key` normalizes correctly ("2511 AA" → "2511AA-123")
- Verify `validate_address` rejects invalid formats
- Verify `check_company_exists` returns correct data for known addresses
- Verify `get_inspection_history` returns correct inspections

### Integration Tests:
- Start MCP server, call tools via HTTP, verify responses
- Start full stack, verify agent handoff works with new prompts

### Manual Testing Steps:
1. Start the MCP inspection-history server
2. Call `check_company_exists` with `postal_code="2511 AA"`, `house_number="123"` — should return Restaurant Bella Rosa
3. Call `get_inspection_history` for each demo address — verify correct data
4. Call with invalid postal code (e.g., "ABCD EF") — should return validation error
5. Run full demo scenario: "Start inspectie bij Restaurant Bella Rosa, postcode 2511 AA nummer 123"
6. Verify agents route correctly and display proper address info

## References

- Research document: `thoughts/shared/research/2026-02-22-kvk-to-postal-code-migration.md`
- MCP server source: `mcp-servers/inspection-history/server.py`
- OpenAI agent definitions: `server-openai/src/agora_openai/core/agent_definitions.py`
- LangGraph agent definitions: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
- LangGraph tools: `server-langgraph/src/agora_langgraph/core/tools.py`
