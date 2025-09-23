# Copyright (c) Microsoft. All rights reserved.

"""Tests for tau2 utils module."""

from typing import Any, cast
from pydantic import BaseModel

from agent_framework._tools import AIFunction
from agent_framework._types import ChatMessage, Role, TextContent, FunctionCallContent, FunctionResultContent
from agent_framework_lab_tau2._tau2_utils import (
    convert_tau2_tool_to_ai_function,
    convert_agent_framework_messages_to_tau2_messages,
)
from tau2.data_model.message import SystemMessage, UserMessage, AssistantMessage, ToolMessage, ToolCall
from tau2.domains.airline.environment import get_environment


def test_convert_tau2_tool_to_ai_function_basic():
    """Test basic conversion from tau2 tool to AIFunction."""
    # Get real tools from tau2 environment
    env = get_environment()
    tools = env.get_tools()

    # Use the first available tool for testing
    assert len(tools) > 0, "No tools available in environment"
    tau2_tool = tools[0]

    # Convert the tool
    ai_function = convert_tau2_tool_to_ai_function(tau2_tool)

    # Verify the conversion
    assert isinstance(ai_function, AIFunction)
    assert ai_function.name == tau2_tool.name
    assert ai_function.description == tau2_tool._get_description()
    assert ai_function.input_model == tau2_tool.params

    # Test that the function is callable (we won't call it with real params to avoid side effects)
    assert callable(ai_function.func)


def test_convert_tau2_tool_to_ai_function_multiple_tools():
    """Test conversion with multiple tau2 tools."""
    # Get real tools from tau2 environment
    env = get_environment()
    tools = env.get_tools()

    # Convert multiple tools
    ai_functions = [convert_tau2_tool_to_ai_function(tool) for tool in tools[:3]]  # Test first 3 tools

    # Verify all conversions
    for ai_function, tau2_tool in zip(ai_functions, tools[:3]):
        assert isinstance(ai_function, AIFunction)
        assert ai_function.name == tau2_tool.name
        assert ai_function.description == tau2_tool._get_description()
        assert ai_function.input_model == tau2_tool.params
        assert callable(ai_function.func)


def test_convert_agent_framework_messages_to_tau2_messages_system():
    """Test converting system message."""
    messages = [ChatMessage(role=Role.SYSTEM, contents=[TextContent(text="System instruction")])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], SystemMessage)
    assert tau2_messages[0].role == "system"
    assert tau2_messages[0].content == "System instruction"


def test_convert_agent_framework_messages_to_tau2_messages_user():
    """Test converting user message."""
    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="Hello assistant")])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], UserMessage)
    assert tau2_messages[0].role == "user"
    assert tau2_messages[0].content == "Hello assistant"
    assert tau2_messages[0].tool_calls is None


def test_convert_agent_framework_messages_to_tau2_messages_assistant():
    """Test converting assistant message."""
    messages = [ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="Hello user")])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], AssistantMessage)
    assert tau2_messages[0].role == "assistant"
    assert tau2_messages[0].content == "Hello user"
    assert tau2_messages[0].tool_calls is None


def test_convert_agent_framework_messages_to_tau2_messages_with_function_call():
    """Test converting message with function call."""
    function_call = FunctionCallContent(call_id="call_123", name="test_function", arguments={"param": "value"})

    messages = [ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="I'll call a function"), function_call])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], AssistantMessage)
    assert tau2_messages[0].content == "I'll call a function"
    assert tau2_messages[0].tool_calls is not None
    assert len(tau2_messages[0].tool_calls) == 1

    tool_call = tau2_messages[0].tool_calls[0]
    assert isinstance(tool_call, ToolCall)
    assert tool_call.id == "call_123"
    assert tool_call.name == "test_function"
    assert tool_call.arguments == {"param": "value"}
    assert tool_call.requestor == "assistant"


def test_convert_agent_framework_messages_to_tau2_messages_with_function_result():
    """Test converting message with function result."""
    function_result = FunctionResultContent(call_id="call_123", result={"success": True, "data": "result data"})

    messages = [ChatMessage(role=Role.TOOL, contents=[function_result])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], ToolMessage)
    assert tau2_messages[0].id == "call_123"
    assert tau2_messages[0].role == "tool"
    assert tau2_messages[0].content is not None
    assert '{"success": true, "data": "result data"}' in tau2_messages[0].content
    assert tau2_messages[0].requestor == "assistant"
    assert tau2_messages[0].error is False


def test_convert_agent_framework_messages_to_tau2_messages_with_error():
    """Test converting function result with error."""
    function_result = FunctionResultContent(
        call_id="call_456", result="Error occurred", exception=Exception("Test error")
    )

    messages = [ChatMessage(role=Role.TOOL, contents=[function_result])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], ToolMessage)
    assert tau2_messages[0].error is True


def test_convert_agent_framework_messages_to_tau2_messages_multiple_text_contents():
    """Test converting message with multiple text contents."""
    messages = [ChatMessage(role=Role.USER, contents=[TextContent(text="First part"), TextContent(text="Second part")])]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 1
    assert isinstance(tau2_messages[0], UserMessage)
    assert tau2_messages[0].content == "First part Second part"


def test_convert_agent_framework_messages_to_tau2_messages_complex_scenario():
    """Test converting complex scenario with multiple message types."""
    function_call = FunctionCallContent(call_id="call_789", name="complex_tool", arguments='{"key": "value"}')

    function_result = FunctionResultContent(call_id="call_789", result={"output": "tool result"})

    messages = [
        ChatMessage(role=Role.SYSTEM, contents=[TextContent(text="System prompt")]),
        ChatMessage(role=Role.USER, contents=[TextContent(text="User request")]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="I'll help you"), function_call]),
        ChatMessage(role=Role.TOOL, contents=[function_result]),
        ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text="Based on the result...")]),
    ]

    tau2_messages = convert_agent_framework_messages_to_tau2_messages(messages)

    assert len(tau2_messages) == 5
    assert isinstance(tau2_messages[0], SystemMessage)
    assert isinstance(tau2_messages[1], UserMessage)
    assert isinstance(tau2_messages[2], AssistantMessage)
    assert isinstance(tau2_messages[3], ToolMessage)
    assert isinstance(tau2_messages[4], AssistantMessage)

    # Check the assistant message with tool call
    assert tau2_messages[2].tool_calls is not None
    assert len(tau2_messages[2].tool_calls) == 1
    assert tau2_messages[2].tool_calls[0].name == "complex_tool"
