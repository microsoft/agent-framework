# Copyright (c) Microsoft. All rights reserved.

"""Tests for ChatKit to Agent Framework converter utilities."""

from unittest.mock import Mock

import pytest
from agent_framework import ChatMessage, Role

from agent_framework_chatkit import ThreadItemConverter, simple_to_agent_input


class TestThreadItemConverter:
    """Tests for ThreadItemConverter class."""

    @pytest.fixture
    def converter(self):
        """Create a ThreadItemConverter instance for testing."""
        return ThreadItemConverter()

    async def test_to_agent_input_none(self, converter):
        """Test converting None input returns empty list."""
        result = await converter.to_agent_input(None)
        assert result == []

    async def test_to_agent_input_with_text(self, converter):
        """Test converting user message with text content."""
        # Mock a ChatKit UserMessageItem
        content_part = Mock()
        content_part.text = "Hello, how can you help me?"

        input_item = Mock()
        input_item.content = [content_part]

        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        assert isinstance(result[0], ChatMessage)
        assert result[0].role == Role.USER
        assert result[0].text == "Hello, how can you help me?"

    async def test_to_agent_input_empty_text(self, converter):
        """Test converting user message with empty or whitespace-only text."""
        content_part = Mock()
        content_part.text = "   "

        input_item = Mock()
        input_item.content = [content_part]

        result = await converter.to_agent_input(input_item)
        assert result == []

    async def test_to_agent_input_no_content(self, converter):
        """Test converting user message with no content."""
        input_item = Mock()
        input_item.content = None

        result = await converter.to_agent_input(input_item)
        assert result == []

    async def test_to_agent_input_multiple_content_parts(self, converter):
        """Test converting user message with multiple text content parts."""
        content_part1 = Mock()
        content_part1.text = "Hello "

        content_part2 = Mock()
        content_part2.text = "world!"

        input_item = Mock()
        input_item.content = [content_part1, content_part2]

        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        assert result[0].text == "Hello world!"

    def test_hidden_context_to_input(self, converter):
        """Test converting hidden context item to ChatMessage."""
        hidden_item = Mock()
        hidden_item.content = "This is hidden context information"

        result = converter.hidden_context_to_input(hidden_item)

        assert isinstance(result, ChatMessage)
        assert result.role == Role.SYSTEM
        assert result.text == "<HIDDEN_CONTEXT>This is hidden context information</HIDDEN_CONTEXT>"

    def test_tag_to_message_content(self, converter):
        """Test converting tag to message content."""
        tag_data = Mock()
        tag_data.name = "user123"

        tag = Mock()
        tag.data = tag_data

        result = converter.tag_to_message_content(tag)
        assert result == "<TAG>Name:user123</TAG>"

    def test_tag_to_message_content_no_name(self, converter):
        """Test converting tag with no name to message content."""
        tag_data = Mock()
        del tag_data.name  # Remove name attribute

        tag = Mock()
        tag.data = tag_data

        result = converter.tag_to_message_content(tag)
        assert result == "<TAG>Name:unknown</TAG>"

    async def test_attachment_to_message_content_not_implemented(self, converter):
        """Test that attachment conversion raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await converter.attachment_to_message_content(Mock())


class TestSimpleToAgentInput:
    """Tests for simple_to_agent_input helper function."""

    async def test_simple_to_agent_input_none(self):
        """Test simple conversion with None input."""
        result = await simple_to_agent_input(None)
        assert result == []

    async def test_simple_to_agent_input_with_text(self):
        """Test simple conversion with text content."""
        content_part = Mock()
        content_part.text = "Test message"

        input_item = Mock()
        input_item.content = [content_part]

        result = await simple_to_agent_input(input_item)

        assert len(result) == 1
        assert isinstance(result[0], ChatMessage)
        assert result[0].role == Role.USER
        assert result[0].text == "Test message"
