---
date: 2026-01-28T12:00:00+01:00
researcher: Claude
git_commit: 02103b2
branch: feat/tool-names
repository: AGORA
topic: "Tool Display Names via AG-UI Protocol"
tags: [research, ag-ui-protocol, tool-naming, mcp, frontend]
status: complete
last_updated: 2026-01-28
last_updated_by: Claude
---

# Research: Tool Display Names via AG-UI Protocol

**Date**: 2026-01-28T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: 02103b2
**Branch**: feat/tool-names
**Repository**: AGORA

## Research Question

Can we define tool display names at the tool or agent level and pass them via the AG-UI protocol to replace the frontend dictionary lookup? This would make the package more robust for external users.

## Summary

**Yes, this is feasible and the protocol already has partial support!**

The AG-UI protocol already defines a `toolDescription` field in `TOOL_CALL_START` events, but it's currently unused by the backend orchestrators. The recommended approach is to:
1. Add a new `toolDisplayName` field to the protocol (or repurpose `toolDescription`)
2. Define display names at MCP tool level via FastMCP metadata or decorator
3. Pass display names through the orchestrator to AG-UI events
4. Update frontend to prefer protocol-provided names over dictionary lookup

## Detailed Findings

### Current Implementation: Frontend Dictionary Lookup

**Location**: `HAI/src/lib/utils/toolNames.ts:5-43`

The frontend maintains a hardcoded dictionary mapping internal tool names to Dutch translations:

```typescript
const TOOL_NAME_TRANSLATIONS: Record<string, string> = {
  // History agent tools
  check_company_exists: 'Controleren bedrijfsgegevens',
  get_inspection_history: 'Ophalen inspectiehistorie',
  // ... 30+ more mappings

  // Handoff tools
  transfer_to_reporting: 'Overdracht naar rapportage',
  // ...
};
```

The `formatToolName()` function (`toolNames.ts:49-60`) looks up translations with fallback:

```typescript
export function formatToolName(name: string): string {
  if (TOOL_NAME_TRANSLATIONS[name]) {
    return TOOL_NAME_TRANSLATIONS[name];
  }
  // Fallback: convert snake_case to Title Case
  return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}
```

**Problem**: External users of the package must modify `toolNames.ts` to add their own tool translations. This creates maintenance burden and isn't configurable.

### Existing Protocol Support: `toolDescription` Field

The AG-UI protocol already defines `toolDescription` in `TOOL_CALL_START` events:

**Protocol Definition** (`docs/hai-contract/asyncapi.yaml:579-586`):
```yaml
toolDescription:
  type: string
  nullable: true
  description: |
    Human-readable spoken description of the tool action.
    Used for TTS to announce what the agent is doing.
    Example: "Ik ga de regelgeving doorzoeken"
```

**Frontend Schema** (`HAI/src/types/schemas.ts:92-99`):
```typescript
export const ToolCallStartEventSchema = z.object({
  type: z.literal(EventType.TOOL_CALL_START),
  toolCallId: z.string(),
  toolCallName: z.string(),
  toolDescription: z.string().nullable().optional(),  // Already exists!
  parentMessageId: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});
```

**Current Usage**: Only the mock server uses `toolDescription` for handoff announcements to TTS. The real backend orchestrators don't pass it.

### Backend Gap: Not Passing `toolDescription`

**server-langgraph** (`server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:285-298`):
```python
async def send_tool_call_start(
    self,
    tool_call_id: str,
    tool_call_name: str,
    parent_message_id: str | None = None,  # No toolDescription parameter!
) -> None:
    event = ToolCallStartEvent(
        tool_call_id=tool_call_id,
        tool_call_name=tool_call_name,
        parent_message_id=parent_message_id,
        timestamp=_now_timestamp(),
    )
```

The method signature doesn't accept `tool_description`, so even though the protocol supports it, it's never sent.

### MCP Tool Definitions: No Display Name Metadata

**Current Pattern** (`mcp-servers/regulation-analysis/server.py:54-62`):
```python
@mcp.tool
async def search_regulations(query: str, filters: Optional[Dict[str, str]] = None) -> dict:
    """Search for relevant regulation articles using vector and hybrid search.

    Args:
        query: Natural language query describing what you're looking for
    """
```

FastMCP derives metadata from:
- `name`: Function name (e.g., `search_regulations`)
- `description`: Docstring first paragraph

**Gap**: No mechanism for defining a separate `displayName` or `title` property.

## Recommended Implementation

### Option A: Add `toolDisplayName` to Protocol (Recommended)

Add a dedicated field for display names, separate from `toolDescription` (which is for TTS):

**1. Update Protocol Schema** (`docs/hai-contract/asyncapi.yaml`):
```yaml
ToolCallStartEvent:
  properties:
    toolDisplayName:
      type: string
      nullable: true
      description: |
        Human-readable display name for the tool.
        Used for UI display. Falls back to toolCallName if not provided.
        Example: "Zoeken in regelgeving"
```

**2. Update Backend Handler** (`ag_ui_handler.py`):
```python
async def send_tool_call_start(
    self,
    tool_call_id: str,
    tool_call_name: str,
    tool_display_name: str | None = None,  # Add parameter
    parent_message_id: str | None = None,
) -> None:
    event = ToolCallStartEvent(
        tool_call_id=tool_call_id,
        tool_call_name=tool_call_name,
        tool_display_name=tool_display_name,  # Include in event
        parent_message_id=parent_message_id,
        timestamp=_now_timestamp(),
    )
```

**3. Define Display Names at MCP Level**:

Option 3a - FastMCP decorator extension:
```python
@mcp.tool(display_name="Zoeken in regelgeving")
async def search_regulations(query: str) -> dict:
    """Search for relevant regulation articles."""
```

Option 3b - Configuration file:
```yaml
# mcp-servers/regulation-analysis/tool_config.yaml
tools:
  search_regulations:
    display_name: "Zoeken in regelgeving"
  get_regulation_context:
    display_name: "Ophalen regelgeving context"
```

Option 3c - Agent-level mapping in orchestrator:
```python
TOOL_DISPLAY_NAMES = {
    "search_regulations": "Zoeken in regelgeving",
    "get_inspection_history": "Ophalen inspectiehistorie",
}
```

**4. Update Frontend** (`HAI/src/hooks/useWebSocket.ts:184-208`):
```typescript
case EventType.TOOL_CALL_START: {
  const toolEvent = event as ToolCallStartEvent;
  const displayName = toolEvent.toolDisplayName ?? formatToolName(toolEvent.toolCallName);
  addToolCall({
    id: toolEvent.toolCallId,
    toolName: toolEvent.toolCallName,
    displayName: displayName,  // Store protocol-provided name
    status: 'started',
  });
}
```

**5. Update Components** to use `displayName` instead of calling `formatToolName()`:
```typescript
// ToolCallCard.tsx
<span>{toolCall.displayName}</span>
```

### Option B: Repurpose `toolDescription` for Display Names

Simpler but conflates two concepts (TTS description vs display name).

### Option C: Custom Event Extension

Use `CUSTOM` event with `agora:tool_metadata`:
```typescript
{
  type: "CUSTOM",
  name: "agora:tool_metadata",
  value: {
    toolCallId: "...",
    displayName: "Zoeken in regelgeving",
    category: "regulation",
    icon: "search"
  }
}
```

More flexible but adds protocol complexity.

## Code References

- `HAI/src/lib/utils/toolNames.ts:5-60` - Current frontend dictionary and formatToolName()
- `HAI/src/hooks/useWebSocket.ts:184-208` - TOOL_CALL_START event handling
- `HAI/src/types/schemas.ts:92-99` - ToolCallStartEvent Zod schema
- `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py:285-298` - Backend event emission
- `server-openai/src/agora_openai/api/ag_ui_handler.py:278-291` - Backend event emission
- `docs/hai-contract/asyncapi.yaml:566-593` - Protocol specification
- `docs/hai-contract/schemas/messages.json:250-264` - JSON Schema
- `mcp-servers/regulation-analysis/server.py:54-62` - MCP tool definition example

## Architecture Insights

1. **Protocol-First Design**: The AG-UI protocol already anticipated display name needs via `toolDescription`, suggesting the design vision supported this from the start.

2. **Layered Architecture**: Display names could be defined at multiple levels:
   - MCP Server (tool definition)
   - Orchestrator (agent configuration)
   - Protocol (event payload)
   - Frontend (fallback dictionary)

3. **Backward Compatibility**: Any solution should maintain backward compatibility - frontend should fallback to dictionary/Title Case when no display name is provided.

## Implementation Recommendations

### Short-term (Quick Win)
1. Add `tool_display_name` parameter to `send_tool_call_start()` in both orchestrators
2. Update protocol schema to include `toolDisplayName`
3. Create orchestrator-level `TOOL_DISPLAY_NAMES` dict
4. Update frontend to prefer protocol name over dictionary

### Medium-term
1. Extend FastMCP with `display_name` decorator parameter
2. MCP servers define their own display names
3. Orchestrator fetches display names from MCP tool metadata

### Long-term
1. Support i18n - display names per locale
2. Configuration file for external users to customize names
3. Consider display names in MCP specification itself

## Open Questions

1. Should display names be locale-aware (i18n support)?
2. Should we extend FastMCP upstream or create a local wrapper?
3. Should `toolDescription` be repurposed or kept separate for TTS?
4. Should display names be required or optional in the protocol?
