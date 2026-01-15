---
date: 2025-01-15T16:30:00+01:00
researcher: Claude
git_commit: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
branch: main
repository: AGORA
topic: "Settings Agent Design for AGORA"
tags: [research, codebase, agent-design, settings, langgraph]
status: complete
last_updated: 2025-01-15
last_updated_by: Claude
---

# Research: Settings Agent Design for AGORA

**Date**: 2025-01-15T16:30:00+01:00
**Researcher**: Claude
**Git Commit**: caf9d75b63c0e1f9de7ae56054b0fa84538d24cd
**Branch**: main
**Repository**: AGORA

## Research Question

Can we design a "settings agent" that is available like the existing four agents (general, regulation, reporting, history) and can be used to change AGORA settings? Initially, the only setting would be the dictate/summarize spoken_text_type preference. The agent would have a tool to update this setting.

## Summary

**Yes, a settings agent can be designed that fits naturally into the AGORA architecture.** The current system already has:

1. User preferences stored in SQLite with a `spoken_text_type` field
2. REST API endpoints for reading/updating preferences
3. The orchestrator already reads `spoken_text_type` to control dual generation

A settings agent would be **the first agent without an MCP server** - it would instead call internal API endpoints or directly use the `UserManager` adapter. This is architecturally valid since the `general-agent` already operates without MCP tools.

## Detailed Findings

### Current Agent Architecture Pattern

Each agent in AGORA follows a consistent pattern defined in `agent_definitions.py`:

```python
class AgentConfig(TypedDict):
    id: str                   # e.g., "settings-agent"
    name: str                 # Display name
    instructions: str         # System prompt
    model: str | None         # None = use default from settings
    tools: list[str]          # Tool names (handoff tools)
    temperature: float        # LLM temperature
    handoffs: list[str]       # Agents this can transfer to
    mcp_server: str | None    # MCP server name or None
```

**Key insight**: The `general-agent` already has `mcp_server: None` and only uses handoff tools. A settings agent can follow the same pattern with a custom tool instead.

### Settings Infrastructure Already Exists

The system already has comprehensive settings infrastructure:

| Component | Location | Purpose |
|-----------|----------|---------|
| `UserPreferences` type | `HAI/src/types/user.ts:5-11` | TypeScript interface including `spoken_text_type` |
| `UpdatePreferencesRequest` | `server.py:308-317` | Pydantic model for validation |
| `GET /users/me/preferences` | `server.py:318-337` | Fetch current preferences |
| `PUT /users/me/preferences` | `server.py:340-407` | Update preferences |
| `UserManager.update_preferences()` | `user_manager.py:246-260` | SQLite persistence |

The `spoken_text_type` field supports two values:
- `"summarize"` (default) - AI generates TTS-optimized summary
- `"dictate"` - Verbatim duplication of written response

### How Settings Affect the Pipeline

The orchestrator reads `spoken_text_type` at runtime (`orchestrator.py:337-346`):

```python
spoken_mode = "summarize"  # default
if self.user_manager:
    user = await self.user_manager.get_user(user_id)
    if user:
        prefs = user.get("preferences", {})
        spoken_mode = prefs.get("spoken_text_type", "summarize")
```

This controls whether the pipeline runs parallel LLM calls (summarize) or duplicates content (dictate).

### Proposed Settings Agent Design

#### 1. Agent Configuration

Add to `AGENT_CONFIGS` in `agent_definitions.py`:

```python
{
    "id": "settings-agent",
    "name": "Instellingen Assistent",
    "instructions": (
        "Je bent een NVWA assistent voor systeeminstellingen.\n\n"
        "🇳🇱 LANGUAGE REQUIREMENT:\n"
        "- ALL responses MUST be in Dutch (Nederlands)\n\n"
        "YOUR FOCUS:\n"
        "Je helpt inspecteurs hun persoonlijke voorkeuren aan te passen.\n\n"
        "AVAILABLE SETTINGS:\n"
        "1. Spraakweergave (spoken_text_type):\n"
        "   - 'dictate': Volledige tekst wordt voorgelezen\n"
        "   - 'summarize': AI vat antwoorden samen voor spraak\n\n"
        "WORKFLOW:\n"
        "1. When inspector asks to change settings:\n"
        "   - Explain current setting value\n"
        "   - Confirm the change they want\n"
        "   - Call update_user_settings tool\n"
        "   - Confirm the change was successful\n\n"
        "TRIGGER PHRASES:\n"
        "- 'wijzig instellingen', 'pas instellingen aan'\n"
        "- 'schakel naar dicteer', 'schakel naar samenvatten'\n"
        "- 'toon mijn instellingen'\n\n"
        "ALWAYS:\n"
        "- Be conversational and helpful\n"
        "- Explain what each setting does before changing\n"
        "- Confirm changes were applied\n"
    ),
    "model": None,
    "tools": ["update_user_settings", "transfer_to_general"],
    "temperature": 0.5,
    "handoffs": ["general-agent"],
    "mcp_server": None,  # No MCP server - uses internal tool
}
```

#### 2. Tool Implementation Options

**Option A: Direct UserManager Access (Recommended)**

Create a tool in `tools.py` that uses the `UserManager` adapter directly:

```python
from langchain_core.tools import tool

@tool
async def update_user_settings(
    spoken_text_type: str | None = None,
) -> str:
    """Update user settings.

    Args:
        spoken_text_type: Set to 'dictate' for full text reading
                         or 'summarize' for AI-generated summaries

    Returns:
        Confirmation message with updated settings
    """
    # Implementation would need access to user_id from state
    # and UserManager instance
    ...
```

**Challenge**: The tool needs access to `user_id` (from conversation state) and the `UserManager` instance. This requires either:
- Passing these through tool context
- Creating a closure at graph build time
- Using a module-level reference

**Option B: Internal HTTP Call**

The tool could call the existing REST API endpoint:

```python
@tool
async def update_user_settings(
    user_id: str,
    spoken_text_type: str | None = None,
) -> str:
    """Update user settings via internal API."""
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"http://localhost:8000/users/me/preferences",
            params={"user_id": user_id},
            json={"spoken_text_type": spoken_text_type},
        )
    ...
```

This is simpler but adds unnecessary HTTP overhead for internal operations.

#### 3. Graph Wiring Changes

In `graph.py`, add the settings agent node:

```python
# In build_agent_graph():

# Add settings agent node
graph.add_node("settings-agent", settings_agent)

# Update routing after tools
graph.add_conditional_edges(
    "tools",
    route_after_tools,
    {
        "general-agent": "general-agent",
        "regulation-agent": "regulation-agent",
        "reporting-agent": "reporting-agent",
        "history-agent": "history-agent",
        "settings-agent": "settings-agent",  # NEW
    },
)
```

#### 4. Handoff Integration

Update `general-agent` to include handoff to settings:

```python
# In agent_definitions.py, general-agent config:
"tools": [
    "transfer_to_history",
    "transfer_to_regulation",
    "transfer_to_reporting",
    "transfer_to_settings",  # NEW
],
"handoffs": ["history-agent", "regulation-agent", "reporting-agent", "settings-agent"],
```

Add handoff detection in `graph.py`:

```python
def detect_handoff_target(tool_name: str) -> str | None:
    tool_lower = tool_name.lower()
    if "transfer_to_settings" in tool_lower:
        return "settings-agent"
    # ... existing handoffs
```

#### 5. Spoken Text Prompt

Add to `SPOKEN_AGENT_PROMPTS` in `agent_definitions.py`:

```python
"settings-agent": (
    "Je bent een instellingen-assistent die KORTE bevestigingen geeft.\n\n"
    "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
    "- Maximaal 1-2 zinnen\n"
    "- Bevestig alleen de belangrijkste wijziging\n"
    "- Geen technische details\n\n"
    "VOORBEELD:\n"
    "Context: Gebruiker wijzigt naar dicteer modus\n"
    "Antwoord: 'Ik heb de spraakweergave aangepast naar dicteer modus. "
    "Alle tekst wordt nu volledig voorgelezen.'"
),
```

### Architecture Fit Analysis

The settings agent fits well into the existing architecture:

| Aspect | Fit | Notes |
|--------|-----|-------|
| Agent pattern | ✅ | Same `AgentConfig` structure as existing agents |
| Graph structure | ✅ | Added as another node with conditional edges |
| Handoff pattern | ✅ | Uses same `transfer_to_*` tool convention |
| MCP integration | ⚠️ | First agent without MCP, but `general-agent` precedent exists |
| Tool execution | ⚠️ | Needs access to conversation state for `user_id` |
| Frontend display | ✅ | Will appear in agent list automatically |

### Implementation Considerations

1. **State Access for Tools**: The biggest challenge is passing `user_id` to the settings tool. Options:
   - Add `user_id` to `AgentState` and access via tool context
   - Create tool closures at graph build time with bound `UserManager`
   - Pass `user_id` as explicit tool parameter (requires agent to extract from conversation)

2. **Immediate Effect**: Settings changes take effect on the *next* message since `spoken_text_type` is read at the start of `process_message()`. The agent should inform the user of this.

3. **Frontend Sync**: After settings change, frontend should refetch preferences. Could emit a custom AG-UI event `agora:settings_changed` to trigger refetch.

4. **Validation**: The existing `PUT /users/me/preferences` endpoint already validates `spoken_text_type` values. The tool should leverage this.

## Code References

- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:19-245` - Agent configurations
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:250-320` - Spoken prompts
- `server-langgraph/src/agora_langgraph/core/graph.py:123-202` - Graph construction
- `server-langgraph/src/agora_langgraph/core/tools.py:71-115` - Tool assembly
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:337-346` - Spoken mode retrieval
- `server-langgraph/src/agora_langgraph/api/server.py:340-407` - Preferences API endpoint
- `server-langgraph/src/agora_langgraph/adapters/user_manager.py:246-260` - Preferences persistence

## Architecture Insights

### Patterns Discovered

1. **Agent-as-Node Pattern**: Each agent is a graph node with tools bound at build time
2. **Handoff-via-Tool Pattern**: Agent transfers use tool calls, not direct edges
3. **Scoped Tool Access**: Agents only get tools relevant to their domain
4. **Module-Level Caching**: Tools and LLMs cached for efficiency

### Design Recommendations

1. **Keep settings agent simple**: Only one tool initially (`update_user_settings`)
2. **Consider future extensibility**: The settings agent could later manage:
   - Theme preferences
   - Notification settings
   - Default agent selection
   - Language preferences
3. **Add frontend notification**: Emit custom event when settings change for UI sync
4. **Document behavior**: Make clear that changes take effect on next message

## Open Questions

1. **Tool context access**: What's the cleanest way to pass `user_id` and `UserManager` to the settings tool?
2. **Real-time effect**: Should settings changes affect the current conversation turn or only subsequent ones?
3. **Frontend UX**: Should the settings agent update be shown in the UI immediately, or wait for explicit refresh?
4. **Validation errors**: How should the agent communicate invalid setting values to the user?
