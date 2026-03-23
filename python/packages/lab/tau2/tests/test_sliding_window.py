# Copyright (c) Microsoft. All rights reserved.

"""Tests for sliding window history provider."""

from unittest.mock import patch

from agent_framework import InMemoryHistoryProvider
from agent_framework._types import Content, Message
from agent_framework_lab_tau2._sliding_window import SlidingWindowHistoryProvider


def _make_state(provider: SlidingWindowHistoryProvider, messages: list[Message] | None = None) -> dict:
    """Helper to create a session state dict with messages pre-loaded."""
    state: dict = {}
    if messages:
        state["messages"] = list(messages)
    return state


def test_initialization():
    """Test initializing with parameters."""
    provider = SlidingWindowHistoryProvider(
        max_tokens=2000,
        system_message="You are a helpful assistant",
        tool_definitions=[{"name": "test_tool"}],
    )

    assert provider.max_tokens == 2000
    assert provider.system_message == "You are a helpful assistant"
    assert provider.tool_definitions == [{"name": "test_tool"}]
    assert provider.source_id == InMemoryHistoryProvider.DEFAULT_SOURCE_ID


async def test_get_messages_empty():
    """Test getting messages from empty state."""
    provider = SlidingWindowHistoryProvider(max_tokens=1000)
    messages = await provider.get_messages(None, state={})
    assert messages == []


async def test_get_messages_simple():
    """Test getting messages without truncation."""
    provider = SlidingWindowHistoryProvider(max_tokens=10000)
    msgs = [
        Message(role="user", contents=[Content.from_text(text="What's the weather?")]),
        Message(role="assistant", contents=[Content.from_text(text="I can help with that.")]),
    ]
    state = _make_state(provider, msgs)

    result = await provider.get_messages(None, state=state)
    assert len(result) == 2
    assert result[0].text == "What's the weather?"
    assert result[1].text == "I can help with that."


async def test_save_and_get_messages():
    """Test saving then getting messages with truncation."""
    provider = SlidingWindowHistoryProvider(max_tokens=50)
    state: dict = {}

    # Save many messages
    msgs = [
        Message(role="user", contents=[Content.from_text(text=f"Message {i} with some content")]) for i in range(10)
    ]
    await provider.save_messages(None, msgs, state=state)

    # get_messages returns truncated
    truncated = await provider.get_messages(None, state=state)
    # Full history is in session state
    all_msgs = state["messages"]

    assert len(all_msgs) == 10
    assert len(truncated) < len(all_msgs)


def test_get_token_count_basic():
    """Test basic token counting."""
    provider = SlidingWindowHistoryProvider(max_tokens=1000)
    messages = [Message(role="user", contents=[Content.from_text(text="Hello")])]

    token_count = provider._get_token_count(messages)
    assert token_count > 0


def test_get_token_count_with_system_message():
    """Test token counting includes system message."""
    provider = SlidingWindowHistoryProvider(max_tokens=1000, system_message="You are a helpful assistant")

    count_empty = provider._get_token_count([])
    count_with_msg = provider._get_token_count([Message(role="user", contents=[Content.from_text(text="Hello")])])

    assert count_with_msg > count_empty
    assert count_empty > 0  # System message contributes tokens


def test_get_token_count_function_call():
    """Test token counting with function calls."""
    function_call = Content.from_function_call(call_id="call_123", name="test_function", arguments={"param": "value"})
    provider = SlidingWindowHistoryProvider(max_tokens=1000)

    token_count = provider._get_token_count([Message(role="assistant", contents=[function_call])])
    assert token_count > 0


def test_get_token_count_function_result():
    """Test token counting with function results."""
    function_result = Content.from_function_result(call_id="call_123", result={"success": True, "data": "result"})
    provider = SlidingWindowHistoryProvider(max_tokens=1000)

    token_count = provider._get_token_count([Message(role="tool", contents=[function_result])])
    assert token_count > 0


@patch("agent_framework_lab_tau2._sliding_window.logger")
def test_truncate_removes_old_messages(mock_logger):
    """Test that truncation removes old messages when token limit exceeded."""
    provider = SlidingWindowHistoryProvider(max_tokens=20)

    messages = [
        Message(
            role="user",
            contents=[Content.from_text(text="This is a very long message that should exceed the token limit")],
        ),
        Message(
            role="assistant",
            contents=[
                Content.from_text(text="This is another very long message that should also exceed the token limit")
            ],
        ),
        Message(role="user", contents=[Content.from_text(text="Short msg")]),
    ]

    result = provider._truncate(list(messages))
    assert len(result) < len(messages)
    assert mock_logger.warning.called


@patch("agent_framework_lab_tau2._sliding_window.logger")
def test_truncate_removes_leading_tool_messages(mock_logger):
    """Test that truncation removes leading tool messages."""
    provider = SlidingWindowHistoryProvider(max_tokens=10000)

    tool_message = Message(role="tool", contents=[Content.from_function_result(call_id="call_123", result="result")])
    user_message = Message(role="user", contents=[Content.from_text(text="Hello")])

    result = provider._truncate([tool_message, user_message])
    assert len(result) == 1
    assert result[0].role == "user"
    mock_logger.warning.assert_called()


def test_estimate_any_object_token_count():
    """Test token counting for various object types."""
    provider = SlidingWindowHistoryProvider(max_tokens=1000)

    assert provider._estimate_any_object_token_count({"key": "value"}) > 0
    assert provider._estimate_any_object_token_count("test string") > 0

    # Non-serializable falls back to str()
    class Custom:
        def __str__(self):
            return "Custom instance"

    assert provider._estimate_any_object_token_count(Custom()) > 0


async def test_real_world_scenario():
    """Test a realistic conversation scenario."""
    provider = SlidingWindowHistoryProvider(max_tokens=30, system_message="You are a helpful assistant")
    state: dict = {}

    conversation = [
        Message(role="user", contents=[Content.from_text(text="Hello, how are you?")]),
        Message(
            role="assistant",
            contents=[Content.from_text(text="I'm doing well, thank you! How can I help you today?")],
        ),
        Message(role="user", contents=[Content.from_text(text="Can you tell me about the weather?")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text(
                    text="I'd be happy to help with weather information, "
                    "but I don't have access to current weather data."
                )
            ],
        ),
        Message(role="user", contents=[Content.from_text(text="What about telling me a joke instead?")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text(text="Sure! Why don't scientists trust atoms? Because they make up everything!")
            ],
        ),
    ]

    await provider.save_messages(None, conversation, state=state)

    truncated = await provider.get_messages(None, state=state)
    all_msgs = state["messages"]

    assert len(all_msgs) == 6
    assert len(truncated) <= 6

    token_count = provider._get_token_count(truncated)
    assert token_count <= provider.max_tokens * 1.1
