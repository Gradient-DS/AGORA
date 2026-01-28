---
date: 2026-01-28T12:00:00+01:00
researcher: Claude
git_commit: ac88f9f2000b62db9ae8d5a3811180d15a74fee5
branch: feat/buffer
repository: AGORA
topic: "UI setting to show streamed written and spoken output for consistency checking"
tags: [research, codebase, HAI, frontend, settings, TTS, streaming, dual-text]
status: complete
last_updated: 2026-01-28
last_updated_by: Claude
---

# Research: UI Setting to Show Written and Spoken Output Together

**Date**: 2026-01-28T12:00:00+01:00
**Researcher**: Claude
**Git Commit**: ac88f9f2000b62db9ae8d5a3811180d15a74fee5
**Branch**: feat/buffer
**Repository**: AGORA

## Research Question
Can we make a setting in the UI to show streamed written and spoken output side-by-side (or stacked) so we can check consistency? The setting should be general for all users in HAI with no backend changes required.

## Summary

**Yes, this is achievable with frontend-only changes.** The backend already sends both written and spoken text as separate event streams for the same message. Currently:
- Written text → stored in message store → displayed in chat
- Spoken text → buffered in `useTTS` hook → sent to ElevenLabs → **NOT stored or displayed**

The implementation requires:
1. Store spoken text alongside written text in the message store
2. Add a new UI setting (persisted to localStorage)
3. Modify `ChatMessage` component to show both when enabled

## Detailed Findings

### Current Dual-Channel Architecture

The backend already streams both written and spoken text via separate AG-UI events:

| Channel | Events | Current Frontend Handling |
|---------|--------|---------------------------|
| Written | `TEXT_MESSAGE_START/CONTENT/END` | Stored in `useMessageStore`, displayed in chat |
| Spoken | `agora:spoken_text_start/content/end` | Buffered in `useTTS` hook, sent to ElevenLabs TTS only |

This is already a dual-channel pattern - we just need to capture the spoken channel in the UI.

### Key Files for Implementation

#### 1. Message Type Extension
**File**: `HAI/src/types/index.ts:4-14`
```typescript
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;           // Written text
  // ADD: spokenContent?: string;  // Spoken text variant
  timestamp: Date;
  isStreaming?: boolean;
  // ...
}
```

#### 2. Message Store Updates
**File**: `HAI/src/stores/useMessageStore.ts`

Add parallel tracking for spoken content:
- Add `spokenContent` field to message interface
- Add `updateSpokenContent(messageId, delta, append)` action
- Add `finalizeSpokenMessage(messageId)` action

#### 3. WebSocket Hook - Capture Spoken Text
**File**: `HAI/src/hooks/useWebSocket.ts:284-306`

Currently spoken text events only emit to TTS:
```typescript
} else if (event.name === 'agora:spoken_text_content') {
  const value = event.value as { messageId?: string; delta?: string };
  emitTTSEvent({
    type: 'spoken_text_content',
    messageId: value.messageId,
    content: value.delta,
  });
}
```

**Change**: Also store in message store:
```typescript
} else if (event.name === 'agora:spoken_text_content') {
  const value = event.value as { messageId?: string; delta?: string };
  // Existing TTS emit
  emitTTSEvent({ type: 'spoken_text_content', messageId: value.messageId, content: value.delta });
  // NEW: Also store for comparison display
  if (value.messageId && value.delta) {
    updateSpokenContent(value.messageId, value.delta, true);
  }
}
```

#### 4. Settings Store
**File**: `HAI/src/stores/useTTSStore.ts` (or new store)

The existing `useTTSStore` already uses Zustand's `persist` middleware for localStorage. Add the comparison toggle here:

```typescript
interface TTSState {
  isEnabled: boolean;
  isSpeaking: boolean;
  showSpokenComparison: boolean;  // NEW
  toggleEnabled: () => void;
  toggleSpokenComparison: () => void;  // NEW
  // ...
}
```

Persist key: Already uses `agora-tts-settings` - add to partialize.

#### 5. Chat Message Display
**File**: `HAI/src/components/chat/ChatMessage.tsx:72-81`

Current rendering:
```tsx
<ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
```

Modified for comparison mode:
```tsx
{showSpokenComparison && message.spokenContent ? (
  <div className="space-y-2">
    <div>
      <span className="text-xs font-medium text-muted-foreground">Written:</span>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
    </div>
    <div className="border-t pt-2">
      <span className="text-xs font-medium text-muted-foreground">Spoken:</span>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.spokenContent}</ReactMarkdown>
    </div>
  </div>
) : (
  <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
)}
```

#### 6. Toggle UI Location

**Option A**: Add to Header (`HAI/src/components/layout/Header.tsx`)
- Near existing TTS toggle location
- Could be a small icon button or badge

**Option B**: Add to TTS Toggle component (`HAI/src/components/chat/TTSToggle.tsx`)
- Keep comparison mode with TTS controls
- Makes conceptual sense since it's about spoken text

**Option C**: Add to Admin Panel (`HAI/src/components/admin/AdminPanel.tsx`)
- Treat as a developer/debug feature
- Less visible to end users

### Existing Settings Pattern

The HAI uses Zustand with persist middleware for client-side settings:

```typescript
// Example from useTTSStore.ts:23-37
persist(
  (set) => ({
    isEnabled: false,
    toggleEnabled: () => set((state) => ({ isEnabled: !state.isEnabled })),
  }),
  {
    name: 'agora-tts-settings',  // localStorage key
    partialize: (state) => ({ isEnabled: state.isEnabled }),  // What to persist
  }
)
```

This pattern should be followed for the new setting.

### Data Flow (After Implementation)

```
Backend
├── generate_written node → TEXT_MESSAGE_* events
└── generate_spoken node  → agora:spoken_text_* events
                                    ↓
WebSocket receives events
├── TEXT_MESSAGE_* → useMessageStore.updateMessageContent() → message.content
└── agora:spoken_text_*
    ├── emitTTSEvent() → ElevenLabs (existing)
    └── useMessageStore.updateSpokenContent() → message.spokenContent (NEW)
                                    ↓
ChatMessage component
├── if showSpokenComparison: render both content + spokenContent
└── else: render content only (current behavior)
```

## Code References

- `HAI/src/types/index.ts:4-14` - ChatMessage interface to extend
- `HAI/src/stores/useMessageStore.ts:49-57` - updateMessageContent pattern to replicate
- `HAI/src/stores/useTTSStore.ts:23-37` - Persist pattern for settings
- `HAI/src/hooks/useWebSocket.ts:284-306` - Spoken text event handlers
- `HAI/src/components/chat/ChatMessage.tsx:72-81` - Content rendering to modify
- `HAI/src/components/layout/Header.tsx:199-206` - Settings button location

## Architecture Insights

1. **Dual-Channel Already Exists**: The backend generates written and spoken text in parallel via separate LangGraph nodes (`generate_written` and `generate_spoken`). The frontend architecture already supports this with separate event types.

2. **No Backend Changes Needed**: All necessary data is already being sent. The spoken text events contain the same `messageId` as written text, allowing easy correlation.

3. **Zustand + localStorage Pattern**: HAI uses Zustand stores with the `persist` middleware for client-side settings. The `useTTSStore` is the natural home for this setting since it's related to spoken text.

4. **Streaming Considerations**: Both channels stream in parallel. The spoken text typically finishes slightly after written text (it's generated by a separate LLM call). The UI should handle showing partial spoken content gracefully.

## Implementation Checklist

- [x] Extend `ChatMessage` interface with `spokenContent?: string` and `isSpokenStreaming?: boolean`
- [x] Add `updateSpokenContent`, `finalizeSpokenMessage`, and `startSpokenContent` actions to `useMessageStore`
- [x] Modify `useWebSocket` hook to store spoken text in message store (in addition to TTS emit)
- [x] Add `showSpokenComparison` state and `toggleSpokenComparison` action to `useTTSStore`
- [x] Update persist middleware to include new setting
- [x] Modify `ChatMessage` component to render both texts when setting is enabled
- [x] Add toggle UI in Header bar with `SplitSquareVertical` icon
- [x] Style the comparison view (stacked vertically with labels and border separator)

## Implementation Complete

The feature has been implemented with the following changes:

| File | Changes |
|------|---------|
| `HAI/src/types/index.ts` | Added `spokenContent?: string` and `isSpokenStreaming?: boolean` to `ChatMessage` |
| `HAI/src/stores/useTTSStore.ts` | Added `showSpokenComparison` state with localStorage persistence |
| `HAI/src/stores/useMessageStore.ts` | Added `startSpokenContent`, `updateSpokenContent`, `finalizeSpokenMessage` actions |
| `HAI/src/hooks/useWebSocket.ts` | Modified to store spoken text in message store alongside TTS emit |
| `HAI/src/components/chat/ChatMessage.tsx` | Added conditional rendering for comparison mode |
| `HAI/src/components/layout/Header.tsx` | Added toggle button with `SplitSquareVertical` icon |

## Open Questions

1. **Toggle Location**: Should the comparison toggle be in the Header (visible), TTS controls, or Admin Panel (hidden)?
2. **Styling**: Stacked vertically vs. side-by-side columns? Labels vs. icons?
3. **Streaming Indicator**: Should we show separate streaming indicators for written vs. spoken?
4. **Persistence Scope**: Should this setting be per-user (server-backed) or client-only (localStorage)?
