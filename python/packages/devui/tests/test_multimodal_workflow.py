# Copyright (c) Microsoft. All rights reserved.

"""Test multimodal input handling for workflows.

This test verifies that workflows with AgentExecutor nodes correctly receive
multimodal content (images, files) from the DevUI frontend.
"""

import json
from unittest.mock import MagicMock

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
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe this image"},
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI},
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
        """Test that OpenAI format with image is converted to ChatMessage with DataContent."""
        from agent_framework import ChatMessage, DataContent, Role, TextContent

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
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI},
                ],
            }
        ]

        # Convert to ChatMessage
        result = executor._convert_input_to_chat_message(openai_input)

        # Verify result is ChatMessage
        assert isinstance(result, ChatMessage), f"Expected ChatMessage, got {type(result)}"
        assert result.role == Role.USER

        # Verify contents
        assert len(result.contents) == 2, f"Expected 2 contents, got {len(result.contents)}"

        # First content should be text
        assert isinstance(result.contents[0], TextContent)
        assert result.contents[0].text == "Describe this image"

        # Second content should be image (DataContent)
        assert isinstance(result.contents[1], DataContent)
        assert result.contents[1].media_type == "image/png"
        assert result.contents[1].uri == TEST_IMAGE_DATA_URI

    def test_parse_workflow_input_handles_json_string_with_multimodal(self):
        """Test that _parse_workflow_input correctly handles JSON string with multimodal content."""
        import asyncio

        from agent_framework import ChatMessage, DataContent, TextContent

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
        result = asyncio.run(executor._parse_workflow_input(mock_workflow, json_string_input))

        # Verify result is ChatMessage with multimodal content
        assert isinstance(result, ChatMessage), f"Expected ChatMessage, got {type(result)}"
        assert len(result.contents) == 2

        # Verify text content
        assert isinstance(result.contents[0], TextContent)
        assert result.contents[0].text == "What is in this image?"

        # Verify image content
        assert isinstance(result.contents[1], DataContent)
        assert result.contents[1].media_type == "image/png"

    def test_parse_workflow_input_still_handles_simple_dict(self):
        """Test that simple dict input still works (backward compatibility)."""
        import asyncio

        from agent_framework import ChatMessage

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Simple dict input (old format)
        simple_input = {"text": "Hello world", "role": "user"}
        json_string_input = json.dumps(simple_input)

        # Mock workflow with ChatMessage input type
        mock_workflow = MagicMock()
        mock_executor = MagicMock()
        mock_executor.input_types = [ChatMessage]
        mock_workflow.get_start_executor.return_value = mock_executor

        # Parse the input
        result = asyncio.run(executor._parse_workflow_input(mock_workflow, json_string_input))

        # Result should be ChatMessage (from _parse_structured_workflow_input)
        assert isinstance(result, ChatMessage), f"Expected ChatMessage, got {type(result)}"
