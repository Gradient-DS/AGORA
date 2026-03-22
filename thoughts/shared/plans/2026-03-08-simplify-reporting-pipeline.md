# Simplify Reporting Pipeline: Single-Pass Extraction

## Overview

Eliminate the double-LLM interpretation in the reporting pipeline by moving extraction logic into the orchestrator's reporting agent (which already has the full conversation context) and reducing the MCP reporting server to a single "render" tool. This removes the second GPT-4o call in the MCP server, merges extraction + validation into one LLM pass, and makes verification questions context-aware.

## Current State Analysis

The reporting pipeline currently works like this:
```
Orchestrator LLM (has full conversation)
  → constructs inspection_summary text (lossy, 5000 char limit)
    → MCP server calls GPT-4o to extract structured data (SECOND LLM call)
      → generates verification questions (without conversation context)
        → 3 separate MCP tool calls with session state between them
```

### Problems:
1. **Double LLM interpretation**: Orchestrator LLM summarizes conversation → MCP server LLM re-extracts from that summary
2. **Information loss**: `inspection_summary` is capped at 5000 chars, excludes tool results, and is subject to LLM summarization quality
3. **Context-blind questions**: Verification questions are generated from extraction output, not from the conversation — leading to questions about things already discussed
4. **Unnecessary complexity**: 3 MCP tools with session state, answer parsing, and fallback question generation

### Key Discoveries:
- Only `extract_inspection_data` makes an LLM call; the other two tools are purely programmatic (`server.py:34-173`)
- `ConversationExtractor`, `Verifier`, `ResponseParser` are only used in `server.py` — no other consumers
- No tests exist for the reporting MCP server
- `MAPPING_SYSTEM_PROMPT`, `VERIFICATION_PROMPT`, and several methods (`analyze_context`, `parse_verification_responses`, `generate_verification_questions`) are defined but never called
- The `FieldMapper`, `PDFGenerator`, `JSONGenerator` are purely programmatic and work well
- Image forwarding already bypasses MCP (direct HTTP POST)
- LangGraph injects `session_id`, `inspector_name`, `inspector_email` into agent instructions (`agents.py:271-294`); server-openai relies on LLM memory

## Desired End State

```
Reporting Agent LLM (has full conversation)
  → single pass: extracts structured HAP data + identifies 1-3 missing fields
    → asks inspector about genuinely missing info (context-aware)
      → merges answers into structured data
        → calls single MCP tool: generate_report(report_data) → PDF + JSON
```

### Verification:
- The reporting MCP server has zero LLM dependencies (no OpenAI API key needed)
- Only 1 MCP tool exists: `generate_report`
- The agent extracts data from the full conversation in its instructions
- Verification questions reference information NOT already in the conversation
- Both orchestrators produce identical reports
- PDF output matches current format

## What We're NOT Doing

- Changing the `HAPReport` Pydantic model or enums
- Changing the PDF layout/styling
- Changing the image forwarding mechanism
- Changing the email service
- Changing the `FileStorage` layer
- Modifying the handoff pattern (general-agent → reporting-agent)
- Adding tests (separate task)

## Implementation Approach

The reporting agent's LLM already has the full conversation. Instead of lossy summarization → second LLM extraction, we embed the HAP JSON schema in the agent's instructions and have it extract directly. The MCP server becomes a stateless renderer: receives structured data, maps to HAPReport, generates PDF.

---

## Phase 1: Simplify MCP Server — Single `generate_report` Tool

### Overview
Replace the 3 MCP tools with 1 `generate_report` tool. Remove all LLM-dependent code from the MCP server.

### Changes Required:

#### 1. Rewrite `server.py`
**File**: `mcp-servers/reporting/server.py`
**Changes**: Replace `extract_inspection_data`, `submit_verification_answers`, `generate_final_report` with a single `generate_report` tool. Remove `ConversationExtractor`, `Verifier`, `ResponseParser` imports and singletons. Simplify `SessionManager` usage to single-call flow.

The new tool signature:

```python
@mcp.tool()
async def generate_report(
    session_id: str,
    report_data: str,  # JSON string of extracted inspection data
    company_name: str | None = None,
    company_address: str | None = None,
    inspector_name: str | None = None,
    inspector_email: str | None = None,
    send_email: bool = True,
) -> dict:
    """Generate a HAP inspection report from structured inspection data.

    Receives pre-extracted structured data from the reporting agent and generates
    the final HAP report as JSON + PDF.

    Args:
        session_id: Unique session identifier
        report_data: JSON string containing the structured inspection data matching
                     the HAP schema (hygiene_general, pest_control, food_safety,
                     allergen_info, additional_info sections)
        company_name: Company name (overrides value in report_data if provided)
        company_address: Company address (overrides value in report_data if provided)
        inspector_name: Inspector name for report metadata
        inspector_email: Inspector email for report delivery
        send_email: Whether to email the report (default True)

    Returns:
        Dict with report_id, download URLs, summary, and status
    """
```

The implementation flow:
1. Parse `report_data` JSON string into dict
2. Inject `company_name`, `company_address`, `inspector_name`, `inspector_email` as top-level keys if provided and not already present
3. Create session via `SessionManager` (generates report ID)
4. Save extracted data to draft (for audit trail)
5. Map to `HAPReport` via `FieldMapper`
6. Generate JSON + PDF via generators
7. Finalize and optionally email
8. Return download URLs + summary

#### 2. Remove LLM-dependent modules
**Delete these files entirely:**
- `mcp-servers/reporting/analyzers/conversation_extractor.py`
- `mcp-servers/reporting/analyzers/prompts.py`
- `mcp-servers/reporting/verification/verifier.py`
- `mcp-servers/reporting/verification/response_parser.py`

**Update these files:**
- `mcp-servers/reporting/analyzers/__init__.py` — remove `ConversationExtractor` export, keep `FieldMapper`
- `mcp-servers/reporting/verification/__init__.py` — remove all exports (or delete directory if empty)

#### 3. Simplify SessionManager
**File**: `mcp-servers/reporting/storage/session_manager.py`
**Changes**: Remove methods only used by the 3-tool flow: `add_verification_questions`, `add_verification_answers`, `store_conversation`. The single-tool flow only needs: `create_session`, `update_extracted_data`, `finalize_report`, `get_session`.

#### 4. Remove OpenAI dependency from MCP server
**File**: `mcp-servers/reporting/requirements.txt` (or `pyproject.toml`)
**Changes**: Remove `openai` from dependencies. The MCP server no longer needs an OpenAI API key.

### Success Criteria:

#### Automated Verification:
- [x] MCP server starts without `OPENAI_API_KEY` set
- [ ] `curl http://localhost:5003/health` returns 200
- [ ] `curl http://localhost:5003/mcp/tools | jq` shows only `generate_report` tool
- [ ] Calling `generate_report` with valid JSON data produces a PDF

#### Manual Verification:
- [ ] Generated PDF matches current format and styling

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Update Reporting Agent Instructions (Both Orchestrators)

### Overview
Rewrite the reporting agent instructions to include the HAP JSON schema and a simplified 2-step workflow: extract + ask questions → call `generate_report`.

### Changes Required:

#### 1. Update server-openai agent definition
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`
**Changes**: Replace the reporting-agent `instructions` (lines 134-191) with new instructions.

New instructions structure:

```python
"instructions": (
    "You are an NVWA inspection reporting expert specialized in HAP reports.\n\n"
    "🇳🇱 LANGUAGE: ALL responses MUST be in Dutch.\n\n"
    "YOUR TASK:\n"
    "Extract structured inspection data from the conversation and generate a HAP report.\n"
    "You have access to the FULL conversation — use ALL information including tool results "
    "(regulation analysis, inspection history) to build a complete picture.\n\n"

    "⚠️ 2-STEP WORKFLOW:\n\n"

    "STEP 1 — EXTRACT & VERIFY:\n"
    "Analyze the entire conversation and extract a JSON object matching this schema:\n"
    "```json\n"
    "{\n"
    '  "company_name": "string or null",\n'
    '  "company_address": "string or null",\n'
    '  "inspection_type": "Reguliere inspectie|Herinspectie|Klachtinspectie|Spoedcontrole|Voedselvergiftiging",\n'
    '  "hygiene_general": {\n'
    '    "compliant": "Ja|Nee|Niet beoordeeld|N.v.t.",\n'
    '    "violations": [{"type": "violation type", "severity": "Ernstige overtreding|Overtreding|Geringe overtreding", "description": "...", "location": "..."}],\n'
    '    "observations": "string",\n'
    '    "washing_facilities": "Ja|Nee|Niet beoordeeld|N.v.t.",\n'
    '    "ventilation": "...", "sanitary_facilities": "...", "lighting": "...",\n'
    '    "drainage": "...", "toilets": "...", "floor_condition": "...",\n'
    '    "ceiling_condition": "...", "wall_condition": "...",\n'
    '    "equipment_cleanliness": "...", "equipment_maintenance": "..."\n'
    '  },\n'
    '  "pest_control": {\n'
    '    "pest_prevention_compliant": "Ja|Nee|Niet beoordeeld|N.v.t.",\n'
    '    "pest_control_compliant": "Ja|Nee|Niet beoordeeld|N.v.t.",\n'
    '    "pest_present": true|false,\n'
    '    "pest_types": ["Muis","Rat","Vliegen","Kakkerlakken","Overige"],\n'
    '    "pest_severity": "Minimale overlast|Matige overlast|Veel overlast|Afwezig",\n'
    '    "violations": [], "observations": "string"\n'
    '  },\n'
    '  "food_safety": {\n'
    '    "storage_compliant": "Ja|Nee|Niet beoordeeld|N.v.t.",\n'
    '    "preparation_cooling_compliant": "...",\n'
    '    "presentation_compliant": "...",\n'
    '    "violations": [],\n'
    '    "temperature_violations": [{"product": "...", "temp": 12.5, "location": "..."}],\n'
    '    "unsafe_products": ["product names"],\n'
    '    "observations": "string"\n'
    '  },\n'
    '  "allergen_info": {\n'
    '    "compliant": "Ja|Nee|Niet beoordeeld|N.v.t.",\n'
    '    "information_method": "written|oral|absent",\n'
    '    "violations": [], "observations": "string"\n'
    '  },\n'
    '  "additional_info": {\n'
    '    "inspection_location_description": "string",\n'
    '    "hygiene_code_used": "Hygiënecode voor de Horeca|...|Geen",\n'
    '    "mobile_temporary_location": false,\n'
    '    "repeat_violation": false,\n'
    '    "repeat_violation_details": "string",\n'
    '    "inspector_notes": "string"\n'
    '  }\n'
    '}\n'
    "```\n\n"

    "After extracting, check if any CRITICAL information is missing:\n"
    "- Company name or address\n"
    "- Overall hygiene compliance status\n"
    "- Violation severity (if violations were mentioned but severity is unclear)\n"
    "- Any topic the inspector discussed but you couldn't determine the conclusion\n\n"
    "If 1-3 fields are genuinely missing (NOT already discussed in the conversation), "
    "ask the inspector in a natural, conversational way in Dutch. "
    "Do NOT ask about information that was already clearly stated.\n"
    "If the inspector says 'sla over' or 'skip', proceed without the missing info.\n\n"

    "STEP 2 — GENERATE REPORT:\n"
    "Call generate_report with:\n"
    "- session_id: current session ID\n"
    "- report_data: the JSON string of your extracted data\n"
    "- company_name, company_address, inspector_name, inspector_email\n"
    "This tool requires inspector approval via a modal dialog.\n"
    "Your spoken response should be: \"Er is goedkeuring nodig voor het genereren van het rapport\"\n"
    "After approval and completion, respond with a summary and download links.\n\n"

    "SEVERITY GUIDELINES:\n"
    "- Ernstige overtreding: Direct food safety risk, pest contamination, unsafe products\n"
    "- Overtreding: Hygiene deficiencies, inadequate facilities, temperature deviations\n"
    "- Geringe overtreding: Minor cleanliness issues, documentation gaps\n\n"

    "VIOLATION TYPES (use exact strings):\n"
    "bedrijfsruimte(s) niet schoon, bedrijfsruimte(s) niet goed onderhouden, "
    "bedrijfsruimte(s) bouwkundig onvoldoende, apparatuur niet schoon, "
    "apparatuur onderhoud/constructie, besmetting van levensmiddelen, "
    "(productbeoordeling) temperatuur gekoeld onverpakt, "
    "(productbeoordeling) temperatuur gekoeld voorverpakt, "
    "(productbeoordeling) temperatuur warm, "
    "(productbeoordeling) onveilig product (ongeschikt), "
    "(productbeoordeling) onveilig product (schadelijk), "
    "(productbeoordeling) houdbaarheid uiterste consumptiedatum (TGT), "
    "Ongediertebestrijding, Constructie, etc. (ongediertewering), "
    "Ramen / andere openingen zonder hor, Huisdieren in bedrijfsruimten, "
    "Er wordt geen allergeneninformatie aangeboden, "
    "allergeneninformatie niet duidelijk, "
    "geen (dekkende) hygiënecode geen vvp, overig\n\n"

    "ALWAYS:\n"
    "- Use the FULL conversation context (including tool results from other agents)\n"
    "- Only ask about genuinely missing critical information\n"
    "- Be concise and professional in Dutch\n"
    "- Flag serious violations: 'ERNSTIGE OVERTREDING'\n"
),
```

#### 2. Update server-langgraph agent definition
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
**Changes**: Same instruction update as server-openai, with the LangGraph-specific additions:
- Verification uses `request_clarification` tool (for `interrupt()` flow)
- Include "COMPLETING YOUR TASK" section
- Keep `handoffs: []`

The verification section should read:
```
"If 1-3 fields are genuinely missing, call request_clarification with your questions "
"in Dutch to pause and wait for the inspector's input.\n"
```

#### 3. Update LangGraph context injection
**File**: `server-langgraph/src/agora_langgraph/core/agents.py` (lines 271-294)
**Changes**: Update the injected instruction to reference `generate_report` instead of `start_inspection_report`:

```python
# Change:
"When calling start_inspection_report, include inspector_name and inspector_email"
# To:
"When calling generate_report, include inspector_name and inspector_email"
```

### Success Criteria:

#### Automated Verification:
- [x] Both servers start without errors
- [ ] `ruff check` passes on both server packages
- [ ] `mypy src/` passes on both server packages

#### Manual Verification:
- [ ] Triggering "genereer rapport" produces a report using the new single-tool flow
- [ ] Verification questions are relevant and don't duplicate already-discussed info
- [ ] Report content matches what was discussed in the conversation
- [ ] Both orchestrators produce equivalent results

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Cleanup

### Overview
Remove dead code, unused dependencies, and update the MCP tool mapping references.

### Changes Required:

#### 1. Delete unused files
- `mcp-servers/reporting/analyzers/conversation_extractor.py`
- `mcp-servers/reporting/analyzers/prompts.py`
- `mcp-servers/reporting/verification/verifier.py`
- `mcp-servers/reporting/verification/response_parser.py`

#### 2. Update `__init__.py` files
**File**: `mcp-servers/reporting/analyzers/__init__.py`
**Changes**: Remove `ConversationExtractor` import, keep `FieldMapper`

**File**: `mcp-servers/reporting/verification/__init__.py`
**Changes**: Remove all exports. If this leaves the file empty, delete the directory entirely (keep `__init__.py` empty or remove it).

#### 3. Remove OpenAI dependency
**File**: `mcp-servers/reporting/Dockerfile` or `requirements.txt` or `pyproject.toml`
**Changes**: Remove `openai` from dependencies. Verify the server starts without it.

#### 4. Clean up SessionManager
**File**: `mcp-servers/reporting/storage/session_manager.py`
**Changes**: Remove methods that are no longer called:
- `add_verification_questions` (was used by `extract_inspection_data`)
- `add_verification_answers` (was used by `submit_verification_answers`)
- `store_conversation` (was used by `extract_inspection_data`)

#### 5. Update server info resource
**File**: `mcp-servers/reporting/server.py`
**Changes**: Update the `server://info` resource (lines 518-547) to reflect the new single-tool architecture.

### Success Criteria:

#### Automated Verification:
- [x] MCP server starts cleanly with no import errors
- [ ] `curl http://localhost:5003/health` returns 200
- [ ] No Python import warnings or missing module errors in logs
- [ ] Docker build succeeds for MCP server

#### Manual Verification:
- [ ] End-to-end flow works: conversation → report generation → PDF download

---

## Testing Strategy

### Manual Testing Steps:
1. Start a conversation with a simulated inspection scenario
2. Discuss hygiene violations, pest issues, food safety concerns
3. Use regulation-agent and history-agent during the conversation
4. Trigger "genereer rapport"
5. Verify the agent asks 1-3 relevant questions about genuinely missing info
6. Answer the questions
7. Approve report generation
8. Download and verify PDF content matches the conversation
9. Repeat with both server-openai and server-langgraph

### Edge Cases:
- Conversation with no violations (clean inspection)
- Conversation with only 1 section discussed (e.g., only hygiene)
- Inspector skips verification ("sla over")
- Very short conversation (minimal info)
- Conversation where regulation-agent provided relevant context that should appear in the report

## Performance Considerations

- **Latency improvement**: Eliminating the second GPT-4o call in the MCP server should reduce report generation time by ~5-15 seconds
- **Cost reduction**: One fewer LLM call per report
- **MCP server simplification**: No OpenAI API key needed, no LLM timeout concerns (the 120s timeout was set specifically for the extraction call)

## Migration Notes

- No data migration needed — the `FileStorage` format doesn't change structurally
- Existing sessions in progress will not be compatible (they relied on the 3-tool state machine). This is acceptable since sessions are ephemeral.
- The `OPENAI_API_KEY` / `MCP_OPENAI_API_KEY` environment variables are no longer needed for the reporting MCP server, but won't cause errors if still set

## References

- Research: `thoughts/shared/research/2026-03-08-reporting-agent-overview.md`
- MCP reporting server: `mcp-servers/reporting/server.py`
- server-openai agent definitions: `server-openai/src/agora_openai/core/agent_definitions.py:131-197`
- server-langgraph agent definitions: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:132-190`
- LangGraph context injection: `server-langgraph/src/agora_langgraph/core/agents.py:271-294`
- HAP schema: `mcp-servers/reporting/models/hap_schema.py`
- PDF generator: `mcp-servers/reporting/generators/pdf_generator.py`
- Field mapper: `mcp-servers/reporting/analyzers/field_mapper.py`
