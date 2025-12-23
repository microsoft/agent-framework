# Copyright (c) Microsoft. All rights reserved.

"""Tests for Agent Framework to ChatKit streaming utilities."""

from unittest.mock import Mock

from agent_framework import AgentRunResponseUpdate, Role, TextContent
from chatkit.types import (
    ThreadItemAddedEvent,
    ThreadItemDoneEvent,
    ThreadItemUpdated,
)

from agent_framework_chatkit import stream_agent_response


class TestStreamAgentResponse:
    """Tests for stream_agent_response function."""

    async def test_stream_empty_response(self):
        """Test streaming empty response."""

        async def empty_stream():
            return
            yield  # Make it a generator

        events = []
        async for event in stream_agent_response(empty_stream(), thread_id="test_thread"):
            events.append(event)

        assert len(events) == 0

    async def test_stream_single_text_update(self):
        """Test streaming single text update."""

        async def single_update_stream():
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[TextContent(text="Hello world")])

        events = []
        async for event in stream_agent_response(single_update_stream(), thread_id="test_thread"):
            events.append(event)

        # Should have: item_added, item_updated (delta), item_done
        assert len(events) == 3

        # Check event types
        assert isinstance(events[0], ThreadItemAddedEvent)
        assert isinstance(events[1], ThreadItemUpdated)
        assert isinstance(events[2], ThreadItemDoneEvent)

        # Check delta event
        assert events[1].update.delta == "Hello world"

        # Check final message content
        assert len(events[2].item.content) == 1
        assert events[2].item.content[0].text == "Hello world"

    async def test_stream_multiple_text_updates(self):
        """Test streaming multiple text updates."""

        async def multiple_updates_stream():
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[TextContent(text="Hello ")])
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[TextContent(text="world!")])

        events = []
        async for event in stream_agent_response(multiple_updates_stream(), thread_id="test_thread"):
            events.append(event)

        # Should have: item_added, item_updated (delta 1), item_updated (delta 2), item_done
        assert len(events) == 4

        # Check event types
        assert isinstance(events[0], ThreadItemAddedEvent)
        assert isinstance(events[1], ThreadItemUpdated)
        assert isinstance(events[2], ThreadItemUpdated)
        assert isinstance(events[3], ThreadItemDoneEvent)

        # Check delta events
        assert events[1].update.delta == "Hello "
        assert events[2].update.delta == "world!"

        # Check final accumulated text
        final_message_event = events[-1]
        assert isinstance(final_message_event, ThreadItemDoneEvent)
        assert final_message_event.item.content[0].text == "Hello world!"

    async def test_stream_with_custom_id_generator(self):
        """Test streaming with custom ID generator."""

        def custom_id_generator(item_type: str) -> str:
            return f"custom_{item_type}_123"

        async def single_update_stream():
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[TextContent(text="Test")])

        events = []
        async for event in stream_agent_response(
            single_update_stream(), thread_id="test_thread", generate_id=custom_id_generator
        ):
            events.append(event)

        # Check that custom IDs are used
        message_added_event = events[0]
        assert message_added_event.item.id == "custom_msg_123"

    async def test_stream_empty_content_updates(self):
        """Test streaming updates with empty content."""

        async def empty_content_stream():
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[])
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=None)

        events = []
        async for event in stream_agent_response(empty_content_stream(), thread_id="test_thread"):
            events.append(event)

        # Should have item_added and item_done
        assert len(events) == 2
        assert isinstance(events[0], ThreadItemAddedEvent)
        assert isinstance(events[1], ThreadItemDoneEvent)

        # Final message should have empty content
        assert len(events[1].item.content) == 0

    async def test_stream_non_text_content(self):
        """Test streaming updates with non-text content."""
        # Mock a content object without text attribute
        non_text_content = Mock()
        # Don't set text attribute
        del non_text_content.text

        async def non_text_stream():
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[non_text_content])

        events = []
        async for event in stream_agent_response(non_text_stream(), thread_id="test_thread"):
            events.append(event)

        # Should have item_added and item_done, but no content since no text
        assert len(events) == 2
        assert isinstance(events[0], ThreadItemAddedEvent)
        assert isinstance(events[1], ThreadItemDoneEvent)
