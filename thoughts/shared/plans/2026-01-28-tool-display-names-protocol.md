# Tool Display Names via AG-UI Protocol - Implementation Plan

## Overview

Add a `toolDisplayName` field to the AG-UI protocol's `TOOL_CALL_START` event, enabling tool display names to be defined at the backend (orchestrator/MCP level) and passed to the frontend. This replaces the hardcoded `TOOL_NAME_TRANSLATIONS` dictionary in the frontend, making the package more robust and configurable for external users.

## Current State Analysis

### Frontend (HAI)
- `HAI/src/lib/utils/toolNames.ts:5-43` contains `TOOL_NAME_TRANSLATIONS` dict with 30+ Dutch translations
- `formatToolName()` function at lines 49-60 does lookup with Title Case fallback
- Used in 3 components: `LoadingIndicator.tsx:25`, `ToolCallCard.tsx:79`, `ToolCallReference.tsx:57`

### Protocol
- `TOOL_CALL_START` event has `toolCallName` (technical name) and `toolDescription` (TTS-only)
- No dedicated field for UI display names
- Defined in: `asyncapi.yaml:566-593`, `messages.json:250-264`, `schemas.ts:92-99`

### Backend
- Both orchestrators have identical `send_tool_call_start()` methods
- `server-langgraph/ag_ui_handler.py:285-298` and `server-openai/ag_ui_handler.py:278-291`
- No display name metadata passed through

### Mock Server
- `docs/hai-contract/mock_server.py:1300-1320` already accepts `tool_description` parameter
- Can be extended to support `tool_display_name`

## Desired End State

1. Protocol defines `toolDisplayName` as an optional field in `TOOL_CALL_START`
2. Backend orchestrators define display names and pass them through the protocol
3. Frontend uses protocol-provided display names, with Title Case fallback
4. `TOOL_NAME_TRANSLATIONS` dictionary is removed from frontend
5. Mock server includes display names for demo tools

### Verification
- All existing tools display correct Dutch names in UI
- Unknown tools fallback to Title Case formatting
- No frontend dictionary lookup needed
- External users can define their own display names at backend level

## What We're NOT Doing

- Adding i18n/locale support (future enhancement)
- Modifying MCP tool definitions (display names at orchestrator level for now)
- Adding `toolDisplayName` to other tool events (only TOOL_CALL_START)
- Changing TTS behavior (`toolDescription` remains separate)

## Implementation Approach

We'll update the system layer by layer: protocol schemas first, then backend handlers, then frontend consumption. The existing Dutch translations will be migrated to a backend dictionary.

---

## Phase 1: Protocol Schema Updates

### Overview
Add `toolDisplayName` field to all three schema definitions to maintain protocol consistency.

### Changes Required:

#### 1. AsyncAPI Specification
**File**: `docs/hai-contract/asyncapi.yaml`
**Location**: Lines 579-585 (after `toolDescription`)

Add after `toolDescription` property:

```yaml
        toolDisplayName:
          type: string
          nullable: true
          description: |
            Human-readable display name for UI rendering.
            Falls back to toolCallName if not provided.
            Example: "Zoeken in regelgeving"
```

#### 2. JSON Schema
**File**: `docs/hai-contract/schemas/messages.json`
**Location**: Lines 257-260 (after `toolDescription`)

Add after `toolDescription` property:

```json
        "toolDisplayName": {
          "type": ["string", "null"],
          "description": "Human-readable display name for UI rendering"
        },
```

#### 3. TypeScript Zod Schema
**File**: `HAI/src/types/schemas.ts`
**Location**: Line 96 (after `toolDescription`)

```typescript
export const ToolCallStartEventSchema = z.object({
  type: z.literal(EventType.TOOL_CALL_START),
  toolCallId: z.string(),
  toolCallName: z.string(),
  toolDescription: z.string().nullable().optional(),
  toolDisplayName: z.string().nullable().optional(),  // ADD THIS LINE
  parentMessageId: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
});
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Tests pass: `cd HAI && pnpm run test`

#### Manual Verification:
- [x] Schema files are consistent across all three definitions

---

## Phase 2: Backend Handler Updates

### Overview
Update `send_tool_call_start()` method in both orchestrators to accept and emit `toolDisplayName`.

### Changes Required:

#### 1. LangGraph AG-UI Handler
**File**: `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py`
**Location**: Lines 285-298

```python
async def send_tool_call_start(
    self,
    tool_call_id: str,
    tool_call_name: str,
    tool_display_name: str | None = None,  # ADD THIS PARAMETER
    parent_message_id: str | None = None,
) -> None:
    """Emit TOOL_CALL_START event."""
    event = ToolCallStartEvent(
        tool_call_id=tool_call_id,
        tool_call_name=tool_call_name,
        tool_display_name=tool_display_name,  # ADD THIS FIELD
        parent_message_id=parent_message_id,
        timestamp=_now_timestamp(),
    )
    await self._send_event(event)
```

#### 2. OpenAI AG-UI Handler
**File**: `server-openai/src/agora_openai/api/ag_ui_handler.py`
**Location**: Lines 278-291

Apply identical changes as LangGraph handler.

#### 3. Update AG-UI Types (if using Pydantic models)
**File**: `server-langgraph/src/agora_langgraph/common/ag_ui_types.py` (and server-openai equivalent)

If `ToolCallStartEvent` is defined locally, add:

```python
class ToolCallStartEvent(BaseModel):
    type: Literal["TOOL_CALL_START"] = "TOOL_CALL_START"
    tool_call_id: str
    tool_call_name: str
    tool_display_name: str | None = None  # ADD THIS FIELD
    tool_description: str | None = None
    parent_message_id: str | None = None
    timestamp: int | None = None
```

### Success Criteria:

#### Automated Verification:
- [x] Type check passes: `cd server-langgraph && mypy src/` (pre-existing errors unrelated to changes)
- [x] Type check passes: `cd server-openai && mypy src/` (pre-existing errors unrelated to changes)
- [x] Linting passes: `cd server-langgraph && ruff check src/agora_langgraph/api/ag_ui_handler.py`
- [x] Linting passes: `cd server-openai && ruff check src/agora_openai/api/ag_ui_handler.py`

---

## Phase 3: Backend Display Name Registry

### Overview
Create a centralized tool display name registry in each orchestrator, using the existing Dutch translations.

### Changes Required:

#### 1. LangGraph Tool Display Names
**File**: `server-langgraph/src/agora_langgraph/core/tool_display_names.py` (NEW FILE)

```python
"""Tool display name registry for AG-UI protocol."""

TOOL_DISPLAY_NAMES: dict[str, str] = {
    # History agent tools
    "check_company_exists": "Controleren bedrijfsgegevens",
    "get_inspection_history": "Ophalen inspectiehistorie",
    "get_company_violations": "Ophalen overtredingen",
    "check_repeat_violation": "Controleren herhaalde overtredingen",
    "get_follow_up_status": "Controleren follow-up status",
    "search_inspections_by_inspector": "Zoeken inspecties per inspecteur",
    "search_kvk": "Zoeken in het KVK",

    # Regulation agent tools
    "search_regulations": "Zoeken in regelgeving",
    "get_regulation_context": "Ophalen regelgeving context",
    "lookup_regulation_articles": "Opzoeken regelgeving artikelen",
    "analyze_document": "Analyseren document",
    "analyze_regulations": "Analyseren regelgeving",
    "get_database_stats": "Ophalen database statistieken",

    # Reporting agent tools
    "start_inspection_report": "Starten inspectie rapport",
    "extract_inspection_data": "Verwerken inspectiegegevens",
    "verify_inspection_data": "Verifiëren inspectiegegevens",
    "submit_verification_answers": "Verwerken antwoorden",
    "request_clarification": "Opvragen aanvullende informatie",
    "generate_final_report": "Genereren eindrapport",
    "get_report_status": "Ophalen rapport status",
    "generate_report": "Genereren rapportage",

    # General tools
    "search_documents": "Zoeken in documenten",
    "query_knowledge_base": "Zoeken in kennisbank",

    # Handoff tools
    "transfer_to_reporting": "Overdracht naar rapportage",
    "transfer_to_regulation": "Overdracht naar regelgeving",
    "transfer_to_history": "Overdracht naar inspectiehistorie",
    "transfer_to_general": "Overdracht naar algemeen",
    "transfer_to_triage": "Overdracht naar triage",
    "transfer_to_agent": "Overdracht naar specialist",

    # Mock server tools
    "get_company_info": "Ophalen bedrijfsgegevens",
    "generate_inspection_report": "Genereren inspectierapport",
}


def get_tool_display_name(tool_name: str) -> str | None:
    """Get display name for a tool, or None to use default formatting."""
    return TOOL_DISPLAY_NAMES.get(tool_name)
```

#### 2. OpenAI Tool Display Names
**File**: `server-openai/src/agora_openai/core/tool_display_names.py` (NEW FILE)

Create identical file to LangGraph version.

#### 3. Update LangGraph Orchestrator Call Site
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Location**: Lines 549-555

```python
from agora_langgraph.core.tool_display_names import get_tool_display_name

# ... in _stream_response() method, around line 549:

if protocol_handler.is_connected:
    log.info(f"[DEBUG] Sending TOOL_CALL_START: {tool_name} ({tool_run_id})")
    await protocol_handler.send_tool_call_start(
        tool_call_id=tool_run_id,
        tool_call_name=tool_name,
        tool_display_name=get_tool_display_name(tool_name),  # ADD THIS
        parent_message_id=message_id,
    )
```

#### 4. Update OpenAI Orchestrator Call Site
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Location**: Lines 422-426

```python
from agora_openai.core.tool_display_names import get_tool_display_name

# ... in tool_callback() function, around line 422:

await protocol_handler.send_tool_call_start(
    tool_call_id=tool_call_id,
    tool_call_name=tool_name,
    tool_display_name=get_tool_display_name(tool_name),  # ADD THIS
    parent_message_id=message_id,
)
```

### Success Criteria:

#### Automated Verification:
- [x] Type check passes: `cd server-langgraph && mypy src/` (pre-existing errors unrelated to changes)
- [x] Type check passes: `cd server-openai && mypy src/` (pre-existing errors unrelated to changes)
- [x] Linting passes for new files (ruff check on tool_display_names.py files)
- [ ] Tests pass: `cd server-langgraph && pytest`
- [ ] Tests pass: `cd server-openai && pytest`

---

## Phase 4: Mock Server Update

### Overview
Update the mock server to include `toolDisplayName` in tool call events.

### Changes Required:

#### 1. Add Display Name Dictionary
**File**: `docs/hai-contract/mock_server.py`
**Location**: After line 102 (after `DEMO_REGULATIONS`)

```python
# Tool display names for UI (Dutch)
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "get_company_info": "Ophalen bedrijfsgegevens",
    "get_inspection_history": "Ophalen inspectiehistorie",
    "search_regulations": "Zoeken in regelgeving",
    "check_repeat_violation": "Controleren herhaalde overtredingen",
    "generate_inspection_report": "Genereren inspectierapport",
    "transfer_to_agent": "Overdracht naar specialist",
}
```

#### 2. Update send_tool_call Function
**File**: `docs/hai-contract/mock_server.py`
**Location**: Lines 1300-1320

```python
async def send_tool_call(
    websocket,
    tool_call_id: str,
    tool_name: str,
    args: dict,
    result: str,
    tool_description: str | None = None,
    tool_display_name: str | None = None,  # ADD THIS PARAMETER
) -> None:
    """Send complete tool call sequence."""
    # Auto-lookup display name if not provided
    if tool_display_name is None:
        tool_display_name = TOOL_DISPLAY_NAMES.get(tool_name)

    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
            "toolDescription": tool_description,
            "toolDisplayName": tool_display_name,  # ADD THIS FIELD
            "parentMessageId": None,
            "timestamp": now_timestamp(),
        },
        tool_name,
    )
    # ... rest of function unchanged
```

### Success Criteria:

#### Automated Verification:
- [x] Mock server starts: `cd docs/hai-contract && python mock_server.py` (Ctrl+C after startup)
- [x] Python syntax valid: `python -m py_compile docs/hai-contract/mock_server.py`

---

## Phase 5: Frontend Updates

### Overview
Update frontend to consume `toolDisplayName` from protocol, store it, and use it for display.

### Changes Required:

#### 1. Update ToolCallInfo Interface
**File**: `HAI/src/types/index.ts`
**Location**: Lines 21-31

```typescript
export interface ToolCallInfo {
  id: string;
  toolName: string;
  displayName?: string;  // ADD THIS FIELD
  parameters?: Record<string, unknown>;
  result?: string;
  error?: string;
  status: 'started' | 'completed' | 'failed';
  parentMessageId?: string;
  agentId?: string;
  timestamp: Date;
}
```

#### 2. Update WebSocket Event Handler
**File**: `HAI/src/hooks/useWebSocket.ts`
**Location**: Lines 184-209

```typescript
case EventType.TOOL_CALL_START: {
  const toolEvent = event as ToolCallStartEvent;
  // Use protocol display name, fallback to Title Case formatting
  const displayName = toolEvent.toolDisplayName ?? formatToolNameFallback(toolEvent.toolCallName);
  addToolCall({
    id: toolEvent.toolCallId,
    toolName: toolEvent.toolCallName,
    displayName: displayName,  // ADD THIS
    status: 'started',
    parentMessageId: toolEvent.parentMessageId ?? undefined,
    agentId: currentAgentId.current,
  });
  addMessage({
    id: toolEvent.toolCallId,
    role: 'tool',
    content: displayName,  // USE displayName instead of toolCallName
    toolName: toolEvent.toolCallName,
    toolStatus: 'started',
    agentId: currentAgentId.current,
  });
  // TTS handling unchanged
  if (toolEvent.toolDescription) {
    emitTTSEvent({
      type: 'tool_description',
      content: toolEvent.toolDescription,
    });
  }
  break;
}
```

#### 3. Add Fallback Formatting Function
**File**: `HAI/src/lib/utils/toolNames.ts`

Replace entire file content with:

```typescript
/**
 * Format a tool name for display when no display name is provided.
 * Converts snake_case to Title Case.
 *
 * @example formatToolNameFallback('search_regulations') => 'Search Regulations'
 */
export function formatToolNameFallback(name: string): string {
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
```

#### 4. Update Components to Use displayName

**File**: `HAI/src/components/chat/LoadingIndicator.tsx`
**Location**: Line 25

```typescript
// BEFORE:
const toolDisplayName = formatToolName(activeToolCall.toolName);

// AFTER:
const toolDisplayName = activeToolCall.displayName ?? formatToolNameFallback(activeToolCall.toolName);
```

Update import at top of file:
```typescript
import { formatToolNameFallback } from '@/lib/utils';
```

**File**: `HAI/src/components/chat/ToolCallCard.tsx`
**Location**: Line 79

```typescript
// BEFORE:
<span className="text-sm font-medium">{formatToolName(toolName)}</span>

// AFTER (assuming toolCall prop has displayName):
<span className="text-sm font-medium">{toolCall.displayName ?? formatToolNameFallback(toolCall.toolName)}</span>
```

**File**: `HAI/src/components/chat/ToolCallReference.tsx`
**Location**: Line 57

```typescript
// BEFORE:
<span>{formatToolName(toolName)}</span>

// AFTER:
<span>{displayName ?? formatToolNameFallback(toolName)}</span>
```

#### 5. Update Utils Export
**File**: `HAI/src/lib/utils/index.ts`

```typescript
// BEFORE:
export { formatToolName } from './toolNames';

// AFTER:
export { formatToolNameFallback } from './toolNames';
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Tests pass: `cd HAI && pnpm run test`

#### Manual Verification:
- [ ] Start mock server and frontend, verify tools show Dutch display names
- [ ] Verify unknown tools fallback to Title Case formatting

**Implementation Note**: After completing this phase, pause for manual testing to confirm display names appear correctly in the UI before proceeding.

---

## Phase 6: Cleanup

### Overview
Remove the deprecated `TOOL_NAME_TRANSLATIONS` dictionary after confirming the protocol-based approach works.

### Changes Required:

#### 1. Verify No Remaining References
Search for any remaining usages of `formatToolName` (the old function) and update them.

#### 2. Final toolNames.ts Content
**File**: `HAI/src/lib/utils/toolNames.ts`

Confirm it only contains the fallback function (already done in Phase 5).

### Success Criteria:

#### Automated Verification:
- [x] No grep matches for `TOOL_NAME_TRANSLATIONS`: `grep -r "TOOL_NAME_TRANSLATIONS" HAI/src/`
- [x] No grep matches for old `formatToolName`: `grep -r "formatToolName\b" HAI/src/` (should only find `formatToolNameFallback`)
- [x] Full test suite passes: `cd HAI && pnpm run test`
- [x] Build succeeds: `cd HAI && pnpm run build`

#### Manual Verification:
- [ ] All tools display correctly with mock server
- [ ] All tools display correctly with real backend

---

## Testing Strategy

### Unit Tests
- Add test for `formatToolNameFallback()` function
- Update existing tool-related tests if they reference `formatToolName`

### Integration Tests
- Test TOOL_CALL_START event with `toolDisplayName` field
- Test fallback behavior when `toolDisplayName` is null/undefined

### Manual Testing Steps
1. Start mock server: `cd docs/hai-contract && python mock_server.py`
2. Start frontend: `cd HAI && pnpm run dev`
3. Open browser to http://localhost:3000
4. Start inspection with "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854"
5. Verify tool calls show Dutch display names (e.g., "Ophalen bedrijfsgegevens")
6. Verify handoff tools show Dutch names (e.g., "Overdracht naar specialist")

---

## Migration Notes

This is a non-breaking change:
- `toolDisplayName` is optional in the protocol
- Frontend gracefully falls back to Title Case formatting
- Existing clients without display names continue to work

---

## References

- Research document: `thoughts/shared/research/2026-01-28-tool-display-names-protocol.md`
- Current dictionary: `HAI/src/lib/utils/toolNames.ts:5-43`
- Protocol spec: `docs/hai-contract/asyncapi.yaml:566-593`
- Mock server: `docs/hai-contract/mock_server.py:1300-1320`
