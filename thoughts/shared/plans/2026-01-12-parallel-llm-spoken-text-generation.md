# True Parallel LLM Spoken Text Generation - Implementation Plan

## Overview

Implement dual-channel text streaming for written (UI) and spoken (TTS) text in both server-langgraph and server-openai backends. The behavior is controlled by the user's `spoken_text_type` preference (already implemented via `/users/me/preferences` REST endpoint):

- **`'summarize'`** (default): Two parallel LLM calls - one with original prompt for written text, one with speech-optimized prompt for shorter spoken text
- **`'dictate'`**: Single LLM call - same markdown content streamed to both written and spoken channels (no transformation)

Both modes always stream to both channels for consistent UI integration. This avoids conditional field switching in the frontend.

## Current State Analysis

### Existing Architecture

Both backends stream text through a single path:
- **LangGraph**: `orchestrator._stream_response()` → `protocol_handler.send_text_message_*()` (lines 300-454)
- **OpenAI SDK**: `stream_callback()` closure → `protocol_handler.send_text_message_*()` (lines 177-205)

The protocol already supports spoken text events via CUSTOM events (defined in `docs/hai-contract/HAI_API_CONTRACT.md:656-706`):
- `agora:spoken_text_start`
- `agora:spoken_text_content`
- `agora:spoken_text_end`

The mock server demonstrates the pattern (`docs/hai-contract/mock_server.py:977-1059`), but uses post-processing transform rather than parallel LLM generation.

### Key Discoveries

- `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:320-341` - Current streaming loop uses `graph.astream_events()`
- `server-openai/src/agora_openai/pipelines/orchestrator.py:177-205` - Current `stream_callback` closure
- Agent prompts are inline strings in `agent_definitions.py` files
- `current_agent_id` is tracked locally in both backends during streaming
- Both `ag_ui_handler.py` files already import `CustomEvent` from `ag_ui.core`

## Desired End State

After implementation:
1. Every agent text response streams to BOTH written and spoken channels
2. Written text (markdown) → `TEXT_MESSAGE_*` events
3. Spoken text → `agora:spoken_text_*` CUSTOM events
4. Both streams share the same `messageId` for correlation
5. Stream lifecycle is synchronized (both start together, both end together)
6. Behavior controlled by user's `spoken_text_type` preference:
   - `'summarize'`: Two parallel LLM calls, spoken text is shorter/TTS-friendly
   - `'dictate'`: Single LLM call, same content to both channels

### Verification Criteria
- Frontend always receives both written and spoken events (regardless of mode)
- In 'summarize' mode: Spoken text is shorter, more conversational, no markdown
- In 'dictate' mode: Written and spoken content are identical
- Response latency increase is minimal (parallel execution in summarize mode)
- Memory usage remains stable (no unbounded buffering)
- Graceful degradation if spoken stream fails (in summarize mode)

## What We're NOT Doing

- Not changing the agent handoff system
- Not modifying the frontend (HAI) - it should already handle spoken text events
- Not implementing caching for spoken text
- Not implementing hybrid approach (Option C from research)
- Not changing the MCP tool integrations
- Not implementing post-processing transform fallback (can be added later)

## Implementation Approach

The implementation uses **true parallel LLM generation** with two concurrent API calls started simultaneously via `asyncio.create_task`. Both calls receive the same conversation history but different system prompts:

1. **Written stream**: Original agent prompt → detailed, markdown-formatted response for UI
2. **Spoken stream**: Speech-optimized prompt → brief, conversational summary for TTS

Both streams are interleaved to the frontend as chunks arrive. The spoken prompt naturally produces shorter responses that summarize the key information without needing to see the written output first.

**Key Pattern:**
```python
async def _stream_parallel_responses(
    self,
    messages: list[BaseMessage],
    written_prompt: str,
    spoken_prompt: str,
    message_id: str,
    protocol_handler: Any,
) -> tuple[str, str]:
    """Run two LLM calls in true parallel and stream both outputs."""
    llm = get_llm_for_agent(current_agent_id)

    written_queue: asyncio.Queue[str | None] = asyncio.Queue()
    spoken_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def stream_written():
        try:
            async for chunk in llm.astream([SystemMessage(written_prompt)] + messages):
                if chunk.content:
                    await written_queue.put(str(chunk.content))
        except Exception as e:
            log.error(f"Written stream error: {e}")
        finally:
            await written_queue.put(None)

    async def stream_spoken():
        try:
            async for chunk in llm.astream([SystemMessage(spoken_prompt)] + messages):
                if chunk.content:
                    await spoken_queue.put(str(chunk.content))
        except Exception as e:
            log.error(f"Spoken stream error: {e}")
            await protocol_handler.send_spoken_text_error(message_id, "generation_failed", str(e))
        finally:
            await spoken_queue.put(None)

    # Start BOTH tasks simultaneously
    written_task = asyncio.create_task(stream_written())
    spoken_task = asyncio.create_task(stream_spoken())

    # Interleave chunks from both queues as they arrive
    written_done = spoken_done = False
    while not (written_done and spoken_done):
        if not written_done:
            try:
                chunk = written_queue.get_nowait()
                if chunk is None:
                    written_done = True
                else:
                    await protocol_handler.send_text_message_content(message_id, chunk)
            except asyncio.QueueEmpty:
                pass

        if not spoken_done:
            try:
                chunk = spoken_queue.get_nowait()
                if chunk is None:
                    spoken_done = True
                else:
                    await protocol_handler.send_spoken_text_content(message_id, chunk)
            except asyncio.QueueEmpty:
                pass

        await asyncio.sleep(0.01)  # Prevent busy-waiting

    await asyncio.gather(written_task, spoken_task)
```

**Error Handling**: If the spoken stream fails, an `agora:spoken_text_error` event is sent to the frontend. The written stream continues unaffected.

---

## Phase 1: AG-UI Protocol Extension (Spoken Text Events)

### Overview
Add spoken text event methods and error handling to both backends. This includes:
- `agora:spoken_text_start`, `agora:spoken_text_content`, `agora:spoken_text_end` events
- `agora:spoken_text_error` event for error handling
- Type definitions in `ag_ui_types.py`
- Protocol documentation updates

### Changes Required:

#### 1. Add Type Definitions (LangGraph)
**File**: `server-langgraph/src/agora_langgraph/common/ag_ui_types.py`
**Changes**: Add new payload class and constant (after `AGORA_ERROR` around line 147)

```python
# Add to __all__ list:
"SpokenTextErrorPayload",
"AGORA_SPOKEN_TEXT_ERROR",

# Add new payload class after ErrorPayload:
class SpokenTextErrorPayload(AgoraBaseModel):
    """Payload for agora:spoken_text_error custom event."""

    message_id: str = Field(
        alias="messageId", description="Message ID this error relates to"
    )
    error_code: str = Field(
        alias="errorCode", description="Error code for programmatic handling"
    )
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )

# Add new constant:
AGORA_SPOKEN_TEXT_ERROR = "agora:spoken_text_error"
```

#### 2. Add Type Definitions (OpenAI SDK)
**File**: `server-openai/src/agora_openai/common/ag_ui_types.py`
**Changes**: Add identical payload class and constant

#### 3. LangGraph AG-UI Handler
**File**: `server-langgraph/src/agora_langgraph/api/ag_ui_handler.py`
**Changes**: Add four new methods after `send_text_message_end()` (after line 214)

```python
    # Spoken text events (for TTS)

    async def send_spoken_text_start(
        self, message_id: str, role: str = "assistant"
    ) -> None:
        """Emit agora:spoken_text_start custom event for TTS stream."""
        event = CustomEvent(
            name="agora:spoken_text_start",
            value={"messageId": message_id, "role": role},
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_spoken_text_content(self, message_id: str, delta: str) -> None:
        """Emit agora:spoken_text_content custom event for TTS stream."""
        if not delta:
            return  # Skip empty deltas
        event = CustomEvent(
            name="agora:spoken_text_content",
            value={"messageId": message_id, "delta": delta},
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_spoken_text_end(self, message_id: str) -> None:
        """Emit agora:spoken_text_end custom event for TTS stream."""
        event = CustomEvent(
            name="agora:spoken_text_end",
            value={"messageId": message_id},
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)

    async def send_spoken_text_error(
        self,
        message_id: str,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Emit agora:spoken_text_error custom event when TTS generation fails."""
        from agora_langgraph.common.ag_ui_types import (
            SpokenTextErrorPayload,
            AGORA_SPOKEN_TEXT_ERROR,
        )
        payload = SpokenTextErrorPayload(
            message_id=message_id,
            error_code=error_code,
            message=message,
            details=details,
        )
        event = CustomEvent(
            name=AGORA_SPOKEN_TEXT_ERROR,
            value=payload.model_dump(by_alias=True),
            timestamp=_now_timestamp(),
        )
        await self._send_event(event)
```

#### 4. OpenAI SDK AG-UI Handler
**File**: `server-openai/src/agora_openai/api/ag_ui_handler.py`
**Changes**: Add identical four methods after `send_text_message_end()` (after line 208)

Same code as above (with import from `agora_openai.common.ag_ui_types`).

#### 5. Update AG-UI Protocol Documentation
**File**: `docs/hai-contract/HAI_API_CONTRACT.md`
**Changes**: Add `agora:spoken_text_error` event documentation after spoken text events (around line 706)

```markdown
### `agora:spoken_text_error`

Emitted when spoken text generation fails. The written text stream continues unaffected.

**Payload Structure:**
```json
{
  "type": "CUSTOM",
  "name": "agora:spoken_text_error",
  "value": {
    "messageId": "msg-abc123",
    "errorCode": "generation_failed",
    "message": "Failed to generate spoken text: API timeout",
    "details": { "retryable": true }
  },
  "timestamp": 1705318202000
}
```

**Error Codes:**
| Code | Description |
|------|-------------|
| `generation_failed` | LLM call for spoken text failed |
| `prompt_not_found` | No spoken prompt defined for agent |
| `timeout` | Spoken generation timed out |
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Type checking passes: `cd server-openai && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Linting passes: `cd server-openai && ruff check src/`
- [ ] Unit tests pass: `cd server-langgraph && pytest`
- [ ] Unit tests pass: `cd server-openai && pytest`

#### Manual Verification:
- [ ] Methods are accessible from orchestrator code

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Spoken Prompts Definition

### Overview
Create speech-optimized system prompts for each agent. These prompts instruct the LLM to generate shorter, conversational **summary-style** responses suitable for TTS. The prompts run in **true parallel** with the written prompts - they receive the same conversation history but produce independently shorter responses.

**Key Design**: Spoken prompts do NOT reference "summarize the written text" - instead they instruct the LLM to give a brief, conversational response to the same question. This enables true parallel generation.

### Changes Required:

#### 1. LangGraph Spoken Prompts
**File**: `server-langgraph/src/agora_langgraph/core/agent_definitions.py`
**Changes**: Add `SPOKEN_AGENT_PROMPTS` dictionary after `AGENT_CONFIGS` (after line 237)

```python
# Spoken text prompts for TTS - independent summary-style responses
# These run in PARALLEL with written prompts, receiving the same conversation context
SPOKEN_AGENT_PROMPTS: dict[str, str] = {
    "general-agent": (
        "Je bent een NVWA inspectie-assistent die KORTE gesproken antwoorden geeft.\n\n"
        "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
        "- Geef een SAMENVATTING van je antwoord in maximaal 2-3 zinnen\n"
        "- Focus op de kernboodschap, laat details weg\n"
        "- Geen opsommingstekens, nummering of markdown\n"
        "- Spreek natuurlijk en conversationeel\n"
        "- Vermijd afkortingen - schrijf ze voluit:\n"
        "  * 'KVK' → 'Kamer van Koophandel'\n"
        "  * 'NVWA' → 'Nederlandse Voedsel- en Warenautoriteit'\n"
        "  * '°C' → 'graden Celsius'\n\n"
        "Je geeft dezelfde informatie als de geschreven versie, maar korter en spreekbaarder.\n\n"
        "VOORBEELD:\n"
        "Vraag: 'Start inspectie bij Bakkerij Jansen KVK 12345678'\n"
        "Antwoord: 'Prima, ik zoek de bedrijfsgegevens voor Bakkerij Jansen bij de Kamer van Koophandel op.'"
    ),
    "regulation-agent": (
        "Je bent een regelgeving-expert die KORTE gesproken antwoorden geeft.\n\n"
        "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
        "- Vat de belangrijkste regel samen in 1-2 zinnen\n"
        "- Noem de essentie, geen gedetailleerde artikelen of bronvermeldingen\n"
        "- Gebruik vloeiende zinnen, geen opsommingen\n"
        "- Spreek getallen en eenheden uit:\n"
        "  * '22°C' → 'tweeëntwintig graden Celsius'\n"
        "  * 'EU 852/2004' → 'Europese Unie verordening achtenvijftig tweeduizendvier'\n"
        "  * 'Art. 5' → 'artikel vijf'\n\n"
        "Je geeft dezelfde informatie als de geschreven versie, maar beknopt en TTS-vriendelijk.\n\n"
        "VOORBEELD:\n"
        "Vraag: 'Welke temperatuur moet vers vlees hebben?'\n"
        "Antwoord: 'Vers vlees moet bewaard worden onder de zeven graden Celsius volgens de levensmiddelenhygiëne voorschriften.'"
    ),
    "reporting-agent": (
        "Je bent een rapportage-specialist die KORTE gesproken statusupdates geeft.\n\n"
        "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
        "- Maximaal 2 zinnen per update\n"
        "- Geef alleen de kernactie of belangrijkste vraag\n"
        "- Geen lijsten of formulier-achtige informatie\n"
        "- Spreek vragen en acties duidelijk uit\n\n"
        "Je vat de rapportage-actie samen voor de inspecteur.\n\n"
        "VOORBEELD:\n"
        "Context: Inspector vraagt om rapport te genereren\n"
        "Antwoord: 'Ik verwerk nu de inspectiegegevens en maak het rapport. Ik heb nog een paar vragen om het compleet te maken.'"
    ),
    "history-agent": (
        "Je bent een bedrijfshistorie-specialist die KORTE gesproken samenvattingen geeft.\n\n"
        "BELANGRIJK - Dit is voor tekst-naar-spraak (TTS):\n"
        "- Vat bedrijfsinfo samen in maximaal 2-3 zinnen\n"
        "- Noem alleen de belangrijkste bevinding of waarschuwing\n"
        "- Geen tabellen, lijsten of gedetailleerde historiek\n"
        "- Spreek waarschuwingen duidelijk en direct uit\n"
        "- Schrijf afkortingen voluit:\n"
        "  * 'KVK' → 'Kamer van Koophandel'\n\n"
        "Je geeft de essentie van de bedrijfsinformatie, de geschreven versie bevat de details.\n\n"
        "VOORBEELD:\n"
        "Context: Bedrijf met 3 eerdere overtredingen waarvan 1 ernstig\n"
        "Antwoord: 'Let op, dit bedrijf heeft drie eerdere overtredingen gehad waarvan één ernstig. Ik raad extra aandacht aan bij de hygiëne controle.'"
    ),
}


def get_spoken_prompt(agent_id: str) -> str | None:
    """Get the spoken text prompt for an agent.

    Returns None if no spoken prompt is defined for the agent,
    which should trigger an agora:spoken_text_error event.
    """
    return SPOKEN_AGENT_PROMPTS.get(agent_id)
```

#### 2. OpenAI SDK Spoken Prompts
**File**: `server-openai/src/agora_openai/core/agent_definitions.py`
**Changes**: Add identical `SPOKEN_AGENT_PROMPTS` dictionary and helper function after `AGENT_CONFIGS` (after line 234)

Same code as above.

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Type checking passes: `cd server-openai && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Linting passes: `cd server-openai && ruff check src/`

#### Manual Verification:
- [ ] Prompts are accessible via `get_spoken_prompt()` function
- [ ] Each active agent has a corresponding spoken prompt

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Parallel Stream Generator (LangGraph)

### Overview
Create a utility module for **true parallel** LLM streaming that runs two concurrent API calls and interleaves their chunks. This module handles error propagation via callbacks for the `agora:spoken_text_error` event.

### Changes Required:

#### 1. Create Parallel Streaming Utility
**File**: `server-langgraph/src/agora_langgraph/core/parallel_streaming.py` (new file)

```python
"""Parallel streaming utilities for true parallel spoken text generation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable, Literal

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

log = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A chunk from either the written or spoken stream."""
    stream_type: Literal["written", "spoken"]
    content: str


@dataclass
class StreamError:
    """An error from the spoken stream."""
    stream_type: Literal["spoken"]
    error_code: str
    message: str


@dataclass
class ParallelStreamState:
    """State for tracking parallel streams."""
    written_done: bool = False
    spoken_done: bool = False
    spoken_error: StreamError | None = None
    written_content: list[str] = field(default_factory=list)
    spoken_content: list[str] = field(default_factory=list)


async def generate_parallel_streams(
    llm: ChatOpenAI,
    messages: list[BaseMessage],
    written_prompt: str,
    spoken_prompt: str,
    on_spoken_error: Callable[[str, str], Awaitable[None]] | None = None,
) -> AsyncIterator[StreamChunk]:
    """Generate written and spoken text streams in TRUE PARALLEL.

    Starts BOTH LLM calls simultaneously using asyncio.create_task().
    Both streams receive the same conversation history but different system prompts.
    Chunks are yielded as they arrive from either stream.

    Args:
        llm: The LLM instance to use for generation
        messages: The conversation messages (without system prompt)
        written_prompt: Full system prompt for written text
        spoken_prompt: Shorter system prompt for spoken text (summary-style)
        on_spoken_error: Optional async callback(error_code, message) for spoken errors

    Yields:
        StreamChunk with stream_type ("written" or "spoken") and content
    """
    # Prepare message lists with respective system prompts
    written_messages = [SystemMessage(content=written_prompt)] + messages
    spoken_messages = [SystemMessage(content=spoken_prompt)] + messages

    # Create queues for both streams
    written_queue: asyncio.Queue[str | None] = asyncio.Queue()
    spoken_queue: asyncio.Queue[str | None] = asyncio.Queue()

    state = ParallelStreamState()

    async def stream_written() -> None:
        """Stream written text to queue."""
        try:
            async for chunk in llm.astream(written_messages):
                if hasattr(chunk, "content") and chunk.content:
                    await written_queue.put(str(chunk.content))
        except Exception as e:
            log.error(f"Error in written stream: {e}")
            # Written errors are critical - re-raise
            raise
        finally:
            await written_queue.put(None)

    async def stream_spoken() -> None:
        """Stream spoken text to queue with error handling."""
        try:
            async for chunk in llm.astream(spoken_messages):
                if hasattr(chunk, "content") and chunk.content:
                    await spoken_queue.put(str(chunk.content))
        except Exception as e:
            error_msg = str(e)
            log.error(f"Error in spoken stream: {error_msg}")
            state.spoken_error = StreamError(
                stream_type="spoken",
                error_code="generation_failed",
                message=error_msg,
            )
            # Call error callback if provided
            if on_spoken_error:
                await on_spoken_error("generation_failed", error_msg)
        finally:
            await spoken_queue.put(None)

    # Start BOTH streams SIMULTANEOUSLY
    written_task = asyncio.create_task(stream_written())
    spoken_task = asyncio.create_task(stream_spoken())

    try:
        # Interleave chunks from both queues as they arrive
        while not (state.written_done and state.spoken_done):
            # Check written queue (non-blocking)
            if not state.written_done:
                try:
                    chunk = written_queue.get_nowait()
                    if chunk is None:
                        state.written_done = True
                    else:
                        state.written_content.append(chunk)
                        yield StreamChunk(stream_type="written", content=chunk)
                except asyncio.QueueEmpty:
                    pass

            # Check spoken queue (non-blocking)
            if not state.spoken_done:
                try:
                    chunk = spoken_queue.get_nowait()
                    if chunk is None:
                        state.spoken_done = True
                    else:
                        state.spoken_content.append(chunk)
                        yield StreamChunk(stream_type="spoken", content=chunk)
                except asyncio.QueueEmpty:
                    pass

            # Small sleep to prevent busy-waiting (10ms)
            if not (state.written_done and state.spoken_done):
                await asyncio.sleep(0.01)

    except asyncio.CancelledError:
        written_task.cancel()
        spoken_task.cancel()
        raise
    finally:
        # Ensure tasks are cleaned up
        if not written_task.done():
            written_task.cancel()
        if not spoken_task.done():
            spoken_task.cancel()

        # Wait for tasks to complete (with cancellation)
        await asyncio.gather(written_task, spoken_task, return_exceptions=True)


def get_full_responses(state: ParallelStreamState) -> tuple[str, str]:
    """Get the complete written and spoken responses from state."""
    return (
        "".join(state.written_content),
        "".join(state.spoken_content),
    )
```

### Success Criteria:

#### Automated Verification:
- [ ] File created at correct path
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Unit tests pass (if any): `cd server-langgraph && pytest`

#### Manual Verification:
- [ ] Module is importable from orchestrator
- [ ] Error callback is invoked when spoken stream fails

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 4.

---

## Phase 4: LangGraph Orchestrator Integration (Preference-Driven)

### Overview
Modify the LangGraph orchestrator to support dual-channel streaming controlled by the user's `spoken_text_type` preference:

- **`'summarize'`** (default): Two parallel LLM calls - one for written text (existing flow), one for speech-optimized spoken text
- **`'dictate'`**: Single LLM call - same content duplicated to both written and spoken channels

**Key Architecture**: LangGraph's `astream_events` handles the written text (including tools and handoffs). In 'summarize' mode, a separate parallel task handles spoken text generation. In 'dictate' mode, each written chunk is also sent to the spoken channel.

### Changes Required:

#### 1. Update Orchestrator Imports
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Add imports at the top of the file (after line 11)

```python
from langchain_core.messages import SystemMessage
from agora_langgraph.core.agent_definitions import get_agent_by_id, get_spoken_prompt
from agora_langgraph.adapters.user_manager import UserManager
```

#### 2. Add UserManager to Orchestrator __init__
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Accept UserManager in constructor for preference fetching

```python
def __init__(self, user_manager: UserManager | None = None):
    # ... existing init code ...
    self.user_manager = user_manager
```

#### 3. Modify _stream_response Method for Preference-Driven Dual-Channel
**File**: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py`
**Changes**: Implement dual-channel streaming with preference-driven behavior. Add `user_id` parameter.

```python
    async def _stream_response(
        self,
        input_state: dict[str, Any],
        config: dict[str, Any],
        thread_id: str,
        run_id: str,
        message_id: str,
        user_id: str,
        protocol_handler: Any,
    ) -> tuple[str, str]:
        """Stream graph response using astream_events with AG-UI Protocol.

        Dual-channel streaming controlled by user's spoken_text_type preference:
        - 'summarize': Two parallel LLM calls (written + speech-optimized spoken)
        - 'dictate': Single LLM call, same content to both channels
        """
        full_response: list[str] = []
        current_agent_id = "general-agent"
        current_step: str | None = "routing"
        active_tool_calls: dict[str, str] = {}
        message_started = False
        spoken_message_started = False

        await protocol_handler.send_step_finished("routing")
        await protocol_handler.send_step_started("thinking")
        current_step = "thinking"

        # Fetch user preference for spoken response mode
        spoken_mode = "summarize"  # default
        if self.user_manager:
            try:
                user = await self.user_manager.get_user(user_id)
                if user:
                    prefs = user.get("preferences", {})
                    spoken_mode = prefs.get("spoken_text_type", "summarize")
            except Exception as e:
                log.warning(f"Failed to fetch user preferences: {e}, using default")

        # Parallel spoken task state (only used in 'summarize' mode)
        spoken_task: asyncio.Task | None = None
        spoken_queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def generate_spoken_parallel(agent_id: str) -> None:
            """Generate spoken response in TRUE PARALLEL with written stream.

            Uses the same conversation context but a spoken-specific prompt
            that produces shorter, TTS-friendly summary responses.
            Only used when spoken_mode == 'summarize'.
            """
            try:
                spoken_prompt = get_spoken_prompt(agent_id)
                if not spoken_prompt:
                    log.warning(f"No spoken prompt for agent {agent_id}")
                    await protocol_handler.send_spoken_text_error(
                        message_id, "prompt_not_found",
                        f"No spoken prompt defined for agent: {agent_id}"
                    )
                    return

                from agora_langgraph.core.agents import get_llm_for_agent
                llm = get_llm_for_agent(agent_id)

                # Use same conversation context as written stream
                messages = list(input_state.get("messages", []))
                spoken_messages = [SystemMessage(content=spoken_prompt)] + messages

                async for chunk in llm.astream(spoken_messages):
                    if hasattr(chunk, "content") and chunk.content:
                        await spoken_queue.put(str(chunk.content))

            except Exception as e:
                error_msg = str(e)
                log.error(f"Error generating spoken response: {error_msg}")
                if protocol_handler.is_connected:
                    await protocol_handler.send_spoken_text_error(
                        message_id, "generation_failed", error_msg
                    )
            finally:
                await spoken_queue.put(None)

        async def stream_spoken_to_frontend() -> None:
            """Stream spoken chunks to frontend as they arrive (summarize mode only)."""
            while True:
                chunk = await spoken_queue.get()
                if chunk is None:
                    break
                if protocol_handler.is_connected:
                    await protocol_handler.send_spoken_text_content(message_id, chunk)

        async for event in self.graph.astream_events(
            input_state, config=config, version="v2"
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content = str(chunk.content)
                    full_response.append(content)

                    if protocol_handler.is_connected:
                        # Start BOTH channels on first content
                        if not message_started:
                            await protocol_handler.send_text_message_start(
                                message_id, "assistant"
                            )
                            await protocol_handler.send_spoken_text_start(
                                message_id, "assistant"
                            )
                            message_started = True
                            spoken_message_started = True

                            # In 'summarize' mode: start parallel LLM call for spoken
                            if spoken_mode == "summarize":
                                spoken_task = asyncio.create_task(
                                    generate_spoken_parallel(current_agent_id)
                                )
                                asyncio.create_task(stream_spoken_to_frontend())

                        # Send written content
                        await protocol_handler.send_text_message_content(
                            message_id, content
                        )

                        # In 'dictate' mode: duplicate content to spoken channel
                        if spoken_mode == "dictate":
                            await protocol_handler.send_spoken_text_content(
                                message_id, content
                            )

            # ... rest of event handling (tool_start, tool_end, chain_end) unchanged ...
            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_run_id = event.get("run_id", str(uuid.uuid4()))
                # ... existing tool handling code ...

            elif kind == "on_tool_end":
                tool_run_id = event.get("run_id", "")
                # ... existing tool handling code ...

            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "current_agent" in output:
                    new_agent = output["current_agent"]
                    if new_agent != current_agent_id:
                        log.info(f"Agent changed: {current_agent_id} → {new_agent}")
                        await self.audit.log_handoff(
                            thread_id, current_agent_id, new_agent
                        )
                        current_agent_id = new_agent
                        # ... existing handoff handling code ...

        # Wait for spoken task to complete (only in 'summarize' mode)
        if spoken_task:
            try:
                await spoken_task
            except Exception as e:
                log.error(f"Spoken task failed: {e}")

        # Finalize BOTH channels
        if protocol_handler.is_connected:
            if message_started:
                await protocol_handler.send_text_message_end(message_id)
            if spoken_message_started:
                await protocol_handler.send_spoken_text_end(message_id)
            if current_step:
                await protocol_handler.send_step_finished(current_step)

        return "".join(full_response), current_agent_id
```

#### 4. Update server.py to Pass UserManager to Orchestrator
**File**: `server-langgraph/src/agora_langgraph/api/server.py`
**Changes**: Pass UserManager instance when creating Orchestrator

```python
# In websocket handler setup:
orchestrator = Orchestrator(user_manager=app.state.user_manager)
```

**Key Points:**
- Both channels ALWAYS stream (written + spoken) for UI consistency
- User preference fetched from UserManager at stream start
- **'dictate' mode**: Each written chunk is duplicated to spoken channel (no extra LLM call)
- **'summarize' mode**: Parallel LLM call with speech-optimized prompt
- Both channels share the same `messageId` for correlation
- Errors in spoken stream send `agora:spoken_text_error` event, written continues

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-langgraph && mypy src/`
- [ ] Linting passes: `cd server-langgraph && ruff check src/`
- [ ] Unit tests pass: `cd server-langgraph && pytest`
- [ ] Black formatting: `cd server-langgraph && black src/`

#### Manual Verification:
- [ ] With `spoken_text_type: 'dictate'`: Written and spoken content are identical
- [ ] With `spoken_text_type: 'summarize'`: Both streams run in parallel, spoken is shorter
- [ ] Both channels always emit events (regardless of mode)
- [ ] Both streams share the same `messageId`
- [ ] In summarize mode: Spoken text is shorter and more conversational
- [ ] On spoken error (summarize mode): `agora:spoken_text_error` event is sent, written continues

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 5.

---

## Phase 5: OpenAI SDK Orchestrator Integration (Preference-Driven)

### Overview
Implement dual-channel streaming in the server-openai backend, controlled by the user's `spoken_text_type` preference. Mirrors the LangGraph implementation from Phase 4.

**Key Difference**: OpenAI Agents SDK uses `Runner.run_streamed()` which we can't easily intercept. We handle the dual-channel logic in `stream_callback`.

### Changes Required:

#### 1. Update Orchestrator Imports
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Add imports for preference handling

```python
from agora_openai.core.agent_definitions import get_spoken_prompt
from agora_openai.adapters.user_manager import UserManager
```

#### 2. Add UserManager to Orchestrator __init__
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Accept UserManager in constructor for preference fetching

```python
def __init__(self, user_manager: UserManager | None = None):
    # ... existing init code ...
    self.user_manager = user_manager
```

#### 3. Modify process_message for Preference-Driven Dual-Channel
**File**: `server-openai/src/agora_openai/pipelines/orchestrator.py`
**Changes**: Implement dual-channel streaming with preference-driven behavior

```python
# In process_message method:

            # Fetch user preference for spoken response mode
            spoken_mode = "summarize"  # default
            if self.user_manager:
                try:
                    user = await self.user_manager.get_user(agent_input.user_id)
                    if user:
                        prefs = user.get("preferences", {})
                        spoken_mode = prefs.get("spoken_text_type", "summarize")
                except Exception as e:
                    log.warning(f"Failed to fetch user preferences: {e}, using default")

            # Parallel spoken task state (only used in 'summarize' mode)
            spoken_task: asyncio.Task | None = None
            spoken_queue: asyncio.Queue[str | None] = asyncio.Queue()
            spoken_message_started = False

            async def generate_spoken_parallel() -> None:
                """Generate spoken response in TRUE PARALLEL (summarize mode only)."""
                try:
                    spoken_prompt = get_spoken_prompt(current_agent_id)
                    if not spoken_prompt:
                        log.warning(f"No spoken prompt for agent {current_agent_id}")
                        await protocol_handler.send_spoken_text_error(
                            message_id, "prompt_not_found",
                            f"No spoken prompt defined for agent: {current_agent_id}"
                        )
                        return

                    from openai import AsyncOpenAI
                    settings = get_settings()
                    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

                    # Use same conversation context as written stream
                    conversation = [{"role": m.get("role"), "content": m.get("content")}
                                   for m in agent_input.messages]
                    spoken_messages = [{"role": "system", "content": spoken_prompt}] + conversation

                    stream = await client.chat.completions.create(
                        model=settings.openai_model,
                        messages=spoken_messages,
                        stream=True,
                    )

                    async for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            await spoken_queue.put(chunk.choices[0].delta.content)

                except Exception as e:
                    error_msg = str(e)
                    log.error(f"Error generating spoken response: {error_msg}")
                    if protocol_handler.is_connected:
                        await protocol_handler.send_spoken_text_error(
                            message_id, "generation_failed", error_msg
                        )
                finally:
                    await spoken_queue.put(None)

            async def stream_spoken_to_frontend() -> None:
                """Stream spoken chunks to frontend as they arrive (summarize mode only)."""
                while True:
                    chunk = await spoken_queue.get()
                    if chunk is None:
                        break
                    if protocol_handler.is_connected:
                        await protocol_handler.send_spoken_text_content(message_id, chunk)

            async def stream_callback(
                chunk: str, agent_id: str | None = None
            ) -> None:
                """Send each chunk to written channel, and handle spoken channel based on mode."""
                nonlocal message_started, current_agent_id, spoken_task, spoken_message_started
                if protocol_handler and protocol_handler.is_connected:
                    # ... existing agent change handling ...

                    # Start BOTH channels on first content
                    if not message_started:
                        await protocol_handler.send_text_message_start(
                            message_id, "assistant"
                        )
                        await protocol_handler.send_spoken_text_start(
                            message_id, "assistant"
                        )
                        message_started = True
                        spoken_message_started = True

                        # In 'summarize' mode: start parallel LLM call for spoken
                        if spoken_mode == "summarize":
                            spoken_task = asyncio.create_task(generate_spoken_parallel())
                            asyncio.create_task(stream_spoken_to_frontend())

                    # Send written content
                    await protocol_handler.send_text_message_content(
                        message_id, chunk
                    )

                    # In 'dictate' mode: duplicate content to spoken channel
                    if spoken_mode == "dictate":
                        await protocol_handler.send_spoken_text_content(
                            message_id, chunk
                        )

            # ... run_agent call ...

            # Wait for spoken task to complete (only in 'summarize' mode)
            if spoken_task:
                try:
                    await spoken_task
                except Exception as e:
                    log.error(f"Spoken task failed: {e}")

            # Finalize BOTH channels
            if protocol_handler.is_connected:
                if message_started:
                    await protocol_handler.send_text_message_end(message_id)
                if spoken_message_started:
                    await protocol_handler.send_spoken_text_end(message_id)
```

#### 4. Update server.py to Pass UserManager to Orchestrator
**File**: `server-openai/src/agora_openai/api/server.py`
**Changes**: Pass UserManager instance when creating Orchestrator

```python
# In websocket handler setup:
orchestrator = Orchestrator(user_manager=app.state.user_manager)
```

**Key Points:**
- Both channels ALWAYS stream (written + spoken) for UI consistency
- User preference fetched from UserManager at process_message start
- **'dictate' mode**: Each written chunk is duplicated to spoken channel (no extra LLM call)
- **'summarize' mode**: Parallel LLM call with speech-optimized prompt
- Both channels share the same `messageId` for correlation
- Errors in spoken stream send `agora:spoken_text_error` event, written continues

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd server-openai && mypy src/`
- [ ] Linting passes: `cd server-openai && ruff check src/`
- [ ] Unit tests pass: `cd server-openai && pytest`
- [ ] Black formatting: `cd server-openai && black src/`

#### Manual Verification:
- [ ] With `spoken_text_type: 'dictate'`: Written and spoken content are identical
- [ ] With `spoken_text_type: 'summarize'`: Both streams run in parallel, spoken is shorter
- [ ] Both channels always emit events (regardless of mode)
- [ ] Both streams share the same `messageId`
- [ ] In summarize mode: Spoken text is shorter and more conversational
- [ ] On spoken error (summarize mode): `agora:spoken_text_error` event is sent, written continues

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to Phase 6.

---

## Phase 6: End-to-End Testing

### Overview
Test the complete flow from frontend WebSocket to both backends with both `spoken_text_type` preferences.

### Changes Required:

#### 1. Create Integration Test
**File**: `server-langgraph/tests/integration/test_dual_channel_spoken.py` (new file)

```python
"""Integration tests for dual-channel spoken text streaming."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from agora_langgraph.pipelines.orchestrator import Orchestrator
from agora_langgraph.common.ag_ui_types import RunAgentInput


@pytest.fixture
def mock_protocol_handler():
    """Create a mock protocol handler that records events."""
    handler = AsyncMock()
    handler.is_connected = True
    handler.events = []

    async def record_event(method_name, *args, **kwargs):
        handler.events.append((method_name, args, kwargs))

    handler.send_text_message_start = AsyncMock(side_effect=lambda *a, **kw: record_event("text_start", *a, **kw))
    handler.send_text_message_content = AsyncMock(side_effect=lambda *a, **kw: record_event("text_content", *a, **kw))
    handler.send_text_message_end = AsyncMock(side_effect=lambda *a, **kw: record_event("text_end", *a, **kw))
    handler.send_spoken_text_start = AsyncMock(side_effect=lambda *a, **kw: record_event("spoken_start", *a, **kw))
    handler.send_spoken_text_content = AsyncMock(side_effect=lambda *a, **kw: record_event("spoken_content", *a, **kw))
    handler.send_spoken_text_end = AsyncMock(side_effect=lambda *a, **kw: record_event("spoken_end", *a, **kw))
    # Add other required mocks...

    return handler


@pytest.fixture
def mock_user_manager_summarize():
    """Create a mock UserManager returning 'summarize' preference."""
    manager = AsyncMock()
    manager.get_user = AsyncMock(return_value={
        "preferences": {"spoken_text_type": "summarize"}
    })
    return manager


@pytest.fixture
def mock_user_manager_dictate():
    """Create a mock UserManager returning 'dictate' preference."""
    manager = AsyncMock()
    manager.get_user = AsyncMock(return_value={
        "preferences": {"spoken_text_type": "dictate"}
    })
    return manager


@pytest.mark.asyncio
async def test_summarize_mode_parallel_generation(mock_protocol_handler, mock_user_manager_summarize):
    """Test that summarize mode generates spoken text via parallel LLM call."""
    # ... test implementation with mock_user_manager_summarize ...

    # Verify both channels emit events
    spoken_starts = [e for e in mock_protocol_handler.events if e[0] == "spoken_start"]
    spoken_contents = [e for e in mock_protocol_handler.events if e[0] == "spoken_content"]
    spoken_ends = [e for e in mock_protocol_handler.events if e[0] == "spoken_end"]
    text_contents = [e for e in mock_protocol_handler.events if e[0] == "text_content"]

    assert len(spoken_starts) == 1
    assert len(spoken_ends) == 1
    assert len(spoken_contents) > 0
    # In summarize mode, spoken content should differ from written content
    # (shorter, TTS-friendly)


@pytest.mark.asyncio
async def test_dictate_mode_duplicates_content(mock_protocol_handler, mock_user_manager_dictate):
    """Test that dictate mode duplicates written content to spoken channel."""
    # ... test implementation with mock_user_manager_dictate ...

    # Verify both channels emit events
    spoken_starts = [e for e in mock_protocol_handler.events if e[0] == "spoken_start"]
    spoken_contents = [e for e in mock_protocol_handler.events if e[0] == "spoken_content"]
    spoken_ends = [e for e in mock_protocol_handler.events if e[0] == "spoken_end"]
    text_contents = [e for e in mock_protocol_handler.events if e[0] == "text_content"]

    assert len(spoken_starts) == 1
    assert len(spoken_ends) == 1
    # In dictate mode, spoken and written content counts should match
    assert len(spoken_contents) == len(text_contents)


@pytest.mark.asyncio
async def test_both_channels_always_emit(mock_protocol_handler, mock_user_manager_dictate):
    """Test that both channels always emit events regardless of mode."""
    # ... test implementation ...

    # Both channels should always have start/end events
    text_starts = [e for e in mock_protocol_handler.events if e[0] == "text_start"]
    text_ends = [e for e in mock_protocol_handler.events if e[0] == "text_end"]
    spoken_starts = [e for e in mock_protocol_handler.events if e[0] == "spoken_start"]
    spoken_ends = [e for e in mock_protocol_handler.events if e[0] == "spoken_end"]

    assert len(text_starts) == 1
    assert len(text_ends) == 1
    assert len(spoken_starts) == 1
    assert len(spoken_ends) == 1
```

### Success Criteria:

#### Automated Verification:
- [ ] Integration tests pass: `cd server-langgraph && pytest tests/integration/`
- [ ] Integration tests pass: `cd server-openai && pytest tests/integration/`

#### Manual Verification:
- [ ] Start HAI frontend and backend
- [ ] Set user preference to `'dictate'` via UI or REST endpoint
- [ ] Send a message and verify written and spoken content are identical
- [ ] Set user preference to `'summarize'` via UI or REST endpoint
- [ ] Send a message and verify spoken text is shorter than written text
- [ ] Verify both channels always emit events (regardless of mode)
- [ ] Verify no markdown in spoken text (summarize mode)
- [ ] Verify abbreviations are expanded in spoken text (summarize mode)

**Implementation Note**: This is the final phase. After all tests pass, the feature is complete.

---

## Testing Strategy

### Unit Tests
- Test `get_spoken_prompt()` returns correct prompts for each agent
- Test AG-UI handler methods emit correct event structure
- Test UserManager preference retrieval

### Integration Tests
- Test full flow with mock LLM and mock UserManager
- Test that both channels always emit events
- Test 'dictate' mode duplicates content correctly
- Test 'summarize' mode generates different spoken content
- Test graceful degradation when spoken generation fails (summarize mode)
- Test messageId correlation between written and spoken streams

### Manual Testing Steps
1. Start HAI frontend: `cd HAI && pnpm run dev`
2. Start backend: `python -m agora_langgraph.api.server`
3. Open browser DevTools → Network → WS
4. **Test 'dictate' mode:**
   - Set preference via `PUT /users/me/preferences` with `{"spoken_text_type": "dictate"}`
   - Send message: "Hallo, start inspectie bij Bakkerij Jansen KVK 12345678"
   - Verify in WS messages that spoken content matches written content exactly
5. **Test 'summarize' mode:**
   - Set preference via `PUT /users/me/preferences` with `{"spoken_text_type": "summarize"}`
   - Send same message
   - Verify spoken content is shorter and TTS-friendly
6. Verify in both modes:
   - `TEXT_MESSAGE_START` with messageId
   - Multiple `TEXT_MESSAGE_CONTENT` events
   - `TEXT_MESSAGE_END`
   - `agora:spoken_text_start` with same messageId
   - Multiple `agora:spoken_text_content` events
   - `agora:spoken_text_end`

## Performance Considerations

1. **LLM Cost**:
   - **'dictate' mode**: No additional cost (single LLM call)
   - **'summarize' mode**: Doubles API cost (two concurrent calls)
2. **Latency**:
   - **'dictate' mode**: No added latency (same content duplicated)
   - **'summarize' mode**: True parallel execution, both streams complete at roughly the same time
3. **Memory**: Two concurrent streams require buffering via asyncio queues (minimal overhead)
4. **Stream Interleaving**: Chunks from both streams are interleaved as they arrive, giving users immediate feedback on both channels

## Migration Notes

- Default behavior is `'summarize'` mode (parallel LLM generation)
- Users can switch to `'dictate'` mode to reduce LLM costs
- No database migrations required (preferences table already exists)
- No frontend changes required (HAI should already handle spoken events)
- Preferences are per-user and persist in SQLite
- To change user preference: `PUT /users/me/preferences?user_id=<uuid>` with `{"spoken_text_type": "dictate"}` or `{"spoken_text_type": "summarize"}`

## References

- Original research: `thoughts/shared/research/2026-01-12-parallel-spoken-text-generation.md`
- AG-UI Protocol spec: `docs/hai-contract/HAI_API_CONTRACT.md:656-706`
- Mock server reference: `docs/hai-contract/mock_server.py:977-1059`
- LangGraph orchestrator: `server-langgraph/src/agora_langgraph/pipelines/orchestrator.py:300-454`
- OpenAI SDK orchestrator: `server-openai/src/agora_openai/pipelines/orchestrator.py:177-205`
