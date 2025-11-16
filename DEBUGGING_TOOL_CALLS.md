# Debugging Tool Calls Disappearing Issue

## Problem
Tool calls are disappearing from the debug panel when new tool calls come in for the same agent. For example, "Check Company Exists" and "Get Inspection History" tool calls are not visible under "NVWA General Assistant", but "Check Repeat Violation" and "Search Regulations" are.

## Changes Made

### 1. Fixed useEffect Dependency Array
**File:** `HAI/src/components/chat/ChatMessage.tsx`

Changed the dependency array from `[message, ...]` to `[message.id, message.type, message.tool_status, message.agent_id, ...]` to prevent unnecessary re-runs when unrelated message properties change.

### 2. Added Debug Logging
Added console.log statements to track tool call lifecycle:

**In `useToolCallStore.ts`:**
- Logs when a tool call already exists (prevents duplicate)
- Logs when a new tool call is being added
- Logs when a tool call is being updated

**In `ChatMessage.tsx`:**
- Logs tool call processing with ID, name, status, and agent

**In `DebugPanel.tsx`:**
- Logs all tool calls in the store every render

## How to Test

1. Start a new conversation
2. Open the browser console (F12 or Cmd+Option+I)
3. Send a message that triggers multiple tool calls
4. Watch the console logs:
   - You should see `[ChatMessage] Processing tool call:` for each tool call
   - You should see `[ToolCallStore] Adding new tool call:` when they're added
   - You should see `[ToolCallStore] Tool call already exists:` if duplicates are prevented
   - You should see `[ToolCallStore] Updating tool call:` when status changes
   - You should see `[DebugPanel] All tool calls:` with the full list

## What to Look For

### If Tool Calls Are Being Added:
- Check the console: Are all tool calls being added to the store?
- If yes, but not visible, the issue is in how `getToolCallsByAgent` filters them

### If Tool Calls Are Not Being Added:
- Check if they're being skipped due to "already exists" message
- Check if the tool_call IDs are unique

### If Tool Calls Are Being Cleared:
- Look for console.log showing the count going down
- This would indicate clearToolCalls is being called somewhere

## Potential Issues

1. **Agent ID mismatch**: The tool calls might have different agent IDs than expected
2. **Tool call ID collision**: Multiple tool calls might have the same ID
3. **Message update causing re-add**: When a tool call message updates from 'started' to 'completed', it might trigger the useEffect again

## Next Steps Based on Console Output

1. If tool calls ARE in the store but not showing:
   - Check the `agentId` field matches the agent in the debug panel
   - Verify `getToolCallsByAgent` is filtering correctly

2. If tool calls are NOT in the store:
   - Check if messages are missing `agent_id`
   - Check if tool_call_id is unique for each call

3. If tool calls disappear after being added:
   - Look for unexpected calls to `clearToolCalls`
   - Check if the store is being reset somehow

