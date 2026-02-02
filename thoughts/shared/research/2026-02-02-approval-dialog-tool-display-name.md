---
date: 2026-02-02T12:35:40+0000
researcher: Claude
git_commit: b71e33470d622b64ff1f95016440310b5e6832b3
branch: feat/displayname
repository: AGORA
topic: "Approval Dialog Missing Tool Display Name"
tags: [research, ag-ui-protocol, tool-naming, approval, hitl, frontend, mock-server, server-langgraph, server-openai]
status: complete
last_updated: 2026-02-02
last_updated_by: Claude
---

# Research: Approval Dialog Missing Tool Display Name

**Date**: 2026-02-02T12:35:40+0000
**Researcher**: Claude
**Git Commit**: b71e33470d622b64ff1f95016440310b5e6832b3
**Branch**: feat/displayname
**Repository**: AGORA

## Research Question

The approval dialog for report generation does not show a human-readable display name. Regular tool calls (`TOOL_CALL_START`) already support `toolDisplayName` since the `feat/tool-names` work (PR #22). The approval flow (`agora:tool_approval_request`) bypasses this entirely. What needs to change across the stack to give the approval request a display name, and how do we confirm success?

## Summary

The `agora:tool_approval_request` custom event payload has **no `toolDisplayName` field** anywhere in the stack: not in the protocol spec, not in the backend Pydantic models, not in the frontend Zod schema, and not in the approval dialog component. The raw `toolName` (e.g., `generate_final_report`) renders directly as the dialog title. Adding `toolDisplayName` requires changes to **12 files** across 5 layers: protocol docs, both backends, mock server, and frontend.

## Detailed Findings

### 1. The Gap: Approval vs. Tool Call Display Name Support

| Aspect | `TOOL_CALL_START` (regular tools) | `agora:tool_approval_request` |
|--------|-----------------------------------|-------------------------------|
| Display name field | `toolDisplayName` (optional) | **Missing** |
| Backend lookup | `get_tool_display_name()` called | Not called |
| Frontend fallback | `formatToolNameFallback()` | None - raw `toolName` rendered |
| UI rendering | Dutch display name or Title Case | Raw snake_case name |

### 2. Current Approval Flow Data Path

```
Orchestrator: _handle_tool_approval_flow()
  --> approval_logic.requires_human_approval() returns (True, reason, risk_level)
  --> protocol_handler.send_tool_approval_request(
        tool_name="generate_final_report",    # raw name
        tool_description="Tool call: generate_final_report",  # generic description
        ...
      )
  --> WebSocket JSON: { "toolName": "generate_final_report", ... }
  --> Frontend: parseToolApprovalRequest() --> addApproval({ toolName })
  --> ApprovalDialog.tsx:91 --> {approval.toolName}  // renders raw name
```

### 3. Files That Need Changes

#### Protocol Documentation (3 files)

**A. `docs/hai-contract/asyncapi.yaml`**
- Add `toolDisplayName` (optional, nullable string) to the `ToolApprovalRequestPayload` schema
- The schema is embedded in the custom event examples (around lines 345-358)

**B. `docs/hai-contract/schemas/messages.json`**
- Add `toolDisplayName` to `ToolApprovalRequestPayload` at lines 347-358
- Field should be optional (not in `required` array)

**C. `docs/hai-contract/HAI_API_CONTRACT.md`**
- Document the new field in the approval request section (around lines 976-993)
- Update the example payload to include `toolDisplayName`

#### Backend - server-langgraph (3 files)

**A. `server-langgraph/src/agora_langgraph/common/ag_ui_types.py:110-121`**
- Add `tool_display_name: str | None = Field(default=None, ...)` to `ToolApprovalRequestPayload`
- This serializes to `toolDisplayName` via the `to_camel` alias generator on `AgoraBaseModel`

**B. `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:351-374`**
- Add `tool_display_name: str | None = None` parameter to `send_tool_approval_request()`
- Pass it to `ToolApprovalRequestPayload(tool_display_name=tool_display_name, ...)`

**C. `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:90-96`**
- Import and call `get_tool_display_name(tool_name)` in `_handle_tool_approval_flow()`
- Pass result as `tool_display_name=get_tool_display_name(tool_name)` to `send_tool_approval_request()`
- Note: `get_tool_display_name` is already imported at line 26

#### Backend - server-openai (3 files)

**A. `server-openai/src/agora_openai/common/ag_ui_types.py:109-119`**
- Same change as server-langgraph: add `tool_display_name` field

**B. `server-openai/src/agora_openai/api/ag_ui_handler.py:343-366`**
- Same change: add parameter to `send_tool_approval_request()`

**C. `server-openai/src/agora_openai/pipelines/orchestrator.py:72-78`**
- Same change: pass display name from `get_tool_display_name()` lookup
- Note: `get_tool_display_name` is already imported at line 28

#### Mock Server (1 file)

**`docs/hai-contract/mock_server.py:1152-1177`**
- Add `"toolDisplayName": TOOL_DISPLAY_NAMES.get("generate_inspection_report")` to the approval request value dict
- The `TOOL_DISPLAY_NAMES` dict at line 110 already has `"generate_inspection_report": "Genereren inspectierapport"`

#### Frontend - HAI (4 files)

**A. `HAI/src/types/schemas.ts:159-166`**
- Add `toolDisplayName: z.string().nullable().optional()` to `ToolApprovalRequestPayloadSchema`

**B. `HAI/src/stores/useApprovalStore.ts:8-15`**
- Add `toolDisplayName?: string` to `ApprovalRequest` interface

**C. `HAI/src/hooks/useWebSocket.ts:279-286`**
- Pass `toolDisplayName: payload.toolDisplayName` in the `addApproval()` call
- Apply fallback: `toolDisplayName: payload.toolDisplayName ?? formatToolNameFallback(payload.toolName)`

**D. `HAI/src/components/approval/ApprovalDialog.tsx:91`**
- Change `{approval.toolName}` to `{approval.toolDisplayName ?? approval.toolName}`
- (The fallback is already applied at the WebSocket layer, but defensive rendering is good practice)

### 4. Existing Display Names for Approval-Triggering Tools

From `server-langgraph/src/agora_langgraph/core/tool_display_names.py`:

| Tool Name | Display Name | Approval Trigger |
|-----------|-------------|-----------------|
| `generate_final_report` | "Genereren eindrapport" | `ALWAYS_APPROVE_TOOLS` (critical) |
| `generate_inspection_report` | "Genereren inspectierapport" | Mock server only |

From `server-langgraph/src/agora_langgraph/core/approval_logic.py`, tools matching `HIGH_RISK_TOOL_PATTERNS` (`delete`, `remove`, `destroy`, `submit_final`, `publish_report`, etc.) would also trigger approval but don't currently exist in `TOOL_DISPLAY_NAMES`. Future tools matching these patterns should be added to the display name registry.

### 5. Mock Server Approval Flow (Current)

At `mock_server.py:1152-1177`, the approval request is sent as:
```python
"value": {
    "toolName": "generate_inspection_report",
    "toolDescription": "Genereert een officieel inspectierapport...",
    "parameters": { ... },
    "reasoning": "Inspecteur heeft om rapportgeneratie gevraagd...",
    "riskLevel": "high",
    "approvalId": approval_id,
    # Missing: "toolDisplayName": "Genereren inspectierapport"
}
```

The display name "Genereren inspectierapport" already exists in `TOOL_DISPLAY_NAMES` at line 110 but is not included in the approval event.

## How to Confirm Success

### 1. Mock Server Visual Test
```bash
# Terminal 1
cd docs/hai-contract && python mock_server.py

# Terminal 2
cd HAI && pnpm run dev
```
- Trigger report generation ("Genereer rapport")
- Verify the approval dialog title shows "Genereren inspectierapport" instead of "generate_inspection_report"

### 2. WebSocket Message Inspection
- Open browser DevTools > Network > WS
- Filter for `agora:tool_approval_request` messages
- Verify the `value` object contains `"toolDisplayName": "Genereren inspectierapport"`

### 3. Backend Unit Tests
```bash
# server-langgraph
cd server-langgraph && pytest tests/ -k "approval" -v

# server-openai
cd server-openai && pytest tests/ -k "approval" -v
```
- Add test case: when `send_tool_approval_request()` is called with a tool that has a display name, the serialized event includes `toolDisplayName`
- Add test case: when the tool has no display name, `toolDisplayName` is either absent or null

### 4. Frontend Unit Tests
```bash
cd HAI && pnpm run test
```
- Add test: `ToolApprovalRequestPayloadSchema` parses payloads with and without `toolDisplayName`
- Add test: `ApprovalDialog` renders `toolDisplayName` when present
- Add test: `ApprovalDialog` falls back to `toolName` when `toolDisplayName` is absent

### 5. Protocol Schema Validation
- Verify `asyncapi.yaml` validates: `npx @asyncapi/cli validate docs/hai-contract/asyncapi.yaml`
- Verify JSON schema is valid: `npx ajv-cli validate -s docs/hai-contract/schemas/messages.json`

### 6. Full Integration Test
```bash
# Start real backend
cd server-langgraph && python -m agora_langgraph.api.server

# Start frontend
cd HAI && pnpm run dev
```
- Trigger a tool that requires approval (e.g., `generate_final_report`)
- Verify the approval dialog shows "Genereren eindrapport"

## Code References

- `docs/hai-contract/mock_server.py:105-112` - Mock server TOOL_DISPLAY_NAMES dict
- `docs/hai-contract/mock_server.py:1152-1177` - Mock server approval request emission
- `server-langgraph/src/agora_langgraph/core/tool_display_names.py:7-51` - Backend display name registry
- `server-langgraph/src/agora_langgraph/core/approval_logic.py:7-68` - Approval decision logic
- `server-langgraph/src/agora_langgraph/common/ag_ui_types.py:110-121` - ToolApprovalRequestPayload model
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:351-374` - send_tool_approval_request()
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:67-107` - _handle_tool_approval_flow()
- `server-openai/src/agora_openai/common/ag_ui_types.py:109-119` - ToolApprovalRequestPayload model
- `server-openai/src/agora_openai/api/ag_ui_handler.py:343-366` - send_tool_approval_request()
- `server-openai/src/agora_openai/pipelines/orchestrator.py:53-89` - _handle_tool_approval_flow()
- `HAI/src/types/schemas.ts:159-166` - ToolApprovalRequestPayloadSchema
- `HAI/src/stores/useApprovalStore.ts:8-15` - ApprovalRequest interface
- `HAI/src/hooks/useWebSocket.ts:275-287` - handleCustomEvent approval handling
- `HAI/src/components/approval/ApprovalDialog.tsx:91` - Tool name rendering in dialog title

## Architecture Insights

1. **Asymmetric Display Name Support**: The `TOOL_CALL_START` path fully supports `toolDisplayName` (protocol, backend, frontend), but the approval path was not updated during the feat/tool-names work. This is likely an oversight since they are separate code paths.

2. **Shared Registry**: Both orchestrators already have `tool_display_names.py` with `get_tool_display_name()` imported in their orchestrator modules. The approval flow just needs to call this same function.

3. **Pydantic camelCase Aliasing**: Both backends use `AgoraBaseModel` with `alias_generator=to_camel`. Adding `tool_display_name` to the Pydantic model will automatically serialize as `toolDisplayName` in JSON -- no manual aliasing needed.

4. **Backward Compatibility**: Making `toolDisplayName` optional in all schemas ensures old clients/servers continue to work. The frontend should apply `formatToolNameFallback()` as defense-in-depth.

## Historical Context

- `thoughts/shared/research/2026-01-28-tool-display-names-protocol.md` - Prior research on adding `toolDisplayName` to `TOOL_CALL_START` events. This was implemented in PR #22 (feat/tool-names) but did not extend to the approval flow.

## Related Research

- `thoughts/shared/research/2026-01-28-tool-display-names-protocol.md` - Original tool display name protocol research

## Open Questions

1. Should the `tool_description` parameter in `send_tool_approval_request()` also be improved? Currently both orchestrators pass the generic string `f"Tool call: {tool_name}"` instead of a meaningful description.
2. Should `formatToolNameFallback()` be applied at the WebSocket handler level (centralized) or at the component level (defensive), or both? The current tool call path does both.
