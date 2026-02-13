# Copyright (c) Microsoft. All rights reserved.

"""Tests for ensuring instructions are not repeated in continued conversations."""

from unittest.mock import MagicMock, patch

import pytest

from agent_framework import Message
from agent_framework.openai import OpenAIResponsesClient


@pytest.mark.asyncio
async def test_instructions_not_repeated_with_conversation_id() -> None:
    """Test that instructions are not sent again when conversation_id is present."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock the OpenAI client
    mock_response = MagicMock()
    mock_response.id = "resp_123"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.finish_reason = None

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Hello! How can I help?"
    mock_message_content.annotations = []

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        # First call - no conversation_id, should include instructions
        await client.get_response(
            messages=[Message(role="user", text="Hello")],
            options={"instructions": "Reply in uppercase."},
        )

        # Check first call included instructions
        first_call_args = mock_create.call_args
        first_input_messages = first_call_args.kwargs["input"]

        # Should have 2 messages: system (instructions) + user
        assert len(first_input_messages) == 2
        assert first_input_messages[0]["role"] == "system"
        assert any("Reply in uppercase" in str(c) for c in first_input_messages[0]["content"])
        assert first_input_messages[1]["role"] == "user"

        # Second call - with conversation_id (server-side continuation)
        # Instructions should NOT be sent again
        await client.get_response(
            messages=[Message(role="user", text="Tell me a joke")],
            options={
                "instructions": "Reply in uppercase.",
                "conversation_id": "resp_123",
            },
        )

        # Check second call
        second_call_args = mock_create.call_args
        second_input_messages = second_call_args.kwargs["input"]

        # Should have only 1 message: user message (no system instructions)
        assert len(second_input_messages) == 1, (
            f"Expected 1 message (user only) when conversation_id is present, "
            f"but got {len(second_input_messages)} messages"
        )
        assert second_input_messages[0]["role"] == "user"
        # Ensure no system message with instructions
        assert not any(msg["role"] == "system" for msg in second_input_messages)


@pytest.mark.asyncio
async def test_instructions_not_repeated_with_response_id() -> None:
    """Test that instructions are not sent again when response_id (resp_) format is used."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_456"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.finish_reason = None

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Response"
    mock_message_content.annotations = []

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        # Call with response_id format (resp_)
        await client.get_response(
            messages=[Message(role="user", text="Continue conversation")],
            options={
                "instructions": "Be helpful.",
                "conversation_id": "resp_456",
            },
        )

        call_args = mock_create.call_args
        input_messages = call_args.kwargs["input"]

        # Should only have user message, no system instructions
        assert len(input_messages) == 1
        assert input_messages[0]["role"] == "user"
        assert not any(msg["role"] == "system" for msg in input_messages)


@pytest.mark.asyncio
async def test_instructions_not_repeated_with_conv_id() -> None:
    """Test that instructions are not sent again when conv_ format is used."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_789"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.finish_reason = None

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Response"
    mock_message_content.annotations = []

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        # Call with conversation_id format (conv_)
        await client.get_response(
            messages=[Message(role="user", text="Continue conversation")],
            options={
                "instructions": "Be helpful.",
                "conversation_id": "conv_abc123",
            },
        )

        call_args = mock_create.call_args
        input_messages = call_args.kwargs["input"]

        # Should only have user message, no system instructions
        assert len(input_messages) == 1
        assert input_messages[0]["role"] == "user"
        assert not any(msg["role"] == "system" for msg in input_messages)


@pytest.mark.asyncio
async def test_instructions_included_without_conversation_id() -> None:
    """Test that instructions ARE included in initial requests (no conversation_id)."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_new"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.finish_reason = None

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Response"
    mock_message_content.annotations = []

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        # Call without conversation_id - this is a NEW conversation
        await client.get_response(
            messages=[Message(role="user", text="Hello")],
            options={"instructions": "You are a helpful assistant."},
        )

        call_args = mock_create.call_args
        input_messages = call_args.kwargs["input"]

        # Should have 2 messages: system (instructions) + user
        assert len(input_messages) == 2
        assert input_messages[0]["role"] == "system"
        assert any("helpful assistant" in str(c) for c in input_messages[0]["content"])
        assert input_messages[1]["role"] == "user"
