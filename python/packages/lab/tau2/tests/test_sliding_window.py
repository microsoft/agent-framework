# Copyright (c) Microsoft. All rights reserved.

"""Tests for sliding window message list."""

import pytest
from unittest.mock import patch

from agent_framework._types import ChatMessage, Role, TextContent, FunctionCallContent, FunctionResultContent
from agent_framework_lab_tau2._sliding_window import SlidingWindowChatMessageList


def test_initialization_empty():
    """Test initializing with no messages."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)

    assert sliding_window.max_tokens == 1000
    assert sliding_window.system_message is None
    assert sliding_window.tool_definitions is None
    assert len(sliding_window._messages) == 0
    assert len(sliding_window._truncated_messages) == 0


def test_initialization_with_parameters():
    """Test initializing with system message and tool definitions."""
    system_msg = "You are a helpful assistant"
    tool_defs = [{"name": "test_tool", "description": "A test tool"}]

    sliding_window = SlidingWindowChatMessageList(
        max_tokens=2000, system_message=system_msg, tool_definitions=tool_defs
    )

    assert sliding_window.max_tokens == 2000
    assert sliding_window.system_message == system_msg
    assert sliding_window.tool_definitions == tool_defs


def test_initialization_with_messages():
    """Test initializing with existing messages."""
    messages = [
        ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="Hi there!")]),
    ]

    sliding_window = SlidingWindowChatMessageList(messages=messages, max_tokens=1000)

    assert len(sliding_window._messages) == 2
    assert len(sliding_window._truncated_messages) == 2


@pytest.mark.asyncio
async def test_add_messages_simple():
    """Test adding messages without truncation."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=10000)  # Large limit

    new_messages = [
        ChatMessage(role=Role.USER, contents=[TextContent(text="What's the weather?")]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="I can help with that.")]),
    ]

    await sliding_window.add_messages(new_messages)

    messages = await sliding_window.list_messages()
    assert len(messages) == 2
    assert messages[0].text == "What's the weather?"
    assert messages[1].text == "I can help with that."


@pytest.mark.asyncio
async def test_list_all_messages_vs_list_messages():
    """Test difference between list_all_messages and list_messages."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=50)  # Small limit to force truncation

    # Add many messages to trigger truncation
    messages = [
        ChatMessage(role=Role.USER, contents=[TextContent(text=f"Message {i} with some content")]) for i in range(10)
    ]

    await sliding_window.add_messages(messages)

    truncated_messages = await sliding_window.list_messages()
    all_messages = await sliding_window.list_all_messages()

    # All messages should contain everything
    assert len(all_messages) == 10

    # Truncated messages should be fewer due to token limit
    assert len(truncated_messages) < len(all_messages)


def test_get_token_count_basic():
    """Test basic token counting."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)
    sliding_window._truncated_messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]

    token_count = sliding_window.get_token_count()

    # Should be more than 0 (exact count depends on encoding)
    assert token_count > 0


def test_get_token_count_with_system_message():
    """Test token counting includes system message."""
    system_msg = "You are a helpful assistant"
    sliding_window = SlidingWindowChatMessageList(max_tokens=1000, system_message=system_msg)

    # Without messages
    token_count_empty = sliding_window.get_token_count()

    # Add a message
    sliding_window._truncated_messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])]
    token_count_with_message = sliding_window.get_token_count()

    # With message should be more tokens
    assert token_count_with_message > token_count_empty
    assert token_count_empty > 0  # System message contributes tokens


def test_get_token_count_function_call():
    """Test token counting with function calls."""
    function_call = FunctionCallContent(call_id="call_123", name="test_function", arguments={"param": "value"})

    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)
    sliding_window._truncated_messages = [ChatMessage(role=Role.ASSISTANT, contents=[function_call])]

    token_count = sliding_window.get_token_count()
    assert token_count > 0


def test_get_token_count_function_result():
    """Test token counting with function results."""
    function_result = FunctionResultContent(call_id="call_123", result={"success": True, "data": "result"})

    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)
    sliding_window._truncated_messages = [ChatMessage(role=Role.TOOL, contents=[function_result])]

    token_count = sliding_window.get_token_count()
    assert token_count > 0


@patch("agent_framework_lab_tau2._sliding_window.logger")
def test_truncate_messages_removes_old_messages(mock_logger):
    """Test that truncation removes old messages when token limit exceeded."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=20)  # Very small limit

    # Create messages that will exceed the limit
    messages = [
        ChatMessage(
            role=Role.USER,
            contents=[TextContent(text="This is a very long message that should exceed the token limit")],
        ),
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text="This is another very long message that should also exceed the token limit")],
        ),
        ChatMessage(role=Role.USER, contents=[TextContent(text="Short msg")]),
    ]

    sliding_window._truncated_messages = messages.copy()
    sliding_window.truncate_messages()

    # Should have fewer messages after truncation
    assert len(sliding_window._truncated_messages) < len(messages)

    # Should have logged warnings
    assert mock_logger.warning.called


@patch("agent_framework_lab_tau2._sliding_window.logger")
def test_truncate_messages_removes_leading_tool_messages(mock_logger):
    """Test that truncation removes leading tool messages."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=10000)  # Large limit

    # Create messages starting with tool message
    tool_message = ChatMessage(role=Role.TOOL, contents=[FunctionResultContent(call_id="call_123", result="result")])
    user_message = ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])

    sliding_window._truncated_messages = [tool_message, user_message]
    sliding_window.truncate_messages()

    # Tool message should be removed from the beginning
    assert len(sliding_window._truncated_messages) == 1
    assert sliding_window._truncated_messages[0].role == Role.USER

    # Should have logged warning about removing tool message
    mock_logger.warning.assert_called()


def test_estimate_any_object_token_count_dict():
    """Test token counting for dictionary objects."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)

    test_dict = {"key": "value", "number": 42}
    token_count = sliding_window.estimate_any_object_token_count(test_dict)

    assert token_count > 0


def test_estimate_any_object_token_count_string():
    """Test token counting for string objects."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)

    test_string = "This is a test string"
    token_count = sliding_window.estimate_any_object_token_count(test_string)

    assert token_count > 0


def test_estimate_any_object_token_count_non_serializable():
    """Test token counting for non-JSON-serializable objects."""
    sliding_window = SlidingWindowChatMessageList(max_tokens=1000)

    # Create an object that can't be JSON serialized
    class CustomObject:
        def __str__(self):
            return "CustomObject instance"

    custom_obj = CustomObject()
    token_count = sliding_window.estimate_any_object_token_count(custom_obj)

    # Should fall back to string representation
    assert token_count > 0


@pytest.mark.asyncio
async def test_real_world_scenario():
    """Test a realistic conversation scenario."""
    sliding_window = SlidingWindowChatMessageList(
        max_tokens=30, system_message="You are a helpful assistant"  # Moderate limit
    )

    # Simulate a conversation
    conversation = [
        ChatMessage(role=Role.USER, contents=[TextContent(text="Hello, how are you?")]),
        ChatMessage(
            role=Role.ASSISTANT, contents=[TextContent(text="I'm doing well, thank you! How can I help you today?")]
        ),
        ChatMessage(role=Role.USER, contents=[TextContent(text="Can you tell me about the weather?")]),
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                TextContent(
                    text="I'd be happy to help with weather information, but I don't have access to current weather data."
                )
            ],
        ),
        ChatMessage(role=Role.USER, contents=[TextContent(text="What about telling me a joke instead?")]),
        ChatMessage(
            role=Role.ASSISTANT,
            contents=[TextContent(text="Sure! Why don't scientists trust atoms? Because they make up everything!")],
        ),
    ]

    await sliding_window.add_messages(conversation)

    current_messages = await sliding_window.list_messages()
    all_messages = await sliding_window.list_all_messages()

    # All messages should be preserved
    assert len(all_messages) == 6

    # Current messages might be truncated
    assert len(current_messages) <= 6

    # Token count should be within or close to limit
    token_count = sliding_window.get_token_count()
    # Allow some margin since truncation happens when exceeded
    assert token_count <= sliding_window.max_tokens * 1.1
