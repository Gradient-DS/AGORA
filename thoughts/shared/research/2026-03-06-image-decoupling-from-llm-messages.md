---
date: 2026-03-06T10:45:00+01:00
researcher: claude
git_commit: ae92e0e4ea49a2de3196674b6ac60bf107d5cdbc
branch: feat/tool-description
repository: AGORA
topic: "Decoupling images from LLM messages — report-only images with background description"
tags: [research, codebase, images, langgraph, reporting, spoken-stream, multimodal]
status: complete
last_updated: 2026-03-06
last_updated_by: claude
---

# Research: Decoupling Images from LLM Messages

**Date**: 2026-03-06T10:45:00+01:00
**Researcher**: claude
**Git Commit**: ae92e0e4ea49a2de3196674b6ac60bf107d5cdbc
**Branch**: feat/tool-description
**Repository**: AGORA

## Research Question
Instead of including images as multimodal messages to the LLM (which causes issues with the parallel written/spoken stream), can we decouple images so they are only used in the report? What would it take to generate a background description of the image for the report, and how does this impact the LangGraph flow?

## Summary

The change is **moderate in scope** and **simplifies** the LangGraph flow rather than complicating it. Currently, images are embedded as `image_url` content parts in `HumanMessage` objects sent to the LLM, which forces the spoken stream to strip them out (causing context divergence). The proposal eliminates this entirely: images become a side-channel artifact (saved to disk + forwarded to reporting) with an optional background description task. The LLM never sees the raw image data.

**Key changes needed:**
1. **Orchestrator** (`orchestrator.py`): Stop building multimodal `user_llm_content`; always use text-only content. Add background image description task.
2. **Graph** (`graph.py`): Remove image-stripping logic in `_create_parallel_sends()` — no longer needed.
3. **Reporting MCP** (`reporting/server.py`): Accept and store AI-generated image descriptions alongside images.
4. **Chat history** (`orchestrator.py`): Simplify reconstruction — no more multimodal content in checkpoints.

## Detailed Findings

### Current Image Flow (What Exists Today)

```
Frontend sends image as binary content part
    ↓
orchestrator.py:143-168 — Parses into multimodal content
    ├── Builds image_url content parts for LLM ← THIS GOES AWAY
    ├── Forwards to reporting MCP (fire-and-forget)
    └── Saves to disk for chat history
    ↓
HumanMessage(content=[text, image_url]) enters AgentState
    ↓
graph.py:411-430 — Strips images for spoken stream ← THIS GOES AWAY
    ├── Written model: sees full image
    └── Spoken model: sees "[De gebruiker heeft een afbeelding bijgevoegd.]"
```

### Proposed New Flow

```
Frontend sends image as binary content part
    ↓
orchestrator.py — Parses message
    ├── user_llm_content = text only (always a plain string)
    ├── Forwards image to reporting MCP (fire-and-forget)
    ├── Saves image to disk for chat history
    └── Launches background image description task
        ↓ (async, non-blocking)
        LLM vision call with image → generates description
        ↓
        POST description to reporting MCP for report inclusion
    ↓
HumanMessage(content="text only") enters AgentState
    ↓
Both written and spoken models see identical text-only messages
(no stripping needed)
```

### Impact on LangGraph Flow

#### 1. Orchestrator Changes (`orchestrator.py:130-190`)

**Before**: Lines 157-168 build `image_url` content parts and set `user_llm_content` to a multimodal list.
**After**: Always set `user_llm_content = user_content` (the text-only joined string). The `image_parts` extraction (lines 150-154) still happens — needed for forwarding to reporting and saving to disk — but no longer feeds into `user_llm_content`.

Add a new background task after the existing forwarding:
```python
if image_parts:
    asyncio.create_task(
        self._describe_images_for_report(
            session_id=thread_id,
            image_parts=image_parts,
        )
    )
```

**New method `_describe_images_for_report()`** — makes a vision LLM call (e.g., `gpt-4o-mini` with vision) to generate a Dutch-language description of each image, then POSTs the description to the reporting MCP server. This runs entirely in the background and does not block the conversation flow.

#### 2. Graph Simplification (`graph.py:411-430`)

The image-stripping logic in `_create_parallel_sends()` becomes **dead code** since `HumanMessage.content` will never contain `image_url` parts. This block can be removed entirely, simplifying the parallel stream setup. Both written and spoken models receive identical message lists.

**Lines to remove**: 411-430 (the entire image-stripping block for spoken messages).

This also eliminates the Dutch placeholder `"[De gebruiker heeft een afbeelding bijgevoegd.]"` — the text part of the user's message is sufficient context.

#### 3. Chat History Reconstruction (`orchestrator.py:1073-1114`)

Currently, this code finds `image_url` parts in checkpointed `HumanMessage` content, decodes the data URL, and matches it to saved files on disk. With text-only messages in the checkpoint, this multimodal parsing becomes unnecessary.

**However**, we still want to show the image in chat history. Two options:
- **Option A**: Keep saving images to disk (already done) and store a reference in the message metadata (e.g., `HumanMessage.additional_kwargs["image_refs"] = [{"filename": "abc123.jpg", "mime_type": "image/jpeg"}]`). History reconstruction reads the metadata instead of parsing content.
- **Option B**: Keep the current disk-save approach but reconstruct history by scanning the `session_images/` directory for the session, matching by timestamp proximity. Less reliable.

**Option A is recommended** — it's explicit and doesn't require parsing base64 data from the checkpoint.

#### 4. Reporting MCP Changes (`mcp-servers/reporting/server.py`)

The existing `POST /reports/{session_id}/images` endpoint (line 465) already accepts images with a `caption` field. Two changes needed:

- **Add a `description` field** to the image upload schema (or add a new endpoint `PATCH /reports/{session_id}/images/{image_id}/description`) for the AI-generated description.
- **Update `generate_final_report()`** (line 246) to include the AI description alongside (or instead of) the user caption in the evidence appendix.

The reporting MCP already stores images in memory per session (`_report_sessions` dict). Adding a description field to the stored image data is straightforward.

#### 5. State Definition (`state.py`)

No changes needed to `AgentState`. The `messages` field type (`list[BaseMessage]`) remains the same — it just won't contain multimodal content anymore.

### Background Image Description — Implementation Options

#### Option A: Direct Vision LLM Call in Orchestrator (Recommended)
```python
async def _describe_images_for_report(self, session_id: str, image_parts: list[dict]):
    """Generate descriptions for images in the background using a vision model."""
    llm = ChatOpenAI(model="gpt-4o-mini", max_tokens=300)
    for img in image_parts:
        data_url = img.get("data", "")
        response = await llm.ainvoke([
            HumanMessage(content=[
                {"type": "text", "text": "Beschrijf deze foto kort in het Nederlands. "
                 "Dit is een inspectie-foto van een voedselzaak. "
                 "Focus op wat zichtbaar is en relevant voor compliance."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ])
        ])
        # Forward description to reporting MCP
        await self._post_image_description(session_id, img, response.content)
```

Pros: Simple, self-contained, no new MCP endpoints needed for the vision call.
Cons: Orchestrator takes on a vision LLM dependency.

#### Option B: Vision Call via MCP Tool
Add a `describe_image` tool to the regulation-analysis or reporting MCP server. The orchestrator calls it as an MCP tool.

Pros: Separation of concerns.
Cons: More plumbing, MCP servers currently don't have LLM access.

#### Option C: Frontend Generates Description
The frontend calls a vision API directly before sending.

Pros: Offloads work from backend.
Cons: Exposes API keys to frontend, adds latency to send action.

**Option A is recommended** for simplicity. The orchestrator already has LLM access and the description is a fire-and-forget background task.

### Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM can no longer "see" the image during conversation | Low — demo doesn't need this | User can describe verbally what they see; description is for report only |
| Background description fails silently | Low | Log errors; report still has image without description |
| Chat history loses image display | Medium | Use Option A (metadata refs) to maintain image rendering |
| Breaking change for server-openai | Medium | Same changes needed in server-openai orchestrator |

### Effort Estimate — Files to Change

| File | Changes | Complexity |
|------|---------|------------|
| `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py` | Stop building multimodal content, add background description task, simplify chat history | Medium |
| `server-langgraph/src/agora_langgraph/core/graph.py` | Remove image-stripping block (lines 411-430) | Simple (deletion) |
| `mcp-servers/reporting/server.py` | Add description field to image storage and PDF rendering | Simple |
| `server-openai/src/agora_openai/pipelines/orchestrator.py` | Mirror changes from LangGraph orchestrator | Medium |
| Chat history reconstruction in orchestrator | Adapt to metadata-based image refs | Medium |

## Code References

- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:143-168` — Current multimodal content building (to be simplified)
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:178-190` — Image forwarding and disk saving (stays)
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:500-526` — `_forward_images_to_reporting()` (stays)
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:80-116` — `_save_session_images()` (stays)
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:1073-1114` — Chat history image reconstruction (simplify)
- `server-langgraph/src/agora_langgraph/core/graph.py:411-430` — Image stripping for spoken stream (remove)
- `server-langgraph/src/agora_langgraph/core/graph.py:324-456` — `_create_parallel_sends()` (simplifies)
- `server-langgraph/src/agora_langgraph/core/state.py:33` — `AgentState.messages` (no change)
- `mcp-servers/reporting/server.py:465` — Image upload endpoint (extend with description)
- `mcp-servers/reporting/server.py:246` — `generate_final_report()` (include descriptions)

## Historical Context

- `thoughts/shared/research/2026-03-01-spoken-written-divergence.md` — Documents the divergence issue between written/spoken streams after image turns. This proposal eliminates the root cause by removing images from LLM messages entirely.
- `thoughts/shared/research/2026-03-01-images-in-pdf-report.md` — Research on including images in PDF reports. The background description feature extends this work.
- `thoughts/shared/plans/2026-02-22-image-vision-processing.md` — Original image vision processing plan. This proposal changes the approach: vision is used for description generation only, not inline conversation.

## Open Questions

1. **Description language**: Should the image description always be in Dutch, or match the conversation language?
2. **Description detail level**: Short caption ("Handwas-instructieposter bij de ingang") vs. detailed compliance analysis ("De poster toont 6 stappen voor handhygiëne conform HACCP-richtlijnen...")?
3. **Multiple images**: Currently only first image per message is processed in chat history. Should descriptions handle multiple images?
4. **User visibility**: Should the AI-generated description be shown to the user in the chat, or only appear in the final report?
5. **Fallback**: If the vision LLM call fails, should we fall back to using the user's text as the description, or leave the image without a description in the report?
