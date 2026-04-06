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
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI},
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

    def test_is_openai_multimodal_format_detects_chat_completions_format(self):
        """Test that _is_openai_multimodal_format detects Chat Completions format (no type field)."""
        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Chat Completions format: role + content, no type field
        chat_completions_format = [{"role": "user", "content": "Describe this image"}]
        assert executor._is_openai_multimodal_format(chat_completions_format) is True

    def test_convert_chat_completions_format_with_string_content(self):
        """Test that Chat Completions format with string content is converted correctly."""
        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Chat Completions format (no type field, string content)
        input_data = [{"role": "user", "content": "Which Google phones are allowed?"}]

        result = executor._convert_input_to_chat_message(input_data)

        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
        assert len(result.contents) == 1
        assert result.contents[0].text == "Which Google phones are allowed?"

    def test_convert_chat_completions_envelope_with_responses_api_content(self):
        """Test Chat Completions-style envelope (no type field) with Responses API content parts."""
        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Chat Completions format with list content (input_text items)
        input_data = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe this image"},
                    {"type": "input_image", "image_url": TEST_IMAGE_DATA_URI},
                ],
            }
        ]

        result = executor._convert_input_to_chat_message(input_data)

        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
        assert len(result.contents) == 2
        assert result.contents[0].text == "Describe this image"
        assert result.contents[1].type == "data"

    async def test_parse_workflow_input_chat_completions_json_string(self):
        """Regression test: JSON-stringified Chat Completions array goes through _parse_workflow_input."""
        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # JSON-stringified Chat Completions format (the path DevUI/frontend commonly uses)
        chat_input = json.dumps([{"role": "user", "content": "Which Google phones are allowed?"}])

        mock_workflow = MagicMock()
        mock_executor = MagicMock()
        mock_executor.input_types = [Message]
        mock_workflow.get_start_executor.return_value = mock_executor

        result = await executor._parse_workflow_input(mock_workflow, chat_input)

        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
        assert len(result.contents) == 1
        assert result.contents[0].text == "Which Google phones are allowed?"

    def test_convert_skips_non_user_messages(self):
        """Test that non-user messages (system, assistant) are skipped during conversion."""
        from agent_framework import Message

        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Mix of system and user messages - only user content should be kept
        input_data = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]

        result = executor._convert_input_to_chat_message(input_data)

        assert isinstance(result, Message), f"Expected Message, got {type(result)}"
        assert len(result.contents) == 1
        assert result.contents[0].text == "Hello!"

    def test_is_openai_multimodal_format_rejects_malformed_input(self):
        """Test that _is_openai_multimodal_format rejects inputs missing content or with invalid roles."""
        discovery = MagicMock(spec=EntityDiscovery)
        mapper = MagicMock(spec=MessageMapper)
        executor = AgentFrameworkExecutor(discovery, mapper)

        # Missing content key
        assert executor._is_openai_multimodal_format([{"role": "user"}]) is False
        # Invalid role value
        assert executor._is_openai_multimodal_format([{"role": "unknown", "content": "hi"}]) is False
        # Role is not a string
        assert executor._is_openai_multimodal_format([{"role": 123, "content": "hi"}]) is False
        # Content is neither str nor list
        assert executor._is_openai_multimodal_format([{"role": "user", "content": 42}]) is False
