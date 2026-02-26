# Copyright (c) Microsoft. All rights reserved.

"""Tests for thread.message.completed event handling in Assistants API streaming.

Validates that _process_stream_events correctly handles thread.message.completed
events, extracting fully-resolved annotations from the completed ThreadMessage.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework.openai._assistants_client import OpenAIAssistantsClient


def _make_stream_event(event: str, data: Any) -> MagicMock:
    """Create a mock stream event."""
    mock = MagicMock()
    mock.event = event
    mock.data = data
    return mock


def _make_text_block(text_value: str, annotations: list | None = None) -> MagicMock:
    """Create a mock TextContentBlock with optional annotations."""
    block = MagicMock()
    block.type = "text"
    block.text = MagicMock()
    block.text.value = text_value
    block.text.annotations = annotations or []
    return block


def _make_image_block() -> MagicMock:
    """Create a mock ImageContentBlock (non-text block)."""
    block = MagicMock()
    block.type = "image_file"
    return block


def _make_file_citation_annotation(
    text: str = "【4:0†source】",
    file_id: str = "file-abc123",
    start_index: int = 10,
    end_index: int = 24,
    quote: str | None = None,
) -> MagicMock:
    """Create a mock FileCitationAnnotation."""
    from openai.types.beta.threads import FileCitationAnnotation

    annotation = MagicMock(spec=FileCitationAnnotation)
    annotation.text = text
    annotation.start_index = start_index
    annotation.end_index = end_index
    annotation.file_citation = MagicMock()
    annotation.file_citation.file_id = file_id
    annotation.file_citation.quote = quote
    return annotation


def _make_file_path_annotation(
    text: str = "sandbox:/file.csv",
    file_id: str = "file-xyz789",
    start_index: int = 5,
    end_index: int = 22,
) -> MagicMock:
    """Create a mock FilePathAnnotation."""
    from openai.types.beta.threads import FilePathAnnotation

    annotation = MagicMock(spec=FilePathAnnotation)
    annotation.text = text
    annotation.start_index = start_index
    annotation.end_index = end_index
    annotation.file_path = MagicMock()
    annotation.file_path.file_id = file_id
    return annotation


def _make_unknown_annotation() -> MagicMock:
    """Create a mock annotation of an unrecognized type."""
    annotation = MagicMock()
    annotation.__class__.__name__ = "FutureAnnotationType"
    return annotation


def _make_thread_message(content_blocks: list) -> MagicMock:
    """Create a mock ThreadMessage."""
    from openai.types.beta.threads import Message as ThreadMessage

    msg = MagicMock(spec=ThreadMessage)
    msg.content = content_blocks
    return msg


async def _collect_updates(client, stream_events, thread_id="thread_123"):
    """Helper to collect ChatResponseUpdate objects from _process_stream_events."""

    class MockAsyncStream:
        def __init__(self, events):
            self._events = events

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._events:
                raise StopAsyncIteration
            return self._events.pop(0)

    mock_stream = MockAsyncStream(list(stream_events))
    results = []
    async for update in client._process_stream_events(mock_stream, thread_id):
        results.append(update)
    return results


class TestMessageCompletedAnnotations:
    """Tests for thread.message.completed event handling."""

    @pytest.fixture
    def client(self):
        """Create a client instance for testing."""
        with patch.object(OpenAIAssistantsClient, "__init__", lambda self, **kw: None):
            c = object.__new__(OpenAIAssistantsClient)
            return c

    @pytest.mark.asyncio
    async def test_message_completed_with_file_citation(self, client):
        """Verify file citation annotations are extracted from completed messages."""
        citation = _make_file_citation_annotation(
            text="【4:0†source】", file_id="file-abc123", start_index=10, end_index=24
        )
        text_block = _make_text_block("Some text with a citation【4:0†source】", [citation])
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        # Should yield exactly one update for the completed message
        assert len(updates) == 1
        update = updates[0]
        assert update.role == "assistant"
        assert len(update.contents) == 1

        content = update.contents[0]
        assert content.text == "Some text with a citation【4:0†source】"
        assert content.annotations is not None
        assert len(content.annotations) == 1

        ann = content.annotations[0]
        assert ann["type"] == "citation"
        assert ann["file_id"] == "file-abc123"
        assert ann["annotated_regions"][0]["start_index"] == 10
        assert ann["annotated_regions"][0]["end_index"] == 24

    @pytest.mark.asyncio
    async def test_message_completed_with_file_citation_quote(self, client):
        """Verify the quote field from file_citation is included in additional_properties."""
        citation = _make_file_citation_annotation(
            text="【4:0†source】",
            file_id="file-abc123",
            start_index=10,
            end_index=24,
            quote="The exact quoted text from the source document.",
        )
        text_block = _make_text_block("Some text【4:0†source】", [citation])
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        assert len(updates) == 1
        ann = updates[0].contents[0].annotations[0]
        assert ann["additional_properties"]["quote"] == "The exact quoted text from the source document."

    @pytest.mark.asyncio
    async def test_message_completed_with_file_citation_no_quote(self, client):
        """Verify annotations work when quote is None (not all citations have quotes)."""
        citation = _make_file_citation_annotation(
            text="【4:0†source】", file_id="file-abc123", start_index=10, end_index=24, quote=None
        )
        text_block = _make_text_block("Some text【4:0†source】", [citation])
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        assert len(updates) == 1
        ann = updates[0].contents[0].annotations[0]
        assert "quote" not in ann["additional_properties"]

    @pytest.mark.asyncio
    async def test_message_completed_with_file_path(self, client):
        """Verify file path annotations are extracted from completed messages."""
        file_path = _make_file_path_annotation(
            text="sandbox:/output.csv", file_id="file-xyz789", start_index=0, end_index=19
        )
        text_block = _make_text_block("sandbox:/output.csv", [file_path])
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        assert len(updates) == 1
        content = updates[0].contents[0]
        assert content.annotations is not None
        assert len(content.annotations) == 1

        ann = content.annotations[0]
        assert ann["type"] == "citation"
        assert ann["file_id"] == "file-xyz789"
        assert ann["annotated_regions"][0]["start_index"] == 0
        assert ann["annotated_regions"][0]["end_index"] == 19

    @pytest.mark.asyncio
    async def test_message_completed_multiple_annotations(self, client):
        """Verify multiple annotations on a single text block are all captured."""
        cit1 = _make_file_citation_annotation(text="【1†src】", file_id="file-a", start_index=5, end_index=12)
        cit2 = _make_file_citation_annotation(text="【2†src】", file_id="file-b", start_index=20, end_index=27)
        text_block = _make_text_block("Hello【1†src】world【2†src】", [cit1, cit2])
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        assert len(updates) == 1
        assert len(updates[0].contents[0].annotations) == 2
        assert updates[0].contents[0].annotations[0]["file_id"] == "file-a"
        assert updates[0].contents[0].annotations[1]["file_id"] == "file-b"

    @pytest.mark.asyncio
    async def test_message_completed_no_annotations(self, client):
        """Verify text-only completed messages produce content without annotations."""
        text_block = _make_text_block("Plain text response")
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        assert len(updates) == 1
        content = updates[0].contents[0]
        assert content.text == "Plain text response"
        assert content.annotations is None or len(content.annotations) == 0

    @pytest.mark.asyncio
    async def test_message_completed_skips_non_text_blocks(self, client):
        """Verify non-text content blocks (e.g., image_file) are skipped."""
        image_block = _make_image_block()
        msg = _make_thread_message([image_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        # No text blocks → no update yielded
        assert len(updates) == 0

    @pytest.mark.asyncio
    async def test_message_completed_mixed_blocks(self, client):
        """Verify only text blocks are processed in mixed-content messages."""
        text_block = _make_text_block("Text content here")
        image_block = _make_image_block()
        msg = _make_thread_message([image_block, text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events)

        assert len(updates) == 1
        assert len(updates[0].contents) == 1
        assert updates[0].contents[0].text == "Text content here"

    @pytest.mark.asyncio
    async def test_message_completed_conversation_id_preserved(self, client):
        """Verify the thread_id is correctly propagated as conversation_id."""
        text_block = _make_text_block("Response text")
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        updates = await _collect_updates(client, events, thread_id="thread_custom_456")

        assert len(updates) == 1
        assert updates[0].conversation_id == "thread_custom_456"

    @pytest.mark.asyncio
    async def test_message_completed_unrecognized_annotation_logged(self, client, caplog):
        """Verify unrecognized annotation types are logged at debug level and skipped."""
        unknown_ann = _make_unknown_annotation()
        citation = _make_file_citation_annotation(text="【1†src】", file_id="file-a", start_index=0, end_index=7)
        text_block = _make_text_block("Text【1†src】", [unknown_ann, citation])
        msg = _make_thread_message([text_block])

        events = [_make_stream_event("thread.message.completed", msg)]
        with caplog.at_level(logging.DEBUG, logger="agent_framework.openai._assistants_client"):
            updates = await _collect_updates(client, events)

        # The known citation should still be processed
        assert len(updates) == 1
        assert len(updates[0].contents[0].annotations) == 1
        assert updates[0].contents[0].annotations[0]["file_id"] == "file-a"

        # The unrecognized annotation should have been logged
        assert any("Unhandled annotation type" in record.message for record in caplog.records)
