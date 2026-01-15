---
date: 2026-01-15T16:30:00+01:00
researcher: Claude
git_commit: 3a26a07069b256101c1f2f9cd715b33c499e9a43
branch: fix/parallel-stream-context
repository: AGORA
topic: "Adding a feedback/listen user preference setting"
tags: [research, codebase, user-preferences, settings, general-agent]
status: complete
last_updated: 2026-01-15
last_updated_by: Claude
---

# Research: Adding a feedback/listen User Preference Setting

**Date**: 2026-01-15T16:30:00+01:00
**Researcher**: Claude
**Git Commit**: 3a26a07069b256101c1f2f9cd715b33c499e9a43
**Branch**: fix/parallel-stream-context
**Repository**: AGORA

## Research Question

How to add a new "feedback/listen" setting similar to the existing "dictate/summarize" setting, which can be flipped via the general agent without backend process changes?

## Summary

The existing `spoken_text_type` setting provides a clear pattern to follow. Adding a new `interaction_mode` (or similar) setting with values `'feedback'` or `'listen'` requires changes in 6-7 files across frontend and both backend implementations. The setting can be stored, displayed, and modified via the general agent's `update_user_settings` tool.

## Detailed Findings

### Existing Pattern: spoken_text_type Setting

The `spoken_text_type` setting follows this pattern:

| Component | File | Purpose |
|-----------|------|---------|
| Type Definition | `HAI/src/types/user.ts:10` | TypeScript interface |
| UI Toggle | `HAI/src/components/admin/UserForm.tsx:192-231` | Two-button toggle in edit form |
| Header Badge | `HAI/src/components/layout/Header.tsx:113-127` | Display current setting |
| Backend Endpoint | `server-langgraph/src/agora_langgraph/api/server.py:337-434` | REST API validation |
| Agent Tool | `server-langgraph/src/agora_langgraph/core/tools.py:77-139` | LangGraph tool |
| Agent Tool | `server-openai/src/agora_openai/adapters/internal_tools.py:29-118` | OpenAI SDK tool |
| System Prompt | `server-langgraph/src/agora_langgraph/core/agent_definitions.py:58-62` | Prompt mentions setting |

### Files to Modify for New Setting

#### 1. Frontend Type Definition

**File**: `HAI/src/types/user.ts:5-11`

```typescript
export interface UserPreferences {
  theme?: 'light' | 'dark' | 'system';
  notifications_enabled?: boolean;
  default_agent_id?: string;
  language?: string;
  spoken_text_type?: 'dictate' | 'summarize';
  interaction_mode?: 'feedback' | 'listen';  // ADD THIS
}
```

#### 2. Frontend Edit Form UI

**File**: `HAI/src/components/admin/UserForm.tsx`

Add state (around line 38):
```typescript
const [interactionMode, setInteractionMode] = useState<'feedback' | 'listen'>('feedback');
```

Load preference in useEffect (around line 52):
```typescript
if (prefs.interaction_mode) {
  setInteractionMode(prefs.interaction_mode);
}
```

Save preference on submit (around line 105):
```typescript
await updateUserPreferences(selectedUser.id, {
  spoken_text_type: spokenTextType,
  interaction_mode: interactionMode,  // ADD THIS
});
```

Add toggle UI (around line 230, after the spoken_text_type toggle):
```tsx
<div className="space-y-2">
  <label className="text-sm font-medium">Interactiemodus</label>
  <div className="flex gap-2">
    <button
      type="button"
      onClick={() => setInteractionMode('feedback')}
      className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${
        interactionMode === 'feedback'
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-muted hover:border-muted-foreground/50'
      }`}
    >
      <MessageSquare className="h-4 w-4" />
      <span>Feedback</span>
    </button>
    <button
      type="button"
      onClick={() => setInteractionMode('listen')}
      className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-lg border-2 transition-all ${
        interactionMode === 'listen'
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-muted hover:border-muted-foreground/50'
      }`}
    >
      <Headphones className="h-4 w-4" />
      <span>Luisteren</span>
    </button>
  </div>
  <p className="text-xs text-muted-foreground">
    Feedback: actief meedenken en suggesties geven. Luisteren: alleen noteren zonder tussenkomst.
  </p>
</div>
```

#### 3. Header Badge Display (Optional)

**File**: `HAI/src/components/layout/Header.tsx:113-127`

Add after the spoken_text_type badge:
```tsx
{preferences?.interaction_mode && (
  <Badge variant="outline" className="text-xs">
    {preferences.interaction_mode === 'feedback' ? (
      <>
        <MessageSquare className="h-3 w-3 mr-1" />
        Feedback
      </>
    ) : (
      <>
        <Headphones className="h-3 w-3 mr-1" />
        Luisteren
      </>
    )}
  </Badge>
)}
```

#### 4. Backend API Validation (server-langgraph)

**File**: `server-langgraph/src/agora_langgraph/api/server.py`

Update `UpdatePreferencesRequest` (around line 337):
```python
class UpdatePreferencesRequest(BaseModel):
    theme: str | None = None
    notifications_enabled: bool | None = None
    default_agent_id: str | None = None
    language: str | None = None
    spoken_text_type: str | None = None
    interaction_mode: str | None = None  # ADD THIS
```

Add validation in PUT endpoint (around line 390):
```python
# Validate interaction_mode
if body.interaction_mode is not None:
    valid_modes = ("feedback", "listen")
    if body.interaction_mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"interaction_mode must be one of {valid_modes}",
        )
    updates["interaction_mode"] = body.interaction_mode
```

Update default preferences (around line 360):
```python
default_preferences = {
    "theme": "system",
    "notifications_enabled": True,
    "default_agent_id": "general-agent",
    "language": "nl-NL",
    "spoken_text_type": "summarize",
    "interaction_mode": "feedback",  # ADD THIS
}
```

#### 5. Backend API Validation (server-openai)

**File**: `server-openai/src/agora_openai/api/server.py`

Apply same changes as server-langgraph (identical API contract).

#### 6. Agent Tool (server-langgraph)

**File**: `server-langgraph/src/agora_langgraph/core/tools.py:77-139`

Update `_update_user_settings_impl`:
```python
async def _update_user_settings_impl(
    user_id: str,
    spoken_text_type: str | None = None,
    interaction_mode: str | None = None,  # ADD THIS
) -> str:
    if not _user_manager:
        return "Error: Instellingen service is niet beschikbaar."

    # Validate spoken_text_type
    valid_spoken_types = {"dictate", "summarize"}
    if spoken_text_type and spoken_text_type not in valid_spoken_types:
        return f"Error: Ongeldige waarde '{spoken_text_type}'..."

    # Validate interaction_mode  # ADD THIS BLOCK
    valid_interaction_modes = {"feedback", "listen"}
    if interaction_mode and interaction_mode not in valid_interaction_modes:
        return f"Error: Ongeldige waarde '{interaction_mode}' voor interaction_mode. Geldige opties: {valid_interaction_modes}"

    updates: dict[str, Any] = {}
    if spoken_text_type:
        updates["spoken_text_type"] = spoken_text_type
    if interaction_mode:  # ADD THIS
        updates["interaction_mode"] = interaction_mode

    await _user_manager.update_preferences(user_id, updates)

    # Build confirmation message
    confirmations = []
    if spoken_text_type:
        mode_nl = "dicteren" if spoken_text_type == "dictate" else "samenvatten"
        confirmations.append(f"spraakweergave naar '{mode_nl}'")
    if interaction_mode:  # ADD THIS
        mode_nl = "feedback" if interaction_mode == "feedback" else "luisteren"
        confirmations.append(f"interactiemodus naar '{mode_nl}'")

    return f"Instellingen bijgewerkt: {', '.join(confirmations)}."
```

#### 7. Agent Tool (server-openai)

**File**: `server-openai/src/agora_openai/adapters/internal_tools.py:85-118`

Update JSON schema in `create_update_user_settings_tool`:
```python
"params_json_schema": {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", ...},
        "spoken_text_type": {
            "type": "string",
            "enum": ["dictate", "summarize"],
            ...
        },
        "interaction_mode": {  # ADD THIS
            "type": "string",
            "enum": ["feedback", "listen"],
            "description": "Interaction mode: 'feedback' for active suggestions, 'listen' for passive note-taking",
        },
    },
    "required": ["user_id"],
}
```

Update `_update_user_settings_invoke` to handle the new field (around line 50).

#### 8. General Agent System Prompt

**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py:58-62`
**File**: `server-openai/src/agora_openai/core/agent_definitions.py:58-62`

Update USER SETTINGS section:
```python
"USER SETTINGS:\n"
"You can directly change user settings with update_user_settings tool:\n"
"- spoken_text_type: 'dictate' (full text) or 'summarize' (TTS summary)\n"
"- interaction_mode: 'feedback' (active suggestions) or 'listen' (passive notes)\n"  # ADD THIS
"- Triggers: 'dicteer modus', 'samenvatten', 'feedback modus', 'luister modus', 'wijzig instellingen', 'settings'\n"
"- The user_id is available from the conversation context\n"
"- Always confirm the change to the user after updating\n\n"
```

## Code References

- `HAI/src/types/user.ts:5-11` - UserPreferences type definition
- `HAI/src/components/admin/UserForm.tsx:35-39` - Form state initialization
- `HAI/src/components/admin/UserForm.tsx:192-231` - Spoken text type toggle UI
- `HAI/src/components/layout/Header.tsx:113-127` - Preference badge display
- `server-langgraph/src/agora_langgraph/api/server.py:337-344` - UpdatePreferencesRequest model
- `server-langgraph/src/agora_langgraph/api/server.py:384-390` - Validation logic
- `server-langgraph/src/agora_langgraph/core/tools.py:77-139` - update_user_settings tool
- `server-openai/src/agora_openai/adapters/internal_tools.py:85-118` - OpenAI SDK tool
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:58-62` - System prompt settings section
- `server-openai/src/agora_openai/core/agent_definitions.py:58-62` - System prompt settings section

## Architecture Insights

1. **Symmetric Implementation**: Both server-openai and server-langgraph must receive identical changes to maintain API parity
2. **Tool-Based Updates**: The general agent can modify settings via the `update_user_settings` tool, which writes directly to the user's preferences in the database
3. **No Backend Process Changes Needed**: The setting is stored but not used for any backend logic - agents simply acknowledge the preference
4. **Frontend Displays Setting**: The Header component can optionally display the current mode as a badge

## Implementation Steps

1. Add type to `UserPreferences` in `HAI/src/types/user.ts`
2. Add state and UI toggle in `HAI/src/components/admin/UserForm.tsx`
3. (Optional) Add badge display in `HAI/src/components/layout/Header.tsx`
4. Add validation in `server-langgraph/src/agora_langgraph/api/server.py`
5. Add validation in `server-openai/src/agora_openai/api/server.py`
6. Update tool in `server-langgraph/src/agora_langgraph/core/tools.py`
7. Update tool in `server-openai/src/agora_openai/adapters/internal_tools.py`
8. Update system prompts in both `agent_definitions.py` files

## Open Questions

1. **Naming**: Should the setting be called `interaction_mode` or something else like `agent_behavior`?
2. **UI Icons**: Which icons best represent "feedback" and "listen" modes? (Suggested: MessageSquare and Headphones)
3. **Dutch Labels**: Should "listen" be translated as "Luisteren" or "Passief"?
4. **Default Value**: Should the default be `'feedback'` (active) or `'listen'` (passive)?
