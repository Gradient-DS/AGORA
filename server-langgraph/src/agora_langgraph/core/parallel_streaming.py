"""Parallel streaming utilities for true parallel spoken text generation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

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
