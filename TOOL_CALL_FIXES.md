# Tool Call Display Fixes

## Issues Fixed

### 1. Duplicate Tool Calls
**Problem:** Tool calls were being displayed multiple times in the debug panel because the `addToolCall` function in `useToolCallStore` was adding duplicate entries when tool status changed from 'started' to 'completed'.

**Solution:** Modified `useToolCallStore.ts` to check if a tool call with the same ID already exists before adding it. If it exists, the state remains unchanged and prevents duplication.

```typescript
addToolCall: (toolCall) =>
  set((state) => {
    const exists = state.toolCalls.some((tc) => tc.id === toolCall.id);
    if (exists) {
      return state; // Don't add duplicate
    }
    return {
      toolCalls: [...state.toolCalls, { ...toolCall, timestamp: new Date() }],
    };
  }),
```

### 2. Collapsible Agents and Tool Calls
**Problem:** There was no way to collapse agents and their tool calls in the debug panel, making it cluttered when many tool calls were executed.

**Solution:** Added collapse/expand functionality to the debug panel:

#### Features Added:
- **Collapsible agents**: Click on any agent that has tool calls to collapse/expand its tool calls
- **Visual indicators**: 
  - Chevron icons (right/down) show collapse state
  - Agents without tool calls don't have chevron icons or clickable behavior
- **Smooth animations**: Tool calls fade in/out when collapsing/expanding
- **State management**: Uses React `useState` with a `Set` to track which agents are collapsed

#### UI Changes:
- Agent headers are now clickable buttons (only when they have tool calls)
- Hover effect on clickable agents
- Chevron icon shows current state (collapsed/expanded)
- Smooth animations for better UX

## Files Modified

1. **`HAI/src/stores/useToolCallStore.ts`**
   - Added duplicate check in `addToolCall` function

2. **`HAI/src/components/debug/DebugPanel.tsx`**
   - Added `useState` for tracking collapsed agents
   - Added `toggleAgentCollapse` function
   - Converted agent display to clickable button
   - Added chevron icons for visual feedback
   - Added conditional rendering based on collapse state
   - Added animations for smooth transitions

## Testing

To verify the fixes:

1. **Duplicate Tool Calls**: 
   - Start a conversation that triggers tool calls
   - Watch the debug panel - each tool call should appear only once
   - Tool status should update from "Executing" to "Completed" without creating duplicates

2. **Collapse Functionality**:
   - Click on an agent that has tool calls in the debug panel
   - Tool calls should collapse/expand smoothly
   - Chevron icon should rotate to indicate state
   - Agents without tool calls should not be clickable

