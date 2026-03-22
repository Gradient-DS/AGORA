# Image Upload UX Improvements

## Overview

Improve the image upload experience so that attaching an image immediately sends it as evidence (no extra send click needed), shows a "Wordt toegevoegd als bewijsmateriaal" label, and does not trigger the conversational LLM when no text accompanies the image. Background vision description still runs.

## Current State Analysis

- `ChatInput.tsx:38-60`: User selects file → stored in local state as preview
- `ChatInput.tsx:73-79`: Image only sent when user clicks send button
- `ChatInput.tsx:96-111`: Preview shown as 20x20 thumbnail with X button, no label
- `ChatMessage.tsx:75-83`: Sent image rendered in message bubble, no label
- `useWebSocket.ts:378-393`: `sendMessage()` adds message to store + sends via WebSocket
- `client.ts:112-157`: Builds `RunAgentInput` with multimodal content parts
- Backend `orchestrator.py`: Always invokes LLM even when `user_content` is empty

### Key Discoveries:
- Image-only messages produce `user_content = ""` on the backend, but the LLM is still invoked with an empty `HumanMessage`
- The "thinking" indicator appears because the backend sends `STEP_STARTED` events
- `handleFileSelect` currently only sets local state; it doesn't trigger send
- Both orchestrators (langgraph + openai) need the early-return logic

## Desired End State

After implementation:
- Attaching an image immediately sends it as a user message (no send button click needed)
- The chat message shows the image with "Wordt toegevoegd als bewijsmateriaal" label
- The backend saves, forwards, and describes the image but does NOT invoke the conversational LLM
- No "thinking" indicator appears for image-only messages
- Text messages (with or without prior image) continue to work normally

### Verification:
- Attach an image → it immediately appears in chat with the evidence label
- No "Algemene assistent is aan het denken" indicator appears
- The image is saved to disk and forwarded to reporting
- The background vision description task still runs
- Typing and sending text after attaching an image works normally
- The PDF report includes the image with AI-generated description

## What We're NOT Doing

- Changing the WebSocket protocol or AG-UI message format
- Changing the image preview in the input area (it won't appear there anymore since send is immediate)
- Adding multi-image support per message
- Changing the file size limit or accepted formats

## Implementation Approach

Frontend first (immediate send + label), then backend (early return for image-only).

---

## Phase 1: Frontend — Immediate Send on Attach + Evidence Label

### Overview
Make image attachment immediately send the image as a chat message with an evidence label. Remove the input preview since the image is sent instantly.

### Changes Required:

#### 1. Immediate Send on File Select
**File**: `HAI/src/components/chat/ChatInput.tsx`
**Changes**: In `handleFileSelect`, after reading the file, immediately call `onSend("", attachment)` instead of storing in local state. Remove the `imageAttachment` local state, the preview rendering, and the `removeAttachment` callback since they're no longer needed.

Replace the `handleFileSelect` callback (lines 38-60):

```typescript
const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      alert('Afbeelding is te groot. Maximaal 2MB.');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const attachment = {
        data: reader.result as string,
        mimeType: file.type,
        filename: file.name,
      };
      // Send immediately — image is evidence, not input for the LLM
      onSend('', attachment);
    };
    reader.readAsDataURL(file);

    e.target.value = '';
  }, [onSend]);
```

Remove:
- `imageAttachment` useState (line 31-35)
- `removeAttachment` callback (lines 62-64)
- Image preview block (lines 96-111)
- `imageAttachment` from `handleSend` (line 75 → just `onSend(message.trim())`)
- `imageAttachment` from send button disabled check (line 181 → just `!message.trim()`)

Updated `handleSend`:
```typescript
const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message.trim());
      setMessage('');
    }
  };
```

Updated send button:
```typescript
disabled={disabled || !message.trim() || isVoiceActive}
```

#### 2. Evidence Label on Chat Messages
**File**: `HAI/src/components/chat/ChatMessage.tsx`
**Changes**: Add "Wordt toegevoegd als bewijsmateriaal" label below the image in user messages.

Find the image rendering block (lines 75-83) and add the label:

```tsx
{isUser && message.imageAttachment && (
  <div className="mb-2">
    <img
      src={message.imageAttachment.data || message.imageAttachment.url}
      alt="Bewijsfoto"
      className="max-w-full max-h-48 rounded-md object-contain"
    />
    <p className="text-xs text-muted-foreground mt-1 italic">
      Wordt toegevoegd als bewijsmateriaal
    </p>
  </div>
)}
```

### Success Criteria:

#### Automated Verification:
- [x] `pnpm run build` succeeds without errors
- [x] `pnpm run type-check` passes
- [x] `pnpm run lint` passes
- [x] `pnpm run test` passes

#### Manual Verification:
- [ ] Clicking the paperclip and selecting an image immediately shows it in chat
- [ ] The evidence label "Wordt toegevoegd als bewijsmateriaal" appears below the image
- [ ] The send button is not affected (still works for text-only messages)
- [ ] No image preview lingers in the input area after attach

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation.

---

## Phase 2: Backend — Skip LLM for Image-Only Messages

### Overview
When the backend receives a message with images but no text, save/forward/describe the images but skip the conversational LLM invocation. Send minimal protocol events so the frontend doesn't show "thinking".

### Changes Required:

#### 1. LangGraph Orchestrator Early Return
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: After image saving/forwarding/description launch, check if `user_content` is empty. If so, send minimal protocol events and return early.

Add after the background description task launch and before the user_id extraction (around line 195):

```python
# Image-only message — no LLM invocation needed
if not user_content.strip() and image_parts:
    log.info(f"Image-only message for session {thread_id}, skipping LLM")
    if protocol_handler:
        run_id = agent_input.run_id or str(uuid.uuid4())
        await protocol_handler.send_run_started(thread_id, run_id)
        await protocol_handler.send_run_finished(thread_id, run_id)
    return self._create_response_message("", str(uuid.uuid4()))
```

#### 2. OpenAI Orchestrator Early Return
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Same early return logic after image handling.

Add after the background description task launch and before the user_id extraction:

```python
# Image-only message — no LLM invocation needed
if not user_content.strip() and image_parts:
    log.info(f"Image-only message for session {thread_id}, skipping LLM")
    if protocol_handler:
        run_id = agent_input.run_id or str(uuid.uuid4())
        await protocol_handler.send_run_started(thread_id, run_id)
        await protocol_handler.send_run_finished(thread_id, run_id)
    return self._create_response_message("", str(uuid.uuid4()))
```

### Success Criteria:

#### Automated Verification:
- [x] `pytest` passes for server-langgraph (11 passed, 1 pre-existing failure)
- [x] `pytest` passes for server-openai (21 passed)
- [x] Python syntax check passes for both orchestrators

#### Manual Verification:
- [ ] Attaching an image does NOT show "Algemene assistent is aan het denken"
- [ ] The image is saved to disk (check session images directory)
- [ ] The image is forwarded to reporting MCP
- [ ] Background vision description task runs (check logs for "Updated image description")
- [ ] Sending text after an image still triggers normal LLM response
- [ ] PDF report includes the image with AI-generated description

---

## Testing Strategy

### Automated Tests:
- Frontend build + type-check + lint
- Backend pytest suites for both orchestrators

### Manual Testing Steps:
1. Attach an image via paperclip → verify it appears immediately in chat with evidence label
2. Verify no "thinking" indicator appears
3. Type and send a text message → verify normal LLM response
4. Attach another image → verify it also appears immediately
5. Generate a PDF report → verify images appear with AI descriptions
6. Reload the page → verify images appear in chat history

## References

- Image decoupling plan: `thoughts/shared/plans/2026-03-06-image-decoupling-from-llm-messages.md`
- ChatInput component: `HAI/src/components/chat/ChatInput.tsx`
- ChatMessage component: `HAI/src/components/chat/ChatMessage.tsx`
- LangGraph orchestrator: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
- OpenAI orchestrator: `server-openai/src/agora_openai/pipelines/orchestrator.py`
