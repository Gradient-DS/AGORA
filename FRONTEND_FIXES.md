# Frontend Fixes Summary

## Issues Fixed

### 1. Tool Call References Stuck on "Loading"

**Problem:** Tool call references in chat were showing loading spinners even after completion.

**Root Cause:** 
- Backend was sending separate `ToolCallMessage` objects for "started" and "completed" statuses
- No unique identifier linked these messages together
- Frontend created new random IDs for each message, so updates couldn't find the original

**Solution:**
- Added `tool_call_id` field to backend `ToolCallMessage` model (Python)
- Backend now generates a UUID when starting a tool call and uses the same ID for completion/failure
- Frontend uses this `tool_call_id` as the message ID
- Updated `useMessageStore.addMessage()` to update existing messages instead of always creating new ones
- Now when "completed" arrives, it updates the existing "started" message's status

**Files Modified:**
- `server-openai/common/hai_types.py` - Added `tool_call_id` field
- `server-openai/src/agora_openai/pipelines/orchestrator.py` - Generate and pass UUID
- `HAI/src/types/schemas.ts` - Added `tool_call_id` to schema
- `HAI/src/hooks/useWebSocket.ts` - Use `tool_call_id` as message ID
- `HAI/src/stores/useMessageStore.ts` - Update existing messages if ID matches

### 2. Agents Always Show as "Inactief" (Inactive)

**Problem:** Agents remained inactive even during active conversations.

**Root Cause:**
- Tool call messages didn't include `agent_id`
- Agent status tracking in `ChatMessage.tsx` couldn't determine which agent was executing tools

**Solution:**
- Backend `ToolCallMessage` already had `agent_id` field (but wasn't in frontend schema)
- Added `agent_id` and `metadata` fields to frontend schema
- Added `agent_id` to tool call handling in `useWebSocket.ts`
- `ChatMessage` component now receives agent_id and updates agent status appropriately

**Files Modified:**
- `HAI/src/types/schemas.ts` - Added `agent_id` and `metadata` to schema
- `HAI/src/hooks/useWebSocket.ts` - Pass `agent_id` when adding tool call messages

### 3. Confusing "4 Tools" Label

**Problem:** "Onder de Motorkap" panel showed "4 Tools" which was misleading - users thought it meant 4 available tools, not 4 executions.

**Solution:**
- Changed label from "4 Tools" to "4 Executions"
- Changed agent badge from "4 tools" to "4 calls"
- Makes it clearer these are execution counts, not available tool counts

**Files Modified:**
- `HAI/src/components/debug/DebugPanel.tsx` - Updated labels

## Testing

After these changes:
1. Tool call references should update from "Executing" (spinning) to "Completed" (checkmark)
2. Agent status indicators should show "Actief" or "Tools Uitvoeren" during conversations
3. Panel should show "X Executions" instead of "X Tools"

## Additional Notes

The frontend now properly tracks:
- Tool call lifecycle (started → completed/failed) using stable IDs
- Which agent is executing which tools
- Clear distinction between tool executions and available tools

