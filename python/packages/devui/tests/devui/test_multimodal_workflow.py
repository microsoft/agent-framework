# Copyright (c) Microsoft. All rights reserved.

"""Test multimodal input handling for workflows.

This test verifies that workflows with AgentExecutor nodes correctly receive
multimodal content (images, files) from the DevUI frontend.
"""

import json
from unittest.mock import MagicMock

import pytest

from agent_framework_devui._discovery import EntityDiscovery
from agent_framework_devui._executor import AgentFrameworkExecutor
from agent_framework_devui._mapper import MessageMapper

# Create a small test image (1x1 red pixel PNG)
TEST_IMAGE_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
TEST_IMAGE_DATA_URI = f"data:image/png;base64,{TEST_IMAGE_BASE64}"


class TestMultimodalWorkflowInput:
    """Test multimodal input handling for workflows."""

    def test_is_openai_multimodal_format_detects_message_format(self):
        """Test that _is_openai_multimodal_format correctly detects OpenAI format."""
        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Valid OpenAI multimodal format
        valid_format = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe this image"},
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI, "detail": "high"},
                ],
            }
        ]
        assert executor._is_openai_multimodal_format(valid_format) is True

        # Invalid formats
        assert executor._is_openai_multimodal_format({}) is False  # dict, not list
        assert executor._is_openai_multimodal_format([]) is False  # empty list
        assert executor._is_openai_multimodal_format("hello") is False  # string
        assert executor._is_openai_multimodal_format([{"type": "other"}]) is False  # wrong type
        assert executor._is_openai_multimodal_format([{"foo": "bar"}]) is False  # no type field

    def test_convert_openai_input_to_chat_message_with_image(self):
        """Test that OpenAI format with image is converted to Message with DataContent."""
        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # OpenAI format input with text and image (as sent by frontend)
        openai_input = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe this image"},
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI, "detail": "high"},
                ],
            }
        ]

        # Convert to Message
        result = executor._convert_input_to_chat_message(openai_input)

        # Verify result is Message
        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
        assert result.role == "user"

        # Verify contents
        assert len(result.contents) == 2, f"Expected 2 contents, got {len(result.contents)}"

        # First content should be text
        assert result.contents[0].type == "text"
        assert result.contents[0].text == "Describe this image"

        # Second content should be image (DataContent)
        assert result.contents[1].type == "data"
        assert result.contents[1].media_type == "image/png"
        assert result.contents[1].uri == TEST_IMAGE_DATA_URI
        assert result.contents[1].additional_properties["detail"] == "high"

    def test_convert_openai_input_preserves_message_roles_and_boundaries(self):
        """Official input message roles remain distinct Agent Framework messages."""
        from agent_framework import Message

        executor = AgentFrameworkExecutor(MagicMock(spec=EntityDiscovery), MagicMock(spec=MessageMapper))
        openai_input = [
            {"role": "system", "content": "System guidance"},
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Developer guidance"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "First part"},
                    {"type": "input_text", "text": "Second part"},
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Assistant output"},
                    {"type": "text", "text": "Generic assistant text"},
                ],
            },
        ]

        result = executor._convert_input_to_chat_message(openai_input)

        assert isinstance(result, list)
        assert all(isinstance(message, Message) for message in result)
        assert [message.role for message in result] == ["system", "developer", "user", "assistant"]
        assert [[content.text for content in message.contents] for message in result] == [
            ["System guidance"],
            ["Developer guidance"],
            ["First part", "Second part"],
            ["Assistant output", "Generic assistant text"],
        ]

    def test_convert_openai_input_preserves_file_ids_and_canonical_media_types(self):
        """Hosted files and straightforward MIME types survive input conversion."""
        executor = AgentFrameworkExecutor(MagicMock(spec=EntityDiscovery), MagicMock(spec=MessageMapper))
        openai_input = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": "https://example.com/photo.jpg?download=1",
                        "detail": "low",
                    },
                    {"type": "input_image", "file_id": "file_image", "detail": "high"},
                    {"type": "input_file", "file_id": "file_audio", "filename": "recording.mp3"},
                    {"type": "input_file", "file_url": "https://example.com/recording.m4a"},
                ],
            }
        ]

        result = executor._convert_input_to_chat_message(openai_input)

        assert result.contents[0].media_type == "image/jpeg"
        assert result.contents[0].additional_properties["detail"] == "low"
        assert result.contents[1].type == "hosted_file"
        assert result.contents[1].file_id == "file_image"
        assert result.contents[1].additional_properties["openai_content_type"] == "input_image"
        assert result.contents[1].additional_properties["detail"] == "high"
        assert result.contents[2].type == "hosted_file"
        assert result.contents[2].file_id == "file_audio"
        assert result.contents[2].media_type == "audio/mpeg"
        assert result.contents[3].media_type == "audio/mp4"

    def test_convert_openai_input_rejects_unsupported_only_content(self):
        """Unsupported input must not become a fabricated empty user message."""
        executor = AgentFrameworkExecutor(MagicMock(spec=EntityDiscovery), MagicMock(spec=MessageMapper))
        openai_input = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "unsupported_content", "value": "ignored"}],
            }
        ]

        with pytest.raises(ValueError, match="did not contain any supported message content"):
            executor._convert_input_to_chat_message(openai_input)

    def test_convert_openai_input_rejects_each_unsupported_only_message(self):
        """A valid message must not hide another message with no supported content."""
        executor = AgentFrameworkExecutor(MagicMock(spec=EntityDiscovery), MagicMock(spec=MessageMapper))
        openai_input = [
            {"type": "message", "role": "user", "content": "Valid message"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "unsupported_content", "value": "ignored"}],
            },
        ]

        with pytest.raises(ValueError, match="did not contain any supported message content"):
            executor._convert_input_to_chat_message(openai_input)

    async def test_parse_workflow_input_rejects_unsupported_only_content(self):
        """Workflow parsing must not fall back to the raw unsupported payload."""
        executor = AgentFrameworkExecutor(MagicMock(spec=EntityDiscovery), MagicMock(spec=MessageMapper))
        openai_input = [
            {
                "role": "user",
                "content": [{"type": "unsupported_content", "value": "ignored"}],
            }
        ]

        with pytest.raises(ValueError, match="did not contain any supported message content"):
            await executor._parse_workflow_input(MagicMock(), openai_input)

    async def test_parse_workflow_input_handles_json_string_with_multimodal(self):
        """Test that _parse_workflow_input correctly handles JSON string with multimodal content."""

        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # This is what the frontend sends: JSON stringified OpenAI format
        openai_input = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "What is in this image?"},
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI},
                ],
            }
        ]
        json_string_input = json.dumps(openai_input)

        # Mock workflow
        mock_workflow = MagicMock()

        # Parse the input
        result = await executor._parse_workflow_input(mock_workflow, json_string_input)

        # Verify result is Message with multimodal content
        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
        assert len(result.contents) == 2

        # Verify text content
        assert result.contents[0].type == "text"
        assert result.contents[0].text == "What is in this image?"

        # Verify image content
        assert result.contents[1].type == "data"
        assert result.contents[1].media_type == "image/png"

    async def test_parse_workflow_input_still_handles_simple_dict(self):
        """Test that simple dict input still works (backward compatibility)."""

        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Simple dict input (old format)
        simple_input = {"text": "Hello world", "role": "user"}
        json_string_input = json.dumps(simple_input)

        # Mock workflow with Message input type
        mock_workflow = MagicMock()
        mock_executor = MagicMock()
        mock_executor.input_types = [Message]
        mock_workflow.get_start_executor.return_value = mock_executor

        # Parse the input
        result = await executor._parse_workflow_input(mock_workflow, json_string_input)

        # Result should be Message (from _parse_structured_workflow_input)
        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
