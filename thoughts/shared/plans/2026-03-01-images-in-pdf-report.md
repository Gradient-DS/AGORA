# Images in PDF Report — Implementation Plan

## Overview

Add the ability for inspector-uploaded photos to be automatically included in the generated HAP PDF report as a "Bewijsmateriaal" (Evidence) appendix. Images are already captured and sent through the chat pipeline; this plan bridges the gap between the existing multimodal chat and the reporting MCP server's PDF generator.

## Current State Analysis

**What already works:**
- Frontend: image capture via `<input type="file" accept="image/*" capture="environment">`, base64 encoding, 2MB limit (`HAI/src/components/chat/ChatInput.tsx:38-60`)
- AG-UI Protocol: `BinaryContentPart` with base64 data URL (`HAI/src/types/schemas.ts:207-223`)
- Both orchestrators: extract `image_parts` from messages, format for LLM (`server-openai/...orchestrator.py:130-156`, `server-langgraph/...orchestrator.py:151-176`)
- GPT-4o: processes images via vision

**What's missing:**
- Images never reach the reporting MCP server
- `HAPReport` model has no image fields
- `PDFGenerator` has no image rendering
- No storage for evidence images on the reporting server

### Key Discoveries:
- `FileStorage._get_session_dir()` creates `storage/reports/{session_id}/` lazily — images can be stored here even before a session is formally created (`file_storage.py:22-25`)
- ReportLab's `Image` flowable is already importable from `reportlab.platypus` (same package in use) and supports `BytesIO` + proportional scaling
- `MCPToolRegistry.server_urls` (server-openai, `mcp_tools.py:74`) and `MCPClientManager.server_urls` (server-langgraph, `mcp_client.py:25`) both store the raw base URLs like `http://localhost:5003`
- `python-multipart` is already in reporting's `requirements.txt` but `httpx` is not a declared dep of the orchestrators (it's available as a transitive dep of `openai`)
- Both `Orchestrator.__init__` signatures are identical: `(runner/graph, moderator, audit, session_metadata, user_manager)` — no MCP URL access currently

## Desired End State

When an inspector uploads photos during a chat session and later generates a report:
1. All uploaded images (max 5 per session) are automatically forwarded from the orchestrator to the reporting MCP server
2. The inspector's accompanying message text is used as the image caption
3. `generate_final_report` includes stored images as a "Bijlage: Bewijsmateriaal" (Appendix: Evidence) section at the end of the PDF
4. Each image is rendered at up to 14cm width with proportional scaling, grouped by upload order, with its caption below

### Verification:
- Upload 1-5 images during a chat session → all appear in the PDF appendix
- Upload 6+ images → only the first 5 are stored, 6th returns a "limit reached" response
- Upload 0 images → no appendix section in the PDF (identical to current behavior)
- Image captions show the text the inspector typed alongside the image
- Images without accompanying text get a default "Bewijsfoto" caption

## What We're NOT Doing

- Inline images within report sections (hygiene, food safety, etc.) — appendix only for now
- Image-to-violation linking (e.g., "this photo shows violation #3")
- Image compression/resizing on the server side (frontend already limits to 2MB)
- Image moderation (future concern)
- Storing images in the JSON report (only in PDF and on disk)
- Frontend changes (the existing upload pipeline is sufficient)

## Implementation Approach

Auto-attach via HTTP endpoint: The orchestrators POST images directly to the reporting MCP server when they detect binary content parts in incoming messages. This avoids routing image data through the LLM/agent tool call pipeline (which would be token-expensive and hit size limits). The PDF generator picks up stored images at report generation time.

---

## Phase 1: MCP Reporting Server — Image Storage & Upload Endpoint

### Overview
Add file-based image storage and an HTTP upload endpoint to the reporting MCP server. This phase makes the server capable of receiving and storing images, independent of whether any orchestrator sends them yet.

### Changes Required:

#### 1. FileStorage — Image Methods
**File**: `mcp-servers/reporting/storage/file_storage.py`
**Changes**: Add three methods for image storage

After the existing `save_pdf` method (line 66), add:

```python
def save_image(self, session_id: str, image_bytes: bytes, filename: str, caption: str, mime_type: str = "image/jpeg") -> dict | None:
    """Save an evidence image for a session. Returns image metadata or None if limit reached."""
    session_dir = self._get_session_dir(session_id)
    images_dir = session_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Load or create manifest
    manifest_path = images_dir / "manifest.json"
    manifest: list[dict] = []
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    # Enforce max 5 images
    if len(manifest) >= 5:
        logger.warning(f"Image limit reached for session {session_id} (max 5)")
        return None

    # Write image file
    index = len(manifest)
    ext = "jpg" if "jpeg" in mime_type else mime_type.split("/")[-1]
    img_filename = f"img_{index}.{ext}"
    img_path = images_dir / img_filename

    with open(img_path, "wb") as f:
        f.write(image_bytes)

    # Update manifest
    entry = {
        "index": index,
        "filename": img_filename,
        "caption": caption,
        "mime_type": mime_type,
        "size_bytes": len(image_bytes),
        "uploaded_at": datetime.now().isoformat(),
    }
    manifest.append(entry)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved evidence image {img_filename} for session {session_id} ({len(image_bytes)} bytes)")
    return entry

def load_images(self, session_id: str) -> list[dict]:
    """Load all evidence images for a session. Returns list of {metadata + 'path': str}."""
    session_dir = self._get_session_dir(session_id)
    manifest_path = session_dir / "images" / "manifest.json"

    if not manifest_path.exists():
        return []

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Add full file paths
    images_dir = session_dir / "images"
    for entry in manifest:
        entry["path"] = str(images_dir / entry["filename"])

    return manifest

def get_image_count(self, session_id: str) -> int:
    """Get the number of evidence images for a session."""
    session_dir = self.reports_path / session_id
    manifest_path = session_dir / "images" / "manifest.json"

    if not manifest_path.exists():
        return 0

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    return len(manifest)
```

#### 2. Server — Image Upload Endpoint
**File**: `mcp-servers/reporting/server.py`
**Changes**: Add a `POST /reports/{session_id}/images` endpoint and a `GET /reports/{session_id}/images` endpoint

Add these after the existing PDF download endpoint (line 452), before the `@mcp.resource` decorator:

```python
import base64

MAX_EVIDENCE_IMAGES = 5

@mcp.custom_route("/reports/{session_id}/images", methods=["POST"])
async def upload_evidence_image(request: Request) -> JSONResponse:
    """Upload an evidence image for an inspection report."""
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Session ID required"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    image_data = body.get("image_data", "")
    caption = body.get("caption", "Bewijsfoto")
    mime_type = body.get("mime_type", "image/jpeg")

    if not image_data:
        return JSONResponse({"error": "image_data is required"}, status_code=400)

    # Decode base64 data URL
    try:
        if "," in image_data:
            _, b64_data = image_data.split(",", 1)
        else:
            b64_data = image_data
        image_bytes = base64.b64decode(b64_data)
    except Exception:
        return JSONResponse({"error": "Invalid base64 image data"}, status_code=400)

    # Save image
    result = storage.save_image(session_id, image_bytes, "", caption, mime_type)

    if result is None:
        return JSONResponse({
            "error": "Image limit reached",
            "message": f"Maximaal {MAX_EVIDENCE_IMAGES} foto's per sessie.",
            "current_count": storage.get_image_count(session_id),
        }, status_code=409)

    return JSONResponse({
        "success": True,
        "image": result,
        "current_count": storage.get_image_count(session_id),
        "max_images": MAX_EVIDENCE_IMAGES,
    }, status_code=201)


@mcp.custom_route("/reports/{session_id}/images", methods=["GET"])
async def list_evidence_images(request: Request) -> JSONResponse:
    """List evidence images for a session."""
    session_id = request.path_params.get("session_id")
    if not session_id:
        return JSONResponse({"error": "Session ID required"}, status_code=400)

    images = storage.load_images(session_id)
    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "images": [
            {k: v for k, v in img.items() if k != "path"}
            for img in images
        ],
        "count": len(images),
        "max_images": MAX_EVIDENCE_IMAGES,
    })
```

### Success Criteria:

#### Automated Verification:
- [ ] Reporting server starts without errors: `cd mcp-servers && docker-compose up --build reporting`
- [ ] Health check passes: `curl http://localhost:5003/health`
- [ ] Upload image returns 201: `curl -X POST http://localhost:5003/reports/test-session/images -H 'Content-Type: application/json' -d '{"image_data":"data:image/jpeg;base64,/9j/4AAQ...","caption":"Test foto"}'`
- [ ] List images returns uploaded image: `curl http://localhost:5003/reports/test-session/images`
- [ ] 6th upload returns 409: upload 6 images and verify the 6th is rejected
- [ ] Image files exist on disk: check `storage/reports/test-session/images/img_0.jpg` and `manifest.json`

#### Manual Verification:
- [ ] Verify manifest.json contents are correct (caption, mime_type, timestamps)
- [ ] Verify image files are valid (open in image viewer)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: MCP Reporting Server — PDF Evidence Appendix

### Overview
Modify the PDF generator to render stored evidence images as an appendix section in the report. Modify `generate_final_report` to load images and pass them to the generator.

### Changes Required:

#### 1. PDFGenerator — Evidence Appendix Section
**File**: `mcp-servers/reporting/generators/pdf_generator.py`
**Changes**: Add `_create_evidence_appendix()` method and update `generate()` to accept images

Update the imports at the top of the file (line 9):

```python
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.platypus import Image as RLImage
```

Add `import base64` to the top imports.

Update the `generate()` method signature and add the evidence section (around line 49):

```python
def generate(self, report: HAPReport, evidence_images: list[dict] | None = None) -> bytes:
```

Before `doc.build(story)` (line 90), add:

```python
# Evidence appendix (after all other sections)
if evidence_images:
    story.append(PageBreak())
    story.extend(self._create_evidence_appendix(evidence_images))
```

Add the new method after `_create_footer` (after line 371):

```python
def _create_evidence_appendix(self, images: list[dict]) -> list:
    """Create evidence photos appendix."""
    elements = []

    elements.append(Paragraph("Bijlage: Bewijsmateriaal", self.styles['CustomTitle']))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Tijdens de inspectie zijn {len(images)} foto('s) vastgelegd.",
        self.styles['Normal']
    ))
    elements.append(Spacer(1, 0.5*cm))

    for i, img_info in enumerate(images, 1):
        img_path = img_info.get("path", "")
        caption = img_info.get("caption", "Bewijsfoto")

        try:
            rl_image = RLImage(img_path, width=14*cm, height=10*cm, kind='proportional')
        except Exception as e:
            logger.warning(f"Failed to load evidence image {img_path}: {e}")
            elements.append(Paragraph(
                f"<i>Foto {i}: kon niet worden geladen</i>",
                self.styles['Normal']
            ))
            elements.append(Spacer(1, 0.3*cm))
            continue

        caption_text = Paragraph(
            f"<b>Foto {i}:</b> {caption}",
            self.styles['Normal']
        )

        # Keep image + caption together across page breaks
        elements.append(KeepTogether([
            rl_image,
            Spacer(1, 0.2*cm),
            caption_text,
        ]))
        elements.append(Spacer(1, 0.5*cm))

    return elements
```

#### 2. generate_final_report — Load and Pass Images
**File**: `mcp-servers/reporting/server.py`
**Changes**: In `generate_final_report`, load stored images and pass to PDF generator

In the `generate_final_report` function, after `hap_report` is created (line 284) and before the generators run (line 286), add:

```python
# Load evidence images for this session
evidence_images = storage.load_images(session_id)
if evidence_images:
    logger.info(f"Including {len(evidence_images)} evidence images in PDF report")
```

Update the PDF generation line (line 287) from:
```python
pdf_content = pdf_generator.generate(hap_report)
```
to:
```python
pdf_content = pdf_generator.generate(hap_report, evidence_images=evidence_images if evidence_images else None)
```

Also update the return dict to include image count (in the return block starting at line 336):
```python
"evidence_images_count": len(evidence_images) if evidence_images else 0,
```

### Success Criteria:

#### Automated Verification:
- [ ] Reporting server starts without errors after changes
- [ ] Upload 2 test images to a session, then call `generate_final_report` (via MCP tool or curl)
- [ ] Generated PDF contains the evidence appendix section
- [ ] PDF without images (no prior uploads) generates normally without appendix

#### Manual Verification:
- [ ] Open generated PDF — evidence appendix appears on a new page after the main report
- [ ] Images render at correct proportions (not stretched/squashed)
- [ ] Captions appear below each image
- [ ] Page breaks work correctly (image+caption not split across pages)
- [ ] Report without images is identical to current behavior (no empty appendix)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Both Orchestrators — Auto-Forward Images

### Overview
When the orchestrator detects image parts in an incoming message, POST them to the reporting MCP server's image endpoint. This completes the pipeline from inspector → PDF.

### Changes Required:

#### 1. server-openai — Orchestrator Constructor & Image Forwarding
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Add `reporting_url` parameter and image forwarding logic

Update the constructor (line 37-51) to accept `reporting_url`:

```python
def __init__(
    self,
    agent_runner: AgentRunner,
    moderator: ModerationPipeline,
    audit_logger: AuditLogger,
    session_metadata: SessionMetadataManager | None = None,
    user_manager: UserManager | None = None,
    reporting_url: str | None = None,
):
    """Initialize orchestrator with dependencies."""
    self.agent_runner = agent_runner
    self.moderator = moderator
    self.audit = audit_logger
    self.session_metadata = session_metadata
    self.user_manager = user_manager
    self.pending_approvals: dict[str, asyncio.Future[bool]] = {}
    self.reporting_url = reporting_url
```

Add `import httpx` at the top of the file.

In `process_message`, after the image extraction loop (after line 162, after `break`), add the forwarding logic:

```python
# Auto-forward images to reporting MCP server for PDF evidence
if image_parts and self.reporting_url:
    asyncio.create_task(
        self._forward_images_to_reporting(
            session_id=thread_id,
            image_parts=image_parts,
            caption=user_content,
        )
    )
```

Add the forwarding method to the class:

```python
async def _forward_images_to_reporting(
    self,
    session_id: str,
    image_parts: list[dict[str, Any]],
    caption: str,
) -> None:
    """Forward uploaded images to the reporting MCP server for PDF evidence."""
    url = f"{self.reporting_url}/reports/{session_id}/images"
    caption = caption.strip() if caption else "Bewijsfoto"

    async with httpx.AsyncClient(timeout=10.0) as client:
        for img in image_parts:
            try:
                resp = await client.post(url, json={
                    "image_data": img.get("data", ""),
                    "caption": caption,
                    "mime_type": img.get("mimeType", "image/jpeg"),
                })
                if resp.status_code == 201:
                    log.info(f"Forwarded evidence image to reporting server for session {session_id}")
                elif resp.status_code == 409:
                    log.info(f"Image limit reached for session {session_id}, skipping remaining")
                    break
                else:
                    log.warning(f"Failed to forward image: {resp.status_code} {resp.text}")
            except Exception as e:
                log.warning(f"Failed to forward evidence image: {e}")
```

**File**: `server-openai/src/agora_openai/api/server.py`
**Changes**: Pass `reporting_url` to the Orchestrator

In the `lifespan` function, after `mcp_servers = parse_mcp_servers(...)` (line 46), extract the reporting URL:

```python
reporting_url = mcp_servers.get("reporting")
```

Update the Orchestrator instantiation (line 81-87):

```python
orchestrator = Orchestrator(
    agent_runner=agent_runner,
    moderator=moderator,
    audit_logger=audit_logger,
    session_metadata=session_metadata,
    user_manager=user_manager,
    reporting_url=reporting_url,
)
```

#### 2. server-langgraph — Identical Changes
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Same pattern as server-openai

Update the constructor (line 54-68):

```python
def __init__(
    self,
    graph: CompiledStateGraph[Any],
    moderator: ModerationPipeline,
    audit_logger: AuditLogger,
    session_metadata: SessionMetadataManager | None = None,
    user_manager: UserManager | None = None,
    reporting_url: str | None = None,
):
    """Initialize orchestrator."""
    self.graph = graph
    self.moderator = moderator
    self.audit = audit_logger
    self.session_metadata = session_metadata
    self.user_manager = user_manager
    self.pending_approvals: dict[str, asyncio.Future[bool]] = {}
    self.reporting_url = reporting_url
```

Add `import httpx` at the top.

In `process_message`, after the image extraction loop ends (after line 181), add:

```python
# Auto-forward images to reporting MCP server for PDF evidence
if image_parts and self.reporting_url:
    asyncio.create_task(
        self._forward_images_to_reporting(
            session_id=thread_id,
            image_parts=image_parts,
            caption="\n".join(user_text_parts).strip(),
        )
    )
```

Add the same `_forward_images_to_reporting` method as in server-openai (the body is identical).

**File**: `server-langgraph/src/agora_langgraph/api/server.py`
**Changes**: Pass `reporting_url` to the Orchestrator

In the `lifespan` function, after `mcp_servers = parse_mcp_servers(...)` (line 49):

```python
reporting_url = mcp_servers.get("reporting")
```

Update the Orchestrator instantiation (line 74-80):

```python
orchestrator = Orchestrator(
    graph=compiled_graph,
    moderator=moderator,
    audit_logger=audit_logger,
    session_metadata=session_metadata,
    user_manager=user_manager,
    reporting_url=reporting_url,
)
```

#### 3. Add httpx dependency (if needed)
**File**: `server-openai/pyproject.toml` (or `requirements.txt`)
**File**: `server-langgraph/pyproject.toml` (or `requirements.txt`)
**Changes**: Add `httpx>=0.27.0` to dependencies if not already declared

`httpx` is available as a transitive dependency of `openai` in both projects, but it should be declared explicitly since the orchestrator now imports it directly. Check if it's already in the dependency list before adding.

### Success Criteria:

#### Automated Verification:
- [ ] Both orchestrators start without import errors
- [ ] Type checking passes: `cd server-openai && mypy src/` and `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-openai && ruff check src/` and `cd server-langgraph && ruff check src/`
- [ ] Existing tests still pass: `cd server-openai && pytest` and `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Start the full stack (MCP servers + one orchestrator + HAI frontend)
- [ ] Upload a photo in chat with accompanying text (e.g., "Vuile keuken" + photo)
- [ ] Verify image appears in `storage/reports/{session_id}/images/` on the reporting server
- [ ] Verify caption matches the inspector's message text
- [ ] Generate a report → PDF appendix contains the uploaded photo with correct caption
- [ ] Upload without text → caption defaults to "Bewijsfoto"
- [ ] Upload 6 photos → only 5 stored, no errors in orchestrator logs
- [ ] Session without photos → report generates normally without appendix

**Implementation Note**: After completing this phase, the full end-to-end flow should work.

---

## Phase 4: Polish — Display Names & Documentation

### Overview
Minor updates to tool display names and README.

### Changes Required:

#### 1. Update Reporting README
**File**: `mcp-servers/reporting/README.md`
**Changes**: Move "Afhandeling van foto/bewijsmateriaal bijlagen" from "Toekomstige Verbeteringen" to a "Features" or "Capabilities" section, noting it now supports up to 5 evidence images per report.

#### 2. Update server_info resource
**File**: `mcp-servers/reporting/server.py`
**Changes**: In the `server_info()` MCP resource (line 455-484), add "Evidence image attachments in PDF reports (max 5 per session)" to the features list.

### Success Criteria:

#### Automated Verification:
- [ ] Server starts without errors
- [ ] `server://info` resource returns updated features

#### Manual Verification:
- [ ] README accurately describes the new functionality

---

## Testing Strategy

### Unit Tests:

#### FileStorage image methods:
- `test_save_image` — saves image, returns metadata dict with correct fields
- `test_save_image_limit` — 6th image returns `None`
- `test_load_images` — returns list with `path` fields
- `test_load_images_empty` — no images dir returns empty list
- `test_get_image_count` — returns correct count

#### PDFGenerator evidence appendix:
- `test_generate_with_images` — PDF bytes are larger than without images
- `test_generate_without_images` — identical to current behavior
- `test_evidence_appendix_bad_image` — graceful fallback for corrupted image file

### Integration Tests:
- Upload image via HTTP endpoint → generate report → verify PDF contains image
- Full orchestrator flow with mock MCP server — verify image forwarding fires

### Manual Testing Steps:
1. Start full stack: `cd mcp-servers && docker-compose up --build` + `cd server-openai && python -m agora_openai.api.server` + `cd HAI && pnpm dev`
2. Open HAI in browser, start an inspection conversation
3. Upload 3 photos with text descriptions during conversation
4. Request report generation ("Genereer rapport")
5. Download the PDF → verify 3 photos in appendix with correct captions
6. Start new session, generate report without photos → no appendix

## Performance Considerations

- **Image forwarding is fire-and-forget** (`asyncio.create_task`) — it does not block the chat response pipeline
- **Base64 decode happens once** on the reporting server (not in the PDF generator)
- **Images stored as files** — not in JSON, avoiding session data bloat
- **Max 5 images cap** prevents PDF size from growing unbounded (~2MB × 5 = ~10MB max additional)
- **`httpx.AsyncClient` timeout is 10s** — if the reporting server is slow/down, the image upload fails silently and chat continues normally

## Migration Notes

- No database migrations needed — purely file-based storage
- Existing sessions without images continue to work identically
- The Docker volume `reporting_data` (mounted at `/app/storage/reports`) automatically covers the new `images/` subdirectory
- No breaking changes to the AG-UI Protocol or frontend

## References

- Research: `thoughts/shared/research/2026-03-01-images-in-pdf-report.md`
- Multimodal feasibility: `thoughts/shared/research/2026-02-22-image-upload-multimodal-feasibility.md`
- ReportLab Image docs: `reportlab.platypus.Image` (proportional scaling via `kind='proportional'`)
- Current PDF generator: `mcp-servers/reporting/generators/pdf_generator.py:49-371`
- Current image extraction: `server-openai/.../orchestrator.py:130-156`, `server-langgraph/.../orchestrator.py:151-176`
