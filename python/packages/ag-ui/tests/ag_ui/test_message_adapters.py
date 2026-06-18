# Copyright (c) Microsoft. All rights reserved.

"""Tests for message adapters."""

import base64
import json
import logging

import pytest
from agent_framework import Content, Message

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
    return Message(role="user", contents=[Content.from_text(text="Hello")], message_id="msg-123")


def test_agui_to_agent_framework_basic(sample_agui_message):
    """Test converting AG-UI message to Agent Framework."""
    messages = agui_messages_to_agent_framework([sample_agui_message])

    assert len(messages) == 1
    assert messages[0].role == "user"
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

    assert message.role == "user"

    assert len(message.contents) == 1
    assert message.contents[0].type == "text"
    assert message.contents[0].text == '{"accepted": true, "steps": []}'

    assert message.additional_properties is not None
    assert message.additional_properties.get("is_tool_result") is True
    assert message.additional_properties.get("tool_call_id") == "call_123"


def test_agui_tool_approval_updates_tool_call_arguments():
    """Tool approval updates matching tool call arguments for snapshots and agent context.

    The LLM context (Message) should contain only enabled steps, so the LLM
    generates responses based on what was actually approved/executed.

    The raw messages (for MESSAGES_SNAPSHOT) should contain all steps with status,
    so the UI can show which steps were enabled/disabled.
    """
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
    # LLM context should only have enabled steps (what was actually approved)
    assert func_call.arguments == {
        "steps": [
            {"description": "Boil water", "status": "enabled"},
            {"description": "Serve coffee", "status": "enabled"},
        ]
    }
    # Raw messages (for MESSAGES_SNAPSHOT) should have all steps with status
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
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[2].role == "user"


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
    assert msg.role == "user"
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
    assert messages[0].role == "system"


def test_agui_non_string_content():
    """Test handling non-string content."""
    messages = agui_messages_to_agent_framework([{"role": "user", "content": {"nested": "object"}}])

    assert len(messages) == 1
    assert len(messages[0].contents) == 1
    assert messages[0].contents[0].type == "text"
    assert "nested" in messages[0].contents[0].text


def test_agui_multimodal_legacy_binary_to_agent_framework():
    """Legacy text/binary multimodal content converts to text + media Content."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "See this image"},
                    {"type": "binary", "mimeType": "image/png", "url": "https://example.com/image.png"},
                ],
            }
        ]
    )

    assert len(messages) == 1
    assert len(messages[0].contents) == 2
    assert messages[0].contents[0].type == "text"
    assert messages[0].contents[0].text == "See this image"
    assert messages[0].contents[1].type == "uri"
    assert messages[0].contents[1].uri == "https://example.com/image.png"
    assert messages[0].contents[1].media_type == "image/png"


def test_agui_multimodal_draft_source_base64_to_agent_framework():
    """Draft-style media source payload converts into data Content."""
    payload = base64.b64encode(b"abc").decode("utf-8")
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "audio",
                        "source": {"type": "base64", "data": payload, "mimeType": "audio/wav"},
                    }
                ],
            }
        ]
    )

    assert len(messages) == 1
    assert len(messages[0].contents) == 1
    assert messages[0].contents[0].type == "data"
    assert messages[0].contents[0].media_type == "audio/wav"
    assert isinstance(messages[0].contents[0].uri, str)
    assert messages[0].contents[0].uri.startswith("data:audio/wav;base64,")


def test_agui_multimodal_invalid_base64_logs_warning(caplog):
    """Malformed base64 payloads should log and fall back to data URI."""
    with caplog.at_level(logging.WARNING):
        messages = agui_messages_to_agent_framework(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "data": "abc", "mimeType": "image/png"},
                        }
                    ],
                }
            ]
        )

    assert len(messages) == 1
    assert len(messages[0].contents) == 1
    assert messages[0].contents[0].type in {"data", "uri"}
    assert messages[0].contents[0].uri == "data:image/png;base64,abc"
    assert any("Failed to decode AG-UI media payload as base64" in record.message for record in caplog.records)


def test_agui_multimodal_mixed_order_preserved():
    """Mixed text/media multimodal input keeps content ordering."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "First"},
                    {"type": "image", "source": {"type": "url", "url": "https://example.com/a.png"}},
                    {"type": "text", "text": "Last"},
                ],
            }
        ]
    )

    assert len(messages[0].contents) == 3
    assert messages[0].contents[0].type == "text"
    assert messages[0].contents[0].text == "First"
    assert messages[0].contents[1].type == "uri"
    assert messages[0].contents[2].type == "text"
    assert messages[0].contents[2].text == "Last"


def test_agui_message_without_id():
    """Test message without ID field."""
    messages = agui_messages_to_agent_framework([{"role": "user", "content": "No ID"}])

    assert len(messages) == 1
    assert messages[0].message_id is None


def test_agui_snapshot_format_preserves_multimodal_content():
    """Snapshot normalization emits legacy binary parts for multimodal content."""
    normalized = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Caption"},
                    {
                        "type": "image",
                        "source": {"type": "url", "url": "https://example.com/image.png", "mime_type": "image/png"},
                    },
                ],
            }
        ]
    )

    assert isinstance(normalized[0]["content"], list)
    content_parts = normalized[0]["content"]
    assert content_parts[0]["type"] == "text"
    assert content_parts[1]["type"] == "binary"
    assert content_parts[1]["mimeType"] == "image/png"
    assert content_parts[1]["url"] == "https://example.com/image.png"


def test_agui_snapshot_format_reads_base64_value_field():
    """Snapshot normalization reads the spec 'value' field for base64 sources."""
    payload = base64.b64encode(b"abc").decode("utf-8")
    normalized = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "value": payload, "mimeType": "image/png"},
                    },
                ],
            }
        ]
    )

    binary_part = normalized[0]["content"][0]
    assert binary_part["type"] == "binary"
    assert binary_part["mimeType"] == "image/png"
    assert binary_part["data"] == payload


def test_agui_snapshot_format_base64_value_preferred_over_data():
    """Snapshot normalization prefers 'value' when both 'value' and 'data' are set."""
    value_payload = base64.b64encode(b"new-spec").decode("utf-8")
    data_payload = base64.b64encode(b"legacy").decode("utf-8")
    normalized = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "value": value_payload,
                            "data": data_payload,
                            "mimeType": "image/png",
                        },
                    },
                ],
            }
        ]
    )

    binary_part = normalized[0]["content"][0]
    assert binary_part["data"] == value_payload


def test_agui_snapshot_format_base64_data_field_backward_compat():
    """Snapshot normalization still reads the legacy 'data' field when 'value' is absent."""
    payload = base64.b64encode(b"legacy").decode("utf-8")
    normalized = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "data": payload, "mimeType": "image/png"},
                    },
                ],
            }
        ]
    )

    binary_part = normalized[0]["content"][0]
    assert binary_part["data"] == payload


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
    assert msg.role == "assistant"
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
    msg = Message(
        role="assistant",
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
    msg = Message(
        role="assistant",
        contents=[Content.from_text(text="Part 1 "), Content.from_text(text="Part 2")],
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert messages[0]["content"] == "Part 1 Part 2"


def test_agent_framework_to_agui_no_message_id():
    """Test message without message_id - should auto-generate ID."""
    msg = Message(role="user", contents=[Content.from_text(text="Hello")])

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    assert "id" in messages[0]  # ID should be auto-generated
    assert messages[0]["id"]  # ID should not be empty
    assert len(messages[0]["id"]) > 0  # ID should be a valid string


def test_agent_framework_to_agui_system_role():
    """Test system role conversion."""
    msg = Message(role="system", contents=[Content.from_text(text="System")])

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
    msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-123", result='{"key": "value", "count": 42}')],
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
    msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-123", result=None)],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # None result maps to empty string (FunctionTool.invoke returns "" for None)
    assert agui_msg["content"] == ""


def test_agent_framework_to_agui_function_result_string():
    """Test converting FunctionResultContent with string result to AG-UI."""
    msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-123", result="plain text result")],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    assert agui_msg["content"] == "plain text result"


def test_agent_framework_to_agui_function_result_empty_list():
    """Test converting FunctionResultContent with empty list result to AG-UI."""
    msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-123", result="[]")],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # Empty list serializes as JSON empty array
    assert agui_msg["content"] == "[]"


def test_agent_framework_to_agui_function_result_single_text_content():
    """Test converting FunctionResultContent with single TextContent-like item (pre-parsed)."""
    msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-123", result='["Hello from MCP!"]')],
        message_id="msg-789",
    )

    messages = agent_framework_messages_to_agui([msg])

    assert len(messages) == 1
    agui_msg = messages[0]
    # TextContent text is extracted and serialized as JSON array
    assert agui_msg["content"] == '["Hello from MCP!"]'


def test_agent_framework_to_agui_function_result_multiple_text_contents():
    """Test converting FunctionResultContent with multiple TextContent-like items (pre-parsed)."""
    msg = Message(
        role="tool",
        contents=[
            Content.from_function_result(
                call_id="call-123",
                result='["First result", "Second result"]',
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
    assert tool_msg.role == "tool"
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


# ── Tool history sanitization edge cases ──


def test_sanitize_multiple_approvals_and_logic():
    """Two function_approval_response contents: True + False → False overall."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    assistant_msg = Message(
        role="assistant",
        contents=[
            Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
            Content.from_function_call(call_id="c2", name="confirm_changes", arguments='{"function_call_id":"c1"}'),
        ],
    )
    user_msg = Message(
        role="user",
        contents=[
            Content.from_function_approval_response(
                approved=True,
                id="a1",
                function_call=Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
            ),
            Content.from_function_approval_response(
                approved=False,
                id="a2",
                function_call=Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
            ),
        ],
    )

    result = _sanitize_tool_history([assistant_msg, user_msg])
    # Both approvals should be preserved in user message
    assert any(msg.role == "user" for msg in result)


def test_sanitize_pending_tool_skip_on_user_followup():
    """User text message after assistant tool call injects synthetic skipped results."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    assistant_msg = Message(
        role="assistant",
        contents=[Content.from_function_call(call_id="c1", name="get_weather", arguments="{}")],
    )
    user_msg = Message(
        role="user",
        contents=[Content.from_text(text="Actually, never mind")],
    )

    result = _sanitize_tool_history([assistant_msg, user_msg])
    # Should have: assistant, synthetic tool result, user
    tool_results = [m for m in result if m.role == "tool"]
    assert len(tool_results) == 1
    assert "skipped" in str(tool_results[0].contents[0].result).lower()


def test_sanitize_tool_result_clears_pending_confirm():
    """Tool result for pending confirm_changes call_id clears pending state."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    assistant_msg = Message(
        role="assistant",
        contents=[
            Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
        ],
    )
    tool_msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="c1", result="done")],
    )

    result = _sanitize_tool_history([assistant_msg, tool_msg])
    assert len(result) == 2
    assert result[1].role == "tool"


def test_sanitize_non_standard_role_resets_state():
    """System message between assistant+user resets pending tool state."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    assistant_msg = Message(
        role="assistant",
        contents=[Content.from_function_call(call_id="c1", name="get_weather", arguments="{}")],
    )
    system_msg = Message(role="system", contents=[Content.from_text(text="System update")])
    user_msg = Message(role="user", contents=[Content.from_text(text="Continue")])

    result = _sanitize_tool_history([assistant_msg, system_msg, user_msg])
    # System message should reset pending state, so no synthetic tool results
    tool_results = [m for m in result if m.role == "tool"]
    assert len(tool_results) == 0


def test_sanitize_json_confirm_changes_response():
    """User sends JSON text with 'accepted' after confirm_changes."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    assistant_msg = Message(
        role="assistant",
        contents=[
            Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
            Content.from_function_call(call_id="c2", name="confirm_changes", arguments='{"function_call_id":"c1"}'),
        ],
    )
    # Note: confirm_changes is filtered, so c2 won't be in pending_tool_call_ids
    # But c1 will remain pending. User message with JSON accepted text doesn't match
    # confirm_changes path since pending_confirm_changes_id was reset.
    user_msg = Message(
        role="user",
        contents=[Content.from_text(text=json.dumps({"accepted": True}))],
    )

    result = _sanitize_tool_history([assistant_msg, user_msg])
    # Should still process without errors
    assert len(result) >= 1


# ── Deduplication edge cases ──


def test_deduplicate_tool_results():
    """Duplicate tool results for same call_id are deduplicated."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="first")])
    msg2 = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="second")])

    result = _deduplicate_messages([msg1, msg2])
    assert len(result) == 1


def test_deduplicate_assistant_tool_calls():
    """Duplicate assistant messages with same tool_calls are deduplicated."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(
        role="assistant",
        contents=[Content.from_function_call(call_id="c1", name="fn", arguments="{}")],
    )
    msg2 = Message(
        role="assistant",
        contents=[Content.from_function_call(call_id="c1", name="fn", arguments="{}")],
    )

    result = _deduplicate_messages([msg1, msg2])
    assert len(result) == 1


def test_deduplicate_by_message_id():
    """Messages with the same message_id are deduplicated."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg1.message_id = "msg-1"
    msg2 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg2.message_id = "msg-1"

    result = _deduplicate_messages([msg1, msg2])
    assert len(result) == 1
    assert result == [msg1]


def test_deduplicate_preserves_repeated_confirmations_with_distinct_ids():
    """Identical content with different message_ids is preserved."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    assistant = Message(role="assistant", contents=[Content.from_text(text="Are you sure?")])
    assistant.message_id = "msg-1"
    confirm1 = Message(role="user", contents=[Content.from_text(text="yes")])
    confirm1.message_id = "msg-2"
    confirm2 = Message(role="user", contents=[Content.from_text(text="yes")])
    confirm2.message_id = "msg-3"

    result = _deduplicate_messages([confirm1, assistant, confirm2])
    assert result == [confirm1, assistant, confirm2]


def test_deduplicate_preserves_repeated_system_messages_with_distinct_ids():
    """Non-consecutive identical system messages with different ids are preserved."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    sys1 = Message(role="system", contents=[Content.from_text(text="You are a helpful assistant.")])
    sys1.message_id = "msg-1"
    user_msg = Message(role="user", contents=[Content.from_text(text="Hi")])
    user_msg.message_id = "msg-2"
    sys2 = Message(role="system", contents=[Content.from_text(text="You are a helpful assistant.")])
    sys2.message_id = "msg-3"

    result = _deduplicate_messages([sys1, user_msg, sys2])
    assert result == [sys1, user_msg, sys2]


def test_deduplicate_skips_replayed_system_messages_with_same_id():
    """System messages replayed with the same message_id are deduplicated."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msgs = []
    for _ in range(3):
        m = Message(role="system", contents=[Content.from_text(text="You are a helpful assistant.")])
        m.message_id = "msg-1"
        msgs.append(m)

    result = _deduplicate_messages(msgs)
    assert len(result) == 1


def test_deduplicate_without_message_id_uses_content_hash():
    """Messages without message_id are deduplicated by content hash."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg2 = Message(role="user", contents=[Content.from_text(text="Hello")])

    result = _deduplicate_messages([msg1, msg2])
    assert result == [msg1]


def test_deduplicate_without_message_id_preserves_different_content():
    """Messages without message_id but different content are preserved."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg2 = Message(role="user", contents=[Content.from_text(text="World")])

    result = _deduplicate_messages([msg1, msg2])
    assert result == [msg1, msg2]


def test_deduplicate_handles_none_contents():
    """Messages with contents=None pass through without errors; duplicates are deduped."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=None)
    msg2 = Message(role="assistant", contents=[Content.from_text(text="Hello")])
    msg3 = Message(role="user", contents=None)

    result = _deduplicate_messages([msg1, msg2, msg3])
    assert result == [msg1, msg2]


def test_deduplicate_mixed_id_and_no_id():
    """Messages with and without message_id coexist correctly."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg1.message_id = "msg-1"
    msg2 = Message(role="user", contents=[Content.from_text(text="Hello")])  # no id
    msg3 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg3.message_id = "msg-1"  # duplicate of msg1

    result = _deduplicate_messages([msg1, msg2, msg3])
    assert len(result) == 2
    assert result == [msg1, msg2]


def test_deduplicate_replaces_empty_tool_result():
    """Empty tool result is replaced by later non-empty result."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="")])
    msg2 = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="actual result")])

    result = _deduplicate_messages([msg1, msg2])
    assert len(result) == 1
    assert result[0].contents[0].result == "actual result"


def test_deduplicate_empty_string_message_id_falls_back_to_content_hash():
    """Empty-string message_id is treated as missing; content-hash dedup is used."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg1.message_id = ""
    msg2 = Message(role="user", contents=[Content.from_text(text="World")])
    msg2.message_id = ""

    result = _deduplicate_messages([msg1, msg2])
    assert result == [msg1, msg2], "Different content with empty IDs should both be preserved"


def test_deduplicate_empty_string_message_id_deduplicates_same_content():
    """Empty-string message_id with identical content should be deduplicated."""
    from agent_framework_ag_ui._message_adapters import _deduplicate_messages

    msg1 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg1.message_id = ""
    msg2 = Message(role="user", contents=[Content.from_text(text="Hello")])
    msg2.message_id = ""

    result = _deduplicate_messages([msg1, msg2])
    assert result == [msg1], "Same content with empty IDs should be deduplicated"


def test_convert_agui_content_unknown_source_type_fallback():
    """Unknown source type falls back to url/data/id fields."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    part = {
        "type": "image",
        "source": {"type": "custom", "url": "https://example.com/img.png"},
    }
    result = _parse_multimodal_media_part(part)
    assert result is not None
    assert result.uri == "https://example.com/img.png"


def test_convert_agui_content_data_uri_prefix():
    """base64 data starting with 'data:' is treated as data URI."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    part = {
        "type": "image",
        "source": {"type": "base64", "data": "data:image/png;base64,abc", "mimeType": "image/png"},
    }
    result = _parse_multimodal_media_part(part)
    assert result is not None
    assert result.uri == "data:image/png;base64,abc"


def test_convert_agui_content_binary_id():
    """Source with 'id' field creates ag-ui:// URI."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    part = {
        "type": "image",
        "source": {"type": "id", "id": "file123"},
    }
    result = _parse_multimodal_media_part(part)
    assert result is not None
    assert result.uri == "ag-ui://binary/file123"


def test_convert_agui_content_string_items_in_list():
    """String items in content list create text Content."""
    from agent_framework_ag_ui._message_adapters import _convert_agui_content_to_framework

    result = _convert_agui_content_to_framework(["hello", "world"])
    assert len(result) == 2
    assert result[0].text == "hello"
    assert result[1].text == "world"


def test_convert_agui_content_non_dict_non_str_items():
    """Non-dict/non-str items in list are stringified."""
    from agent_framework_ag_ui._message_adapters import _convert_agui_content_to_framework

    result = _convert_agui_content_to_framework([123, None])
    assert len(result) == 2
    assert result[0].text == "123"
    assert result[1].text == "None"


def test_convert_agui_content_unknown_part_type_with_text():
    """Unknown part type with 'text' key extracts the text."""
    from agent_framework_ag_ui._message_adapters import _convert_agui_content_to_framework

    result = _convert_agui_content_to_framework([{"type": "widget", "text": "hi"}])
    assert len(result) == 1
    assert result[0].text == "hi"


def test_convert_agui_content_unknown_part_type_without_text():
    """Unknown part type without 'text' key stringifies the dict."""
    from agent_framework_ag_ui._message_adapters import _convert_agui_content_to_framework

    result = _convert_agui_content_to_framework([{"type": "widget", "data": 42}])
    assert len(result) == 1
    assert "widget" in result[0].text


def test_convert_agui_content_none():
    """None content returns empty list."""
    from agent_framework_ag_ui._message_adapters import _convert_agui_content_to_framework

    result = _convert_agui_content_to_framework(None)
    assert result == []


def test_convert_agui_content_non_str_non_list_non_none():
    """Non-string, non-list, non-None content is stringified."""
    from agent_framework_ag_ui._message_adapters import _convert_agui_content_to_framework

    result = _convert_agui_content_to_framework(42)
    assert len(result) == 1
    assert result[0].text == "42"


# ── Snapshot normalization edge cases ──


def test_snapshot_input_image_to_binary():
    """input_image type is normalized to binary in snapshot."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "source": {"type": "url", "url": "https://example.com/img.png"}},
                ],
            }
        ]
    )
    assert isinstance(result[0]["content"], list)
    assert result[0]["content"][0]["type"] == "binary"


def test_snapshot_mime_type_snake_case():
    """mime_type (snake_case) is normalized to mimeType."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Caption", "mime_type": "text/plain"},
                    {
                        "type": "image",
                        "source": {"type": "url", "url": "https://x.com/a.png", "mime_type": "image/png"},
                    },
                ],
            }
        ]
    )
    content = result[0]["content"]
    assert isinstance(content, list)
    # The text part should have mimeType added
    text_part = content[0]
    assert text_part.get("mimeType") == "text/plain"


def test_snapshot_text_only_list_collapsed():
    """List of only text parts is collapsed to string."""
    result = agui_messages_to_snapshot_format(
        [{"role": "user", "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": " World"}]}]
    )
    assert result[0]["content"] == "Hello World"


def test_snapshot_legacy_binary_data_and_id():
    """Legacy binary part with data and id fields."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Caption"},
                    {"type": "binary", "data": "base64data", "id": "file1", "mimeType": "image/png"},
                ],
            }
        ]
    )
    content = result[0]["content"]
    assert isinstance(content, list)
    binary_part = content[1]
    assert binary_part["type"] == "binary"
    assert binary_part["data"] == "base64data"
    assert binary_part["id"] == "file1"


# ── Message conversion edge cases ──


def test_agui_tool_message_action_execution_id_fallback():
    """Tool message with actionExecutionId but no tool_call_id."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "tool",
                "content": "result data",
                "actionExecutionId": "action_1",
            }
        ]
    )
    assert len(messages) == 1
    assert messages[0].contents[0].type == "function_result"
    assert messages[0].contents[0].call_id == "action_1"


def test_agui_tool_message_result_key_instead_of_content():
    """Tool message with 'result' key instead of 'content'."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "tool",
                "result": "the result",
                "toolCallId": "c1",
            }
        ]
    )
    assert len(messages) == 1
    assert messages[0].contents[0].result == "the result"


def test_agui_tool_message_dict_content():
    """Tool message with dict content."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "tool",
                "content": {"key": "value"},
                "toolCallId": "c1",
            }
        ]
    )
    assert len(messages) == 1
    # Dict content as approval check: no 'accepted' key, so it's a regular tool result
    assert messages[0].contents[0].type == "function_result"


def test_agui_tool_message_list_content():
    """Tool message with list content."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "tool",
                "content": ["item1", "item2"],
                "toolCallId": "c1",
            }
        ]
    )
    assert len(messages) == 1
    assert messages[0].contents[0].type == "function_result"


def test_agui_action_execution_id_without_role():
    """Message with actionExecutionId but no role maps to tool."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "actionExecutionId": "action_1",
                "result": "tool result",
            }
        ]
    )
    assert len(messages) == 1
    assert messages[0].role == "tool"
    assert messages[0].contents[0].call_id == "action_1"


def test_agui_non_dict_tool_call_skipped():
    """Non-dict tool_call entries in tool_calls array are skipped."""
    messages = agui_messages_to_agent_framework(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    "not_a_dict",
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "fn", "arguments": "{}"},
                    },
                ],
            }
        ]
    )
    assert len(messages) == 1
    func_calls = [c for c in messages[0].contents if c.type == "function_call"]
    assert len(func_calls) == 1


def test_agui_empty_content_default():
    """Message with empty/null content gets default empty text."""
    messages = agui_messages_to_agent_framework([{"role": "user"}])
    assert len(messages) == 1
    assert len(messages[0].contents) == 1
    assert messages[0].contents[0].text == ""


def test_agui_dict_tool_msg_without_tool_call_id():
    """Dict tool message missing toolCallId gets empty string."""
    result = agui_messages_to_snapshot_format([{"role": "tool", "content": "result"}])
    assert len(result) == 1
    assert result[0].get("toolCallId") == ""


def test_snapshot_argument_serialization_none():
    """None arguments in tool_calls are serialized to empty string."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "fn", "arguments": None}},
                ],
            }
        ]
    )
    tc = result[0]["tool_calls"][0]
    assert tc["function"]["arguments"] == ""


def test_snapshot_argument_serialization_object():
    """Object arguments in tool_calls are JSON-serialized."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "fn", "arguments": {"key": "val"}}},
                ],
            }
        ]
    )
    tc = result[0]["tool_calls"][0]
    assert tc["function"]["arguments"] == '{"key": "val"}'


def test_snapshot_tool_call_id_normalization():
    """tool_call_id is normalized to toolCallId in snapshot."""
    result = agui_messages_to_snapshot_format([{"role": "tool", "content": "result", "tool_call_id": "c1"}])
    assert result[0].get("toolCallId") == "c1"
    assert "tool_call_id" not in result[0]


def test_agui_to_framework_dict_tool_msg_without_tool_call_id():
    """Dict tool message in agent_framework_messages_to_agui without toolCallId."""
    result = agent_framework_messages_to_agui(
        [{"role": "tool", "content": "result"}]  # type: ignore[list-item]
    )
    assert len(result) == 1
    assert result[0].get("toolCallId") == ""


def test_snapshot_none_content():
    """None content is normalized to empty string."""
    result = agui_messages_to_snapshot_format([{"role": "user", "content": None}])
    assert result[0]["content"] == ""


def test_sanitize_confirm_changes_with_approval_accepted():
    """Approval for pending confirm_changes creates synthetic result."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    # Create assistant with both a real tool and confirm_changes
    assistant_msg = Message(
        role="assistant",
        contents=[
            Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
            Content.from_function_call(call_id="c2", name="confirm_changes", arguments='{"function_call_id":"c1"}'),
        ],
    )
    # Note: confirm_changes gets filtered out, so pending_confirm_changes_id becomes None.
    # The test verifies the filtering path works without error.
    user_msg = Message(
        role="user",
        contents=[
            Content.from_function_approval_response(
                approved=True,
                id="a1",
                function_call=Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
            ),
        ],
    )

    result = _sanitize_tool_history([assistant_msg, user_msg])
    # Should process without errors; confirm_changes is filtered from assistant msg
    assert len(result) >= 1


def test_sanitize_json_accepted_text_for_pending_confirm():
    """JSON text with 'accepted' field for non-filtered confirm_changes path."""
    from agent_framework_ag_ui._message_adapters import _sanitize_tool_history

    # Create an assistant with a tool call that requires a result
    assistant_msg = Message(
        role="assistant",
        contents=[
            Content.from_function_call(call_id="c1", name="tool_a", arguments="{}"),
        ],
    )
    # A tool result arrives, then a user message
    tool_msg = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="c1", result="done")],
    )
    user_msg = Message(
        role="user",
        contents=[Content.from_text(text="Continue please")],
    )

    result = _sanitize_tool_history([assistant_msg, tool_msg, user_msg])
    # Should have: assistant, tool result, user
    assert len(result) == 3


def test_parse_multimodal_media_part_no_data_no_url():
    """Part with no url, data, or id returns None."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part({"type": "image"})
    assert result is None


def test_parse_multimodal_media_part_binary_source_type():
    """Source with type='binary' extracts data field."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part(
        {"type": "image", "source": {"type": "binary", "data": "data:image/png;base64,abc"}}
    )
    assert result is not None
    assert result.uri == "data:image/png;base64,abc"


def test_snapshot_non_dict_item_in_content_list():
    """Non-dict items in content list are stringified."""
    result = agui_messages_to_snapshot_format([{"role": "user", "content": [42, "text"]}])
    # Text-only after stringification means collapsed to string
    assert isinstance(result[0]["content"], str)


def test_snapshot_non_dict_tool_call_skipped():
    """Non-dict entries in tool_calls are skipped during argument serialization."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    "not_a_dict",
                    {"id": "c1", "type": "function", "function": {"name": "fn", "arguments": "{}"}},
                ],
            }
        ]
    )
    # Should not error
    assert len(result) == 1


def test_snapshot_tool_call_without_function_payload():
    """tool_call dict without function payload is skipped."""
    result = agui_messages_to_snapshot_format(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "c1", "type": "function"}],
            }
        ]
    )
    assert len(result) == 1


def test_agui_to_framework_action_name_without_role():
    """Message with actionName but no explicit role maps to tool."""
    messages = agui_messages_to_agent_framework([{"actionName": "get_weather", "result": "Sunny", "toolCallId": "c1"}])
    assert len(messages) == 1
    assert messages[0].role == "tool"


def test_agui_to_framework_tool_message_content_none():
    """Tool message with content=None uses result field fallback."""
    messages = agui_messages_to_agent_framework(
        [{"role": "tool", "content": None, "result": "fallback_result", "toolCallId": "c1"}]
    )
    assert len(messages) == 1
    assert messages[0].contents[0].result == "fallback_result"


def test_agui_fresh_approval_is_still_processed():
    """A fresh approval (no assistant response after it) must still produce function_approval_response.

    On Turn 2, the approval is fresh (no subsequent assistant message), so it
    must be processed normally to execute the tool.
    """
    messages_input = [
        # Turn 1: user asks something
        {"role": "user", "content": "What time is it?", "id": "msg_1"},
        # Turn 1: assistant calls a tool
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {"name": "get_datetime", "arguments": "{}"},
                }
            ],
            "id": "msg_2",
        },
        # Turn 2: user approves (no assistant message after this)
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": "call_456",
            "id": "msg_3",
        },
    ]

    messages = agui_messages_to_agent_framework(messages_input)

    # The fresh approval SHOULD produce a function_approval_response
    approval_contents = [
        content for msg in messages for content in (msg.contents or []) if content.type == "function_approval_response"
    ]
    assert len(approval_contents) == 1, "Fresh approval should produce function_approval_response"
    assert approval_contents[0].approved is True
    assert approval_contents[0].function_call.name == "get_datetime"


class TestReasoningRoundTrip:
    """Tests for reasoning message handling in inbound/outbound adapters."""

    def test_reasoning_skipped_on_inbound(self):
        """Reasoning messages from prior snapshot are not forwarded to the LLM."""
        messages_input = [
            {"id": "u1", "role": "user", "content": "Hello"},
            {"id": "r1", "role": "reasoning", "content": "Thinking..."},
            {"id": "a1", "role": "assistant", "content": "Hi there"},
        ]

        result = agui_messages_to_agent_framework(messages_input)

        roles = [m.role if hasattr(m.role, "value") else str(m.role) for m in result]
        assert "reasoning" not in roles
        assert len(result) == 2

    def test_reasoning_preserved_in_snapshot_format(self):
        """Reasoning messages retain their role through snapshot normalization."""
        messages_input = [
            {"id": "u1", "role": "user", "content": "Hello"},
            {"id": "r1", "role": "reasoning", "content": "Thinking about this..."},
            {"id": "a1", "role": "assistant", "content": "Answer"},
        ]

        result = agui_messages_to_snapshot_format(messages_input)

        reasoning_msgs = [m for m in result if m.get("role") == "reasoning"]
        assert len(reasoning_msgs) == 1
        assert reasoning_msgs[0]["content"] == "Thinking about this..."

    def test_reasoning_with_encrypted_value_in_snapshot_format(self):
        """Reasoning with encryptedValue passes through snapshot normalization."""
        messages_input = [
            {
                "id": "r1",
                "role": "reasoning",
                "content": "visible",
                "encryptedValue": "secret-data",
            },
        ]

        result = agui_messages_to_snapshot_format(messages_input)

        assert len(result) == 1
        assert result[0]["role"] == "reasoning"
        assert result[0]["encryptedValue"] == "secret-data"

    def test_reasoning_encrypted_value_snake_case_normalized(self):
        """Snake-case encrypted_value is normalized to encryptedValue in snapshot format."""
        messages_input = [
            {
                "id": "r1",
                "role": "reasoning",
                "content": "visible",
                "encrypted_value": "snake-case-data",
            },
        ]

        result = agui_messages_to_snapshot_format(messages_input)

        assert len(result) == 1
        assert result[0]["encryptedValue"] == "snake-case-data"
        assert "encrypted_value" not in result[0]

    def test_multi_turn_with_reasoning_in_prior_snapshot(self):
        """Second turn with reasoning from prior snapshot does not corrupt messages."""
        messages_input = [
            {"id": "u1", "role": "user", "content": "First question"},
            {"id": "r1", "role": "reasoning", "content": "Prior reasoning"},
            {"id": "a1", "role": "assistant", "content": "First answer"},
            {"id": "u2", "role": "user", "content": "Follow-up question"},
        ]

        result = agui_messages_to_agent_framework(messages_input)

        roles = [m.role if hasattr(m.role, "value") else str(m.role) for m in result]
        # Reasoning is filtered out, other messages preserved in order
        assert roles == ["user", "assistant", "user"]
        # Content not corrupted
        texts = []
        for m in result:
            for c in m.contents or []:
                if hasattr(c, "text") and c.text:
                    texts.append(c.text)
        assert "First question" in texts
        assert "First answer" in texts
        assert "Follow-up question" in texts
        assert "Prior reasoning" not in texts


def test_parse_multimodal_media_part_base64_value_field():
    """Source with type='base64' reads data from the 'value' field per AG-UI spec."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part(
        {"type": "image", "source": {"type": "base64", "value": "aGVsbG8=", "mimeType": "image/png"}}
    )
    assert result is not None
    assert "aGVsbG8=" in result.uri


def test_parse_multimodal_media_part_data_source_value_field():
    """Source with type='data' reads data from the 'value' field per AG-UI spec."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part(
        {"type": "image", "source": {"type": "data", "value": "aGVsbG8=", "mimeType": "image/png"}}
    )
    assert result is not None
    assert "aGVsbG8=" in result.uri


def test_parse_multimodal_media_part_base64_data_field_backward_compat():
    """Source with type='base64' still supports deprecated 'data' field."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part(
        {"type": "image", "source": {"type": "base64", "data": "aGVsbG8=", "mimeType": "image/png"}}
    )
    assert result is not None
    assert "aGVsbG8=" in result.uri


def test_parse_multimodal_media_part_value_preferred_over_data():
    """When both 'value' and 'data' are present, 'value' takes precedence."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part(
        {
            "type": "image",
            "source": {
                "type": "base64",
                "value": "dmFsdWU=",
                "data": "ZGF0YQ==",
                "mimeType": "image/png",
            },
        }
    )
    assert result is not None
    # 'value' field content should be used (base64 of "value")
    assert "dmFsdWU=" in result.uri


def test_parse_multimodal_media_part_unknown_source_value_fallback():
    """Unknown source type falls back to 'value' field before 'data' field."""
    from agent_framework_ag_ui._message_adapters import _parse_multimodal_media_part

    result = _parse_multimodal_media_part(
        {"type": "image", "source": {"type": "custom", "value": "aGVsbG8=", "mimeType": "image/png"}}
    )
    assert result is not None
    assert "aGVsbG8=" in result.uri
