# Images in Chat History — Implementation Plan

## Overview

Fix image persistence in conversation history so that inspector-uploaded photos appear when reloading old chat sessions. Currently, images are stored in LangGraph's SQLite checkpoint but are discarded during history retrieval (`str(msg.content)` on multimodal messages) and the frontend has no image-aware history mapping. This plan covers the **server-langgraph** backend and **HAI** frontend only (server-openai is out of scope).

## Current State Analysis

**What already works:**
- Frontend captures images, sends them as `BinaryContentPart` with base64 data URLs over WebSocket
- LangGraph orchestrator extracts image parts, builds `HumanMessage(content=[{"type": "text", ...}, {"type": "image_url", ...}])` (`orchestrator.py:170-180`)
- `AsyncSqliteSaver` checkpointer persists the full `HumanMessage` including multimodal content lists
- During live sessions, images render correctly via `ChatMessage.imageAttachment` in the Zustand store

**What's broken:**
- `get_conversation_history` at `orchestrator.py:954-956` calls `str(msg.content)` on multimodal lists, producing a Python repr string instead of structured data
- The history API returns `{"role": "user", "content": "<python repr string>"}` — no image data
- Frontend `HistoryMessage` interface (`sessions.ts:27-34`) has no image field
- `fetchSessionHistory` mapping (`sessions.ts:129-137`) never sets `imageAttachment` on `ChatMessage` objects
- Mock server `get_mock_history()` (`mock_server.py:166-305`) has no multimodal history entries

### Key Discoveries:
- `sessions.ts:13-19` has a local `getBaseUrl()` that derives HTTP base URL from `VITE_WS_URL`. The shared `getApiBaseUrl()` from `env.ts:59` is the proper version that handles backend routing.
- The image endpoint needs no authentication — the backend doesn't enforce API keys on REST endpoints currently.
- `HistoryMessage` in the contract specs (`openapi.yaml:835-839`, `schemas/messages.json:71-74`) defines `content` as `type: string` only — needs updating.
- LangChain `BaseMessage` has a `.text` property (`base.py:263-290`) that extracts only text from multimodal content lists — we should NOT use it because it silently drops content, which would be confusing. Better to handle extraction explicitly.

## Desired End State

When an inspector uploads photos during a chat session and later reloads that session:
1. All uploaded images appear inline in the chat history, exactly as they did during the live session
2. Images are served via HTTP URLs (not embedded as base64 in the history API response)
3. The history API response includes an `image_attachment` field with `{ url, mimeType }` for user messages that had images
4. The mock server includes at least one multimodal history entry for testing

### Verification:
- Upload an image during a chat session → reload the page → image appears in the restored conversation
- Upload multiple images across several messages → all appear correctly after reload
- Sessions without images → history loads identically to current behavior (no regression)
- Mock server history endpoint returns image attachment data for the multimodal test entry

## What We're NOT Doing

- Fixing server-openai's `_extract_content()` (out of scope per user request)
- Lazy extraction of images from old sessions' checkpoints (forward-only fix)
- Image compression or resizing on the backend
- Authentication on the image serving endpoint
- Changing how images are stored in LangGraph checkpoints (the full data URL stays in the checkpoint for LLM access)

## Implementation Approach

**Forward-only eager save**: When the orchestrator receives images in `process_message`, save them to disk immediately alongside the existing evidence forwarding. During history retrieval, detect multimodal messages, extract text properly, and include image URLs pointing to the saved files. A new file-serving endpoint returns the saved images.

Images are saved with content-hash-based filenames (`{md5(b64_data)[:12]}.{ext}`) for deterministic, stable URLs. The same image always maps to the same file.

---

## Phase 1: Backend — Image Storage and Serving (server-langgraph)

### Overview
Save uploaded images to disk during message processing, serve them via a new HTTP endpoint, and update `get_conversation_history` to return image URLs for multimodal messages.

### Changes Required:

#### 1. Image Storage Utility
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Add a helper method to save images to disk and update `process_message` to call it

Add to the imports at the top of the file:

```python
import base64
import hashlib
from pathlib import Path
```

Add a class-level constant and helper method to `Orchestrator`:

```python
SESSION_IMAGES_DIR = Path("session_images")

def _save_session_images(
    self,
    session_id: str,
    image_parts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Save uploaded images to disk. Returns list of {filename, mime_type}."""
    images_dir = self.SESSION_IMAGES_DIR / session_id
    images_dir.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, str]] = []
    for img in image_parts:
        data_url = img.get("data", "")
        mime_type = img.get("mimeType", "image/jpeg")

        if "," not in data_url:
            continue
        _, b64_data = data_url.split(",", 1)

        try:
            image_bytes = base64.b64decode(b64_data)
        except Exception:
            log.warning("Failed to decode image base64 data")
            continue

        # Deterministic filename from content hash
        content_hash = hashlib.md5(image_bytes).hexdigest()[:12]
        ext = "jpg" if "jpeg" in mime_type else mime_type.split("/")[-1]
        filename = f"{content_hash}.{ext}"
        file_path = images_dir / filename

        if not file_path.exists():
            file_path.write_bytes(image_bytes)
            log.info(f"Saved session image {filename} for session {session_id} ({len(image_bytes)} bytes)")

        saved.append({"filename": filename, "mime_type": mime_type})

    return saved
```

In `process_message`, after the existing image forwarding block (the `if image_parts and self.reporting_url:` block), add:

```python
# Save images to disk for chat history persistence
if image_parts:
    self._save_session_images(thread_id, image_parts)
```

#### 2. Update `get_conversation_history` for Multimodal Messages
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Handle multimodal `HumanMessage.content` properly — extract text, construct image URLs

Replace the human message handling block (currently around lines 950-957):

From:
```python
if msg.type == "human":
    prev_was_ai_without_tools = False
    history.append(
        {
            "role": "user",
            "content": str(msg.content),
        }
    )
```

To:
```python
if msg.type == "human":
    prev_was_ai_without_tools = False

    if isinstance(msg.content, list):
        # Multimodal message — extract text and image info
        text_parts = [
            part.get("text", "")
            for part in msg.content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        content_text = "\n".join(text_parts)

        # Find saved image file for this message
        image_attachment = None
        for part in msg.content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                data_url = part.get("image_url", {}).get("url", "")
                mime_type = "image/jpeg"
                if data_url.startswith("data:"):
                    mime_header = data_url.split(",")[0]
                    if "image/" in mime_header:
                        mime_type = mime_header.split(":", 1)[1].split(";")[0]

                # Derive filename from content hash (same as save logic)
                if "," in data_url:
                    _, b64_data = data_url.split(",", 1)
                    try:
                        image_bytes = base64.b64decode(b64_data)
                        content_hash = hashlib.md5(image_bytes).hexdigest()[:12]
                        ext = "jpg" if "jpeg" in mime_type else mime_type.split("/")[-1]
                        filename = f"{content_hash}.{ext}"
                        file_path = self.SESSION_IMAGES_DIR / thread_id / filename
                        if file_path.exists():
                            image_attachment = {
                                "url": f"/sessions/{thread_id}/images/{filename}",
                                "mimeType": mime_type,
                            }
                    except Exception:
                        pass
                break  # Only first image per message

        entry: dict[str, Any] = {"role": "user", "content": content_text}
        if image_attachment:
            entry["image_attachment"] = image_attachment
        history.append(entry)
    else:
        history.append(
            {
                "role": "user",
                "content": str(msg.content),
            }
        )
```

#### 3. Image Serving Endpoint
**File**: `server-langgraph/src/agora_langgraph/api/server.py`
**Changes**: Add a `GET /sessions/{session_id}/images/{filename}` endpoint

Add these imports at the top:
```python
from pathlib import Path
from fastapi.responses import FileResponse
```

Add the endpoint after the existing session endpoints (after `delete_session`):

```python
SESSION_IMAGES_DIR = Path("session_images")


@app.get("/sessions/{session_id}/images/{filename}")
async def get_session_image(session_id: str, filename: str) -> FileResponse:
    """Serve a saved session image file."""
    # Sanitize filename to prevent path traversal
    safe_filename = Path(filename).name
    file_path = SESSION_IMAGES_DIR / session_id / safe_filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    # Derive content type from extension
    ext = file_path.suffix.lower()
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    return FileResponse(file_path, media_type=content_type)
```

#### 4. Add `session_images/` to `.gitignore`
**File**: `server-langgraph/.gitignore`
**Changes**: Add `session_images/` to prevent committing uploaded images

### Success Criteria:

#### Automated Verification:
- [x] Python syntax check passes for all changed files
- [ ] Server starts without import errors: `cd server-langgraph && python -m agora_langgraph.api.server`
- [x] Existing tests still pass: `cd server-langgraph && pytest`
- [ ] Image endpoint returns 404 for non-existent image: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/sessions/test/images/nonexistent.jpg` → 404

#### Manual Verification:
- [ ] Send a message with an image via the chat → check `session_images/{session_id}/` directory exists with the image file
- [ ] Call `GET /sessions/{session_id}/history` → response contains `image_attachment` with URL for the image message
- [ ] Call `GET /sessions/{session_id}/images/{filename}` → image is served correctly
- [ ] Non-image messages in history still return plain `content` strings (no regression)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Frontend — History Image Rendering (HAI)

### Overview
Update the frontend to recognize image attachments in history API responses and render them in restored chat conversations.

### Changes Required:

#### 1. Update `HistoryMessage` Interface
**File**: `HAI/src/lib/api/sessions.ts`
**Changes**: Add optional `image_attachment` field to `HistoryMessage`

Update the interface (lines 27-34):

```typescript
interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool_call' | 'tool';
  content: string;
  tool_name?: string;
  tool_call_id?: string;
  agent_id?: string;
  spoken_text?: string;
  image_attachment?: {
    url: string;
    mimeType: string;
  };
}
```

#### 2. Update History-to-ChatMessage Mapping
**File**: `HAI/src/lib/api/sessions.ts`
**Changes**: Populate `imageAttachment` when `image_attachment` is present in the history response

In the `fetchSessionHistory` function, update the mapping for user/assistant messages (around lines 126-138).

Replace the existing `sessions.ts` local `getBaseUrl()` usage: import `getApiBaseUrl` from `@/lib/env` instead of using the local copy. Add at the top of the file:

```typescript
import { getApiBaseUrl } from '@/lib/env';
```

Update the user/assistant message mapping:

```typescript
if (msg.role === 'user' || msg.role === 'assistant') {
  const chatMessage: ChatMessage = {
    id: `history-${sessionId}-${messageIndex}`,
    role: msg.role,
    content: msg.content,
    agentId: msg.agent_id,
    spokenContent: msg.spoken_text,
    timestamp: new Date(),
    isStreaming: false,
  };

  // Reconstruct image attachment from history
  if (msg.image_attachment) {
    chatMessage.imageAttachment = {
      data: `${getApiBaseUrl()}${msg.image_attachment.url}`,
      mimeType: msg.image_attachment.mimeType,
    };
  }

  messages.push(chatMessage);
  messageIndex++;
}
```

This works because `<img src>` in `ChatMessage.tsx:79` handles both `data:` URLs (live session) and `http://` URLs (history) natively.

### Success Criteria:

#### Automated Verification:
- [x] TypeScript type check passes: `cd HAI && pnpm run type-check`
- [x] Linting passes: `cd HAI && pnpm run lint`
- [x] Tests pass: `cd HAI && pnpm run test`
- [x] Build succeeds: `cd HAI && pnpm run build`

#### Manual Verification:
- [ ] Start the full stack (MCP servers + langgraph orchestrator + HAI)
- [ ] Send a message with an image during a chat session → image appears inline
- [ ] Reload the page → session history loads with the image visible in the correct position
- [ ] Send multiple messages with images → all appear correctly after reload
- [ ] Sessions without images → history loads normally (no regression)
- [ ] Image proportions and styling match the live session rendering

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Documentation and Mock Server Updates

### Overview
Update the mock server to include a multimodal history entry for testing, and update the protocol documentation and schemas to reflect `image_attachment` support in history messages.

### Changes Required:

#### 1. Mock Server — Add Image History Entry and Endpoint
**File**: `docs/hai-contract/mock_server.py`
**Changes**: Add a multimodal entry to `get_mock_history()`, add an image serving endpoint, and save a test image on startup

Add a small test image (a 1x1 pixel JPEG) as a constant and save it on startup:

```python
import base64 as b64_module

# Minimal 1x1 JPEG for mock image history
MOCK_IMAGE_B64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AVQH/2Q=="
MOCK_IMAGE_FILENAME = "mock_test_image.jpg"
```

In the server startup (inside `lifespan` or at module level), save this image:

```python
mock_images_dir = Path("session_images/session-koen-bella-rosa")
mock_images_dir.mkdir(parents=True, exist_ok=True)
mock_image_path = mock_images_dir / MOCK_IMAGE_FILENAME
if not mock_image_path.exists():
    mock_image_path.write_bytes(b64_module.b64decode(MOCK_IMAGE_B64))
```

Add a multimodal history entry to `get_mock_history()` for the `session-koen-bella-rosa` session. Insert it as a user message in the conversation (e.g., after the initial inspection start):

```python
{
    "role": "user",
    "content": "Ik zie dit in de keuken, er liggen vuile pannen op het aanrecht.",
    "image_attachment": {
        "url": f"/sessions/session-koen-bella-rosa/images/{MOCK_IMAGE_FILENAME}",
        "mimeType": "image/jpeg",
    },
},
```

Add a file-serving endpoint for mock session images:

```python
@app.get("/sessions/{session_id}/images/{filename}")
async def get_session_image(request):
    session_id = request.path_params["session_id"]
    filename = request.path_params["filename"]
    safe_filename = Path(filename).name
    file_path = Path(f"session_images/{session_id}") / safe_filename

    if not file_path.exists():
        return JSONResponse({"error": "Image not found"}, status_code=404)

    from starlette.responses import FileResponse
    ext = file_path.suffix.lower()
    content_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    return FileResponse(file_path, media_type=content_types.get(ext, "application/octet-stream"))
```

#### 2. Update OpenAPI Spec
**File**: `docs/hai-contract/openapi.yaml`
**Changes**: Add `image_attachment` to `HistoryMessage` schema

In the `HistoryMessage` schema properties (around line 835), add:

```yaml
image_attachment:
  type: object
  nullable: true
  description: Image attachment for messages that included uploaded photos
  properties:
    url:
      type: string
      description: Relative URL to retrieve the image file
      example: "/sessions/{session_id}/images/abc123def456.jpg"
    mimeType:
      type: string
      description: MIME type of the image
      example: "image/jpeg"
  required:
    - url
    - mimeType
```

Also add the new image endpoint:

```yaml
/sessions/{session_id}/images/{filename}:
  get:
    summary: Get session image
    description: Serve a saved session image file (evidence photo uploaded during chat)
    parameters:
      - name: session_id
        in: path
        required: true
        schema:
          type: string
      - name: filename
        in: path
        required: true
        schema:
          type: string
    responses:
      '200':
        description: Image file
        content:
          image/jpeg:
            schema:
              type: string
              format: binary
          image/png:
            schema:
              type: string
              format: binary
      '404':
        description: Image not found
```

#### 3. Update JSON Schema
**File**: `docs/hai-contract/schemas/messages.json`
**Changes**: Add `image_attachment` to `HistoryMessage` definition

In the `HistoryMessage` `properties` object (around line 71), add:

```json
"image_attachment": {
  "type": "object",
  "description": "Image attachment for messages that included uploaded photos",
  "properties": {
    "url": {
      "type": "string",
      "description": "Relative URL to retrieve the image file"
    },
    "mimeType": {
      "type": "string",
      "description": "MIME type of the image"
    }
  },
  "required": ["url", "mimeType"]
}
```

#### 4. Update HAI API Contract
**File**: `docs/hai-contract/HAI_API_CONTRACT.md`
**Changes**: Update the history endpoint documentation to mention `image_attachment` and add a multimodal history example

In the history endpoint section (around lines 150-163), add an example showing a message with `image_attachment`:

```json
{
  "role": "user",
  "content": "Ik zie dit in de keuken, er liggen vuile pannen op het aanrecht.",
  "image_attachment": {
    "url": "/sessions/session-abc/images/a1b2c3d4e5f6.jpg",
    "mimeType": "image/jpeg"
  }
}
```

Add a note explaining that `image_attachment` is present on user messages that included uploaded photos, and that the URL is relative to the server base URL.

In the changelog section, add a new entry for this version.

### Success Criteria:

#### Automated Verification:
- [ ] Mock server starts without errors: `cd docs/hai-contract && python mock_server.py`
- [ ] Mock server health check passes: `curl http://localhost:8000/health`
- [ ] Mock history includes image_attachment: `curl http://localhost:8000/sessions/session-koen-bella-rosa/history | python -m json.tool | grep image_attachment`
- [ ] Mock image endpoint serves file: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/sessions/session-koen-bella-rosa/images/mock_test_image.jpg` → 200

#### Manual Verification:
- [ ] Start mock server + HAI frontend → navigate to the Bella Rosa session → image appears in history
- [ ] OpenAPI spec validates without errors
- [ ] HAI_API_CONTRACT.md accurately describes the new field

---

## Testing Strategy

### Unit Tests:

#### Orchestrator image save:
- `test_save_session_images` — saves image to disk, returns metadata with correct filename
- `test_save_session_images_deterministic` — same image content produces same filename
- `test_save_session_images_dedup` — saving same image twice doesn't overwrite
- `test_save_session_images_invalid_data` — gracefully handles invalid base64

#### History retrieval with images:
- `test_history_multimodal_message` — multimodal HumanMessage returns text content + image_attachment
- `test_history_text_only_message` — plain string HumanMessage returns text content, no image_attachment
- `test_history_image_not_on_disk` — multimodal message without saved file returns text only (no crash)

### Integration Tests:
- Send image via WebSocket → retrieve history via REST → verify image_attachment URL → fetch image → verify file content

### Manual Testing Steps:
1. Start full stack: langgraph orchestrator + MCP servers + HAI
2. Open HAI, start a conversation
3. Upload a photo with text "Vuile keuken" → verify image renders
4. Send 2 more text messages
5. Upload another photo with text "Kapotte koeling"
6. Reload the page → verify both photos appear in the correct message positions
7. Start a new session without images → verify no regression
8. Switch between the two sessions → images persist correctly

## Performance Considerations

- **Image save is synchronous** in `_save_session_images` but fast (disk write of ≤2MB). Could be made async if needed, but not worth the complexity now.
- **History retrieval computes MD5 hashes** of image data from checkpoint content. For sessions with many images this adds negligible overhead (<1ms per image).
- **Image serving uses `FileResponse`** which streams directly from disk — efficient for large files.
- **No caching headers** on image endpoint initially — could add `Cache-Control` if needed.

## Migration Notes

- No database migrations needed — purely file-based storage
- Existing sessions without saved images will NOT show images in history (forward-only fix)
- The `session_images/` directory is created lazily — no manual setup required
- Docker volume mounts should include `session_images/` for persistence across container restarts

## References

- Evidence images plan: `thoughts/shared/plans/2026-03-01-images-in-pdf-report.md`
- Research: `thoughts/shared/research/2026-03-01-images-in-pdf-report.md`
- Multimodal feasibility: `thoughts/shared/research/2026-02-22-image-upload-multimodal-feasibility.md`
- Current image extraction: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:148-186`
- Current history retrieval: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:925-1028`
- Frontend history loading: `HAI/src/lib/api/sessions.ts:95-178`
- Mock server: `docs/hai-contract/mock_server.py`
