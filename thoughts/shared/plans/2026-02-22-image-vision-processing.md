# Image Vision Processing Implementation Plan

## Overview

Wire actual image data through to the LLMs in both orchestrators, replacing the current Dutch placeholder text with real multimodal vision input. Images already arrive correctly from the frontend as base64 data URLs — the fix is converting them into each LLM SDK's expected format and passing them through to the model.

Spoken generation remains text-only (current model is small/text-only). Mock server already handles image messages and needs no changes.

## Current State Analysis

Both orchestrators receive multimodal content arrays from the frontend:
```json
[
  {"type": "text", "text": "user's message"},
  {"type": "binary", "mimeType": "image/jpeg", "data": "data:image/jpeg;base64,..."}
]
```

Both orchestrators parse this but **discard the image data** and append a hardcoded placeholder:
- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:144-166`
- `server-openai/src/agora_openai/pipelines/orchestrator.py:123-144`

The LLM receives: `"user text\n\n[De gebruiker heeft een afbeelding bijgevoegd...]"` — never the actual image.

### Key Discoveries:
- **LangChain ChatOpenAI** accepts: `HumanMessage(content=[{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}])` — direct passthrough, zero conversion overhead
- **OpenAI Agents SDK** accepts: `Runner.run_streamed(input=[{"role": "user", "content": [{"type": "input_image", "image_url": "data:...", "detail": "auto"}]}])` — uses Responses API format (`input_image` / `input_text`, not `image_url` / `text`)
- **OpenAI Agents SDK session constraint**: Passing `list` input with `SQLiteSession` requires a `RunConfig.session_input_callback` (otherwise raises `UserError`). The callback simply merges history + new input. See `agents/run.py:1898-1904`
- **Spoken generation** (`server-openai/orchestrator.py:230-304`): Uses `client.chat.completions.create()` with a small text-only model. It reads from `agent_input.messages` directly — we must NOT pass image data to it.
- **Downstream text-only consumers**: Moderation (`moderator.validate_input`), audit logging, and session metadata all expect plain text strings. These must continue receiving text-only content.
- **Frontend `data` field**: `FileReader.readAsDataURL()` produces `data:image/jpeg;base64,...` — this is already the format both LLM APIs expect for inline base64 images.
- **Mock server**: Already handles image messages at `mock_server.py:904-905` → `handle_image_message()` at line 1201. No changes needed.

## Desired End State

After implementation:
1. When a user sends an image, the LLM (GPT-4o or compatible vision model) **actually sees the image** and can describe/analyze it
2. Text-only messages work identically (no regressions)
3. Spoken generation remains text-only (no image data sent to spoken model)
4. Moderation, audit logging, and session metadata continue to receive text-only content
5. Both backends produce equivalent behavior

### Verification:
- Send image + text message → LLM response references actual image content (not generic placeholder)
- Send text-only message → identical behavior to current
- Spoken channel produces a text summary (doesn't error from missing image)
- Audit logs contain text content, not base64 blobs

## What We're NOT Doing

- **Spoken generation with images** — Current spoken model is small/text-only. Will discuss with team later.
- **Image moderation/safety filtering** — No content safety on uploaded images.
- **Image compression/resizing** — Base64 passes through as-is from frontend.
- **Multi-image support** — One image per message (already enforced by frontend).
- **Mock server changes** — Already works with image messages.
- **New agent types** — Images go through existing agent pipeline, no image-analysis specialist.
- **Frontend changes** — Frontend already sends correct multimodal format.

## Implementation Approach

Extract image data at the point where it's currently discarded (the content parsing loop in each orchestrator), and convert it into the LLM SDK's expected multimodal format. Keep a text-only version for all non-LLM consumers.

---

## Phase 1: server-langgraph — Multimodal HumanMessage

### Overview
Update the LangGraph orchestrator to build a multimodal `HumanMessage` with image content parts instead of discarding images.

### Changes Required:

#### 1. Update content extraction in process_message()
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Lines**: 144-166
**Changes**: Extract both text-only content (for moderation/logging) and multimodal content (for the LLM). When images are present, build a LangChain multimodal content list.

Replace lines 144-166:
```python
        # Extract user messages, keeping both text-only (for logging/moderation)
        # and multimodal content (for the LLM) when images are present
        user_text_parts: list[str] = []
        user_llm_content: str | list[dict[str, Any]] = ""
        for msg in agent_input.messages:
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                if isinstance(raw_content, list):
                    # Multimodal content array — extract text and image parts
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

                    if image_parts:
                        # Build LangChain multimodal content list
                        llm_parts: list[dict[str, Any]] = []
                        for tp in text_parts:
                            llm_parts.append({"type": "text", "text": tp})
                        for img in image_parts:
                            data_url = img.get("data", "")
                            llm_parts.append({
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            })
                        user_llm_content = llm_parts
                    else:
                        user_llm_content = "\n".join(text_parts)
                else:
                    user_text_parts.append(raw_content)
                    user_llm_content = raw_content

        # Text-only content for moderation, logging, and session metadata
        user_content = "\n".join(user_text_parts)
```

#### 2. Use multimodal content for HumanMessage
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Lines**: 278-279 and 284-285
**Changes**: Use `user_llm_content` (which may be a multimodal list) for the `HumanMessage`, instead of `user_content` (which is always a plain string).

Replace line 279:
```python
                    "messages": [HumanMessage(content=user_llm_content)],
```

Replace line 285:
```python
                    "messages": [HumanMessage(content=user_llm_content)],
```

**Note**: All other uses of `user_content` (moderation at line 192, audit at line 202, session metadata at line 181) remain unchanged — they use the text-only string.

### Success Criteria:

#### Automated Verification:
- [x] server-langgraph tests pass: `cd server-langgraph && pytest`
- [x] Type checking passes: `cd server-langgraph && mypy src/`
- [x] Linting passes: `cd server-langgraph && ruff check src/`

#### Manual Verification:
- [ ] Send text-only message → identical behavior (no regressions)
- [ ] Send image + text → LLM response actually describes image content
- [ ] Send image only (no text) → LLM response describes image
- [ ] Spoken channel produces a text summary (no errors)
- [ ] Audit log contains text content, not base64 data

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: server-openai — Multimodal Agent Input

### Overview
Update the OpenAI orchestrator and agent runner to pass multimodal input to `Runner.run_streamed()`. This requires changes in three areas: content extraction, agent runner signature, and session callback handling.

### Changes Required:

#### 1. Update content extraction in process_message()
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Lines**: 123-144
**Changes**: Extract both text-only content and multimodal content in OpenAI Responses API format. The key format difference from LangChain: content parts use `input_text`/`input_image` types (not `text`/`image_url`).

Replace lines 123-144:
```python
        # Extract user message, keeping both text-only (for logging/moderation)
        # and multimodal content (for the LLM) when images are present
        user_content = ""
        user_llm_input: str | list[dict[str, Any]] = ""
        for msg in agent_input.messages:
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                if isinstance(raw_content, list):
                    # Multimodal content array — extract text and image parts
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
                    user_content = "\n".join(text_parts)

                    if image_parts:
                        # Build OpenAI Responses API multimodal input
                        content_parts: list[dict[str, Any]] = []
                        for tp in text_parts:
                            content_parts.append({"type": "input_text", "text": tp})
                        for img in image_parts:
                            data_url = img.get("data", "")
                            content_parts.append({
                                "type": "input_image",
                                "image_url": data_url,
                                "detail": "auto",
                            })
                        user_llm_input = [{"role": "user", "content": content_parts}]
                    else:
                        user_llm_input = user_content
                else:
                    user_content = raw_content
                    user_llm_input = raw_content
                break
```

#### 2. Update message_with_context to use multimodal input
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Lines**: 486-490
**Changes**: When `user_llm_input` is a list (multimodal), prepend the system context as an `input_text` part. When it's a string, keep existing behavior.

Replace lines 486-490:
```python
                # Include user_id context for settings tool
                if isinstance(user_llm_input, list) and user_id:
                    # Multimodal list input — prepend system context as text part
                    context_msg = {"role": "user", "content": [
                        {"type": "input_text", "text": f"[SYSTEM CONTEXT: user_id={user_id}]"},
                    ]}
                    message_with_context = [context_msg] + user_llm_input
                elif isinstance(user_llm_input, str) and user_id:
                    message_with_context = (
                        f"[SYSTEM CONTEXT: user_id={user_id}]\n\n{user_llm_input}"
                    )
                else:
                    message_with_context = user_llm_input
```

#### 3. Update run_agent call to pass multimodal input
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Line**: 492
**Changes**: Pass `message_with_context` which is now `str | list`.

Replace line 492:
```python
                response_content, active_agent_id = await self.agent_runner.run_agent(
                    message=message_with_context,
                    session_id=thread_id,
                    stream_callback=stream_callback,
                    tool_callback=tool_callback,
                )
```

No change needed to the actual call — just the type signature update in agent_runner.

#### 4. Update AgentRunner.run_agent() signature
**File**: `server-openai/src/agora_openai/core/agent_runner.py`
**Lines**: 160-171
**Changes**: Accept `str | list` instead of `str`. Pass through to streamed/blocking sessions.

```python
    async def run_agent(
        self,
        message: str | list[dict[str, Any]],
        session_id: str,
        stream_callback: Callable[[str, str | None], Awaitable[None]] | None = None,
        tool_callback: (
            Callable[
                [str, str, dict[str, Any], str, str | None, str | None], Awaitable[Any]
            ]
            | None
        ) = None,
    ) -> tuple[str, str]:
```

Update the forwarding calls at lines 187 and 191 (no change needed — `message` variable name stays the same).

#### 5. Update _run_streamed_session() and _run_blocking_session()
**File**: `server-openai/src/agora_openai/core/agent_runner.py`
**Lines**: 193-225
**Changes**: Accept `str | list` input. When input is a list, provide a `RunConfig` with `session_input_callback` to satisfy the SDK's session requirement.

```python
    async def _run_blocking_session(
        self, session: SQLiteSession, entry_agent: Agent, message: str | list[dict[str, Any]]
    ) -> tuple[str, str]:
        """Run agent in blocking mode."""
        log.info("Running agent without streaming")
        run_kwargs: dict[str, Any] = {
            "starting_agent": entry_agent,
            "input": message,
            "session": session,
        }
        if isinstance(message, list):
            from agents import RunConfig
            run_kwargs["run_config"] = RunConfig(
                session_input_callback=lambda history, new: history + new,
            )
        result = await Runner.run(**run_kwargs)
        final_output = result.final_output or ""
        log.info(f"Agent run completed. Output: {len(final_output)} characters")

        active_agent_id = self._get_agent_id_from_agent(entry_agent)
        log.info(f"Agent run completed. Active agent: {active_agent_id}")
        return final_output, active_agent_id

    async def _run_streamed_session(
        self,
        session: SQLiteSession,
        entry_agent: Agent,
        message: str | list[dict[str, Any]],
        stream_callback: Callable[[str, str | None], Awaitable[None]],
        tool_callback: Callable | None,
    ) -> tuple[str, str]:
        """Run agent in streaming mode."""
        log.info("Running agent with streaming enabled")
        run_kwargs: dict[str, Any] = {
            "starting_agent": entry_agent,
            "input": message,
            "session": session,
        }
        if isinstance(message, list):
            from agents import RunConfig
            run_kwargs["run_config"] = RunConfig(
                session_input_callback=lambda history, new: history + new,
            )
        result = Runner.run_streamed(**run_kwargs)

        state = StreamState(current_agent_id=self._get_agent_id_from_agent(entry_agent))

        async for event in result.stream_events():
            await self._process_stream_event(
                event, state, stream_callback, tool_callback
            )

        final_output = "".join(state.full_response)
        return final_output, state.current_agent_id
```

#### 6. Ensure spoken generation stays text-only
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Lines**: 258-265 (inside `generate_spoken_parallel()`)
**Changes**: Filter out binary content parts when building the conversation for spoken generation.

Replace lines 258-265:
```python
                        # Use same conversation context but text-only
                        # (spoken model is small/text-only, cannot handle images)
                        conversation = []
                        for m in agent_input.messages:
                            raw = m.get("content", "")
                            if isinstance(raw, list):
                                # Extract only text parts for spoken model
                                text_only = " ".join(
                                    part["text"]
                                    for part in raw
                                    if isinstance(part, dict) and part.get("type") == "text"
                                )
                                conversation.append({"role": m.get("role"), "content": text_only})
                            else:
                                conversation.append({"role": m.get("role"), "content": raw})
```

### Success Criteria:

#### Automated Verification:
- [x] server-openai tests pass: `cd server-openai && pytest`
- [x] Type checking passes: `cd server-openai && mypy src/`
- [x] Linting passes: `cd server-openai && ruff check src/`

#### Manual Verification:
- [ ] Send text-only message → identical behavior (no regressions)
- [ ] Send image + text → LLM response actually describes image content
- [ ] Send image only (no text) → LLM response describes image
- [ ] Spoken channel produces a text summary (no errors, no image data sent)
- [ ] Agent handoffs still work correctly with multimodal input
- [ ] Session history is preserved correctly across turns with images
- [ ] Audit log contains text content, not base64 data

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation.

---

## Testing Strategy

### Unit Tests:
- Both orchestrators should handle text-only messages identically (regression)
- Both orchestrators should build correct multimodal format when images present
- Agent runner should accept both `str` and `list` input types

### Manual Integration Tests:
1. **Text-only regression**: Send text message to both backends → identical to current behavior
2. **Image + text (langgraph)**: Send image with text → response references actual image content
3. **Image + text (openai)**: Same test against server-openai
4. **Image only**: Send image without text → response describes image
5. **Spoken channel**: Verify spoken generation completes without errors (text-only)
6. **Session continuity**: Send image message, then follow-up text message → conversation context maintained
7. **Agent handoff with image**: Send image during inspection → verify handoff still works
8. **Mock server**: Send image to mock → mock responds with contextual acknowledgment (already works)

### Edge Cases:
- Image with empty text (image-only message)
- Multiple consecutive image messages
- Image message followed by text-only message
- Image during interrupted graph flow (server-langgraph)

## Performance Considerations

- **Base64 in LLM input**: A 2MB image encodes to ~2.67MB base64. This is within OpenAI's API limits (20MB for high-detail images) but adds significant token count. The `"detail": "auto"` setting lets the API decide resolution.
- **No additional latency**: Images are already in the backend memory (received via WebSocket). Converting format is O(1). The only added latency is the LLM processing the image tokens.
- **Audit log safety**: Text-only content is logged, not base64 blobs, keeping logs manageable.

## References

- Phase 1 plan (frontend + protocol): `thoughts/shared/plans/2026-02-22-image-upload-multimodal-support.md`
- LangChain vision format: `HumanMessage(content=[{"type": "image_url", "image_url": {"url": "data:..."}}])`
- OpenAI Agents SDK format: `Runner.run_streamed(input=[{"role": "user", "content": [{"type": "input_image", "image_url": "data:...", "detail": "auto"}]}])`
- Session callback constraint: `agents/run.py:1898-1904`
- server-langgraph orchestrator: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
- server-openai orchestrator: `server-openai/src/agora_openai/pipelines/orchestrator.py`
- server-openai agent runner: `server-openai/src/agora_openai/core/agent_runner.py`
