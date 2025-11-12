# Copyright (c) Microsoft. All rights reserved.
import os
from pathlib import Path
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponseUpdate,
    DataContent,
    FinishReason,
    FunctionCallContent,
    FunctionResultContent,
    HostedCodeInterpreterTool,
    HostedMCPTool,
    HostedWebSearchTool,
    Role,
    TextContent,
    TextReasoningContent,
    ai_function,
)
from agent_framework.exceptions import ServiceInitializationError
from anthropic.types.beta import (
    BetaMessage,
    BetaTextBlock,
    BetaToolUseBlock,
    BetaUsage,
)
from pydantic import Field, ValidationError

from agent_framework_anthropic import AnthropicClient
from agent_framework_anthropic._chat_client import AnthropicSettings

skip_if_anthropic_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("ANTHROPIC_API_KEY", "") in ("", "test-api-key-12345"),
    reason="No real ANTHROPIC_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def create_test_anthropic_client(
    mock_anthropic_client: MagicMock,
    model_id: str | None = None,
    anthropic_settings: AnthropicSettings | None = None,
) -> AnthropicClient:
    """Helper function to create AnthropicClient instances for testing, bypassing normal validation."""
    if anthropic_settings is None:
        anthropic_settings = AnthropicSettings(api_key="test-api-key-12345", chat_model_id="claude-3-5-sonnet-20241022")

    # Create client instance directly
    client = object.__new__(AnthropicClient)

    # Set attributes directly
    client.anthropic_client = mock_anthropic_client
    client.model_id = model_id or anthropic_settings.chat_model_id
    client._last_call_id_name = None
    client.additional_properties = {}
    client.middleware = None

    return client


# Settings Tests


def test_anthropic_settings_init(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicSettings initialization."""
    settings = AnthropicSettings()

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == anthropic_unit_test_env["ANTHROPIC_API_KEY"]
    assert settings.chat_model_id == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


def test_anthropic_settings_init_with_explicit_values() -> None:
    """Test AnthropicSettings initialization with explicit values."""
    settings = AnthropicSettings(
        api_key="custom-api-key",
        chat_model_id="claude-3-opus-20240229",
    )

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "custom-api-key"
    assert settings.chat_model_id == "claude-3-opus-20240229"


@pytest.mark.parametrize("exclude_list", [["ANTHROPIC_API_KEY"]], indirect=True)
def test_anthropic_settings_missing_api_key(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicSettings when API key is missing."""
    settings = AnthropicSettings()
    assert settings.api_key is None
    assert settings.chat_model_id == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


# Client Initialization Tests


def test_anthropic_client_init_with_client(mock_anthropic_client: MagicMock) -> None:
    """Test AnthropicClient initialization with existing anthropic_client."""
    chat_client = create_test_anthropic_client(mock_anthropic_client, model_id="claude-3-5-sonnet-20241022")

    assert chat_client.anthropic_client is mock_anthropic_client
    assert chat_client.model_id == "claude-3-5-sonnet-20241022"
    assert isinstance(chat_client, ChatClientProtocol)


def test_anthropic_client_init_auto_create_client(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicClient initialization with auto-created anthropic_client."""
    client = AnthropicClient(
        api_key=anthropic_unit_test_env["ANTHROPIC_API_KEY"],
        model_id=anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"],
    )

    assert client.anthropic_client is not None
    assert client.model_id == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


def test_anthropic_client_init_missing_api_key() -> None:
    """Test AnthropicClient initialization when API key is missing."""
    with patch("agent_framework_anthropic._chat_client.AnthropicSettings") as mock_settings:
        mock_settings.return_value.api_key = None
        mock_settings.return_value.chat_model_id = "claude-3-5-sonnet-20241022"

        with pytest.raises(ServiceInitializationError, match="Anthropic API key is required"):
            AnthropicClient()


def test_anthropic_client_init_validation_error() -> None:
    """Test that ValidationError in AnthropicSettings is properly handled."""
    with patch("agent_framework_anthropic._chat_client.AnthropicSettings") as mock_settings:
        mock_settings.side_effect = ValidationError.from_exception_data("test", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Anthropic settings"):
            AnthropicClient()


def test_anthropic_client_service_url(mock_anthropic_client: MagicMock) -> None:
    """Test service_url method."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    assert chat_client.service_url() == "https://api.anthropic.com"


# Message Conversion Tests


def test_convert_message_to_anthropic_format_text(mock_anthropic_client: MagicMock) -> None:
    """Test converting text message to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    message = ChatMessage(role=Role.USER, text="Hello, world!")

    result = chat_client._convert_message_to_anthropic_format(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Hello, world!"


def test_convert_message_to_anthropic_format_function_call(mock_anthropic_client: MagicMock) -> None:
    """Test converting function call message to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    message = ChatMessage(
        role=Role.ASSISTANT,
        contents=[
            FunctionCallContent(
                call_id="call_123",
                name="get_weather",
                arguments={"location": "San Francisco"},
            )
        ],
    )

    result = chat_client._convert_message_to_anthropic_format(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "tool_use"
    assert result["content"][0]["id"] == "call_123"
    assert result["content"][0]["name"] == "get_weather"
    assert result["content"][0]["input"] == {"location": "San Francisco"}


def test_convert_message_to_anthropic_format_function_result(mock_anthropic_client: MagicMock) -> None:
    """Test converting function result message to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    message = ChatMessage(
        role=Role.TOOL,
        contents=[
            FunctionResultContent(
                call_id="call_123",
                name="get_weather",
                result="Sunny, 72°F",
            )
        ],
    )

    result = chat_client._convert_message_to_anthropic_format(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "tool_result"
    assert result["content"][0]["tool_use_id"] == "call_123"
    # The degree symbol might be escaped differently depending on JSON encoder
    assert "Sunny" in result["content"][0]["content"]
    assert "72" in result["content"][0]["content"]
    assert result["content"][0]["is_error"] is False


def test_convert_message_to_anthropic_format_text_reasoning(mock_anthropic_client: MagicMock) -> None:
    """Test converting text reasoning message to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    message = ChatMessage(
        role=Role.ASSISTANT,
        contents=[TextReasoningContent(text="Let me think about this...")],
    )

    result = chat_client._convert_message_to_anthropic_format(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "thinking"
    assert result["content"][0]["thinking"] == "Let me think about this..."


def test_convert_messages_to_anthropic_format_with_system(mock_anthropic_client: MagicMock) -> None:
    """Test converting messages list with system message."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant."),
        ChatMessage(role=Role.USER, text="Hello!"),
    ]

    result = chat_client._convert_messages_to_anthropic_format(messages)

    # System message should be skipped
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"][0]["text"] == "Hello!"


def test_convert_messages_to_anthropic_format_without_system(mock_anthropic_client: MagicMock) -> None:
    """Test converting messages list without system message."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    messages = [
        ChatMessage(role=Role.USER, text="Hello!"),
        ChatMessage(role=Role.ASSISTANT, text="Hi there!"),
    ]

    result = chat_client._convert_messages_to_anthropic_format(messages)

    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"


# Tool Conversion Tests


def test_convert_tools_to_anthropic_format_ai_function(mock_anthropic_client: MagicMock) -> None:
    """Test converting AIFunction to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    @ai_function
    def get_weather(location: Annotated[str, Field(description="Location to get weather for")]) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    tools = [get_weather]

    result = chat_client._convert_tools_to_anthropic_format(tools)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "custom"
    assert result["tools"][0]["name"] == "get_weather"
    assert "Get weather for a location" in result["tools"][0]["description"]


def test_convert_tools_to_anthropic_format_web_search(mock_anthropic_client: MagicMock) -> None:
    """Test converting HostedWebSearchTool to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    tools = [HostedWebSearchTool()]

    result = chat_client._convert_tools_to_anthropic_format(tools)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "web_search_20250305"
    assert result["tools"][0]["name"] == "web_search"


def test_convert_tools_to_anthropic_format_code_interpreter(mock_anthropic_client: MagicMock) -> None:
    """Test converting HostedCodeInterpreterTool to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    tools = [HostedCodeInterpreterTool()]

    result = chat_client._convert_tools_to_anthropic_format(tools)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "code_execution_20250825"
    assert result["tools"][0]["name"] == "code_interpreter"


def test_convert_tools_to_anthropic_format_mcp_tool(mock_anthropic_client: MagicMock) -> None:
    """Test converting HostedMCPTool to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    tools = [HostedMCPTool(name="test-mcp", url="https://example.com/mcp")]

    result = chat_client._convert_tools_to_anthropic_format(tools)

    assert result is not None
    assert "mcp_servers" in result
    assert len(result["mcp_servers"]) == 1
    assert result["mcp_servers"][0]["type"] == "url"
    assert result["mcp_servers"][0]["name"] == "test-mcp"
    assert result["mcp_servers"][0]["url"] == "https://example.com/mcp"


def test_convert_tools_to_anthropic_format_mcp_with_auth(mock_anthropic_client: MagicMock) -> None:
    """Test converting HostedMCPTool with authorization headers."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    tools = [
        HostedMCPTool(
            name="test-mcp",
            url="https://example.com/mcp",
            headers={"authorization": "Bearer token123"},
        )
    ]

    result = chat_client._convert_tools_to_anthropic_format(tools)

    assert result is not None
    assert "mcp_servers" in result
    # The authorization header is converted to authorization_token
    assert "authorization_token" in result["mcp_servers"][0]
    assert result["mcp_servers"][0]["authorization_token"] == "Bearer token123"


def test_convert_tools_to_anthropic_format_dict_tool(mock_anthropic_client: MagicMock) -> None:
    """Test converting dict tool to Anthropic format."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)
    tools = [{"type": "custom", "name": "custom_tool", "description": "A custom tool"}]

    result = chat_client._convert_tools_to_anthropic_format(tools)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["name"] == "custom_tool"


def test_convert_tools_to_anthropic_format_none(mock_anthropic_client: MagicMock) -> None:
    """Test converting None tools."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    result = chat_client._convert_tools_to_anthropic_format(None)

    assert result is None


# Run Options Tests


async def test_create_run_options_basic(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with basic ChatOptions."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(max_tokens=100, temperature=0.7)

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["model"] == chat_client.model_id
    assert run_options["max_tokens"] == 100
    assert run_options["temperature"] == 0.7
    assert "messages" in run_options


async def test_create_run_options_with_system_message(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with system message."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are helpful."),
        ChatMessage(role=Role.USER, text="Hello"),
    ]
    chat_options = ChatOptions()

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["system"] == "You are helpful."
    assert len(run_options["messages"]) == 1  # System message not in messages list


async def test_create_run_options_with_tool_choice_auto(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with auto tool choice."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(tool_choice="auto")

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "auto"


async def test_create_run_options_with_tool_choice_required(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with required tool choice."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    # For required with specific function, need to pass as dict
    chat_options = ChatOptions(tool_choice={"mode": "required", "required_function_name": "get_weather"})

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "tool"
    assert run_options["tool_choice"]["name"] == "get_weather"


async def test_create_run_options_with_tool_choice_none(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with none tool choice."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(tool_choice="none")

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "none"


async def test_create_run_options_with_tools(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with tools."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    @ai_function
    def get_weather(location: str) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(tools=[get_weather])

    run_options = chat_client._create_run_options(messages, chat_options)

    assert "tools" in run_options
    assert len(run_options["tools"]) == 1


async def test_create_run_options_with_stop_sequences(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with stop sequences."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(stop=["STOP", "END"])

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["stop_sequences"] == ["STOP", "END"]


async def test_create_run_options_with_top_p(mock_anthropic_client: MagicMock) -> None:
    """Test _create_run_options with top_p."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    messages = [ChatMessage(role=Role.USER, text="Hello")]
    chat_options = ChatOptions(top_p=0.9)

    run_options = chat_client._create_run_options(messages, chat_options)

    assert run_options["top_p"] == 0.9


# Response Processing Tests


def test_process_message_basic(mock_anthropic_client: MagicMock) -> None:
    """Test _process_message with basic text response."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    mock_message = MagicMock(spec=BetaMessage)
    mock_message.id = "msg_123"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.content = [BetaTextBlock(type="text", text="Hello there!")]
    mock_message.usage = BetaUsage(input_tokens=10, output_tokens=5)
    mock_message.stop_reason = "end_turn"

    response = chat_client._process_message(mock_message)

    assert response.response_id == "msg_123"
    assert response.model_id == "claude-3-5-sonnet-20241022"
    assert len(response.messages) == 1
    assert response.messages[0].role == Role.ASSISTANT
    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], TextContent)
    assert response.messages[0].contents[0].text == "Hello there!"
    assert response.finish_reason == FinishReason.STOP
    assert response.usage_details is not None
    assert response.usage_details.input_token_count == 10
    assert response.usage_details.output_token_count == 5


def test_process_message_with_tool_use(mock_anthropic_client: MagicMock) -> None:
    """Test _process_message with tool use."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    mock_message = MagicMock(spec=BetaMessage)
    mock_message.id = "msg_123"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.content = [
        BetaToolUseBlock(
            type="tool_use",
            id="call_123",
            name="get_weather",
            input={"location": "San Francisco"},
        )
    ]
    mock_message.usage = BetaUsage(input_tokens=10, output_tokens=5)
    mock_message.stop_reason = "tool_use"

    response = chat_client._process_message(mock_message)

    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert response.messages[0].contents[0].call_id == "call_123"
    assert response.messages[0].contents[0].name == "get_weather"
    assert response.finish_reason == FinishReason.TOOL_CALLS


def test_parse_message_usage_basic(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_message_usage with basic usage."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    usage = BetaUsage(input_tokens=10, output_tokens=5)
    result = chat_client._parse_message_usage(usage)

    assert result is not None
    assert result.input_token_count == 10
    assert result.output_token_count == 5


def test_parse_message_usage_none(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_message_usage with None usage."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    result = chat_client._parse_message_usage(None)

    assert result is None


def test_parse_message_contents_text(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_message_contents with text content."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    content = [BetaTextBlock(type="text", text="Hello!")]
    result = chat_client._parse_message_contents(content)

    assert len(result) == 1
    assert isinstance(result[0], TextContent)
    assert result[0].text == "Hello!"


def test_parse_message_contents_tool_use(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_message_contents with tool use."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    content = [
        BetaToolUseBlock(
            type="tool_use",
            id="call_123",
            name="get_weather",
            input={"location": "SF"},
        )
    ]
    result = chat_client._parse_message_contents(content)

    assert len(result) == 1
    assert isinstance(result[0], FunctionCallContent)
    assert result[0].call_id == "call_123"
    assert result[0].name == "get_weather"


# Stream Processing Tests


def test_process_stream_event_simple(mock_anthropic_client: MagicMock) -> None:
    """Test _process_stream_event with simple mock event."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    # Test with a basic mock event - the actual implementation will handle real events
    mock_event = MagicMock()
    mock_event.type = "message_stop"

    result = chat_client._process_stream_event(mock_event)

    # message_stop events return None
    assert result is None


async def test_inner_get_response(mock_anthropic_client: MagicMock) -> None:
    """Test _inner_get_response method."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    # Create a mock message response
    mock_message = MagicMock(spec=BetaMessage)
    mock_message.id = "msg_test"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.content = [BetaTextBlock(type="text", text="Hello!")]
    mock_message.usage = BetaUsage(input_tokens=5, output_tokens=3)
    mock_message.stop_reason = "end_turn"

    mock_anthropic_client.beta.messages.create.return_value = mock_message

    messages = [ChatMessage(role=Role.USER, text="Hi")]
    chat_options = ChatOptions(max_tokens=10)

    response = await chat_client._inner_get_response(  # type: ignore[attr-defined]
        messages=messages, chat_options=chat_options
    )

    assert response is not None
    assert response.response_id == "msg_test"
    assert len(response.messages) == 1


async def test_inner_get_streaming_response(mock_anthropic_client: MagicMock) -> None:
    """Test _inner_get_streaming_response method."""
    chat_client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock streaming response
    async def mock_stream():
        mock_event = MagicMock()
        mock_event.type = "message_stop"
        yield mock_event

    mock_anthropic_client.beta.messages.create.return_value = mock_stream()

    messages = [ChatMessage(role=Role.USER, text="Hi")]
    chat_options = ChatOptions(max_tokens=10)

    chunks: list[ChatResponseUpdate] = []
    async for chunk in chat_client._inner_get_streaming_response(  # type: ignore[attr-defined]
        messages=messages, chat_options=chat_options
    ):
        if chunk:
            chunks.append(chunk)

    # We should get at least some response (even if empty due to message_stop)
    assert isinstance(chunks, list)


# Integration Tests


@ai_function
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a location."""
    return f"The weather in {location} is sunny and 72°F"


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_basic_chat() -> None:
    """Integration test for basic chat completion."""
    client = AnthropicClient()

    messages = [ChatMessage(role=Role.USER, text="Say 'Hello, World!' and nothing else.")]

    response = await client.get_response(messages=messages, chat_options=ChatOptions(max_tokens=50))

    assert response is not None
    assert len(response.messages) > 0
    assert response.messages[0].role == Role.ASSISTANT
    assert len(response.messages[0].text) > 0
    assert response.usage_details is not None


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_streaming_chat() -> None:
    """Integration test for streaming chat completion."""
    client = AnthropicClient()

    messages = [ChatMessage(role=Role.USER, text="Count from 1 to 5.")]

    chunks = []
    async for chunk in client.get_streaming_response(messages=messages, chat_options=ChatOptions(max_tokens=50)):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert any(chunk.contents for chunk in chunks)


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_function_calling() -> None:
    """Integration test for function calling."""
    client = AnthropicClient()

    messages = [ChatMessage(role=Role.USER, text="What's the weather in San Francisco?")]
    tools = [get_weather]

    response = await client.get_response(
        messages=messages,
        chat_options=ChatOptions(tools=tools, max_tokens=100),
    )

    assert response is not None
    # Should contain function call
    has_function_call = any(
        isinstance(content, FunctionCallContent) for msg in response.messages for content in msg.contents
    )
    assert has_function_call


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_with_system_message() -> None:
    """Integration test with system message."""
    client = AnthropicClient()

    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a pirate. Always respond like a pirate."),
        ChatMessage(role=Role.USER, text="Hello!"),
    ]

    response = await client.get_response(messages=messages, chat_options=ChatOptions(max_tokens=50))

    assert response is not None
    assert len(response.messages) > 0


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_temperature_control() -> None:
    """Integration test with temperature control."""
    client = AnthropicClient()

    messages = [ChatMessage(role=Role.USER, text="Say hello.")]

    response = await client.get_response(
        messages=messages,
        chat_options=ChatOptions(max_tokens=20, temperature=0.0),
    )

    assert response is not None
    assert response.messages[0].text is not None


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_ordering() -> None:
    """Integration test with ordering."""
    client = AnthropicClient()

    messages = [
        ChatMessage(role=Role.USER, text="Say hello."),
        ChatMessage(role=Role.USER, text="Then say goodbye."),
        ChatMessage(role=Role.ASSISTANT, text="Thank you for chatting!"),
        ChatMessage(role=Role.ASSISTANT, text="Let me know if I can help."),
        ChatMessage(role=Role.USER, text="Just testing things."),
    ]

    response = await client.get_response(messages=messages)

    assert response is not None
    assert response.messages[0].text is not None


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_images() -> None:
    """Integration test with images."""
    client = AnthropicClient()

    # get a image from the assets folder
    image_path = Path(__file__).parent / "assets" / "sample_image.jpg"
    with open(image_path, "rb") as img_file:  # noqa [ASYNC230]
        image_bytes = img_file.read()

    messages = [
        ChatMessage(
            role=Role.USER,
            contents=[
                TextContent(text="Describe this image"),
                DataContent(media_type="image/jpeg", data=image_bytes),
            ],
        ),
    ]

    response = await client.get_response(messages=messages)

    assert response is not None
    assert response.messages[0].text is not None
    assert "house" in response.messages[0].text.lower()
