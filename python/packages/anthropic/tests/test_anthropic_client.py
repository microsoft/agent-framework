# Copyright (c) Microsoft. All rights reserved.
import os
from pathlib import Path
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    ChatOptions,
    ChatResponseUpdate,
    Content,
    Message,
    SupportsChatGetResponse,
    tool,
)
from agent_framework._settings import load_settings
from agent_framework.exceptions import ServiceInitializationError
from anthropic.types.beta import (
    BetaMessage,
    BetaTextBlock,
    BetaToolUseBlock,
    BetaUsage,
)
from pydantic import Field

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
        anthropic_settings = load_settings(
            AnthropicSettings,
            env_prefix="ANTHROPIC_",
            api_key="test-api-key-12345",
            chat_model_id="claude-3-5-sonnet-20241022",
            env_file_path="test.env",
        )

    # Create client instance directly
    client = object.__new__(AnthropicClient)

    # Set attributes directly
    client.anthropic_client = mock_anthropic_client
    client.model_id = model_id or anthropic_settings["chat_model_id"]
    client._last_call_id_name = None
    client.additional_properties = {}
    client.middleware = None
    client.additional_beta_flags = []

    return client


# Settings Tests


def test_anthropic_settings_init(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicSettings initialization."""
    settings = load_settings(AnthropicSettings, env_prefix="ANTHROPIC_", env_file_path="test.env")

    assert settings["api_key"] is not None
    assert settings["api_key"].get_secret_value() == anthropic_unit_test_env["ANTHROPIC_API_KEY"]
    assert settings["chat_model_id"] == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


def test_anthropic_settings_init_with_explicit_values() -> None:
    """Test AnthropicSettings initialization with explicit values."""
    settings = load_settings(
        AnthropicSettings,
        env_prefix="ANTHROPIC_",
        api_key="custom-api-key",
        chat_model_id="claude-3-opus-20240229",
        env_file_path="test.env",
    )

    assert settings["api_key"] is not None
    assert settings["api_key"].get_secret_value() == "custom-api-key"
    assert settings["chat_model_id"] == "claude-3-opus-20240229"


@pytest.mark.parametrize("exclude_list", [["ANTHROPIC_API_KEY"]], indirect=True)
def test_anthropic_settings_missing_api_key(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicSettings when API key is missing."""
    settings = load_settings(AnthropicSettings, env_prefix="ANTHROPIC_", env_file_path="test.env")
    assert settings["api_key"] is None
    assert settings["chat_model_id"] == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


# Client Initialization Tests


def test_anthropic_client_init_with_client(mock_anthropic_client: MagicMock) -> None:
    """Test AnthropicClient initialization with existing anthropic_client."""
    client = create_test_anthropic_client(mock_anthropic_client, model_id="claude-3-5-sonnet-20241022")

    assert client.anthropic_client is mock_anthropic_client
    assert client.model_id == "claude-3-5-sonnet-20241022"
    assert isinstance(client, SupportsChatGetResponse)


def test_anthropic_client_init_auto_create_client(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicClient initialization with auto-created anthropic_client."""
    client = AnthropicClient(
        api_key=anthropic_unit_test_env["ANTHROPIC_API_KEY"],
        model_id=anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"],
        env_file_path="test.env",
    )

    assert client.anthropic_client is not None
    assert client.model_id == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


def test_anthropic_client_init_missing_api_key() -> None:
    """Test AnthropicClient initialization when API key is missing."""
    with patch("agent_framework_anthropic._chat_client.load_settings") as mock_load:
        mock_load.return_value = {"api_key": None, "chat_model_id": "claude-3-5-sonnet-20241022"}

        with pytest.raises(ServiceInitializationError, match="Anthropic API key is required"):
            AnthropicClient()


def test_anthropic_client_service_url(mock_anthropic_client: MagicMock) -> None:
    """Test service_url method."""
    client = create_test_anthropic_client(mock_anthropic_client)
    assert client.service_url() == "https://api.anthropic.com"


# Message Conversion Tests


def test_prepare_message_for_anthropic_text(mock_anthropic_client: MagicMock) -> None:
    """Test converting text message to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(role="user", text="Hello, world!")

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Hello, world!"


def test_prepare_message_for_anthropic_function_call(mock_anthropic_client: MagicMock) -> None:
    """Test converting function call message to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="assistant",
        contents=[
            Content.from_function_call(
                call_id="call_123",
                name="get_weather",
                arguments={"location": "San Francisco"},
            )
        ],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "tool_use"
    assert result["content"][0]["id"] == "call_123"
    assert result["content"][0]["name"] == "get_weather"
    assert result["content"][0]["input"] == {"location": "San Francisco"}


def test_prepare_message_for_anthropic_function_result(mock_anthropic_client: MagicMock) -> None:
    """Test converting function result message to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="tool",
        contents=[
            Content.from_function_result(
                call_id="call_123",
                result="Sunny, 72°F",
            )
        ],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "tool_result"
    assert result["content"][0]["tool_use_id"] == "call_123"
    # The degree symbol might be escaped differently depending on JSON encoder
    assert "Sunny" in result["content"][0]["content"]
    assert "72" in result["content"][0]["content"]
    assert result["content"][0]["is_error"] is False


def test_prepare_message_for_anthropic_text_reasoning(mock_anthropic_client: MagicMock) -> None:
    """Test converting text reasoning message to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="assistant",
        contents=[Content.from_text_reasoning(text="Let me think about this...")],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "thinking"
    assert result["content"][0]["thinking"] == "Let me think about this..."


def test_prepare_messages_for_anthropic_with_system(mock_anthropic_client: MagicMock) -> None:
    """Test converting messages list with system message."""
    client = create_test_anthropic_client(mock_anthropic_client)
    messages = [
        Message(role="system", text="You are a helpful assistant."),
        Message(role="user", text="Hello!"),
    ]

    result = client._prepare_messages_for_anthropic(messages)

    # System message should be skipped
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"][0]["text"] == "Hello!"


def test_prepare_messages_for_anthropic_without_system(mock_anthropic_client: MagicMock) -> None:
    """Test converting messages list without system message."""
    client = create_test_anthropic_client(mock_anthropic_client)
    messages = [
        Message(role="user", text="Hello!"),
        Message(role="assistant", text="Hi there!"),
    ]

    result = client._prepare_messages_for_anthropic(messages)

    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"


# Tool Conversion Tests


def test_prepare_tools_for_anthropic_tool(mock_anthropic_client: MagicMock) -> None:
    """Test converting FunctionTool to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)

    @tool(approval_mode="never_require")
    def get_weather(location: Annotated[str, Field(description="Location to get weather for")]) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    chat_options = ChatOptions(tools=[get_weather])
    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "custom"
    assert result["tools"][0]["name"] == "get_weather"
    assert "Get weather for a location" in result["tools"][0]["description"]


def test_prepare_tools_for_anthropic_web_search(mock_anthropic_client: MagicMock) -> None:
    """Test converting web_search dict tool to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    chat_options = ChatOptions(tools=[client.get_web_search_tool()])

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "web_search_20250305"


def test_prepare_tools_for_anthropic_code_interpreter(mock_anthropic_client: MagicMock) -> None:
    """Test converting code_interpreter dict tool to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    chat_options = ChatOptions(tools=[client.get_code_interpreter_tool()])

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "code_execution_20250825"


def test_prepare_tools_for_anthropic_mcp_tool(mock_anthropic_client: MagicMock) -> None:
    """Test converting MCP dict tool to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    chat_options = ChatOptions(tools=[client.get_mcp_tool(name="test-mcp", url="https://example.com/mcp")])

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "mcp_servers" in result
    assert len(result["mcp_servers"]) == 1
    assert result["mcp_servers"][0]["type"] == "url"
    assert result["mcp_servers"][0]["name"] == "test-mcp"
    assert result["mcp_servers"][0]["url"] == "https://example.com/mcp"


def test_prepare_tools_for_anthropic_mcp_with_auth(mock_anthropic_client: MagicMock) -> None:
    """Test converting MCP dict tool with authorization token."""
    client = create_test_anthropic_client(mock_anthropic_client)
    # Use the static method with authorization_token
    mcp_tool = client.get_mcp_tool(
        name="test-mcp",
        url="https://example.com/mcp",
        authorization_token="Bearer token123",
    )
    chat_options = ChatOptions(tools=[mcp_tool])

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "mcp_servers" in result
    # The authorization_token should be passed through
    assert "authorization_token" in result["mcp_servers"][0]
    assert result["mcp_servers"][0]["authorization_token"] == "Bearer token123"


def test_prepare_tools_for_anthropic_dict_tool(mock_anthropic_client: MagicMock) -> None:
    """Test converting dict tool to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    chat_options = ChatOptions(tools=[{"type": "custom", "name": "custom_tool", "description": "A custom tool"}])

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["name"] == "custom_tool"


def test_prepare_tools_for_anthropic_none(mock_anthropic_client: MagicMock) -> None:
    """Test converting None tools."""
    client = create_test_anthropic_client(mock_anthropic_client)
    chat_options = ChatOptions()

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is None


# Run Options Tests


async def test_prepare_options_basic(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with basic ChatOptions."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options = ChatOptions(max_tokens=100, temperature=0.7)

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["model"] == client.model_id
    assert run_options["max_tokens"] == 100
    assert run_options["temperature"] == 0.7
    assert "messages" in run_options


async def test_prepare_options_with_system_message(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with system message."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [
        Message(role="system", text="You are helpful."),
        Message(role="user", text="Hello"),
    ]
    chat_options = ChatOptions()

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["system"] == "You are helpful."
    assert len(run_options["messages"]) == 1  # System message not in messages list


async def test_prepare_options_with_tool_choice_auto(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with auto tool choice."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options = ChatOptions(tool_choice="auto")

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "auto"


async def test_prepare_options_with_tool_choice_required(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with required tool choice."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    # For required with specific function, need to pass as dict
    chat_options = ChatOptions(tool_choice={"mode": "required", "required_function_name": "get_weather"})

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "tool"
    assert run_options["tool_choice"]["name"] == "get_weather"


async def test_prepare_options_with_tool_choice_none(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with none tool choice."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options = ChatOptions(tool_choice="none")

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "none"


async def test_prepare_options_with_tools(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with tools."""
    client = create_test_anthropic_client(mock_anthropic_client)

    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    messages = [Message(role="user", text="Hello")]
    chat_options = ChatOptions(tools=[get_weather])

    run_options = client._prepare_options(messages, chat_options)

    assert "tools" in run_options
    assert len(run_options["tools"]) == 1


async def test_prepare_options_with_stop_sequences(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with stop sequences."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options = ChatOptions(stop=["STOP", "END"])

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["stop_sequences"] == ["STOP", "END"]


async def test_prepare_options_with_top_p(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options with top_p."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options = ChatOptions(top_p=0.9)

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["top_p"] == 0.9


async def test_prepare_options_filters_internal_kwargs(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options filters internal framework kwargs.

    Internal kwargs like _function_middleware_pipeline, thread, and middleware
    should be filtered out before being passed to the Anthropic API.
    """
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options: ChatOptions = {}

    # Simulate internal kwargs that get passed through the middleware pipeline
    internal_kwargs = {
        "_function_middleware_pipeline": object(),
        "_chat_middleware_pipeline": object(),
        "_any_underscore_prefixed": object(),
        "thread": object(),
        "middleware": [object()],
    }

    run_options = client._prepare_options(messages, chat_options, **internal_kwargs)

    # Internal kwargs should be filtered out
    assert "_function_middleware_pipeline" not in run_options
    assert "_chat_middleware_pipeline" not in run_options
    assert "_any_underscore_prefixed" not in run_options
    assert "thread" not in run_options
    assert "middleware" not in run_options


# Response Processing Tests


def test_process_message_basic(mock_anthropic_client: MagicMock) -> None:
    """Test _process_message with basic text response."""
    client = create_test_anthropic_client(mock_anthropic_client)

    mock_message = MagicMock(spec=BetaMessage)
    mock_message.id = "msg_123"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.content = [BetaTextBlock(type="text", text="Hello there!")]
    mock_message.usage = BetaUsage(input_tokens=10, output_tokens=5)
    mock_message.stop_reason = "end_turn"

    response = client._process_message(mock_message, {})

    assert response.response_id == "msg_123"
    assert response.model_id == "claude-3-5-sonnet-20241022"
    assert len(response.messages) == 1
    assert response.messages[0].role == "assistant"
    assert len(response.messages[0].contents) == 1
    assert response.messages[0].contents[0].type == "text"
    assert response.messages[0].contents[0].text == "Hello there!"
    assert response.finish_reason == "stop"
    assert response.usage_details is not None
    assert response.usage_details["input_token_count"] == 10
    assert response.usage_details["output_token_count"] == 5


def test_process_message_with_tool_use(mock_anthropic_client: MagicMock) -> None:
    """Test _process_message with tool use."""
    client = create_test_anthropic_client(mock_anthropic_client)

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

    response = client._process_message(mock_message, {})

    assert len(response.messages[0].contents) == 1
    assert response.messages[0].contents[0].type == "function_call"
    assert response.messages[0].contents[0].call_id == "call_123"
    assert response.messages[0].contents[0].name == "get_weather"
    assert response.finish_reason == "tool_calls"


def test_parse_usage_from_anthropic_basic(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_usage_from_anthropic with basic usage."""
    client = create_test_anthropic_client(mock_anthropic_client)

    usage = BetaUsage(input_tokens=10, output_tokens=5)
    result = client._parse_usage_from_anthropic(usage)

    assert result is not None
    assert result["input_token_count"] == 10
    assert result["output_token_count"] == 5


def test_parse_usage_from_anthropic_none(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_usage_from_anthropic with None usage."""
    client = create_test_anthropic_client(mock_anthropic_client)

    result = client._parse_usage_from_anthropic(None)

    assert result is None


def test_parse_contents_from_anthropic_text(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_contents_from_anthropic with text content."""
    client = create_test_anthropic_client(mock_anthropic_client)

    content = [BetaTextBlock(type="text", text="Hello!")]
    result = client._parse_contents_from_anthropic(content)

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "Hello!"


def test_parse_contents_from_anthropic_tool_use(mock_anthropic_client: MagicMock) -> None:
    """Test _parse_contents_from_anthropic with tool use."""
    client = create_test_anthropic_client(mock_anthropic_client)

    content = [
        BetaToolUseBlock(
            type="tool_use",
            id="call_123",
            name="get_weather",
            input={"location": "SF"},
        )
    ]
    result = client._parse_contents_from_anthropic(content)

    assert len(result) == 1
    assert result[0].type == "function_call"
    assert result[0].call_id == "call_123"
    assert result[0].name == "get_weather"


def test_parse_contents_from_anthropic_input_json_delta_no_duplicate_name(mock_anthropic_client: MagicMock) -> None:
    """Test that input_json_delta events have empty name to prevent duplicate ToolCallStartEvents.

    When streaming tool calls, the initial tool_use event provides the name,
    and subsequent input_json_delta events should have name="" to prevent
    ag-ui from emitting duplicate ToolCallStartEvents.
    """
    client = create_test_anthropic_client(mock_anthropic_client)

    # First, simulate a tool_use event that sets _last_call_id_name
    tool_use_content = MagicMock()
    tool_use_content.type = "tool_use"
    tool_use_content.id = "call_123"
    tool_use_content.name = "get_weather"
    tool_use_content.input = {}

    result = client._parse_contents_from_anthropic([tool_use_content])
    assert len(result) == 1
    assert result[0].type == "function_call"
    assert result[0].call_id == "call_123"
    assert result[0].name == "get_weather"  # Initial event has name

    # Now simulate input_json_delta events (argument streaming)
    delta_content_1 = MagicMock()
    delta_content_1.type = "input_json_delta"
    delta_content_1.partial_json = '{"location":'

    result = client._parse_contents_from_anthropic([delta_content_1])
    assert len(result) == 1
    assert result[0].type == "function_call"
    assert result[0].call_id == "call_123"
    assert result[0].name == ""  # Delta events should have empty name
    assert result[0].arguments == '{"location":'

    # Another delta
    delta_content_2 = MagicMock()
    delta_content_2.type = "input_json_delta"
    delta_content_2.partial_json = '"San Francisco"}'

    result = client._parse_contents_from_anthropic([delta_content_2])
    assert len(result) == 1
    assert result[0].type == "function_call"
    assert result[0].call_id == "call_123"
    assert result[0].name == ""  # Still empty name for subsequent deltas
    assert result[0].arguments == '"San Francisco"}'


# Stream Processing Tests


def test_process_stream_event_simple(mock_anthropic_client: MagicMock) -> None:
    """Test _process_stream_event with simple mock event."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Test with a basic mock event - the actual implementation will handle real events
    mock_event = MagicMock()
    mock_event.type = "message_stop"

    result = client._process_stream_event(mock_event)

    # message_stop events return None
    assert result is None


async def test_inner_get_response(mock_anthropic_client: MagicMock) -> None:
    """Test _inner_get_response method."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create a mock message response
    mock_message = MagicMock(spec=BetaMessage)
    mock_message.id = "msg_test"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.content = [BetaTextBlock(type="text", text="Hello!")]
    mock_message.usage = BetaUsage(input_tokens=5, output_tokens=3)
    mock_message.stop_reason = "end_turn"

    mock_anthropic_client.beta.messages.create.return_value = mock_message

    messages = [Message(role="user", text="Hi")]
    chat_options = ChatOptions(max_tokens=10)

    response = await client._inner_get_response(  # type: ignore[attr-defined]
        messages=messages, options=chat_options
    )

    assert response is not None
    assert response.response_id == "msg_test"
    assert len(response.messages) == 1


async def test_inner_get_response_streaming(mock_anthropic_client: MagicMock) -> None:
    """Test _inner_get_response method with streaming."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock streaming response
    async def mock_stream():
        mock_event = MagicMock()
        mock_event.type = "message_stop"
        yield mock_event

    mock_anthropic_client.beta.messages.create.return_value = mock_stream()

    messages = [Message(role="user", text="Hi")]
    chat_options = ChatOptions(max_tokens=10)

    chunks: list[ChatResponseUpdate] = []
    async for chunk in client._inner_get_response(  # type: ignore[attr-defined]
        messages=messages, options=chat_options, stream=True
    ):
        if chunk:
            chunks.append(chunk)

    # We should get at least some response (even if empty due to message_stop)
    assert isinstance(chunks, list)


# Integration Tests


@tool(approval_mode="never_require")
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

    messages = [Message(role="user", text="Say 'Hello, World!' and nothing else.")]

    response = await client.get_response(messages=messages, options={"max_tokens": 50})

    assert response is not None
    assert len(response.messages) > 0
    assert response.messages[0].role == "assistant"
    assert len(response.messages[0].text) > 0
    assert response.usage_details is not None


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_streaming_chat() -> None:
    """Integration test for streaming chat completion."""
    client = AnthropicClient()

    messages = [Message(role="user", text="Count from 1 to 5.")]

    chunks = []
    async for chunk in client.get_response(messages=messages, stream=True, options={"max_tokens": 50}):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert any(chunk.contents for chunk in chunks)


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_function_calling() -> None:
    """Integration test for function calling."""
    client = AnthropicClient()

    messages = [Message(role="user", text="What's the weather in San Francisco?")]
    tools = [get_weather]

    response = await client.get_response(
        messages=messages,
        options={"tools": tools, "max_tokens": 100},
    )

    assert response is not None
    # Should contain function call
    has_function_call = any(content.type == "function_call" for msg in response.messages for content in msg.contents)
    assert has_function_call


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_hosted_tools() -> None:
    """Integration test for hosted tools."""
    client = AnthropicClient()

    messages = [Message(role="user", text="What tools do you have available?")]
    tools = [
        AnthropicClient.get_web_search_tool(),
        AnthropicClient.get_code_interpreter_tool(),
        AnthropicClient.get_mcp_tool(
            name="example-mcp",
            url="https://learn.microsoft.com/api/mcp",
        ),
    ]

    response = await client.get_response(
        messages=messages,
        options={"tools": tools, "max_tokens": 100},
    )

    assert response is not None
    assert response.text is not None


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_with_system_message() -> None:
    """Integration test with system message."""
    client = AnthropicClient()

    messages = [
        Message(role="system", text="You are a pirate. Always respond like a pirate."),
        Message(role="user", text="Hello!"),
    ]

    response = await client.get_response(messages=messages, options={"max_tokens": 50})

    assert response is not None
    assert len(response.messages) > 0


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_temperature_control() -> None:
    """Integration test with temperature control."""
    client = AnthropicClient()

    messages = [Message(role="user", text="Say hello.")]

    response = await client.get_response(
        messages=messages,
        options={"max_tokens": 20, "temperature": 0.0},
    )

    assert response is not None
    assert response.messages[0].text is not None


@pytest.mark.flaky
@skip_if_anthropic_integration_tests_disabled
async def test_anthropic_client_integration_ordering() -> None:
    """Integration test with ordering."""
    client = AnthropicClient()

    messages = [
        Message(role="user", text="Say hello."),
        Message(role="user", text="Then say goodbye."),
        Message(role="assistant", text="Thank you for chatting!"),
        Message(role="assistant", text="Let me know if I can help."),
        Message(role="user", text="Just testing things."),
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
        Message(
            role="user",
            contents=[
                Content.from_text(text="Describe this image"),
                Content.from_data(media_type="image/jpeg", data=image_bytes),
            ],
        ),
    ]

    response = await client.get_response(messages=messages)

    assert response is not None
    assert response.messages[0].text is not None
    assert "house" in response.messages[0].text.lower()
