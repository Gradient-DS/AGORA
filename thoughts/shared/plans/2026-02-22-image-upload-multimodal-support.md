# Image Upload & Multimodal Support Implementation Plan

## Overview

Add image upload and camera capture support to AGORA, allowing inspectors to attach photos (e.g., of food safety labels, violations, equipment) alongside text messages. Images are sent from the frontend through the AG-UI protocol to the backend orchestrators, where they provide additional context for the AI agents. The system remains fully backward-compatible — text-only messages work identically.

**Phase 1 scope**: Images reach the backend and are acknowledged with a hardcoded text placeholder. Real GPT-4o vision processing is Phase 2 (out of scope for this plan).

## Current State Analysis

Every layer in AGORA constrains message content to plain strings:

| Layer | File | Constraint |
|-------|------|------------|
| Frontend `ChatInput` props | `HAI/src/components/chat/ChatInput.tsx:10` | `onSend: (message: string) => void` |
| Frontend `ChatMessage` type | `HAI/src/types/index.ts:7` | `content: string` |
| Frontend `RunAgentInput` Zod | `HAI/src/types/schemas.ts:215` | `content: z.string()` |
| WebSocket client | `HAI/src/lib/websocket/client.ts:111` | `sendRunInput(..., content: string)` |
| Offline buffer | `HAI/src/lib/websocket/offlineBuffer.ts:9` | `content: string` |
| useWebSocket hook | `HAI/src/hooks/useWebSocket.ts:378` | `sendMessage(content: string)` |
| App handler | `HAI/src/App.tsx:112` | `handleSendMessage(message: string)` |
| server-openai orchestrator | `server-openai/.../orchestrator.py:127` | `user_content = msg.get("content", "")` |
| server-langgraph orchestrator | `server-langgraph/.../orchestrator.py:146` | `msg.get("content", "")` in list comprehension |
| AsyncAPI spec | `docs/hai-contract/asyncapi.yaml:439` | `content: type: string` |
| JSON Schema | `docs/hai-contract/schemas/messages.json:149` | `content: { "type": "string" }` |

### Key Discoveries:
- The upstream AG-UI protocol already defines `BinaryInputContent` (draft) with `mime_type`, `url`, `data` fields
- Both GPT-4o and the agent SDKs (OpenAI Agents SDK, LangChain) natively support multimodal image inputs
- The backend `RunAgentInput.messages` is `list[dict[str, Any]]` (loosely typed) — it won't reject new fields
- WebSocket text frames can carry base64-encoded images as JSON strings — no transport changes needed
- The `CUSTOM` event mechanism provides an alternative path, but aligning with AG-UI `BinaryInputContent` is better long-term

## Desired End State

After implementation:
1. Inspectors see an attachment button (paperclip icon) in the chat input area
2. Clicking it opens a file picker for images (on mobile, also offers camera capture)
3. Selected image shows as a preview thumbnail with a remove button
4. Sending a message with an image attachment sends multimodal content (text + binary) to the backend
5. The image is displayed inline in the chat message bubble
6. The backend receives the image data and injects a text placeholder (Phase 1 hardcoded)
7. Without an image, the system behaves identically to today
8. Mock server demonstrates image handling for testing
9. All protocol documentation is updated

### Verification:
- Text-only messages work identically (no regressions)
- Image can be selected via file picker and previewed before sending
- Image + text message displays correctly in chat (thumbnail + text)
- Backend receives multimodal content and responds with acknowledgment
- Mock server handles image messages with a demo response
- Offline buffer correctly stores and replays image messages
- All existing tests pass
- Documentation reflects the new multimodal content support

## What We're NOT Doing

- **Real image processing** — No GPT-4o vision calls. Images get a hardcoded text placeholder in Phase 1.
- **New image-analysis agent** — Images are an input modality, not a domain. The general-agent handles them.
- **Image storage/blob service** — Base64 stays in the message. No external storage.
- **Multi-image support** — One image per message for now.
- **Image annotation/editing** — No cropping, drawing, or markup tools.
- **Image moderation** — No content safety filtering on uploaded images.
- **Drag-and-drop** — File picker only (keeps scope manageable).
- **Clipboard paste** — Not in this phase.

## Implementation Approach

We use **Option A from the research**: multimodal content arrays aligned with the AG-UI `BinaryInputContent` type. The `content` field in messages becomes `string | ContentPart[]` where `ContentPart` is a discriminated union of `{ type: "text", text: string }` and `{ type: "binary", mimeType: string, data: string }`.

This approach:
- Aligns with the upstream AG-UI protocol draft
- Matches how both OpenAI and LangChain expect multimodal content
- Is backward-compatible — string content still works everywhere
- Only changes the content field, not the message structure

---

## Phase 1: Frontend Types & Schema Changes

### Overview
Update the TypeScript types, Zod schemas, and interfaces to support multimodal content while maintaining backward compatibility.

### Changes Required:

#### 1. Extend ChatMessage interface
**File**: `HAI/src/types/index.ts`
**Changes**: Add optional `imageAttachment` field to `ChatMessage` for UI rendering purposes.

```typescript
// UI message representation (rendered in chat)
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: Date;
  agentId?: string;
  metadata?: Record<string, unknown>;
  isStreaming?: boolean;
  toolName?: string;
  toolDisplayName?: string;
  toolStatus?: 'started' | 'completed' | 'failed';
  /** Spoken text variant (for TTS consistency comparison) */
  spokenContent?: string;
  /** Whether spoken content is still streaming */
  isSpokenStreaming?: boolean;
  /** Optional image attachment (base64 data URL) */
  imageAttachment?: {
    data: string;       // base64 data URL (e.g., "data:image/jpeg;base64,...")
    mimeType: string;   // e.g., "image/jpeg", "image/png"
    filename?: string;  // original filename if available
  };
}
```

#### 2. Extend RunAgentInput Zod schema
**File**: `HAI/src/types/schemas.ts`
**Changes**: Make `content` accept both `string` and an array of content parts. Add a `ContentPartSchema`.

After line 227 (existing `MessageSchema`), add new schemas. Then update lines 212-219 (`RunAgentInputSchema`) and 222-227 (`MessageSchema`):

```typescript
// Content part types for multimodal messages
export const TextContentPartSchema = z.object({
  type: z.literal('text'),
  text: z.string(),
});

export const BinaryContentPartSchema = z.object({
  type: z.literal('binary'),
  mimeType: z.string(),
  data: z.string(),  // base64-encoded
  filename: z.string().optional(),
});

export const ContentPartSchema = z.discriminatedUnion('type', [
  TextContentPartSchema,
  BinaryContentPartSchema,
]);

// Update MessageSchema to accept multimodal content
export const MessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system', 'tool', 'developer']),
  content: z.union([z.string(), z.array(ContentPartSchema)]),
  id: z.string().optional(),
  toolCallId: z.string().optional(),
});

// Update RunAgentInputSchema with the new MessageSchema
export const RunAgentInputSchema = z.object({
  threadId: z.string(),
  runId: z.string().optional(),
  userId: z.string().uuid(),
  messages: z.array(MessageSchema),
});

// Type exports
export type TextContentPart = z.infer<typeof TextContentPartSchema>;
export type BinaryContentPart = z.infer<typeof BinaryContentPartSchema>;
export type ContentPart = z.infer<typeof ContentPartSchema>;
```

#### 3. Update offline buffer interface
**File**: `HAI/src/lib/websocket/offlineBuffer.ts`
**Changes**: Extend `BufferedMessage` to optionally carry an image attachment. Since IndexedDB handles arbitrary JS objects, no DB migration is needed.

```typescript
interface BufferedMessage {
  id: string;
  content: string;
  timestamp: number;
  threadId: string;
  userId: string;
  /** Optional image attachment for multimodal messages */
  imageAttachment?: {
    data: string;       // base64 data URL
    mimeType: string;
    filename?: string;
  };
}
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript type checking passes: `cd HAI && pnpm run type-check`
- [x] All existing tests pass: `cd HAI && pnpm run test`
- [x] Linting passes: `cd HAI && pnpm run lint`

#### Manual Verification:
- [ ] No regressions — existing text-only messages still render correctly

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 2: Frontend Image Capture & Upload UI

### Overview
Add an attachment button to `ChatInput`, a file picker for images, and an image preview with remove functionality.

### Changes Required:

#### 1. Extend ChatInput component
**File**: `HAI/src/components/chat/ChatInput.tsx`
**Changes**: Add image attachment state, file input, attachment button, and preview. Extend `onSend` callback signature.

Update the props interface (line 9-17):
```typescript
interface ChatInputProps {
  onSend: (message: string, imageAttachment?: { data: string; mimeType: string; filename?: string }) => void;
  disabled?: boolean;
  placeholder?: string;
  onToggleVoice?: () => void;
  isVoiceActive?: boolean;
  voiceDisabled?: boolean;
}
```

Add state and file handling logic inside the component (after line 30):
```typescript
const [imageAttachment, setImageAttachment] = useState<{
  data: string;
  mimeType: string;
  filename?: string;
} | null>(null);
const fileInputRef = useRef<HTMLInputElement>(null);

const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0];
  if (!file) return;

  // Limit to 2MB
  if (file.size > 2 * 1024 * 1024) {
    alert('Afbeelding is te groot. Maximaal 2MB.');
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    setImageAttachment({
      data: reader.result as string,
      mimeType: file.type,
      filename: file.name,
    });
  };
  reader.readAsDataURL(file);

  // Reset input so same file can be re-selected
  e.target.value = '';
};

const removeAttachment = () => {
  setImageAttachment(null);
};
```

Update `handleSend` (line 39-44):
```typescript
const handleSend = () => {
  if ((message.trim() || imageAttachment) && !disabled) {
    onSend(message.trim(), imageAttachment ?? undefined);
    setMessage('');
    setImageAttachment(null);
  }
};
```

Update the send button disabled condition (line 109):
```typescript
disabled={disabled || (!message.trim() && !imageAttachment) || isVoiceActive}
```

Add the hidden file input and attachment button in the render (before the Textarea, after TTSToggle at line 93):
```tsx
<input
  ref={fileInputRef}
  type="file"
  accept="image/*"
  capture="environment"
  onChange={handleFileSelect}
  className="hidden"
  aria-hidden="true"
/>
<Button
  onClick={() => fileInputRef.current?.click()}
  disabled={disabled || isVoiceActive}
  size="icon"
  variant="outline"
  className="h-[60px] w-[60px] flex-shrink-0"
  aria-label="Afbeelding toevoegen"
>
  <Paperclip className="h-5 w-5" aria-hidden="true" />
</Button>
```

Add image preview above the input row (inside the `flex-col gap-2` div, before the voice status indicator):
```tsx
{imageAttachment && (
  <div className="relative inline-block">
    <img
      src={imageAttachment.data}
      alt={imageAttachment.filename || 'Bijlage'}
      className="h-20 w-20 object-cover rounded-md border"
    />
    <button
      onClick={removeAttachment}
      className="absolute -top-2 -right-2 h-5 w-5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center text-xs"
      aria-label="Bijlage verwijderen"
    >
      <X className="h-3 w-3" />
    </button>
  </div>
)}
```

Add `Paperclip` and `X` to the lucide-react imports (line 4):
```typescript
import { Send, Mic, MicOff, Loader2, Paperclip, X } from 'lucide-react';
```

#### 2. Extend ChatMessage rendering for images
**File**: `HAI/src/components/chat/ChatMessage.tsx`
**Changes**: Render image attachment above the text content in user message bubbles.

Inside the message bubble div (after line 74, before the conditional rendering of spoken comparison / standard mode), add:
```tsx
{isUser && message.imageAttachment && (
  <div className="mb-2">
    <img
      src={message.imageAttachment.data}
      alt={message.imageAttachment.filename || 'Bijlage'}
      className="max-w-full max-h-48 rounded-md object-contain"
    />
  </div>
)}
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript type checking passes: `cd HAI && pnpm run type-check`
- [x] All existing tests pass: `cd HAI && pnpm run test`
- [x] Linting passes: `cd HAI && pnpm run lint`

#### Manual Verification:
- [ ] Attachment button (paperclip) appears next to the input
- [ ] Clicking attachment button opens file picker
- [ ] On mobile: camera option is offered alongside file picker
- [ ] Selected image shows as thumbnail preview with X button to remove
- [ ] Clicking X removes the preview
- [ ] Can send message with image only (no text)
- [ ] Can send message with image + text
- [ ] Sending clears both text and image preview
- [ ] Image appears in the chat message bubble

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 3: Frontend Message Pipeline (WebSocket, Hook, Store)

### Overview
Thread the image attachment through the full frontend message pipeline: `App.tsx` → `useWebSocket.sendMessage` → `client.sendRunInput` → WebSocket/offline buffer.

### Changes Required:

#### 1. Update App.tsx handler
**File**: `HAI/src/App.tsx`
**Changes**: Update `handleSendMessage` to accept and forward the optional image attachment.

Replace lines 112-114:
```typescript
const handleSendMessage = (message: string, imageAttachment?: { data: string; mimeType: string; filename?: string }) => {
  sendMessage(message, imageAttachment);
};
```

#### 2. Update ChatInterface prop threading
**File**: `HAI/src/components/chat/ChatInterface.tsx`
**Changes**: Update the `onSendMessage` prop type to match the new signature. The prop is passed directly to `ChatInput`'s `onSend`, so the types must align.

Update the props interface:
```typescript
interface ChatInterfaceProps {
  onSendMessage: (message: string, imageAttachment?: { data: string; mimeType: string; filename?: string }) => void;
  // ... rest unchanged
}
```

#### 3. Update useWebSocket hook
**File**: `HAI/src/hooks/useWebSocket.ts`
**Changes**: Update `sendMessage` to accept optional image attachment. Thread it to both `addMessage` (for UI) and `sendRunInput` (for WebSocket).

Replace lines 378-392:
```typescript
const sendMessage = (content: string, imageAttachment?: { data: string; mimeType: string; filename?: string }) => {
  const userId = useUserStore.getState().currentUser?.id;
  if (!userId) {
    return;
  }
  if (clientRef.current && session) {
    addMessage({
      id: `msg-${Date.now()}-${Math.random()}`,
      role: 'user',
      content,
      imageAttachment,
    });
    clientRef.current.sendRunInput(session.id, userId, content, imageAttachment);
    updateActivity();
  }
};
```

#### 4. Update WebSocket client
**File**: `HAI/src/lib/websocket/client.ts`
**Changes**: Update `sendRunInput` to build multimodal content when an image is attached. Update offline buffer storage.

Replace lines 111-138:
```typescript
sendRunInput(
  threadId: string,
  userId: string,
  content: string,
  imageAttachment?: { data: string; mimeType: string; filename?: string }
): string {
  const runId = generateUUID();

  // Build message content: multimodal array if image attached, plain string otherwise
  const messageContent: string | Array<{ type: string; text?: string; mimeType?: string; data?: string; filename?: string }> =
    imageAttachment
      ? [
          ...(content ? [{ type: 'text' as const, text: content }] : []),
          { type: 'binary' as const, mimeType: imageAttachment.mimeType, data: imageAttachment.data, filename: imageAttachment.filename },
        ]
      : content;

  const input: RunAgentInput = {
    threadId,
    runId,
    userId,
    messages: [{ role: 'user', content: messageContent }],
  };

  if (this.ws?.readyState === WebSocket.OPEN) {
    this.sendRaw(JSON.stringify(input));
  } else {
    offlineBuffer.addMessage({
      id: runId,
      content,
      timestamp: Date.now(),
      threadId,
      userId,
      imageAttachment,
    }).then(() => {
      console.log('Message buffered offline');
    }).catch((error) => {
      console.error('Failed to buffer message:', error);
    });
  }

  return runId;
}
```

#### 5. Update offline buffer replay
**File**: `HAI/src/lib/websocket/client.ts`
**Changes**: Update the replay logic (lines 220-232) to reconstruct multimodal content from buffered messages.

Replace lines 224-229:
```typescript
const batchInput: RunAgentInput = {
  threadId: firstMessage.threadId,
  runId: generateUUID(),
  userId: firstMessage.userId,
  messages: buffered.map(m => {
    const messageContent = m.imageAttachment
      ? [
          ...(m.content ? [{ type: 'text' as const, text: m.content }] : []),
          { type: 'binary' as const, mimeType: m.imageAttachment.mimeType, data: m.imageAttachment.data, filename: m.imageAttachment.filename },
        ]
      : m.content;
    return { role: 'user' as const, content: messageContent };
  }),
};
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript type checking passes: `cd HAI && pnpm run type-check`
- [x] All existing tests pass: `cd HAI && pnpm run test`
- [x] Linting passes: `cd HAI && pnpm run lint`

#### Manual Verification:
- [ ] Sending a text-only message works exactly as before (no regressions)
- [ ] Sending a message with an image sends multimodal content over WebSocket (verify in browser DevTools → Network → WS frames)
- [ ] The WebSocket frame for image messages contains `content: [{ type: "text", ... }, { type: "binary", ... }]`
- [ ] The WebSocket frame for text-only messages contains `content: "string"` (unchanged)
- [ ] Image messages sent while offline are correctly buffered and replayed on reconnect

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 4: Backend Multimodal Content Parsing

### Overview
Update both orchestrators to detect and handle multimodal content arrays. Phase 1: inject a hardcoded text placeholder for images. The agent signatures remain unchanged (they still receive text).

### Changes Required:

#### 1. Update server-openai orchestrator
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Replace the user content extraction logic (lines 124-128) to handle both string and array content.

Replace lines 124-128:
```python
        # Extract user message from input (supports multimodal content)
        user_content = ""
        for msg in agent_input.messages:
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                if isinstance(raw_content, list):
                    # Multimodal content array
                    text_parts = [
                        part["text"]
                        for part in raw_content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    has_image = any(
                        isinstance(part, dict) and part.get("type") == "binary"
                        for part in raw_content
                    )
                    user_content = "\n".join(text_parts)
                    if has_image:
                        user_content += "\n\n[De gebruiker heeft een afbeelding bijgevoegd. Beschrijf wat je ziet en help de gebruiker verder op basis van de context van het gesprek.]"
                else:
                    user_content = raw_content
                break
```

#### 2. Update server-langgraph orchestrator
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Replace the user content extraction logic (lines 145-150) to handle both string and array content.

Replace lines 145-150:
```python
        # Extract and join all user messages from input (supports multimodal content)
        user_contents = []
        for msg in agent_input.messages:
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                if isinstance(raw_content, list):
                    # Multimodal content array
                    text_parts = [
                        part["text"]
                        for part in raw_content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    has_image = any(
                        isinstance(part, dict) and part.get("type") == "binary"
                        for part in raw_content
                    )
                    text = "\n".join(text_parts)
                    if has_image:
                        text += "\n\n[De gebruiker heeft een afbeelding bijgevoegd. Beschrijf wat je ziet en help de gebruiker verder op basis van de context van het gesprek.]"
                    user_contents.append(text)
                else:
                    user_contents.append(raw_content)
        user_content = "\n".join(user_contents)
```

### Success Criteria:

#### Automated Verification:
- [x] server-openai tests pass: `cd server-openai && pytest`
- [x] server-langgraph tests pass: `cd server-langgraph && pytest`
- [x] Type checking passes: `cd server-openai && mypy src/` and `cd server-langgraph && mypy src/`

#### Manual Verification:
- [ ] Text-only messages are processed identically (no regressions)
- [ ] Image messages result in the hardcoded Dutch placeholder being appended to the extracted text
- [ ] The agent responds acknowledging the image context

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 5: Mock Server Image Handling

### Overview
Update the mock server to recognize and respond to image attachments, demonstrating the feature for frontend testing without a real backend.

### Changes Required:

#### 1. Update mock server message handling
**File**: `docs/hai-contract/mock_server.py`
**Changes**: Update `handle_run_input` to detect multimodal content and add an image-aware response scenario.

In the `handle_run_input` function (around line 849-853), update the user content extraction:
```python
    # Extract last user message content (supports multimodal)
    user_content = ""
    has_image = False
    for msg in reversed(messages):
        if msg.get("role") == "user":
            raw_content = msg.get("content", "")
            if isinstance(raw_content, list):
                text_parts = [
                    part["text"]
                    for part in raw_content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                has_image = any(
                    isinstance(part, dict) and part.get("type") == "binary"
                    for part in raw_content
                )
                user_content = " ".join(text_parts)
            else:
                user_content = raw_content
            break
```

Add an image response scenario handler. After the existing routing logic (around line 887-894), add a check for `has_image`:
```python
    if has_image:
        await handle_image_message(websocket, thread_id, run_id, state, user_content)
    elif is_inspection_start(user_content.lower()):
        # ... existing routing
```

Add the new handler function:
```python
async def handle_image_message(
    websocket: WebSocket,
    thread_id: str,
    run_id: str,
    state: ConversationState,
    user_text: str,
):
    """Handle messages that include an image attachment."""
    message_id = f"msg-{uuid.uuid4()}"

    await send_step_started(websocket, "thinking")

    response = (
        "Ik heb uw afbeelding ontvangen. "
    )

    if state.inspection_started:
        response += (
            "Op basis van de foto en de huidige inspectie kan ik het volgende opmerken:\n\n"
            "**Observatie**: De afbeelding toont een situatie die relevant kan zijn voor de inspectie. "
            "Ik zal dit meenemen in mijn analyse.\n\n"
        )
        if user_text:
            response += f"Uw opmerking: *\"{user_text}\"* is genoteerd bij deze observatie.\n\n"
        response += "Wilt u dat ik:\n- De relevante **regelgeving** opzoek?\n- Dit als **bevinding** vastleg in het rapport?\n- Verder ga met de inspectie?"
    else:
        response += (
            "Om de afbeelding goed te kunnen beoordelen, is het handig als u eerst een inspectie start. "
            "Probeer bijvoorbeeld: **\"Start inspectie bij Bella Rosa, Den Haag\"**"
        )

    content_chunks = split_into_chunks(response)
    await stream_response(
        websocket, thread_id, run_id, message_id,
        content_chunks, "general-agent"
    )
```

### Success Criteria:

#### Automated Verification:
- [x] Mock server starts without errors: `cd docs/hai-contract && python mock_server.py` (verify it binds to port 8000)

#### Manual Verification:
- [ ] Text-only messages to mock server work as before
- [ ] Sending an image message to mock server returns the image acknowledgment response
- [ ] During an active inspection, the image response offers relevant next steps
- [ ] Without an active inspection, the image response suggests starting one first

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding.

---

## Phase 6: Documentation Updates

### Overview
Update the AsyncAPI spec, JSON Schema, and protocol contract document to reflect multimodal content support.

### Changes Required:

#### 1. Update AsyncAPI Message schema
**File**: `docs/hai-contract/asyncapi.yaml`
**Changes**: Update the `Message` schema (lines 431-443) to accept multimodal content.

Replace the `content` property in the `Message` schema:
```yaml
    Message:
      type: object
      required:
        - role
        - content
      properties:
        role:
          type: string
          enum: [user, assistant, system, tool]
        content:
          oneOf:
            - type: string
              description: Plain text content
            - type: array
              description: Multimodal content parts
              items:
                oneOf:
                  - type: object
                    required: [type, text]
                    properties:
                      type:
                        type: string
                        const: text
                      text:
                        type: string
                  - type: object
                    required: [type, mimeType, data]
                    properties:
                      type:
                        type: string
                        const: binary
                      mimeType:
                        type: string
                        description: "MIME type (e.g., image/jpeg, image/png)"
                      data:
                        type: string
                        description: "Base64-encoded data URL"
                      filename:
                        type: string
                        description: "Original filename (optional)"
        id:
          type: string
        toolCallId:
          type: string
```

#### 2. Update JSON Schema Message definition
**File**: `docs/hai-contract/schemas/messages.json`
**Changes**: Update the `Message` definition (lines 143-152) to accept multimodal content.

Replace the `content` property:
```json
{
  "required": ["role", "content"],
  "properties": {
    "id": { "type": "string" },
    "role": { "$ref": "#/definitions/MessageRole" },
    "content": {
      "oneOf": [
        { "type": "string" },
        {
          "type": "array",
          "items": {
            "oneOf": [
              {
                "type": "object",
                "required": ["type", "text"],
                "properties": {
                  "type": { "const": "text" },
                  "text": { "type": "string" }
                }
              },
              {
                "type": "object",
                "required": ["type", "mimeType", "data"],
                "properties": {
                  "type": { "const": "binary" },
                  "mimeType": { "type": "string", "description": "MIME type (e.g., image/jpeg, image/png)" },
                  "data": { "type": "string", "description": "Base64-encoded data URL" },
                  "filename": { "type": "string", "description": "Original filename" }
                }
              }
            ]
          }
        }
      ]
    },
    "toolCallId": { "type": "string" }
  }
}
```

#### 3. Update protocol contract document
**File**: `docs/hai-contract/HAI_API_CONTRACT.md`
**Changes**: Add a section documenting multimodal message content support. Update the existing Message schema description.

Add a new section after the existing message documentation explaining:
- The `content` field now accepts either a string or an array of content parts
- Content part types: `text` (with `text` field) and `binary` (with `mimeType`, `data`, optional `filename`)
- Binary content is base64-encoded data URLs
- Maximum recommended image size: 2MB
- Supported MIME types: `image/jpeg`, `image/png`, `image/webp`, `image/gif`
- Backward compatibility: string content continues to work identically

Also add multimodal support to the AGORA Extensions section (around line 1312) as a new extension point.

### Success Criteria:

#### Automated Verification:
- [x] AsyncAPI YAML is valid: `cd docs/hai-contract && python -c "import yaml; yaml.safe_load(open('asyncapi.yaml'))"`
- [x] JSON Schema is valid: `cd docs/hai-contract && python -c "import json; json.load(open('schemas/messages.json'))"`

#### Manual Verification:
- [ ] AsyncAPI spec accurately describes the multimodal content format
- [ ] JSON Schema definition matches the AsyncAPI spec
- [ ] Contract document clearly explains the new capability
- [ ] Backward compatibility is explicitly documented

**Implementation Note**: After completing this phase, all documentation should be consistent and complete.

---

## Testing Strategy

### Unit Tests:
- **Zod schema tests**: Verify `MessageSchema` accepts both `string` and `ContentPart[]` content
- **Zod schema tests**: Verify `RunAgentInputSchema` validates multimodal messages
- **Offline buffer**: Verify `BufferedMessage` with `imageAttachment` can be stored and retrieved

### Integration Tests (Manual):
1. Send text-only message → verify identical behavior to current
2. Select image via file picker → verify preview appears
3. Remove image via X button → verify preview disappears
4. Send image + text → verify both appear in chat bubble
5. Send image only (no text) → verify image appears in chat bubble
6. Select image > 2MB → verify error message
7. Send image while offline → verify buffered and replayed on reconnect
8. Verify mock server responds to image messages
9. Verify both backends (server-openai, server-langgraph) handle multimodal content

### Edge Cases:
- Empty text with image attachment (image-only message)
- Very large image (2MB limit enforced client-side)
- Rapid sequential image messages
- Image message followed by text-only message
- Offline buffer with mix of text-only and image messages

## Performance Considerations

- **Client-side size limit**: 2MB max image size enforced before base64 encoding (~2.67MB encoded)
- **WebSocket frame size**: Base64 images in JSON are large but within practical WebSocket limits for single images
- **IndexedDB storage**: Base64 images in offline buffer consume significant space. IndexedDB has generous limits (typically 50MB+), but this is a concern for future multi-image support.
- **No image compression**: Phase 1 does not compress images client-side. Future phases should consider using Canvas API to resize/compress before encoding.

## References

- Research document: `thoughts/shared/research/2026-02-22-image-upload-multimodal-feasibility.md`
- Upstream AG-UI `BinaryInputContent`: `ag_ui/core/types.py:80-101` (in venv)
- Frontend entry point: `HAI/src/components/chat/ChatInput.tsx`
- Backend touchpoints: `server-openai/.../orchestrator.py:124-128`, `server-langgraph/.../orchestrator.py:145-150`
- Protocol specs: `docs/hai-contract/asyncapi.yaml`, `docs/hai-contract/schemas/messages.json`, `docs/hai-contract/HAI_API_CONTRACT.md`
- Mock server: `docs/hai-contract/mock_server.py`
