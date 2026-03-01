---
date: 2026-03-01T10:00:00+01:00
researcher: claude
git_commit: e263eb30d3b6267eb8af00bf84ffcc706113dd60
branch: main
repository: AGORA
topic: "How to include uploaded images in the PDF inspection report"
tags: [research, codebase, reporting, pdf, images, multimodal, reportlab, mcp-servers]
status: complete
last_updated: 2026-03-01
last_updated_by: claude
---

# Research: Including Uploaded Images in the PDF Inspection Report

**Date**: 2026-03-01T10:00:00+01:00
**Researcher**: claude
**Git Commit**: e263eb3
**Branch**: main
**Repository**: AGORA

## Research Question

How could uploaded images (photos taken during inspection) be included in the generated PDF report? What changes are needed across the stack?

## Summary

AGORA already has a **fully working image upload pipeline** for chat messages — inspectors can attach photos that reach GPT-4o for vision analysis. However, these images **never reach the reporting MCP server** and the PDF generator has **no image rendering capability**. Including images in PDF reports requires changes across 4 layers: (1) the HAPReport data model, (2) the MCP reporting tool interface, (3) the orchestrator's image forwarding logic, and (4) the ReportLab-based PDF generator. ReportLab natively supports image embedding via `reportlab.platypus.Image`, making the PDF rendering itself straightforward.

The reporting README already lists "Afhandeling van foto/bewijsmateriaal bijlagen" (photo/evidence attachment handling) as a planned future improvement (`mcp-servers/reporting/README.md:129`).

## Detailed Findings

### 1. Current State: The Gap

When an inspector uploads a photo today, here's what happens:

```
Inspector uploads photo
  → ChatInput.tsx (base64, max 2MB)
  → WebSocket (ContentPart[{type:"binary"}])
  → Orchestrator (builds multimodal LLM input)
  → GPT-4o (can SEE the image, describes it in text)
  → Agent response streams back to user

  ✗ Image data NEVER reaches the reporting MCP server
  ✗ extract_inspection_data only receives text (inspection_summary: str)
  ✗ HAPReport has no image fields
  ✗ PDFGenerator has no image rendering
```

The gap is at the **orchestrator → MCP tool call boundary**. The `reporting-agent` calls `extract_inspection_data` with a text `inspection_summary` parameter. Even though the agent has seen images (via GPT-4o vision), it only passes text descriptions to the MCP server.

### 2. What Already Works

| Component | Image Support | Status |
|-----------|--------------|--------|
| Frontend image capture | `<input accept="image/*" capture="environment">` | **Working** (`ChatInput.tsx:147-155`) |
| Frontend base64 encoding | `FileReader.readAsDataURL()`, 2MB limit | **Working** (`ChatInput.tsx:38-60`) |
| Frontend preview/display | Thumbnail in input, full in messages | **Working** (`ChatInput.tsx:96-111`, `ChatMessage.tsx:75-83`) |
| AG-UI Protocol | `BinaryContentPart` with base64 data | **Working** (`schemas.ts:207-223`, `asyncapi.yaml:441-482`) |
| WebSocket transport | JSON text frames with base64 | **Working** (`client.ts:121-129`) |
| Offline buffering | IndexedDB stores image attachments | **Working** (`offlineBuffer.ts:7-19`) |
| server-openai parsing | Extracts `input_image` for OpenAI format | **Working** (`orchestrator.py:125-162`) |
| server-langgraph parsing | Extracts `image_url` for LangChain format | **Working** (`orchestrator.py:146-184`) |
| GPT-4o vision | Analyzes images inline | **Working** (both orchestrators) |
| ReportLab Image class | `reportlab.platypus.Image` renders in PDF | **Available** (not yet used) |
| HAPReport model | No image fields | **Missing** |
| MCP tool interface | No image parameters | **Missing** |
| PDF generator | No image rendering | **Missing** |

### 3. ReportLab Image Support

ReportLab's Platypus layout engine (already used for the entire PDF) natively supports images:

```python
from reportlab.platypus import Image as RLImage
from io import BytesIO
import base64

# From base64 data URL:
header, data = base64_data_url.split(",", 1)
img_bytes = base64.b64decode(data)
img_buffer = BytesIO(img_bytes)

# Create flowable with auto-scaling:
img = RLImage(img_buffer, width=12*cm, height=8*cm, kind='proportional')
# kind='proportional' maintains aspect ratio within the bounding box

story.append(img)
story.append(Paragraph("Caption text", caption_style))
```

Key considerations:
- `kind='proportional'` scales while maintaining aspect ratio
- A4 page with 2cm margins gives ~17cm usable width (currently used for violation tables)
- Images should be constrained to ~15cm width to leave breathing room
- Multiple images per section are possible using `KeepTogether` to avoid page-break mid-image+caption
- ReportLab handles JPEG, PNG, GIF natively; no extra system libraries needed

### 4. Proposed Architecture: Two Approaches

#### Approach A: Image Collection via Dedicated MCP Tool (Recommended)

Add a new `attach_evidence_image` MCP tool that the `reporting-agent` calls during the report generation workflow:

```
Inspector uploads photo in chat
  → GPT-4o describes it ("dirty kitchen counter")
  → reporting-agent calls attach_evidence_image(session_id, image_data, caption, section)
  → MCP server stores image in session
  → Later: generate_final_report reads stored images and embeds in PDF
```

**Advantages**:
- Clean separation: agent decides which images are relevant
- Agent provides caption and section assignment (informed by GPT-4o vision)
- Multiple images per report supported naturally
- Inspector can upload images at any point during conversation
- Doesn't bloat the `extract_inspection_data` call

**New MCP Tool**:
```python
@mcp.tool()
async def attach_evidence_image(
    session_id: str,
    image_data: str,        # base64 data URL
    caption: str,           # Agent-generated description
    section: str = "general",  # hygiene, pest_control, food_safety, allergen, general
    violation_index: int | None = None,  # Link to specific violation
) -> dict:
    """Attach an evidence photo to the inspection report."""
```

**Key challenge**: The `reporting-agent` currently only receives text from the orchestrator (tool results come as text). For the agent to forward actual image data to this tool, the **orchestrator must make images from the conversation available** to the agent or to the MCP tool call.

Two sub-approaches for getting image data to the MCP tool:

**A1: Agent forwards base64 directly** — The orchestrator passes multimodal content (including images) to the LLM. The agent's tool call includes `image_data` as a base64 string argument. This works but means the full base64 string goes through the LLM's output → tool call pipeline, which is wasteful and may hit token/size limits.

**A2: Orchestrator-managed image registry** — The orchestrator stores uploaded images in a session-scoped registry (keyed by index or hash). The agent references images by index (`image_ref: 0`), and the orchestrator resolves the reference to actual base64 data before calling the MCP tool. This is more efficient but requires orchestrator-level changes.

**A3: Direct upload endpoint on MCP server** — Add an HTTP multipart upload endpoint (`POST /reports/{session_id}/images`) on the reporting MCP server. The orchestrator uploads images directly when they arrive, bypassing the agent entirely. The agent then references them by ID. This is the most efficient approach for large images.

#### Approach B: Extend `generate_final_report` with Images Parameter

Add an `images` parameter to the existing `generate_final_report` tool:

```python
@mcp.tool()
async def generate_final_report(
    session_id: str,
    send_email: bool = True,
    images: list[dict] | None = None,  # [{data: str, caption: str, section: str}]
) -> dict:
```

**Advantages**: Simpler, fewer new tools.
**Disadvantages**: All images must be passed at generation time; large payload; doesn't allow incremental collection.

### 5. Data Model Changes

#### New Models (in `models/hap_schema.py`)

```python
class EvidenceImage(BaseModel):
    """An evidence photo attached to the inspection report."""
    image_data: str              # base64 data URL
    mime_type: str = "image/jpeg"
    caption: str                 # Description of what's shown
    section: str = "general"    # Which report section this belongs to
    violation_index: Optional[int] = None  # Links to specific violation
    timestamp: datetime = Field(default_factory=datetime.now)
```

#### HAPReport Extension

```python
class HAPReport(BaseModel):
    # ... existing fields ...
    evidence_images: List[EvidenceImage] = Field(default_factory=list)
```

#### Storage

Images should be stored in the session directory alongside the existing report files:
```
storage/reports/{session_id}/
  ├── draft_data.json
  ├── final_report.json
  ├── final_report.pdf
  └── images/              # NEW
      ├── img_0.jpg
      ├── img_1.png
      └── manifest.json    # Maps index → filename, caption, section
```

Storing actual image files (decoded from base64) rather than keeping base64 in JSON prevents session data from becoming excessively large.

### 6. PDF Generator Changes

Add a new section builder in `pdf_generator.py`:

```python
from reportlab.platypus import Image as RLImage, KeepTogether

def _create_evidence_section(self, report: HAPReport) -> list:
    """Render evidence images grouped by report section."""
    if not report.evidence_images:
        return []

    elements = []
    elements.append(Paragraph("Bewijsmateriaal / Foto's", self.styles['SectionHeader']))

    # Group by section
    by_section = {}
    for img in report.evidence_images:
        by_section.setdefault(img.section, []).append(img)

    section_titles = {
        "hygiene": "Hygiëne",
        "pest_control": "Ongediertebestrijding",
        "food_safety": "Voedselveiligheid",
        "allergen": "Allergenen",
        "general": "Algemeen",
    }

    for section_key, images in by_section.items():
        title = section_titles.get(section_key, section_key)
        elements.append(Paragraph(f"<b>{title}</b>", self.styles['Normal']))

        for img in images:
            img_buffer = self._decode_image(img.image_data)
            rl_image = RLImage(img_buffer, width=14*cm, height=10*cm, kind='proportional')
            caption = Paragraph(f"<i>{img.caption}</i>", self.styles['Normal'])
            # Keep image + caption together across page breaks
            elements.append(KeepTogether([rl_image, Spacer(1, 0.2*cm), caption]))
            elements.append(Spacer(1, 0.3*cm))

    return elements

def _decode_image(self, data_url: str) -> BytesIO:
    """Decode base64 data URL to BytesIO buffer."""
    if "," in data_url:
        _, data = data_url.split(",", 1)
    else:
        data = data_url
    return BytesIO(base64.b64decode(data))
```

This section would be inserted in the story between the allergen section and violations summary (or as the last section before recommendations), adding it to `generate()`:

```python
# In generate() method, after allergen section:
story.extend(self._create_evidence_section(report))
story.append(Spacer(1, 0.5*cm))
```

### 7. Orchestrator Changes Needed

The key missing piece: **getting images from the chat conversation to the MCP tool calls**.

#### Option: Orchestrator Image Registry (Recommended for Approach A3)

In both orchestrators, when processing a message with image content:

```python
# In orchestrator.py process_message():
if image_parts:
    for img in image_parts:
        self.session_images.setdefault(thread_id, []).append({
            "data": img["data"],  # base64 data URL
            "mimeType": img.get("mimeType", "image/jpeg"),
            "timestamp": datetime.now().isoformat(),
        })
    # Upload to reporting MCP server immediately
    if self.mcp_client:
        for img in image_parts:
            await self._upload_image_to_reporting(session_id, img)
```

This way, by the time the `reporting-agent` calls `generate_final_report`, all uploaded images are already stored on the reporting MCP server.

### 8. Agent Instructions Update

The `reporting-agent` instructions (`agent_definitions.py:132-193`) need to be updated to:
1. Inform the agent that images may be available
2. Instruct it to reference images in the report context
3. (If using Approach A with `attach_evidence_image` tool) instruct it to call the tool for each relevant image

### 9. End-to-End Flow (Recommended: Approach A3)

```
1. Inspector takes photo → ChatInput (base64, ≤2MB)
2. WebSocket sends ContentPart[{type:"binary"}]
3. Orchestrator extracts image parts
   ├── Passes to LLM as multimodal input (existing behavior)
   └── POST /reports/{session_id}/images on reporting MCP server (NEW)
4. Reporting MCP server stores image in session directory
5. Later: reporting-agent calls generate_final_report
6. generate_final_report loads stored images from session
7. PDFGenerator._create_evidence_section() renders images in PDF
8. Final PDF includes embedded evidence photos with captions
```

## Code References

### Existing Image Pipeline
- `HAI/src/components/chat/ChatInput.tsx:38-60` — File selection, base64 encoding, 2MB limit
- `HAI/src/components/chat/ChatInput.tsx:147-155` — Hidden file input with camera capture
- `HAI/src/lib/websocket/client.ts:121-129` — Multimodal ContentPart construction
- `HAI/src/types/schemas.ts:207-223` — BinaryContentPartSchema
- `server-openai/src/agora_openai/pipelines/orchestrator.py:125-162` — Image extraction (OpenAI format)
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:146-184` — Image extraction (LangChain format)

### Current PDF Generation (No Images)
- `mcp-servers/reporting/generators/pdf_generator.py:49-96` — `generate()` method, story-based layout
- `mcp-servers/reporting/generators/pdf_generator.py:17-47` — Styles setup
- `mcp-servers/reporting/models/hap_schema.py:110-148` — `HAPReport` model (no image fields)
- `mcp-servers/reporting/models/hap_schema.py:22-29` — `Violation` model (`evidence` is text-only)

### MCP Tool Definitions
- `mcp-servers/reporting/server.py:33-172` — `extract_inspection_data` (text input only)
- `mcp-servers/reporting/server.py:244-354` — `generate_final_report` (no image params)
- `mcp-servers/reporting/server.py:430-452` — PDF download endpoint

### Storage Layer
- `mcp-servers/reporting/storage/file_storage.py:11-100` — File-based storage (no image handling)
- `mcp-servers/reporting/storage/session_manager.py:10-140` — Session lifecycle

### Agent Configuration
- `server-openai/src/agora_openai/core/agent_runner.py:34-39` — `AGENT_MCP_MAPPING`
- `server-openai/src/agora_openai/core/agent_definitions.py:132-193` — reporting-agent instructions

## Architecture Insights

- **ReportLab is sufficient** — No need to switch PDF libraries. ReportLab's `Image` flowable handles JPEG/PNG natively, supports proportional scaling, and integrates with the existing `SimpleDocTemplate` + story pattern.
- **Base64 over WebSocket works for ≤2MB** — The existing 2MB frontend limit is reasonable for inspection photos. Photos will be compressed as JPEG anyway.
- **Images should be stored as files, not in JSON** — The current session storage uses JSON files (`draft_data.json`). Embedding base64 images in JSON would make these files huge. Store image files separately with a manifest.
- **Orchestrator is the key integration point** — The orchestrator already extracts images from messages. Extending it to forward images to the reporting MCP server (via HTTP upload) is the most efficient approach.
- **Agent captions are valuable** — GPT-4o's description of each image provides useful captions for the PDF. The agent can provide context like "Photo shows contaminated food storage area" which enriches the report.
- **Both orchestrators need identical changes** — Per project convention, API changes must be implemented in both server-openai and server-langgraph.

## Historical Context (from thoughts/)

- `thoughts/shared/research/2026-02-22-image-upload-multimodal-feasibility.md` — Original feasibility research for image upload. At that time, the system was text-only at every layer. The recommended phased approach has since been implemented (multimodal content parts, base64 encoding, both backend parsers).
- `thoughts/shared/plans/2026-02-22-image-upload-multimodal-support.md` — Implementation plan for the multimodal chat support that is now live.
- `thoughts/shared/plans/2026-02-22-image-vision-processing.md` — Implementation plan for backend vision processing.

## Related Research

- `thoughts/shared/research/2026-02-04-report-cross-conversation-leakage.md` — Report generation context isolation (relevant for ensuring images are session-scoped)

## Open Questions

1. **Image compression** — Should the frontend compress/resize images before encoding? JPEG quality 80% at 1280px max dimension would significantly reduce payload while keeping photo detail.
2. **Max images per report** — How many evidence photos per inspection? Should there be a limit (e.g., 10 per report) to keep PDF size manageable?
3. **Image-violation linking** — Should images be linked to specific violations (e.g., "this photo shows violation #3")? The `violation_index` field enables this, but it adds UX complexity.
4. **Caption source** — Should captions come from (a) the agent's GPT-4o description, (b) the inspector's text message accompanying the image, or (c) a dedicated caption prompt?
5. **Inline vs. appendix** — Should images appear inline within their respective sections (hygiene, food safety, etc.) or in a separate "Evidence Photos" appendix at the end?
6. **Image in email** — Should the emailed PDF also contain images? This increases email attachment size significantly.
7. **Approach selection** — Approach A3 (direct upload endpoint) is most efficient but bypasses agent control. Approach A1 (agent forwards base64) gives the agent control over which images are relevant but is token-expensive. Which tradeoff is preferred?
