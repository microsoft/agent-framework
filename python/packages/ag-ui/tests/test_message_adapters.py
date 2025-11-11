# Copyright (c) Microsoft. All rights reserved.

"""Tests for message adapters."""

import pytest
from agent_framework import ChatMessage, FunctionCallContent, Role, TextContent

from agent_framework_ag_ui._message_adapters import (
    agent_framework_messages_to_agui,
    agui_messages_to_agent_framework,
    extract_text_from_contents,
)


@pytest.fixture
def sample_agui_message():
    """Create a sample AG-UI message."""
    return {"role": "user", "content": "Hello", "id": "msg-123"}


@pytest.fixture
def sample_agent_framework_message():
    """Create a sample Agent Framework message."""
    return ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")], message_id="msg-123")


def test_agui_to_agent_framework_basic(sample_agui_message):
    """Test converting AG-UI message to Agent Framework."""
    messages = agui_messages_to_agent_framework([sample_agui_message])

    assert len(messages) == 1
    assert messages[0].role == Role.USER
    assert messages[0].message_id == "msg-123"


def test_agent_framework_to_agui_basic(sample_agent_framework_message):
    """Test converting Agent Framework message to AG-UI."""
    messages = agent_framework_messages_to_agui([sample_agent_framework_message])

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[0]["id"] == "msg-123"


def test_agui_tool_result_to_agent_framework():
    """Test converting AG-UI tool result message to Agent Framework."""
    tool_result_message = {
        "role": "tool",
        "content": '{"accepted": true, "steps": []}',
        "toolCallId": "call_123",
        "id": "msg_456",
    }

    messages = agui_messages_to_agent_framework([tool_result_message])

    assert len(messages) == 1
    message = messages[0]

    assert message.role == Role.USER

    assert len(message.contents) == 1
    assert isinstance(message.contents[0], TextContent)
    assert message.contents[0].text == '{"accepted": true, "steps": []}'

    assert message.additional_properties is not None
    assert message.additional_properties.get("is_tool_result") is True
    assert message.additional_properties.get("tool_call_id") == "call_123"


def test_agui_multiple_messages_to_agent_framework():
    """Test converting multiple AG-UI messages."""
    messages_input = [
        {"role": "user", "content": "First message", "id": "msg-1"},
        {"role": "assistant", "content": "Second message", "id": "msg-2"},
        {"role": "user", "content": "Third message", "id": "msg-3"},
    ]

    messages = agui_messages_to_agent_framework(messages_input)

    assert len(messages) == 3
    assert messages[0].role == Role.USER
    assert messages[1].role == Role.ASSISTANT
    assert messages[2].role == Role.USER


def test_agui_empty_messages():
    """Test handling of empty messages list."""
    messages = agui_messages_to_agent_framework([])
    assert len(messages) == 0


def test_agui_function_approvals():
    """Test converting function approvals from AG-UI to Agent Framework."""
    agui_msg = {
        "role": "user",
        "function_approvals": [
            {
                "call_id": "call-1",
                "name": "search",
                "arguments": {"query": "test"},
                "approved": True,
                "id": "approval-1",
            },
            {
                "call_id": "call-2",
                "name": "update",
                "arguments": {"value": 42},
                "approved": False,
                "id": "approval-2",
            },
        ],
        "id": "msg-123",
    }

    messages = agui_messages_to_agent_framework([agui_msg])

    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == Role.USER
    assert len(msg.contents) == 2

    from agent_framework import FunctionApprovalResponseContent

    assert isinstance(msg.contents[0], FunctionApprovalResponseContent)
    assert msg.contents[0].approved is True
    assert msg.contents[0].id == "approval-1"
    assert msg.contents[0].function_call.name == "search"
    assert msg.contents[0].function_call.call_id == "call-1"

    assert isinstance(msg.contents[1], FunctionApprovalResponseContent)
    assert msg.contents[1].approved is False


def test_agui_system_role():
    """Test converting system role messages."""
    messages = agui_messages_to_agent_framework([{"role": "system", "content": "System prompt"}])

    assert len(messages) == 1
    assert messages[0].role == Role.SYSTEM


def test_agui_non_string_content():
    """Test handling non-string content."""
    messages = agui_messages_to_agent_framework([{"role": "user", "content": {"nested": "object"}}])

    assert len(messages) == 1
    assert len(messages[0].contents) == 1
    assert isinstance(messages[0].contents[0], TextContent)
    assert "nested" in messages[0].contents[0].text


def test_agui_message_without_id():
    """Test message without ID field."""
    messages = agui_messages_to_agent_framework([{"role": "user", "content": "No ID"}])

    assert len(messages) == 1
    assert messages[0].message_id is None


def test_agui_with_tool_calls_to_agent_framework():
    """Assistant message with tool_calls is converted to FunctionCallContent."""
    agui_msg = {
        "role": "assistant",
        "content": "Calling tool",
        "tool_calls": [
            {
                "id": "call-123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": {"location": "Seattle"}},
            }
        ],
        "id": "msg-789",
    }

    messages = agui_messages_to_agent_framework([agui_msg])

    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == Role.ASSISTANT
    assert msg.message_id == "msg-789"
    # First content is text, second is the function call
    assert isinstance(msg.contents[0], TextContent)
    assert msg.contents[0].text == "Calling tool"
    assert isinstance(msg.contents[1], FunctionCallContent)
    assert msg.contents[1].call_id == "call-123"
    assert msg.contents[1].name == "get_weather"
    assert msg.contents[1].arguments == {"location": "Seattle"}


def test_agent_framework_to_agui_with_tool_calls():
    """Test converting Agent Framework message with tool calls to AG-UI."""
    msg = ChatMessage(
        role=Role.ASSISTANT,
        contents=[
            TextContent(text="Calling tool"),
            FunctionCallContent(call_id="call-123", name="search", arguments={"query": "test"}),
        ],
        message_id="msg-456",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    assert agui_msg["role"] == "assistant"
    assert agui_msg["content"] == "Calling tool"
    assert "tool_calls" in agui_msg
    assert len(agui_msg["tool_calls"]) == 1
    assert agui_msg["tool_calls"][0]["id"] == "call-123"
    assert agui_msg["tool_calls"][0]["type"] == "function"
    assert agui_msg["tool_calls"][0]["function"]["name"] == "search"
    assert agui_msg["tool_calls"][0]["function"]["arguments"] == {"query": "test"}


def test_agent_framework_to_agui_multiple_text_contents():
    """Test concatenating multiple text contents."""
    msg = ChatMessage(
        role=Role.ASSISTANT,
        contents=[TextContent(text="Part 1 "), TextContent(text="Part 2")],
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert messages[0]["content"] == "Part 1 Part 2"


def test_agent_framework_to_agui_no_message_id():
    """Test message without message_id - should auto-generate ID."""
    msg = ChatMessage(role=Role.USER, contents=[TextContent(text="Hello")])

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert "id" in messages[0]  # ID should be auto-generated
    assert messages[0]["id"]  # ID should not be empty
    assert len(messages[0]["id"]) > 0  # ID should be a valid string


def test_agent_framework_to_agui_system_role():
    """Test system role conversion."""
    msg = ChatMessage(role=Role.SYSTEM, contents=[TextContent(text="System")])

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert messages[0]["role"] == "system"


def test_extract_text_from_contents():
    """Test extracting text from contents list."""
    contents = [TextContent(text="Hello "), TextContent(text="World")]

    result = extract_text_from_contents(contents)

    assert result == "Hello World"


def test_extract_text_from_empty_contents():
    """Test extracting text from empty contents."""
    result = extract_text_from_contents([])

    assert result == ""


class CustomTextContent:
    """Custom content with text attribute."""

    def __init__(self, text: str):
        self.text = text


def test_extract_text_from_custom_contents():
    """Test extracting text from custom content objects."""
    contents = [CustomTextContent(text="Custom "), TextContent(text="Mixed")]

    result = extract_text_from_contents(contents)

    assert result == "Custom Mixed"
