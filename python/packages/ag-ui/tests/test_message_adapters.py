# Copyright (c) Microsoft. All rights reserved.

"""Tests for message adapters."""

import json

import pytest
from agent_framework import ChatMessage, Content, Role

from agent_framework_ag_ui._message_adapters import (
    agent_framework_messages_to_agui,
    agui_messages_to_agent_framework,
    agui_messages_to_snapshot_format,
    extract_text_from_contents,
)


@pytest.fixture
def sample_agui_message():
    """Create a sample AG-UI message."""
    return {"role": "user", "content": "Hello", "id": "msg-123"}


@pytest.fixture
def sample_agent_framework_message():
    """Create a sample Agent Framework message."""
    return ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")], message_id="msg-123")


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


def test_agent_framework_to_agui_normalizes_dict_roles():
    """Dict inputs normalize unknown roles for UI compatibility."""
    messages = [
        {"role": "developer", "content": "policy"},
        {"role": "weird_role", "content": "payload"},
    ]

    converted = agent_framework_messages_to_agui(messages)

    assert converted[0]["role"] == "system"
    assert converted[1]["role"] == "user"


def test_agui_snapshot_format_normalizes_roles():
    """Snapshot normalization coerces roles into supported AG-UI values."""
    messages = [
        {"role": "Developer", "content": "policy"},
        {"role": "unknown", "content": "payload"},
    ]

    normalized = agui_messages_to_snapshot_format(messages)

    assert normalized[0]["role"] == "system"
    assert normalized[1]["role"] == "user"


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
    assert message.contents[0].type == "text"
    assert message.contents[0].text == '{"accepted": true, "steps": []}'

    assert message.additional_properties is not None
    assert message.additional_properties.get("is_tool_result") is True
    assert message.additional_properties.get("tool_call_id") == "call_123"


def test_agui_tool_approval_updates_tool_call_arguments():
    """Tool approval updates matching tool call arguments for snapshots and agent context."""
    messages_input = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "generate_task_steps",
                        "arguments": {
                            "steps": [
                                {"description": "Boil water", "status": "enabled"},
                                {"description": "Brew coffee", "status": "enabled"},
                                {"description": "Serve coffee", "status": "enabled"},
                            ]
                        },
                    },
                }
            ],
            "id": "msg_1",
        },
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "accepted": True,
                    "steps": [
                        {"description": "Boil water", "status": "enabled"},
                        {"description": "Serve coffee", "status": "enabled"},
                    ],
                }
            ),
            "toolCallId": "call_123",
            "id": "msg_2",
        },
    ]

    messages = agui_messages_to_agent_framework(messages_input)

    assert len(messages) == 2
    assistant_msg = messages[0]
    func_call = next(content for content in assistant_msg.contents if content.type == "function_call")
    assert func_call.arguments == {
        "steps": [
            {"description": "Boil water", "status": "enabled"},
            {"description": "Brew coffee", "status": "disabled"},
            {"description": "Serve coffee", "status": "enabled"},
        ]
    }
    assert messages_input[0]["tool_calls"][0]["function"]["arguments"] == {
        "steps": [
            {"description": "Boil water", "status": "enabled"},
            {"description": "Brew coffee", "status": "disabled"},
            {"description": "Serve coffee", "status": "enabled"},
        ]
    }

    approval_msg = messages[1]
    approval_content = next(
        content for content in approval_msg.contents if content.type == "function_approval_response"
    )
    assert approval_content.function_call.parse_arguments() == {
        "steps": [
            {"description": "Boil water", "status": "enabled"},
            {"description": "Serve coffee", "status": "enabled"},
        ]
    }
    assert approval_content.additional_properties is not None
    assert approval_content.additional_properties.get("ag_ui_state_args") == {
        "steps": [
            {"description": "Boil water", "status": "enabled"},
            {"description": "Brew coffee", "status": "disabled"},
            {"description": "Serve coffee", "status": "enabled"},
        ]
    }


def test_agui_tool_approval_from_confirm_changes_maps_to_function_call():
    """Confirm_changes approvals map back to the original tool call when metadata is present."""
    messages_input = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_tool",
                    "type": "function",
                    "function": {"name": "get_datetime", "arguments": {}},
                },
                {
                    "id": "call_confirm",
                    "type": "function",
                    "function": {
                        "name": "confirm_changes",
                        "arguments": {"function_call_id": "call_tool"},
                    },
                },
            ],
            "id": "msg_1",
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True, "function_call_id": "call_tool"}),
            "toolCallId": "call_confirm",
            "id": "msg_2",
        },
    ]

    messages = agui_messages_to_agent_framework(messages_input)
    approval_msg = messages[1]
    approval_content = next(
        content for content in approval_msg.contents if content.type == "function_approval_response"
    )

    assert approval_content.function_call.call_id == "call_tool"
    assert approval_content.function_call.name == "get_datetime"
    assert approval_content.function_call.parse_arguments() == {}
    assert messages_input[0]["tool_calls"][0]["function"]["arguments"] == {}


def test_agui_tool_approval_from_confirm_changes_falls_back_to_sibling_call():
    """Confirm_changes approvals map to the only sibling tool call when metadata is missing."""
    messages_input = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_tool",
                    "type": "function",
                    "function": {"name": "get_datetime", "arguments": {}},
                },
                {
                    "id": "call_confirm",
                    "type": "function",
                    "function": {"name": "confirm_changes", "arguments": {}},
                },
            ],
            "id": "msg_1",
        },
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "accepted": True,
                    "steps": [{"description": "Approve get_datetime", "status": "enabled"}],
                }
            ),
            "toolCallId": "call_confirm",
            "id": "msg_2",
        },
    ]

    messages = agui_messages_to_agent_framework(messages_input)
    approval_msg = messages[1]
    approval_content = next(
        content for content in approval_msg.contents if content.type == "function_approval_response"
    )

    assert approval_content.function_call.call_id == "call_tool"
    assert approval_content.function_call.name == "get_datetime"
    assert approval_content.function_call.parse_arguments() == {}
    assert messages_input[0]["tool_calls"][0]["function"]["arguments"] == {}


def test_agui_tool_approval_from_generate_task_steps_maps_to_function_call():
    """Approval tool payloads map to the referenced function call when function_call_id is present."""
    messages_input = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_tool",
                    "type": "function",
                    "function": {"name": "get_datetime", "arguments": {}},
                },
                {
                    "id": "call_steps",
                    "type": "function",
                    "function": {
                        "name": "generate_task_steps",
                        "arguments": {
                            "function_name": "get_datetime",
                            "function_call_id": "call_tool",
                            "function_arguments": {},
                            "steps": [{"description": "Execute get_datetime", "status": "enabled"}],
                        },
                    },
                },
            ],
            "id": "msg_1",
        },
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "accepted": True,
                    "steps": [{"description": "Execute get_datetime", "status": "enabled"}],
                }
            ),
            "toolCallId": "call_steps",
            "id": "msg_2",
        },
    ]

    messages = agui_messages_to_agent_framework(messages_input)
    approval_msg = messages[1]
    approval_content = next(
        content for content in approval_msg.contents if content.type == "function_approval_response"
    )

    assert approval_content.function_call.call_id == "call_tool"
    assert approval_content.function_call.name == "get_datetime"
    assert approval_content.function_call.parse_arguments() == {}


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

    assert msg.contents[0].type == "function_approval_response"
    assert msg.contents[0].approved is True
    assert msg.contents[0].id == "approval-1"
    assert msg.contents[0].function_call.name == "search"
    assert msg.contents[0].function_call.call_id == "call-1"

    assert msg.contents[1].type == "function_approval_response"
    assert msg.contents[1].id == "approval-2"
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
    assert messages[0].contents[0].type == "text"
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
    assert msg.contents[0].type == "text"
    assert msg.contents[0].text == "Calling tool"
    assert msg.contents[1].type == "function_call"
    assert msg.contents[1].call_id == "call-123"
    assert msg.contents[1].name == "get_weather"
    assert msg.contents[1].arguments == {"location": "Seattle"}


def test_agent_framework_to_agui_with_tool_calls():
    """Test converting Agent Framework message with tool calls to AG-UI."""
    msg = ChatMessage(
        role=Role.ASSISTANT,
        contents=[
            Content.from_text(text="Calling tool"),
            Content.from_function_call(call_id="call-123", name="search", arguments={"query": "test"}),
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
        contents=[Content.from_text(text="Part 1 "), Content.from_text(text="Part 2")],
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert messages[0]["content"] == "Part 1 Part 2"


def test_agent_framework_to_agui_no_message_id():
    """Test message without message_id - should auto-generate ID."""
    msg = ChatMessage(role=Role.USER, contents=[Content.from_text(text="Hello")])

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert "id" in messages[0]  # ID should be auto-generated
    assert messages[0]["id"]  # ID should not be empty
    assert len(messages[0]["id"]) > 0  # ID should be a valid string


def test_agent_framework_to_agui_system_role():
    """Test system role conversion."""
    msg = ChatMessage(role=Role.SYSTEM, contents=[Content.from_text(text="System")])

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert messages[0]["role"] == "system"


def test_extract_text_from_contents():
    """Test extracting text from contents list."""
    contents = [Content.from_text(text="Hello "), Content.from_text(text="World")]

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
    contents = [CustomTextContent(text="Custom "), Content.from_text(text="Mixed")]

    result = extract_text_from_contents(contents)

    assert result == "Custom Mixed"


# Tests for FunctionResultContent serialization in agent_framework_messages_to_agui


def test_agent_framework_to_agui_function_result_dict():
    """Test converting FunctionResultContent with dict result to AG-UI."""
    msg = ChatMessage(
        role=Role.TOOL,
        contents=[Content.from_function_result(call_id="call-123", result={"key": "value", "count": 42})],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    assert agui_msg["role"] == "tool"
    assert agui_msg["toolCallId"] == "call-123"
    assert agui_msg["content"] == '{"key": "value", "count": 42}'


def test_agent_framework_to_agui_function_result_none():
    """Test converting FunctionResultContent with None result to AG-UI."""
    msg = ChatMessage(
        role=Role.TOOL,
        contents=[Content.from_function_result(call_id="call-123", result=None)],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # None serializes as JSON null
    assert agui_msg["content"] == "null"


def test_agent_framework_to_agui_function_result_string():
    """Test converting FunctionResultContent with string result to AG-UI."""
    msg = ChatMessage(
        role=Role.TOOL,
        contents=[Content.from_function_result(call_id="call-123", result="plain text result")],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    assert agui_msg["content"] == "plain text result"


def test_agent_framework_to_agui_function_result_empty_list():
    """Test converting FunctionResultContent with empty list result to AG-UI."""
    msg = ChatMessage(
        role=Role.TOOL,
        contents=[Content.from_function_result(call_id="call-123", result=[])],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # Empty list serializes as JSON empty array
    assert agui_msg["content"] == "[]"


def test_agent_framework_to_agui_function_result_single_text_content():
    """Test converting FunctionResultContent with single TextContent-like item."""
    from dataclasses import dataclass

    @dataclass
    class MockTextContent:
        text: str

    msg = ChatMessage(
        role=Role.TOOL,
        contents=[Content.from_function_result(call_id="call-123", result=[MockTextContent("Hello from MCP!")])],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # TextContent text is extracted and serialized as JSON array
    assert agui_msg["content"] == '["Hello from MCP!"]'


def test_agent_framework_to_agui_function_result_multiple_text_contents():
    """Test converting FunctionResultContent with multiple TextContent-like items."""
    from dataclasses import dataclass

    @dataclass
    class MockTextContent:
        text: str

    msg = ChatMessage(
        role=Role.TOOL,
        contents=[
            Content.from_function_result(
                call_id="call-123",
                result=[MockTextContent("First result"), MockTextContent("Second result")],
            )
        ],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # Multiple items should return JSON array
    assert agui_msg["content"] == '["First result", "Second result"]'


# Additional tests for better coverage


def test_extract_text_from_contents_empty():
    """Test extracting text from empty contents."""
    result = extract_text_from_contents([])
    assert result == ""


def test_extract_text_from_contents_multiple():
    """Test extracting text from multiple text contents."""
    contents = [
        Content.from_text("Hello "),
        Content.from_text("World"),
    ]
    result = extract_text_from_contents(contents)
    assert result == "Hello World"


def test_extract_text_from_contents_non_text():
    """Test extracting text ignores non-text contents."""
    contents = [
        Content.from_text("Hello"),
        Content.from_function_call(call_id="call_1", name="tool", arguments="{}"),
    ]
    result = extract_text_from_contents(contents)
    assert result == "Hello"


def test_agui_to_agent_framework_with_tool_calls():
    """Test converting AG-UI message with tool_calls."""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "NYC"}'},
                }
            ],
        }
    ]

    result = agui_messages_to_agent_framework(messages)

    assert len(result) == 1
    assert len(result[0].contents) == 1
    assert result[0].contents[0].type == "function_call"
    assert result[0].contents[0].name == "get_weather"


def test_agui_to_agent_framework_tool_result():
    """Test converting AG-UI tool result message."""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "content": "Sunny",
            "toolCallId": "call_123",
        },
    ]

    result = agui_messages_to_agent_framework(messages)

    assert len(result) == 2
    # Second message should be tool result
    tool_msg = result[1]
    assert tool_msg.role == Role.TOOL
    assert tool_msg.contents[0].type == "function_result"
    assert tool_msg.contents[0].result == "Sunny"


def test_agui_messages_to_snapshot_format_empty():
    """Test converting empty messages to snapshot format."""
    result = agui_messages_to_snapshot_format([])
    assert result == []


def test_agui_messages_to_snapshot_format_basic():
    """Test converting messages to snapshot format."""
    messages = [
        {"role": "user", "content": "Hello", "id": "msg_1"},
        {"role": "assistant", "content": "Hi there", "id": "msg_2"},
    ]

    result = agui_messages_to_snapshot_format(messages)

    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "Hello"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "Hi there"
