---
date: 2026-02-22T12:00:00+01:00
researcher: claude
git_commit: ac8982c58a640949daafc8331ab97bda483e9e44
branch: main
repository: AGORA
topic: "Feasibility of image upload/capture and multimodal support in AGORA"
tags: [research, codebase, multimodal, image-upload, ag-ui-protocol, vision, gpt-4o]
status: complete
last_updated: 2026-02-22
last_updated_by: claude
---

# Research: Feasibility of Image Upload/Capture and Multimodal Support in AGORA

**Date**: 2026-02-22T12:00:00+01:00
**Researcher**: claude
**Git Commit**: ac8982c
**Branch**: main
**Repository**: AGORA

## Research Question

Can AGORA support sending images (upload or capture) from the frontend to the backend? What does the AG-UI protocol support? Should a new image-analysis agent be created? What's the recommended implementation approach?

## Summary

**Image support is feasible and can be implemented incrementally.** The AG-UI protocol already defines a `BinaryInputContent` type (draft status) in the upstream SDK. Both GPT-4o (used by AGORA) and the agent SDKs (OpenAI Agents SDK, LangGraph/LangChain) natively support multimodal image inputs. However, AGORA currently treats all message content as plain strings at every layer of the stack. Implementation requires changes across 4 layers: frontend UI, frontend protocol, backend message parsing, and agent invocation.

**Recommendation: Do NOT create a new image-analysis agent.** Instead, extend the `general-agent` to handle images. Images are a message modality, not a domain specialty. The general-agent already triages conversations — it can describe images and then route to the appropriate specialist based on what's in the image. A hardcoded fallback (Phase 1) is even simpler: just inject a text description alongside the image reference.

## Detailed Findings

### 1. AG-UI Protocol: Upstream Multimodal Support (Draft)

The upstream `ag-ui-protocol` Python package **already defines** multimodal message types, though this is still a **draft feature**.

**`BinaryInputContent`** (`server-langgraph/.venv/.../ag_ui/core/types.py:80-101`):
```python
class BinaryInputContent(ConfiguredBaseModel):
    type: Literal["binary"] = "binary"
    mime_type: str          # e.g., "image/jpeg"
    id: Optional[str]       # provider-managed reference
    url: Optional[str]      # remote URL
    data: Optional[str]     # base64-encoded data
    filename: Optional[str]
```

**`UserMessage`** supports multimodal content (`types.py:104-110`):
```python
class UserMessage(BaseMessage):
    role: Literal["user"] = "user"
    content: Union[str, List[InputContent]]  # string OR array of content blocks
```

Where `InputContent = Union[TextInputContent, BinaryInputContent]`.

**JS/TS SDK** mirrors this with identical types (`@ag-ui/core`).

### 2. AGORA Current State: Text-Only at Every Layer

Every layer in AGORA constrains message content to plain strings:

| Layer | File | Constraint |
|-------|------|------------|
| Frontend Zod schema | `HAI/src/types/schemas.ts:215` | `content: z.string()` |
| Frontend WS client | `HAI/src/lib/websocket/client.ts:111` | `sendRunInput(threadId, userId, content: string)` |
| Frontend ChatMessage type | `HAI/src/types/index.ts:6` | `content: string` |
| AsyncAPI spec | `docs/hai-contract/asyncapi.yaml:439` | `content: type: string` |
| JSON Schema | `docs/hai-contract/schemas/messages.json:149` | `content: { "type": "string" }` |
| Backend RunAgentInput | `server-openai/.../ag_ui_types.py:101` | `messages: list[dict[str, Any]]` (loosely typed, but only strings sent) |
| server-openai orchestrator | `server-openai/.../orchestrator.py:124-128` | `user_content = msg.get("content", "")` -- extracts as string |
| server-openai agent_runner | `server-openai/.../agent_runner.py:163` | `run_agent(message: str)` -- string-only signature |
| server-langgraph orchestrator | `server-langgraph/.../orchestrator.py:260` | `HumanMessage(content=user_content)` -- always string |

### 3. SDK Support for Multimodal

Both agent SDKs fully support images:

**OpenAI Agents SDK** (used by server-openai):
```python
from openai.types.responses import ResponseInputImageParam, ResponseInputTextParam
result = await Runner.run(agent, input=[
    Message(content=[
        ResponseInputTextParam(type="input_text", text="Describe this image"),
        ResponseInputImageParam(type="input_image",
            image_url=f"data:image/jpeg;base64,{base64_image}",
            detail="low")
    ], role="user")
])
```

**LangChain/LangGraph** (used by server-langgraph):
```python
message = HumanMessage(content=[
    {"type": "text", "text": "Describe this image."},
    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
])
response = await llm.ainvoke([message])
```

**GPT-4o** natively supports vision — already the default model in both orchestrators (`config.py:23` in both).

### 4. Agent Architecture: New Agent vs. Extending Existing

**Current agents**: `general-agent` (triage), `history-agent`, `regulation-agent`, `reporting-agent`.

**Adding a new agent requires** (per orchestrator):
- server-openai: 4-5 files (agent_definitions, agent_runner mapping, tool_display_names, general-agent handoff config)
- server-langgraph: 6-8 files (agent_definitions, tools.py transfer function, graph.py node/edges/routing in 7+ locations, agents.py node function, tool_display_names)

**Recommendation: Do NOT create a separate image-analysis agent.** Reasons:
1. Images are an **input modality**, not a **domain**. The existing agents already have domain expertise — they just need to receive image context.
2. The general-agent already serves as the triage point. It can interpret images and route accordingly.
3. Adding a new agent in server-langgraph is particularly complex (7+ graph.py changes).
4. For the Phase 1 hardcoded fallback, a new agent adds unnecessary complexity.

Instead: **general-agent receives the image**, interprets it (or receives a hardcoded description), and routes to the appropriate specialist with the text context.

### 5. Frontend: No Existing Media Capabilities

The HAI frontend has zero file/media handling:
- No `<input type="file">` elements
- No drag-and-drop handlers
- No clipboard paste handlers for images
- No camera/media capture API usage (except microphone for voice)
- No `FormData` or multipart upload logic
- WebSocket uses text frames only (`ws.send(string)` at `client.ts:162`)

The `ChatInput.tsx` component (lines 9-17) accepts `onSend: (message: string) => void` — string-only callback. The message input is a `<Textarea>` with no attachment UI.

### 6. Custom Events as Extension Point

The `CUSTOM` event type's `value` field is unconstrained (`{}` in JSON Schema, `Any` in Python, `z.record(z.unknown())` in Zod). Existing custom events follow the `agora:*` namespace convention. A new `agora:image_attachment` event could carry image data without modifying the core protocol.

Current custom events: `agora:tool_approval_request`, `agora:tool_approval_response`, `agora:error`, `agora:spoken_text_start/content/end/error`.

## Recommended Implementation Approach

### Phase 1: Hardcoded Fallback (MVP — Get Image to Backend)

**Goal**: User can upload/capture an image, it reaches the backend, agent receives a hardcoded text description.

#### Frontend Changes (HAI)

1. **Extend `ChatInput.tsx`** — Add an attachment button (paperclip icon or camera icon) next to the send button:
   - `<input type="file" accept="image/*" capture="environment">` for mobile camera
   - `<input type="file" accept="image/*">` for file upload
   - Handle `onChange` to read file as base64 via `FileReader.readAsDataURL()`

2. **Extend message types** — Update `ChatMessage` interface (`types/index.ts:4`) to support optional image attachment:
   ```typescript
   interface ChatMessage {
     // ...existing fields
     imageAttachment?: {
       data: string;       // base64 data URL
       mimeType: string;
       filename?: string;
     };
   }
   ```

3. **Extend `RunAgentInput`** — Two approaches:

   **Option A: Multimodal content array** (aligns with AG-UI upstream):
   ```typescript
   // schemas.ts - update content type
   content: z.union([
     z.string(),
     z.array(z.discriminatedUnion("type", [
       z.object({ type: z.literal("text"), text: z.string() }),
       z.object({ type: z.literal("binary"), mimeType: z.string(), data: z.string() })
     ]))
   ])
   ```

   **Option B: Separate attachments field** (simpler, backward-compatible):
   ```typescript
   messages: z.array(z.object({
     role: z.enum([...]),
     content: z.string(),
     attachments: z.array(z.object({
       type: z.literal("image"),
       mimeType: z.string(),
       data: z.string(),  // base64
     })).optional(),
   }))
   ```

   **Recommended: Option A** — it aligns with the AG-UI `BinaryInputContent` type and with how both OpenAI and LangChain expect multimodal content.

4. **Display images in chat** — Update `ChatMessage.tsx` to render image attachments above the text content (or as inline images). ReactMarkdown already renders `<img>` tags from markdown, but explicit rendering of `imageAttachment` data is cleaner.

5. **Update WebSocket client** (`client.ts`) — Modify `sendRunInput` to accept structured content:
   ```typescript
   sendRunInput(threadId: string, userId: string, content: string | InputContent[]): string
   ```

#### Backend Changes (Both Orchestrators)

6. **Parse multimodal content** — In both `orchestrator.py` files, detect when `content` is an array vs. string:
   ```python
   raw_content = msg.get("content", "")
   if isinstance(raw_content, list):
       # Extract text parts and image parts
       text_parts = [c["text"] for c in raw_content if c["type"] == "text"]
       image_parts = [c for c in raw_content if c["type"] == "binary"]
       user_content = "\n".join(text_parts)
       # Phase 1: Replace image with hardcoded description
       if image_parts:
           user_content += "\n\n[The user attached an image showing: a food safety label on a product package]"
   else:
       user_content = raw_content
   ```

7. **No changes to agent definitions needed** — The general-agent prompt can handle the injected text context as-is.

#### Protocol Changes

8. **Update AsyncAPI spec** (`asyncapi.yaml`) — Change `content` from `type: string` to `oneOf: [string, array]`.
9. **Update JSON Schema** (`messages.json`) — Same change.

### Phase 2: Real Image Processing (Future)

Once the pipeline is proven with the hardcoded fallback:

1. **Pass image to GPT-4o** — Replace the hardcoded description with actual multimodal LLM call:
   - server-openai: Pass `ResponseInputImageParam` in the `Runner.run()` input
   - server-langgraph: Pass `HumanMessage(content=[text_block, image_block])` to the graph

2. **General-agent describes the image**, then routes to the appropriate specialist with the description as context.

3. **Consider image size limits** — Compress/resize before base64 encoding. GPT-4o supports up to 50MB but WebSocket frames have practical limits. Recommend max ~2MB images, use `detail: "low"` for initial analysis.

### Phase 3: Dedicated Capabilities (Optional, Future)

- Image storage (don't keep base64 in chat history — store in blob storage, reference by URL)
- Camera capture UI with preview
- Image annotation tools
- Multi-image support
- Image context passed to specialist agents (e.g., photo of violation passed to regulation-agent)

## Architecture Insights

- The `CUSTOM` event mechanism provides an alternative path if modifying the core message schema feels too invasive. However, aligning with the upstream AG-UI `BinaryInputContent` type is the better long-term approach.
- The backend `RunAgentInput.messages` field is `list[dict[str, Any]]` (not strongly typed), which means it already accepts arbitrary message structures — the backend won't reject multimodal content arrays, it just doesn't process them yet.
- Both orchestrators have a single extraction point where `content` is read from messages (`orchestrator.py:124-128` in server-openai, `orchestrator.py:142-147` in server-langgraph). This is the key backend touchpoint.
- WebSocket text frames can carry base64-encoded images (they're just JSON strings), so no WebSocket transport changes are needed.

## Code References

### Frontend
- `HAI/src/components/chat/ChatInput.tsx:9-17` — Input component props (string-only `onSend`)
- `HAI/src/components/chat/ChatMessage.tsx:80-104` — Message rendering with ReactMarkdown
- `HAI/src/lib/websocket/client.ts:111-138` — `sendRunInput()` method (string content)
- `HAI/src/types/index.ts:4-19` — `ChatMessage` interface
- `HAI/src/types/schemas.ts:208-220` — `RunAgentInputSchema` (Zod)
- `HAI/src/hooks/useWebSocket.ts:378-392` — `sendMessage()` hook
- `HAI/src/stores/useMessageStore.ts:43-86` — `addMessage()` store action

### Backend (server-openai)
- `server-openai/src/agora_openai/common/ag_ui_types.py:88-106` — `RunAgentInput` model
- `server-openai/src/agora_openai/pipelines/orchestrator.py:124-128` — User content extraction
- `server-openai/src/agora_openai/core/agent_runner.py:160-163` — `run_agent(message: str)`
- `server-openai/src/agora_openai/core/agent_definitions.py:16-76` — general-agent config

### Backend (server-langgraph)
- `server-langgraph/src/agora_langgraph/common/ag_ui_types.py:89-104` — `RunAgentInput` model
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:142-147` — User content extraction
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:260` — `HumanMessage(content=str)`
- `server-langgraph/src/agora_langgraph/core/agent_definitions.py:19-82` — general-agent config

### Protocol
- `docs/hai-contract/asyncapi.yaml:431-443` — Message schema
- `docs/hai-contract/schemas/messages.json:143-152` — Message JSON Schema
- Upstream AG-UI: `ag_ui/core/types.py:80-101` — `BinaryInputContent` (in venv)

## Historical Context (from thoughts/)

No prior research, plans, or notes exist on image handling, multimodal capabilities, or vision support. This is entirely new territory for the project.

## Open Questions

1. **Image size limits** — What's the practical max for base64 over WebSocket? Should we compress client-side?
2. **Image persistence** — Should images be stored in session history (SQLite)? Base64 in SQLite is feasible but bloated. Blob storage + URL reference is better for production.
3. **AG-UI draft timeline** — When will `BinaryInputContent` move from draft to stable? Should we align now or use a custom approach?
4. **Mobile camera capture** — The `capture="environment"` attribute works on mobile browsers. Do we need specific UX for this?
5. **Moderation** — The current input moderator validates text only. Should uploaded images be moderated? (OpenAI's moderation API supports images.)
6. **Offline support** — The offline buffer stores `content: string`. How should image attachments be buffered?
