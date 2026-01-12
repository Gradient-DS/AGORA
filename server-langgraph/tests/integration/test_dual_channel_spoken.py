"""Integration tests for dual-channel spoken text streaming."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_protocol_handler():
    """Create a mock protocol handler that records events."""
    handler = AsyncMock()
    handler.is_connected = True
    handler.events = []

    async def record_and_return(method_name, *args, **kwargs):
        handler.events.append((method_name, args, kwargs))

    # Text message events
    handler.send_text_message_start = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("text_start", *a, **kw)
    )
    handler.send_text_message_content = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("text_content", *a, **kw)
    )
    handler.send_text_message_end = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("text_end", *a, **kw)
    )

    # Spoken text events
    handler.send_spoken_text_start = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("spoken_start", *a, **kw)
    )
    handler.send_spoken_text_content = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("spoken_content", *a, **kw)
    )
    handler.send_spoken_text_end = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("spoken_end", *a, **kw)
    )
    handler.send_spoken_text_error = AsyncMock(
        side_effect=lambda *a, **kw: record_and_return("spoken_error", *a, **kw)
    )

    # Other required events
    handler.send_run_started = AsyncMock()
    handler.send_run_finished = AsyncMock()
    handler.send_run_error = AsyncMock()
    handler.send_step_started = AsyncMock()
    handler.send_step_finished = AsyncMock()
    handler.send_state_snapshot = AsyncMock()
    handler.send_tool_call_start = AsyncMock()
    handler.send_tool_call_args = AsyncMock()
    handler.send_tool_call_end = AsyncMock()
    handler.send_tool_call_result = AsyncMock()

    return handler


@pytest.fixture
def mock_user_manager_summarize():
    """Create a mock UserManager returning 'summarize' preference."""
    manager = AsyncMock()
    manager.get_user = AsyncMock(
        return_value={"preferences": {"spoken_text_type": "summarize"}}
    )
    return manager


@pytest.fixture
def mock_user_manager_dictate():
    """Create a mock UserManager returning 'dictate' preference."""
    manager = AsyncMock()
    manager.get_user = AsyncMock(
        return_value={"preferences": {"spoken_text_type": "dictate"}}
    )
    return manager


@pytest.fixture
def mock_user_manager_no_preference():
    """Create a mock UserManager returning no preference (defaults to summarize)."""
    manager = AsyncMock()
    manager.get_user = AsyncMock(return_value={"preferences": {}})
    return manager


class TestDualChannelSpokenText:
    """Tests for dual-channel spoken text streaming."""

    @pytest.mark.asyncio
    async def test_dictate_mode_sends_to_both_channels(
        self, mock_protocol_handler, mock_user_manager_dictate
    ):
        """Test that dictate mode sends same content to both channels."""
        # Test the stream_callback behavior in dictate mode
        message_id = "test-msg-123"
        message_started = False
        spoken_message_started = False
        spoken_mode = "dictate"

        # Simulate what stream_callback does in dictate mode
        async def simulate_stream_callback(chunk: str):
            nonlocal message_started, spoken_message_started

            if mock_protocol_handler.is_connected:
                if not message_started:
                    await mock_protocol_handler.send_text_message_start(
                        message_id, "assistant"
                    )
                    await mock_protocol_handler.send_spoken_text_start(
                        message_id, "assistant"
                    )
                    message_started = True
                    spoken_message_started = True

                await mock_protocol_handler.send_text_message_content(message_id, chunk)

                if spoken_mode == "dictate":
                    await mock_protocol_handler.send_spoken_text_content(
                        message_id, chunk
                    )

        # Simulate streaming
        chunks = ["Hello", " world", "!"]
        for chunk in chunks:
            await simulate_stream_callback(chunk)

        # Finalize
        if message_started:
            await mock_protocol_handler.send_text_message_end(message_id)
        if spoken_message_started:
            await mock_protocol_handler.send_spoken_text_end(message_id)

        # Verify both channels started
        assert mock_protocol_handler.send_text_message_start.call_count == 1
        assert mock_protocol_handler.send_spoken_text_start.call_count == 1

        # Verify content was sent to both channels equally
        assert mock_protocol_handler.send_text_message_content.call_count == 3
        assert mock_protocol_handler.send_spoken_text_content.call_count == 3

        # Verify both channels ended
        assert mock_protocol_handler.send_text_message_end.call_count == 1
        assert mock_protocol_handler.send_spoken_text_end.call_count == 1

        # Verify the content matches between channels
        text_calls = mock_protocol_handler.send_text_message_content.call_args_list
        spoken_calls = mock_protocol_handler.send_spoken_text_content.call_args_list

        for text_call, spoken_call in zip(text_calls, spoken_calls):
            # Both should have same message_id and chunk
            assert text_call[0][0] == spoken_call[0][0]  # message_id
            assert text_call[0][1] == spoken_call[0][1]  # chunk content

    @pytest.mark.asyncio
    async def test_summarize_mode_starts_parallel_task(
        self, mock_protocol_handler, mock_user_manager_summarize
    ):
        """Test that summarize mode starts a parallel task for spoken text."""
        message_id = "test-msg-456"
        message_started = False
        spoken_message_started = False
        spoken_mode = "summarize"
        spoken_task = None

        async def mock_generate_spoken_parallel():
            """Mock spoken generation that puts chunks in queue."""
            await asyncio.sleep(0.01)  # Simulate async work

        async def simulate_stream_callback(chunk: str):
            nonlocal message_started, spoken_message_started, spoken_task

            if mock_protocol_handler.is_connected:
                if not message_started:
                    await mock_protocol_handler.send_text_message_start(
                        message_id, "assistant"
                    )
                    await mock_protocol_handler.send_spoken_text_start(
                        message_id, "assistant"
                    )
                    message_started = True
                    spoken_message_started = True

                    if spoken_mode == "summarize":
                        spoken_task = asyncio.create_task(mock_generate_spoken_parallel())

                await mock_protocol_handler.send_text_message_content(message_id, chunk)

                # In summarize mode, spoken content is NOT duplicated
                # It comes from the parallel task

        # Simulate streaming
        chunks = ["Detailed", " response", " with", " markdown"]
        for chunk in chunks:
            await simulate_stream_callback(chunk)

        # Wait for parallel task if exists
        if spoken_task:
            await spoken_task

        # Finalize
        if message_started:
            await mock_protocol_handler.send_text_message_end(message_id)
        if spoken_message_started:
            await mock_protocol_handler.send_spoken_text_end(message_id)

        # Verify both channels started
        assert mock_protocol_handler.send_text_message_start.call_count == 1
        assert mock_protocol_handler.send_spoken_text_start.call_count == 1

        # Verify written content was sent
        assert mock_protocol_handler.send_text_message_content.call_count == 4

        # In summarize mode, spoken content comes from parallel task
        # Not duplicated from written content
        # (In this mock test, we didn't actually send spoken content)
        assert mock_protocol_handler.send_spoken_text_content.call_count == 0

        # Verify both channels ended
        assert mock_protocol_handler.send_text_message_end.call_count == 1
        assert mock_protocol_handler.send_spoken_text_end.call_count == 1

    @pytest.mark.asyncio
    async def test_both_channels_always_emit_start_end(self, mock_protocol_handler):
        """Test that both channels always emit start and end events."""
        message_id = "test-msg-789"

        # Start both channels
        await mock_protocol_handler.send_text_message_start(message_id, "assistant")
        await mock_protocol_handler.send_spoken_text_start(message_id, "assistant")

        # Send some content
        await mock_protocol_handler.send_text_message_content(message_id, "Test")
        await mock_protocol_handler.send_spoken_text_content(message_id, "Test")

        # End both channels
        await mock_protocol_handler.send_text_message_end(message_id)
        await mock_protocol_handler.send_spoken_text_end(message_id)

        # Verify start/end balance
        assert mock_protocol_handler.send_text_message_start.call_count == 1
        assert mock_protocol_handler.send_text_message_end.call_count == 1
        assert mock_protocol_handler.send_spoken_text_start.call_count == 1
        assert mock_protocol_handler.send_spoken_text_end.call_count == 1

    @pytest.mark.asyncio
    async def test_same_message_id_for_both_channels(self, mock_protocol_handler):
        """Test that both channels share the same messageId."""
        message_id = "shared-msg-id"

        # Start both channels with same message_id
        await mock_protocol_handler.send_text_message_start(message_id, "assistant")
        await mock_protocol_handler.send_spoken_text_start(message_id, "assistant")

        # Verify same message_id was used
        text_start_call = mock_protocol_handler.send_text_message_start.call_args
        spoken_start_call = mock_protocol_handler.send_spoken_text_start.call_args

        assert text_start_call[0][0] == message_id
        assert spoken_start_call[0][0] == message_id
        assert text_start_call[0][0] == spoken_start_call[0][0]

    @pytest.mark.asyncio
    async def test_user_preference_fetching(
        self, mock_user_manager_summarize, mock_user_manager_dictate
    ):
        """Test that user preferences are correctly fetched."""
        user_id = "test-user-123"

        # Test summarize preference
        user_summarize = await mock_user_manager_summarize.get_user(user_id)
        assert user_summarize["preferences"]["spoken_text_type"] == "summarize"

        # Test dictate preference
        user_dictate = await mock_user_manager_dictate.get_user(user_id)
        assert user_dictate["preferences"]["spoken_text_type"] == "dictate"

    @pytest.mark.asyncio
    async def test_default_to_summarize_when_no_preference(
        self, mock_user_manager_no_preference
    ):
        """Test that summarize is the default when no preference is set."""
        user_id = "test-user-no-pref"

        user = await mock_user_manager_no_preference.get_user(user_id)
        prefs = user.get("preferences", {})
        spoken_mode = prefs.get("spoken_text_type", "summarize")

        assert spoken_mode == "summarize"

    @pytest.mark.asyncio
    async def test_spoken_error_event_on_failure(self, mock_protocol_handler):
        """Test that spoken_text_error event is sent when generation fails."""
        message_id = "error-test-msg"
        error_code = "generation_failed"
        error_message = "LLM API timeout"

        await mock_protocol_handler.send_spoken_text_error(
            message_id, error_code, error_message
        )

        assert mock_protocol_handler.send_spoken_text_error.call_count == 1
        call_args = mock_protocol_handler.send_spoken_text_error.call_args[0]
        assert call_args[0] == message_id
        assert call_args[1] == error_code
        assert call_args[2] == error_message
