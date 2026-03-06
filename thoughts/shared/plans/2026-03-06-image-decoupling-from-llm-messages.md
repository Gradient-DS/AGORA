# Image Decoupling from LLM Messages Implementation Plan

## Overview

Decouple images from LLM conversation messages so they are only used in the report. Instead of embedding images as multimodal content in `HumanMessage` objects (which causes spoken/written stream divergence), images become a side-channel: saved to disk, forwarded to reporting, and described in the background by a vision LLM. The conversational LLM never sees raw image data.

## Current State Analysis

Currently, when a user attaches an image:
1. The orchestrator builds a multimodal `HumanMessage` with `image_url` content parts (`orchestrator.py:157-168`)
2. This multimodal message enters LangGraph state and is checkpointed
3. The graph must strip images for the spoken model (`graph.py:411-430`), creating context divergence
4. Chat history reconstruction parses base64 from checkpointed multimodal messages (`orchestrator.py:1073-1114`)

Images are already separately forwarded to reporting (`orchestrator.py:500-526`) and saved to disk (`orchestrator.py:80-116`). These side-channels stay unchanged.

### Key Discoveries:
- Image stripping for spoken stream at `graph.py:411-430` becomes dead code after this change
- The reporting MCP already stores images with captions (`file_storage.py:68-110`) but has no `description` field
- PDF evidence appendix renders caption as `"Foto {i}: {caption}"` (`pdf_generator.py:406-409`)
- Chat history reconstruction decodes base64 from checkpointed messages to find saved files (`orchestrator.py:1084-1108`) — this is fragile and will simplify
- `server-openai` has identical image handling (`server-openai/orchestrator.py:125-177`) — needs same changes

## Desired End State

After implementation:
- Images are **never** included as content parts in `HumanMessage` objects sent to the LLM
- Both written and spoken models receive **identical text-only messages** (no stripping needed)
- A background vision LLM call generates a Dutch-language description of each image
- The description is forwarded to the reporting MCP and included in the PDF report
- Chat history still displays images via metadata-based references (not by parsing multimodal checkpoint data)
- The image is still saved to disk and forwarded to reporting (existing behavior)

### Verification:
- Send a message with an image attached — the LLM should respond based on text only, not referencing image content
- The spoken and written streams should have identical context (no `[De gebruiker heeft een afbeelding bijgevoegd.]` placeholder)
- The PDF report should include the image with an AI-generated description
- Chat history reload should still display the image thumbnail

## What We're NOT Doing

- Changing the frontend image upload/display logic (stays as-is)
- Changing the WebSocket protocol or AG-UI message format (frontend still sends `binary` content parts)
- Adding multi-image support per message (keeping current single-image behavior)
- Adding image compression or resizing
- Exposing the AI-generated description to the user in the chat UI

## Implementation Approach

Work back-to-front: start with the reporting MCP (description storage), then modify the orchestrators (stop multimodal, add background description), then clean up the graph (remove stripping), and finally simplify chat history.

---

## Phase 1: Reporting MCP — Add Description Support

### Overview
Extend the reporting MCP server to accept and store an AI-generated `description` field alongside images, and render it in the PDF.

### Changes Required:

#### 1. Image Upload Endpoint
**File**: `mcp-servers/reporting/server.py`
**Changes**: Accept optional `description` field in the image upload JSON body, and add a new PATCH endpoint to update the description after upload.

At the `upload_evidence_image` function (line 465), add `description` extraction:

```python
# After line 478:
description = body.get("description", "")
```

Pass `description` to `storage.save_image()`:
```python
# Line 495, add description parameter:
result = storage.save_image(session_id, image_bytes, "", caption, mime_type, description=description)
```

Add a new PATCH endpoint to update the description after the initial upload (needed because the background description task completes after the image is already forwarded):

```python
@mcp.custom_route("/reports/{session_id}/images/{image_index}/description", methods=["PATCH"])
async def update_image_description(request: Request) -> JSONResponse:
    """Update the AI-generated description for an evidence image."""
    session_id = request.path_params.get("session_id")
    image_index = int(request.path_params.get("image_index", "0"))

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    description = body.get("description", "")
    if not description:
        return JSONResponse({"error": "description is required"}, status_code=400)

    success = storage.update_image_description(session_id, image_index, description)
    if not success:
        return JSONResponse({"error": "Image not found"}, status_code=404)

    return JSONResponse({"success": True}, status_code=200)
```

#### 2. File Storage — Add Description to Manifest
**File**: `mcp-servers/reporting/storage/file_storage.py`
**Changes**: Add `description` field to manifest entries and add `update_image_description` method.

In `save_image()` (line 68), add `description` parameter and include in manifest entry:

```python
def save_image(self, session_id: str, image_bytes: bytes, filename: str, caption: str, mime_type: str = "image/jpeg", description: str = "") -> dict | None:
```

Add to the entry dict (after line 102):
```python
"description": description,
```

Add new method:
```python
def update_image_description(self, session_id: str, image_index: int, description: str) -> bool:
    """Update the AI-generated description for an image in the manifest."""
    session_dir = self._get_session_dir(session_id)
    manifest_path = session_dir / "images" / "manifest.json"

    if not manifest_path.exists():
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for entry in manifest:
        if entry.get("index") == image_index:
            entry["description"] = description
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            return True

    return False
```

#### 3. PDF Generator — Include Description
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: In `_create_evidence_appendix()` (line 379), render the description below the caption.

```python
# After line 409 (caption_text), add description rendering:
description = img_info.get("description", "")
description_el = None
if description:
    description_el = Paragraph(
        f"<i>{description}</i>",
        self.styles['Normal']
    )

# Update KeepTogether block (lines 412-416):
keep_elements = [rl_image, Spacer(1, 0.2*cm), caption_text]
if description_el:
    keep_elements.append(Spacer(1, 0.1*cm))
    keep_elements.append(description_el)
elements.append(KeepTogether(keep_elements))
```

### Success Criteria:

#### Automated Verification:
- [x] Reporting MCP server starts without errors
- [x] `POST /reports/{session_id}/images` still works with existing payload (description is optional)
- [x] `PATCH /reports/{session_id}/images/{index}/description` returns 200 with valid description
- [x] `PATCH` returns 404 for non-existent image
- [x] Generated PDF includes description text below image caption when description is present
- [x] Generated PDF works normally when no description is provided

#### Manual Verification:
- [ ] Verify PDF formatting looks good with description text

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation.

---

## Phase 2: LangGraph Orchestrator — Stop Multimodal, Add Background Description

### Overview
Stop building multimodal `user_llm_content`. Always pass text-only content to the LLM. Add a background task that describes images using a vision LLM and forwards the description to reporting.

### Changes Required:

#### 1. Simplify Message Parsing
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Remove multimodal content building (lines 157-168). Always use text-only content.

Replace lines 135-173 with:

```python
# Extract user messages — always text-only for the LLM
user_text_parts: list[str] = []
image_parts: list[dict[str, Any]] = []
for msg in agent_input.messages:
    if msg.get("role") == "user":
        raw_content = msg.get("content", "")
        if isinstance(raw_content, list):
            # Multimodal content array — extract text and image parts separately
            text_parts = [
                part["text"]
                for part in raw_content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            image_parts = [
                part
                for part in raw_content
                if isinstance(part, dict) and part.get("type") == "binary"
            ]
            user_text_parts.append("\n".join(text_parts))
        else:
            user_text_parts.append(raw_content)

# Text-only content for both LLM and logging
user_content = "\n".join(user_text_parts)
```

#### 2. Update Graph Input Construction
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: At lines 307-314, replace `user_llm_content` with `user_content` (now always a plain string).

```python
# Line 308 and 314: use user_content instead of user_llm_content
"messages": [HumanMessage(content=user_content)],
```

#### 3. Store Image References in HumanMessage Metadata
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: After saving images to disk, store references in the `HumanMessage.additional_kwargs` so chat history can find them without parsing base64.

After the existing image save block (line 188-190), capture the saved filenames:

```python
# Save images to disk for chat history persistence
saved_images: list[dict[str, str]] = []
if image_parts:
    saved_images = self._save_session_images(thread_id, image_parts)
```

Then at lines 307-314 where the `HumanMessage` is constructed, include image refs:

```python
human_msg = HumanMessage(content=user_content)
if saved_images:
    human_msg.additional_kwargs["image_refs"] = saved_images

# Use human_msg in graph_input:
graph_input = {
    "messages": [human_msg],
    ...
}
```

#### 4. Add Background Image Description Task
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Add a new method `_describe_and_update_images()` and launch it as a background task.

Add after `_forward_images_to_reporting()` (after line 526):

```python
async def _describe_and_update_images(
    self,
    session_id: str,
    image_parts: list[dict[str, Any]],
) -> None:
    """Generate AI descriptions for images and update reporting server."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.api_key,
        max_tokens=300,
    )

    for i, img in enumerate(image_parts):
        data_url = img.get("data", "")
        if not data_url:
            continue

        try:
            response = await llm.ainvoke([
                HumanMessage(content=[
                    {"type": "text", "text": (
                        "Beschrijf deze foto kort in het Nederlands (max 2 zinnen). "
                        "Dit is een inspectie-foto gemaakt door een NVWA-inspecteur. "
                        "Focus op wat zichtbaar is dat relevant kan zijn voor "
                        "voedselveiligheid of compliance."
                    )},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ])
            ])
            description = response.content if isinstance(response.content, str) else str(response.content)

            # Update the reporting MCP server with the description
            if self.reporting_url:
                url = f"{self.reporting_url}/reports/{session_id}/images/{i}/description"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.patch(url, json={"description": description})
                    if resp.status_code == 200:
                        log.info(f"Updated image {i} description for session {session_id}")
                    else:
                        log.warning(f"Failed to update image description: {resp.status_code}")
        except Exception as e:
            log.warning(f"Failed to describe image {i}: {e}")
```

Launch it as a background task in `process_message()`, after the existing image forwarding (after line 190):

```python
# Generate AI descriptions for images in the background
if image_parts and self.reporting_url:
    asyncio.create_task(
        self._describe_and_update_images(
            session_id=thread_id,
            image_parts=image_parts,
        )
    )
```

### Success Criteria:

#### Automated Verification:
- [x] Server starts without import errors
- [x] `pytest` passes (existing tests should still work since text-only messages are a subset of what was supported)
- [x] `mypy src/` passes (no new errors introduced; pre-existing errors remain)
- [x] `ruff check src/` passes (no new errors introduced; pre-existing E501s remain)

#### Manual Verification:
- [ ] Send a message with an image — the LLM responds based on text only (no image analysis in response)
- [ ] Both written and spoken outputs have consistent context
- [ ] Image appears in the PDF report with an AI-generated description
- [ ] Chat history reload still shows the image

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation.

---

## Phase 3: Graph Cleanup — Remove Image Stripping

### Overview
Remove the now-dead image-stripping logic from `_create_parallel_sends()` since `HumanMessage.content` is always a plain string.

### Changes Required:

#### 1. Remove Image Stripping Block
**File**: `server-langgraph/src/agora_langgraph/core/graph.py`
**Changes**: Delete lines 411-430 (the image stripping block) and use `messages` directly for both streams.

Replace the spoken message building (lines 411-430) and the Send dispatches (lines 432-456) with:

```python
# Both models receive identical text-only messages
return [
    Send(
        "generate_written",
        GeneratorState(
            messages=messages,
            system_prompt=written_prompt,
            stream_type="written",
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata,
        ),
    ),
    Send(
        "generate_spoken",
        GeneratorState(
            messages=messages,  # Same messages — no stripping needed
            system_prompt=spoken_prompt,
            stream_type="spoken",
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata,
        ),
    ),
]
```

### Success Criteria:

#### Automated Verification:
- [x] `pytest` passes (11 passed, 1 pre-existing failure)
- [x] `mypy src/` passes (no new errors)
- [x] No references to `image_url` stripping remain in `graph.py`

#### Manual Verification:
- [ ] Send image + text message — both spoken and written responses are coherent and consistent
- [ ] No `[De gebruiker heeft een afbeelding bijgevoegd.]` placeholder in spoken output

---

## Phase 4: Chat History Simplification

### Overview
Simplify chat history reconstruction to use `additional_kwargs["image_refs"]` instead of parsing base64 from multimodal checkpoint data.

### Changes Required:

#### 1. Simplify History Reconstruction
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Replace lines 1073-1114 (multimodal message parsing) with metadata-based lookup.

```python
if msg.type == "human":
    prev_was_ai_without_tools = False
    content_text = extract_text(msg.content)

    # Check for image refs in metadata (new approach)
    image_attachment = None
    image_refs = msg.additional_kwargs.get("image_refs", []) if hasattr(msg, "additional_kwargs") else []
    if image_refs:
        ref = image_refs[0]  # First image
        filename = ref.get("filename", "")
        mime_type = ref.get("mime_type", "image/jpeg")
        file_path = self.SESSION_IMAGES_DIR / thread_id / filename
        if file_path.exists():
            image_attachment = {
                "url": f"/sessions/{thread_id}/images/{filename}",
                "mimeType": mime_type,
            }

    # Fallback: check for legacy multimodal messages (backward compatibility)
    if not image_attachment and isinstance(msg.content, list):
        for part in msg.content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                data_url = part.get("image_url", {}).get("url", "")
                mime_type = "image/jpeg"
                if data_url.startswith("data:"):
                    mime_header = data_url.split(",")[0]
                    if "image/" in mime_header:
                        mime_type = mime_header.split(":", 1)[1].split(";")[0]
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
                break

    entry: dict[str, Any] = {"role": "user", "content": content_text}
    if image_attachment:
        entry["image_attachment"] = image_attachment
    history.append(entry)
```

Note: The legacy fallback block handles existing sessions that already have multimodal messages checkpointed from before this change. It can be removed once all existing sessions have expired.

### Success Criteria:

#### Automated Verification:
- [x] `pytest` passes (11 passed, 1 pre-existing failure)
- [x] `mypy src/` passes (no new errors)

#### Manual Verification:
- [ ] New sessions: image visible in chat history after page reload
- [ ] Existing sessions (with old multimodal checkpoints): image still visible via legacy fallback

---

## Phase 5: Server-OpenAI Parity

### Overview
Apply equivalent changes to the OpenAI orchestrator to maintain API parity.

### Changes Required:

#### 1. Simplify Message Parsing
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Remove multimodal content building (lines 149-161). Always use text-only `user_content`.

Replace the `if image_parts:` block (lines 149-163) with:
```python
user_llm_input = user_content
```

The image extraction (lines 142-146) stays to support forwarding/saving.

#### 2. Add Background Description Task
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Add the same `_describe_and_update_images()` method and launch it as a background task. The implementation is identical to the LangGraph version but uses `openai` client instead of `langchain_openai`:

```python
async def _describe_and_update_images(
    self,
    session_id: str,
    image_parts: list[dict[str, Any]],
) -> None:
    """Generate AI descriptions for images and update reporting server."""
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    for i, img in enumerate(image_parts):
        data_url = img.get("data", "")
        if not data_url:
            continue

        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": (
                            "Beschrijf deze foto kort in het Nederlands (max 2 zinnen). "
                            "Dit is een inspectie-foto gemaakt door een NVWA-inspecteur. "
                            "Focus op wat zichtbaar is dat relevant kan zijn voor "
                            "voedselveiligheid of compliance."
                        )},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
            )
            description = response.choices[0].message.content or ""

            if self.reporting_url:
                url = f"{self.reporting_url}/reports/{session_id}/images/{i}/description"
                async with httpx.AsyncClient(timeout=15.0) as http_client:
                    await http_client.patch(url, json={"description": description})
        except Exception as e:
            log.warning(f"Failed to describe image {i}: {e}")
```

### Success Criteria:

#### Automated Verification:
- [x] `pytest` passes for server-openai (21 passed)
- [x] `mypy src/` passes (no new errors)
- [x] `ruff check src/` passes (no new errors)

#### Manual Verification:
- [ ] Run with server-openai backend — same behavior as server-langgraph

---

## Testing Strategy

### Unit Tests:
- Test that `process_message` with image parts produces a text-only `HumanMessage`
- Test that `_describe_and_update_images` handles vision LLM errors gracefully
- Test that chat history reconstruction uses `additional_kwargs["image_refs"]` when present
- Test that chat history falls back to legacy multimodal parsing when `image_refs` is absent

### Integration Tests:
- End-to-end: send image message → verify text-only content in LangGraph state
- End-to-end: send image message → verify description appears in PDF report
- Verify both written and spoken streams receive identical messages

### Manual Testing Steps:
1. Send a text+image message and verify the LLM does not analyze the image in its response
2. Verify the spoken output does not mention an attached image placeholder
3. Generate a PDF report and verify the image appears with an AI-generated description
4. Reload the page and verify the image appears in chat history
5. Test with an existing session that has old multimodal checkpoints (backward compatibility)
6. Test with the vision LLM unavailable — verify the system still works, just without a description

## Performance Considerations

- Background description task adds a vision LLM call (~2-3s) but is fire-and-forget — does not block the conversation
- Removing multimodal content from `HumanMessage` **reduces** checkpoint size (no more base64 image data in state)
- Removing image stripping in `_create_parallel_sends` saves a small amount of processing per turn

## References

- Research document: `thoughts/shared/research/2026-03-06-image-decoupling-from-llm-messages.md`
- Spoken/written divergence analysis: `thoughts/shared/research/2026-03-01-spoken-written-divergence.md`
- Original image implementation plan: `thoughts/shared/plans/2026-02-22-image-upload-multimodal-support.md`
- Images in PDF report plan: `thoughts/shared/plans/2026-03-01-images-in-pdf-report.md`
