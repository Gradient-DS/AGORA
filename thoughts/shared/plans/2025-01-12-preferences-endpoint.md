# User Preferences Endpoint Implementation Plan

## Overview

Simplify and fix the user preferences infrastructure to support a single setting (`spoken_response_mode`) with proper GET/PUT endpoints. This prepares the foundation for future preference settings while implementing only the infrastructure (not the actual spoken response behavior).

## Current State Analysis

### What Exists (Unused)
- **TypeScript types**: `theme`, `notifications_enabled`, `default_agent_id`, `language`
- **Frontend API**: `updateUserPreferences()` sends JSON body (never called)
- **Backend endpoints**: `PUT /users/me/preferences` uses query params (broken contract)
- **No GET endpoint** for preferences

### Problems
1. Backend expects query params, frontend sends JSON body
2. No way to read current preferences (must fetch entire user)
3. Four unused preference fields add complexity

## Desired End State

A working preferences system with:
- `GET /users/me/preferences?user_id={id}` - Returns current preferences
- `PUT /users/me/preferences?user_id={id}` - Updates preferences (JSON body)
- Single preference: `spoken_response_mode: 'dictate' | 'summarize'` (default: `'summarize'`)
- UI indicator showing current mode in Header

### Verification
```bash
# Test GET
curl "http://localhost:8000/users/me/preferences?user_id=550e8400-e29b-41d4-a716-446655440001"
# Expected: {"success": true, "preferences": {"spoken_response_mode": "summarize"}}

# Test PUT
curl -X PUT "http://localhost:8000/users/me/preferences?user_id=550e8400-e29b-41d4-a716-446655440001" \
  -H "Content-Type: application/json" \
  -d '{"spoken_response_mode": "dictate"}'
# Expected: {"success": true, "preferences": {"spoken_response_mode": "dictate"}}
```

## What We're NOT Doing

- Implementing actual dictation vs summarization behavior
- Adding authentication/authorization
- Removing the existing (unused) preference fields from database schema
- Building a full settings panel UI

## Implementation Approach

Update all three backend implementations (mock, openai, langgraph) identically, then update frontend types and add a simple UI indicator.

---

## Phase 1: Backend - Mock Server

### Overview
Update `mock_server.py` to use the new simplified preferences model with proper GET/PUT endpoints.

### Changes Required:

#### 1. Update Default Preferences in Mock Users
**File**: `docs/hai-contract/mock_server.py`
**Location**: Lines 308-339 (mock user definitions)

Replace the `preferences` object for each user:
```python
"preferences": {
    "spoken_response_mode": "summarize",
},
```

#### 2. Update UpdatePreferencesRequest Model
**File**: `docs/hai-contract/mock_server.py`
**Location**: Lines 379-385

```python
class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""
    spoken_response_mode: str | None = Field(
        None,
        description="Spoken response mode: 'dictate' or 'summarize'"
    )
```

#### 3. Add GET /users/me/preferences Endpoint
**File**: `docs/hai-contract/mock_server.py`
**Location**: Before the PUT endpoint (around line 540)

```python
@app.get("/users/me/preferences")
async def get_current_user_preferences(
    user_id: str = Query(..., description="Current user ID")
):
    """Get current user's preferences."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    user = MOCK_USERS[user_id]
    preferences = user.get("preferences", {"spoken_response_mode": "summarize"})
    log_event("send", "HTTP", f"GET /users/me/preferences?user_id={user_id}")
    return {"success": True, "preferences": preferences}
```

#### 4. Update PUT /users/me/preferences Endpoint
**File**: `docs/hai-contract/mock_server.py`
**Location**: Lines 540-557

```python
@app.put("/users/me/preferences")
async def update_current_user_preferences(
    request: UpdatePreferencesRequest,
    user_id: str = Query(..., description="Current user ID")
):
    """Update current user's preferences."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    user = MOCK_USERS[user_id]
    if "preferences" not in user:
        user["preferences"] = {"spoken_response_mode": "summarize"}
    if request.spoken_response_mode is not None:
        if request.spoken_response_mode not in ("dictate", "summarize"):
            raise HTTPException(
                status_code=400,
                detail="spoken_response_mode must be 'dictate' or 'summarize'"
            )
        user["preferences"]["spoken_response_mode"] = request.spoken_response_mode
    log_event("send", "HTTP", f"PUT /users/me/preferences?user_id={user_id}")
    return {"success": True, "preferences": user["preferences"]}
```

#### 5. Update Default Preferences for New Users
**File**: `docs/hai-contract/mock_server.py`
**Location**: Lines 569-576 (in POST /users)

```python
"preferences": {
    "spoken_response_mode": "summarize",
},
```

#### 6. Update Help Text
**File**: `docs/hai-contract/mock_server.py`
**Location**: Lines 1418-1421

Add GET endpoint to the printed help:
```python
print("    GET  /users/me/preferences             - Get preferences")
print("    PUT  /users/me/preferences             - Update preferences")
```

### Success Criteria:

#### Automated Verification:
- [x] Mock server starts without errors: `cd docs/hai-contract && python mock_server.py`
- [ ] GET returns preferences: `curl "http://localhost:8000/users/me/preferences?user_id=550e8400-e29b-41d4-a716-446655440001"`
- [ ] PUT updates preferences: `curl -X PUT "http://localhost:8000/users/me/preferences?user_id=550e8400-e29b-41d4-a716-446655440001" -H "Content-Type: application/json" -d '{"spoken_response_mode": "dictate"}'`
- [ ] Invalid mode rejected: `curl -X PUT ... -d '{"spoken_response_mode": "invalid"}'` returns 400

#### Manual Verification:
- [ ] Confirm mock server logs show correct endpoint calls

---

## Phase 2: Backend - server-openai

### Overview
Update the OpenAI orchestrator server with the same preference changes.

### Changes Required:

#### 1. Add GET /users/me/preferences Endpoint
**File**: `server-openai/src/agora_openai/api/server.py`
**Location**: Before line 301 (before PUT endpoint)

```python
@app.get("/users/me/preferences")
async def get_current_user_preferences(
    user_id: str = Query(..., description="Current user ID"),
):
    """Get current user's preferences."""
    user_manager: UserManager = app.state.user_manager
    user = await user_manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    preferences = user.get("preferences", {"spoken_response_mode": "summarize"})
    return {"success": True, "preferences": preferences}
```

#### 2. Update PUT /users/me/preferences Endpoint
**File**: `server-openai/src/agora_openai/api/server.py`
**Location**: Lines 301-335

Replace with JSON body approach:
```python
from pydantic import BaseModel

class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""
    spoken_response_mode: str | None = None


@app.put("/users/me/preferences")
async def update_current_user_preferences(
    request: UpdatePreferencesRequest,
    user_id: str = Query(..., description="Current user ID"),
):
    """Update current user's preferences."""
    user_manager: UserManager = app.state.user_manager

    # Validate spoken_response_mode
    if request.spoken_response_mode is not None:
        if request.spoken_response_mode not in ("dictate", "summarize"):
            raise HTTPException(
                status_code=400,
                detail="spoken_response_mode must be 'dictate' or 'summarize'"
            )

    preferences = {}
    if request.spoken_response_mode is not None:
        preferences["spoken_response_mode"] = request.spoken_response_mode

    if not preferences:
        raise HTTPException(status_code=400, detail="No preferences provided")

    user = await user_manager.update_preferences(user_id, preferences)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "preferences": user.get("preferences"),
    }
```

#### 3. Update Default Preferences in UserManager
**File**: `server-openai/src/agora_openai/adapters/user_manager.py`

Find where default preferences are set (in `create_user`) and update:
```python
"preferences": json.dumps({"spoken_response_mode": "summarize"})
```

### Success Criteria:

#### Automated Verification:
- [ ] Type check passes: `cd server-openai && mypy src/`
- [ ] Server starts: `cd server-openai && python -m agora_openai.api.server`
- [ ] GET works: `curl "http://localhost:8000/users/me/preferences?user_id=..."`
- [ ] PUT works with JSON body

#### Manual Verification:
- [ ] Create new user via API, verify default preferences

---

## Phase 3: Backend - server-langgraph

### Overview
Mirror the exact same changes from Phase 2 to server-langgraph.

### Changes Required:

#### 1. Add GET /users/me/preferences Endpoint
**File**: `server-langgraph/src/agora_langgraph/api/server.py`
**Location**: Before line 302

Same as server-openai implementation.

#### 2. Update PUT /users/me/preferences Endpoint
**File**: `server-langgraph/src/agora_langgraph/api/server.py`
**Location**: Lines 302-335

Same as server-openai implementation.

#### 3. Update Default Preferences in UserManager
**File**: `server-langgraph/src/agora_langgraph/adapters/user_manager.py`

Same as server-openai implementation.

### Success Criteria:

#### Automated Verification:
- [ ] Type check passes: `cd server-langgraph && mypy src/`
- [ ] Server starts: `cd server-langgraph && python -m agora_langgraph.api.server`
- [ ] GET and PUT work identically to server-openai

---

## Phase 4: Frontend - Types and API

### Overview
Update TypeScript types and API functions to match the new preference model.

### Changes Required:

#### 1. Update UserPreferences Type
**File**: `HAI/src/types/user.ts`
**Location**: Lines 5-10

```typescript
export interface UserPreferences {
  spoken_response_mode?: 'dictate' | 'summarize';
}
```

#### 2. Add fetchUserPreferences Function
**File**: `HAI/src/lib/api/users.ts`

```typescript
/**
 * Fetch preferences for the current user.
 */
export async function fetchUserPreferences(
  userId: string
): Promise<UserPreferences> {
  const baseUrl = getBaseUrl();
  const response = await fetch(
    `${baseUrl}/users/me/preferences?user_id=${encodeURIComponent(userId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch preferences: ${response.statusText}`);
  }

  const data: { success: boolean; preferences: UserPreferences } = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch preferences');
  }

  return data.preferences;
}
```

#### 3. Update updateUserPreferences Function
**File**: `HAI/src/lib/api/users.ts`
**Location**: Lines 195-218

```typescript
/**
 * Update preferences for the current user.
 */
export async function updateUserPreferences(
  userId: string,
  preferences: UserPreferences
): Promise<UserPreferences> {
  const baseUrl = getBaseUrl();
  const response = await fetch(
    `${baseUrl}/users/me/preferences?user_id=${encodeURIComponent(userId)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(preferences),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to update preferences: ${response.statusText}`);
  }

  const data: { success: boolean; preferences: UserPreferences } = await response.json();

  if (!data.success) {
    throw new Error('Failed to update preferences');
  }

  return data.preferences;
}
```

### Success Criteria:

#### Automated Verification:
- [ ] Type check passes: `cd HAI && pnpm run type-check`
- [ ] Lint passes: `cd HAI && pnpm run lint`

---

## Phase 5: Frontend - UI Indicator

### Overview
Add a small badge in the Header showing the current spoken response mode.

### Changes Required:

#### 1. Add Preferences State to UserStore
**File**: `HAI/src/stores/useUserStore.ts`

Add preferences fetching:
```typescript
import { fetchUserPreferences } from '@/lib/api/users';
import type { UserPreferences } from '@/types/user';

interface UserStore {
  // Existing state...
  preferences: UserPreferences | null;

  // Existing actions...
  loadPreferences: (userId: string) => Promise<void>;
}

// In the store implementation:
preferences: null,

loadPreferences: async (userId: string) => {
  try {
    const preferences = await fetchUserPreferences(userId);
    set({ preferences });
  } catch (error) {
    console.error('[UserStore] Error loading preferences:', error);
    // Default to summarize on error
    set({ preferences: { spoken_response_mode: 'summarize' } });
  }
},
```

Update `loadUsers` to also load preferences when setting current user.

#### 2. Add Preference Indicator to Header
**File**: `HAI/src/components/layout/Header.tsx`

Add import and state:
```typescript
import { Mic, FileText } from 'lucide-react';

// In component:
const preferences = useUserStore((state) => state.preferences);

// In JSX, after the currentUser badge (around line 111):
{preferences?.spoken_response_mode && (
  <Badge variant="outline" className="text-xs">
    {preferences.spoken_response_mode === 'dictate' ? (
      <>
        <Mic className="h-3 w-3 mr-1" />
        Dicteer
      </>
    ) : (
      <>
        <FileText className="h-3 w-3 mr-1" />
        Samenvatten
      </>
    )}
  </Badge>
)}
```

### Success Criteria:

#### Automated Verification:
- [ ] Type check passes: `cd HAI && pnpm run type-check`
- [ ] Build succeeds: `cd HAI && pnpm run build`

#### Manual Verification:
- [ ] Badge appears in Header showing current mode
- [ ] Badge updates when preference is changed via API (curl)
- [ ] Default shows "Samenvatten" for new users

---

## Testing Strategy

### Unit Tests
None required for this phase (infrastructure only).

### Integration Tests
Test all three backends with the same curl commands:
```bash
# GET
curl "http://localhost:8000/users/me/preferences?user_id=..."
# PUT valid
curl -X PUT "...?user_id=..." -H "Content-Type: application/json" -d '{"spoken_response_mode": "dictate"}'
# PUT invalid (should 400)
curl -X PUT "...?user_id=..." -H "Content-Type: application/json" -d '{"spoken_response_mode": "invalid"}'
```

### Manual Testing Steps
1. Start mock server, verify UI shows "Samenvatten" badge
2. Use curl to change to "dictate", refresh UI, verify badge shows "Dicteer"
3. Create new user, verify default is "summarize"

## References

- Earlier research on preference handling (this conversation)
- `docs/hai-contract/mock_server.py` - Mock server implementation
- `server-openai/src/agora_openai/api/server.py` - OpenAI backend
- `server-langgraph/src/agora_langgraph/api/server.py` - LangGraph backend
