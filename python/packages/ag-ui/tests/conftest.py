# Copyright (c) Microsoft. All rights reserved.

"""Test configuration and fixtures."""

import pytest
from agent_framework import ChatAgent, ChatMessage, Role, TextContent
from agent_framework._types import ChatResponseUpdate


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""

    class MockChatClient:
        async def get_streaming_response(self, messages, chat_options, **kwargs):
            yield ChatResponseUpdate(contents=[TextContent(text="Hello!")])

    return ChatAgent(
        name="test_agent",
        instructions="Test agent",
        chat_client=MockChatClient(),
    )


@pytest.fixture
def sample_agui_message():
    """Create a sample AG-UI message."""
    return {"role": "user", "content": "Hello", "id": "msg-123"}


@pytest.fixture
def sample_agent_framework_message():
    """Create a sample Agent Framework message."""
    return ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")], message_id="msg-123")
