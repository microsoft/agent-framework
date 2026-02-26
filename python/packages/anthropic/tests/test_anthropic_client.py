# Copyright (c) Microsoft. All rights reserved.
import os
from pathlib import Path
from typing import Annotated, Any
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
from anthropic.types.beta import (
    BetaMessage,
    BetaTextBlock,
    BetaToolUseBlock,
    BetaUsage,
)
from pydantic import BaseModel, Field

from agent_framework_anthropic import AnthropicClient
from agent_framework_anthropic._chat_client import AnthropicSettings

# Test constants
VALID_PNG_BASE64 = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

skip_if_anthropic_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("ANTHROPIC_API_KEY", "") in ("", "test-api-key-12345"),
    reason="No real ANTHROPIC_API_KEY provided; skipping integration tests.",
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
    settings = load_settings(AnthropicSettings, env_prefix="ANTHROPIC_")

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
    )

    assert settings["api_key"] is not None
    assert settings["api_key"].get_secret_value() == "custom-api-key"
    assert settings["chat_model_id"] == "claude-3-opus-20240229"


@pytest.mark.parametrize("exclude_list", [["ANTHROPIC_API_KEY"]], indirect=True)
def test_anthropic_settings_missing_api_key(anthropic_unit_test_env: dict[str, str]) -> None:
    """Test AnthropicSettings when API key is missing."""
    settings = load_settings(AnthropicSettings, env_prefix="ANTHROPIC_")
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
    )

    assert client.anthropic_client is not None
    assert client.model_id == anthropic_unit_test_env["ANTHROPIC_CHAT_MODEL_ID"]


def test_anthropic_client_init_missing_api_key() -> None:
    """Test AnthropicClient initialization when API key is missing."""
    with patch("agent_framework_anthropic._chat_client.load_settings") as mock_load:
        mock_load.return_value = {"api_key": None, "chat_model_id": "claude-3-5-sonnet-20241022"}

        with pytest.raises(ValueError, match="Anthropic API key is required"):
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
    assert "signature" not in result["content"][0]


def test_prepare_message_for_anthropic_text_reasoning_with_signature(mock_anthropic_client: MagicMock) -> None:
    """Test converting text reasoning message with signature to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="assistant",
        contents=[Content.from_text_reasoning(text="Let me think about this...", protected_data="sig_abc123")],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "thinking"
    assert result["content"][0]["thinking"] == "Let me think about this..."
    assert result["content"][0]["signature"] == "sig_abc123"


def test_prepare_message_for_anthropic_mcp_server_tool_call(mock_anthropic_client: MagicMock) -> None:
    """Test converting MCP server tool call message to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="assistant",
        contents=[
            Content.from_mcp_server_tool_call(
                call_id="mcp_call_123",
                tool_name="search_docs",
                server_name="microsoft-learn",
                arguments={"query": "Azure Functions"},
            )
        ],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "mcp_tool_use"
    assert result["content"][0]["id"] == "mcp_call_123"
    assert result["content"][0]["name"] == "search_docs"
    assert result["content"][0]["server_name"] == "microsoft-learn"
    assert result["content"][0]["input"] == {"query": "Azure Functions"}


def test_prepare_message_for_anthropic_mcp_server_tool_call_no_server_name(mock_anthropic_client: MagicMock) -> None:
    """Test converting MCP server tool call with no server name defaults to empty string."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="assistant",
        contents=[
            Content.from_mcp_server_tool_call(
                call_id="mcp_call_456",
                tool_name="list_files",
                arguments=None,
            )
        ],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "assistant"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "mcp_tool_use"
    assert result["content"][0]["id"] == "mcp_call_456"
    assert result["content"][0]["name"] == "list_files"
    assert result["content"][0]["server_name"] == ""
    assert result["content"][0]["input"] == {}


def test_prepare_message_for_anthropic_mcp_server_tool_result(mock_anthropic_client: MagicMock) -> None:
    """Test converting MCP server tool result message to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="tool",
        contents=[
            Content.from_mcp_server_tool_result(
                call_id="mcp_call_123",
                output="Found 3 results for Azure Functions.",
            )
        ],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "mcp_tool_result"
    assert result["content"][0]["tool_use_id"] == "mcp_call_123"
    assert result["content"][0]["content"] == "Found 3 results for Azure Functions."


def test_prepare_message_for_anthropic_mcp_server_tool_result_none_output(mock_anthropic_client: MagicMock) -> None:
    """Test converting MCP server tool result with None output defaults to empty string."""
    client = create_test_anthropic_client(mock_anthropic_client)
    message = Message(
        role="tool",
        contents=[
            Content.from_mcp_server_tool_result(
                call_id="mcp_call_789",
                output=None,
            )
        ],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "mcp_tool_result"
    assert result["content"][0]["tool_use_id"] == "mcp_call_789"
    assert result["content"][0]["content"] == ""


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
    assert result["tools"][0]["name"] == "web_search"


def test_prepare_tools_for_anthropic_code_interpreter(mock_anthropic_client: MagicMock) -> None:
    """Test converting code_interpreter dict tool to Anthropic format."""
    client = create_test_anthropic_client(mock_anthropic_client)
    chat_options = ChatOptions(tools=[client.get_code_interpreter_tool()])

    result = client._prepare_tools_for_anthropic(chat_options)

    assert result is not None
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "code_execution_20250825"
    assert result["tools"][0]["name"] == "code_execution"


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
    chat_options = ChatOptions(tool_choice="auto", allow_multiple_tool_calls=False)

    run_options = client._prepare_options(messages, chat_options)

    assert run_options["tool_choice"]["type"] == "auto"
    assert run_options["tool_choice"]["disable_parallel_tool_use"] is True
    assert "allow_multiple_tool_calls" not in run_options


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


async def test_prepare_options_excludes_stream_option(mock_anthropic_client: MagicMock) -> None:
    """Test _prepare_options excludes stream when stream is provided in options."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", text="Hello")]
    chat_options: dict[str, Any] = {"stream": True, "max_tokens": 100}

    run_options = client._prepare_options(messages, chat_options)

    assert "stream" not in run_options


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


async def test_inner_get_response_ignores_options_stream_non_streaming(mock_anthropic_client: MagicMock) -> None:
    """Test stream option in options does not conflict in non-streaming mode."""
    client = create_test_anthropic_client(mock_anthropic_client)

    mock_message = MagicMock(spec=BetaMessage)
    mock_message.id = "msg_test"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.content = [BetaTextBlock(type="text", text="Hello!")]
    mock_message.usage = BetaUsage(input_tokens=5, output_tokens=3)
    mock_message.stop_reason = "end_turn"
    mock_anthropic_client.beta.messages.create.return_value = mock_message

    messages = [Message(role="user", text="Hi")]
    options: dict[str, Any] = {"max_tokens": 10, "stream": True}

    await client._inner_get_response(  # type: ignore[attr-defined]
        messages=messages,
        options=options,
    )

    assert mock_anthropic_client.beta.messages.create.call_count == 1
    assert mock_anthropic_client.beta.messages.create.call_args.kwargs["stream"] is False


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


async def test_inner_get_response_ignores_options_stream_streaming(mock_anthropic_client: MagicMock) -> None:
    """Test stream option in options does not conflict in streaming mode."""
    client = create_test_anthropic_client(mock_anthropic_client)

    async def mock_stream():
        mock_event = MagicMock()
        mock_event.type = "message_stop"
        yield mock_event

    mock_anthropic_client.beta.messages.create.return_value = mock_stream()

    messages = [Message(role="user", text="Hi")]
    options: dict[str, Any] = {"max_tokens": 10, "stream": False}

    async for _ in client._inner_get_response(  # type: ignore[attr-defined]
        messages=messages,
        options=options,
        stream=True,
    ):
        pass

    assert mock_anthropic_client.beta.messages.create.call_count == 1
    assert mock_anthropic_client.beta.messages.create.call_args.kwargs["stream"] is True


# Integration Tests


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a location."""
    return f"The weather in {location} is sunny and 72°F"


@pytest.mark.flaky
@pytest.mark.integration
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
@pytest.mark.integration
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
@pytest.mark.integration
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
@pytest.mark.integration
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
@pytest.mark.integration
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
@pytest.mark.integration
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
@pytest.mark.integration
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
@pytest.mark.integration
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


# Response Format Tests


def test_prepare_response_format_openai_style(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with OpenAI-style json_schema."""
    client = create_test_anthropic_client(mock_anthropic_client)

    response_format = {
        "json_schema": {
            "schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        }
    }

    result = client._prepare_response_format(response_format)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["name"]["type"] == "string"


def test_prepare_response_format_direct_schema(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with direct schema key."""
    client = create_test_anthropic_client(mock_anthropic_client)

    response_format = {
        "schema": {
            "type": "object",
            "properties": {"value": {"type": "number"}},
        }
    }

    result = client._prepare_response_format(response_format)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["value"]["type"] == "number"


def test_prepare_response_format_raw_schema(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with raw schema dict."""
    client = create_test_anthropic_client(mock_anthropic_client)

    response_format = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
    }

    result = client._prepare_response_format(response_format)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert result["schema"]["properties"]["count"]["type"] == "integer"


def test_prepare_response_format_pydantic_model(mock_anthropic_client: MagicMock) -> None:
    """Test response_format with Pydantic BaseModel."""
    client = create_test_anthropic_client(mock_anthropic_client)

    class TestModel(BaseModel):
        name: str
        age: int

    result = client._prepare_response_format(TestModel)

    assert result["type"] == "json_schema"
    assert result["schema"]["additionalProperties"] is False
    assert "properties" in result["schema"]


# Message Preparation Tests


def test_prepare_message_with_image_data(mock_anthropic_client: MagicMock) -> None:
    """Test preparing messages with base64-encoded image data."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create message with image data content
    message = Message(
        role="user",
        contents=[Content.from_data(media_type="image/png", data=VALID_PNG_BASE64)],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["source"]["type"] == "base64"
    assert result["content"][0]["source"]["media_type"] == "image/png"


def test_prepare_message_with_image_uri(mock_anthropic_client: MagicMock) -> None:
    """Test preparing messages with image URI."""
    client = create_test_anthropic_client(mock_anthropic_client)

    message = Message(
        role="user",
        contents=[Content.from_uri(uri="https://example.com/image.jpg", media_type="image/jpeg")],
    )

    result = client._prepare_message_for_anthropic(message)

    assert result["role"] == "user"
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "image"
    assert result["content"][0]["source"]["type"] == "url"
    assert result["content"][0]["source"]["url"] == "https://example.com/image.jpg"


def test_prepare_message_with_unsupported_data_type(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test preparing messages with unsupported data content type."""
    client = create_test_anthropic_client(mock_anthropic_client)

    message = Message(
        role="user",
        contents=[Content.from_data(media_type="application/pdf", data=b"PDF data")],
    )

    result = client._prepare_message_for_anthropic(message)

    # PDF should be ignored
    assert result["role"] == "user"
    assert len(result["content"]) == 0


def test_prepare_message_with_unsupported_uri_type(mock_anthropic_client: MagicMock) -> None:
    """Test preparing messages with unsupported URI content type."""
    client = create_test_anthropic_client(mock_anthropic_client)

    message = Message(
        role="user",
        contents=[Content.from_uri(uri="https://example.com/video.mp4", media_type="video/mp4")],
    )

    result = client._prepare_message_for_anthropic(message)

    # Video should be ignored
    assert result["role"] == "user"
    assert len(result["content"]) == 0


# Content Parsing Tests


def test_parse_contents_mcp_tool_use(mock_anthropic_client: MagicMock) -> None:
    """Test parsing MCP tool use content."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock MCP tool use block
    mock_block = MagicMock()
    mock_block.type = "mcp_tool_use"
    mock_block.id = "call_123"
    mock_block.name = "test_tool"
    mock_block.input = {"arg": "value"}

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "mcp_server_tool_call"


def test_parse_contents_code_execution_tool(mock_anthropic_client: MagicMock) -> None:
    """Test parsing code execution tool use."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock code execution tool use block
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.id = "call_456"
    mock_block.name = "code_execution_tool"
    mock_block.input = "print('hello')"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "code_interpreter_tool_call"


def test_parse_contents_mcp_tool_result_list_content(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test parsing MCP tool result with list content."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_123", "test_tool")

    # Create mock MCP tool result with list content
    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Result text"

    mock_block = MagicMock()
    mock_block.type = "mcp_tool_result"
    mock_block.tool_use_id = "call_123"
    mock_block.content = [mock_text_block]

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "mcp_server_tool_result"


def test_parse_contents_mcp_tool_result_string_content(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test parsing MCP tool result with string content."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_123", "test_tool")

    # Create mock MCP tool result with string content
    mock_block = MagicMock()
    mock_block.type = "mcp_tool_result"
    mock_block.tool_use_id = "call_123"
    mock_block.content = "Simple string result"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "mcp_server_tool_result"


def test_parse_contents_mcp_tool_result_bytes_content(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test parsing MCP tool result with bytes content."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_123", "test_tool")

    # Create mock MCP tool result with bytes content
    mock_block = MagicMock()
    mock_block.type = "mcp_tool_result"
    mock_block.tool_use_id = "call_123"
    mock_block.content = b"Binary data"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "mcp_server_tool_result"


def test_parse_contents_mcp_tool_result_object_content(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test parsing MCP tool result with object content."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_123", "test_tool")

    # Create mock MCP tool result with object content
    mock_content_obj = MagicMock()
    mock_content_obj.type = "text"
    mock_content_obj.text = "Object content"

    mock_block = MagicMock()
    mock_block.type = "mcp_tool_result"
    mock_block.tool_use_id = "call_123"
    mock_block.content = mock_content_obj

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "mcp_server_tool_result"


def test_parse_contents_web_search_tool_result(mock_anthropic_client: MagicMock) -> None:
    """Test parsing web search tool result."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_789", "web_search")

    # Create mock web search tool result
    mock_block = MagicMock()
    mock_block.type = "web_search_tool_result"
    mock_block.tool_use_id = "call_789"
    mock_block.content = "Search results"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


def test_parse_contents_web_fetch_tool_result(mock_anthropic_client: MagicMock) -> None:
    """Test parsing web fetch tool result."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_101", "web_fetch")

    # Create mock web fetch tool result
    mock_block = MagicMock()
    mock_block.type = "web_fetch_tool_result"
    mock_block.tool_use_id = "call_101"
    mock_block.content = "Fetched content"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


# MCP Tool Configuration Tests


def test_get_mcp_tool_with_allowed_tools() -> None:
    """Test get_mcp_tool with allowed_tools parameter."""
    result = AnthropicClient.get_mcp_tool(
        name="Test Server",
        url="https://example.com/mcp",
        allowed_tools=["tool1", "tool2"],
    )

    assert result["type"] == "mcp"
    assert result["server_label"] == "Test_Server"
    assert result["server_url"] == "https://example.com/mcp"
    assert result["allowed_tools"] == ["tool1", "tool2"]


def test_get_mcp_tool_without_allowed_tools() -> None:
    """Test get_mcp_tool without allowed_tools parameter."""
    result = AnthropicClient.get_mcp_tool(name="Test Server", url="https://example.com/mcp")

    assert result["type"] == "mcp"
    assert result["server_label"] == "Test_Server"
    assert result["server_url"] == "https://example.com/mcp"
    assert "allowed_tools" not in result


def test_prepare_tools_mcp_with_allowed_tools(mock_anthropic_client: MagicMock) -> None:
    """Test MCP tool with allowed_tools configuration."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    mcp_tool = {
        "type": "mcp",
        "server_label": "test_server",
        "server_url": "https://example.com/mcp",
        "allowed_tools": ["tool1", "tool2"],
    }

    options = {"tools": [mcp_tool]}

    result = client._prepare_options(messages, options)

    assert "mcp_servers" in result
    assert len(result["mcp_servers"]) == 1
    assert result["mcp_servers"][0]["tool_configuration"]["allowed_tools"] == [
        "tool1",
        "tool2",
    ]


# Tool Choice Mode Tests


def test_tool_choice_auto_with_allow_multiple(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice auto mode with allow_multiple=False."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {
        "tools": [test_func],
        "tool_choice": "auto",
        "allow_multiple_tool_calls": False,
    }

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "auto"
    assert result["tool_choice"]["disable_parallel_tool_use"] is True


def test_tool_choice_required_any(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice required mode without specific function."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {"tools": [test_func], "tool_choice": "required"}

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "any"


def test_tool_choice_required_specific_function(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice required mode with specific function."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {
        "tools": [test_func],
        "tool_choice": {"mode": "required", "required_function_name": "test_func"},
    }

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "tool"
    assert result["tool_choice"]["name"] == "test_func"


def test_tool_choice_none(mock_anthropic_client: MagicMock) -> None:
    """Test tool_choice none mode."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {"tools": [test_func], "tool_choice": "none"}

    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "none"


def test_tool_choice_required_allows_parallel_use(mock_anthropic_client: MagicMock) -> None:
    """Test tool choice required mode with allow_multiple=True."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]

    @tool(approval_mode="never_require")
    def test_func() -> str:
        """Test function."""
        return "test"

    options = {
        "tools": [test_func],
        "tool_choice": "required",
        "allow_multiple_tool_calls": True,
    }

    # This tests line 739: setting disable_parallel_tool_use in required mode
    result = client._prepare_options(messages, options)

    assert result["tool_choice"]["type"] == "any"
    assert result["tool_choice"]["disable_parallel_tool_use"] is False


# Options Preparation Tests


def test_prepare_options_with_instructions(mock_anthropic_client: MagicMock) -> None:
    """Test prepare_options with instructions parameter."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {"instructions": "You are a helpful assistant"}

    result = client._prepare_options(messages, options)

    # Instructions should be prepended as system message
    assert result["model"] == "claude-3-5-sonnet-20241022"
    assert result["max_tokens"] == 1024


def test_prepare_options_missing_model_id(mock_anthropic_client: MagicMock) -> None:
    """Test prepare_options raises error when model_id is missing."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client.model_id = ""  # Set empty model_id

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {}

    try:
        client._prepare_options(messages, options)
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "model_id must be a non-empty string" in str(e)


def test_prepare_options_with_user_metadata(mock_anthropic_client: MagicMock) -> None:
    """Test prepare_options maps user to metadata.user_id."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {"user": "user123"}

    result = client._prepare_options(messages, options)

    assert "user" not in result
    assert result["metadata"]["user_id"] == "user123"


def test_prepare_options_user_metadata_no_override(
    mock_anthropic_client: MagicMock,
) -> None:
    """Test user option doesn't override existing user_id in metadata."""
    client = create_test_anthropic_client(mock_anthropic_client)

    messages = [Message(role="user", contents=[Content.from_text("Hello")])]
    options = {"user": "user123", "metadata": {"user_id": "existing_user"}}

    result = client._prepare_options(messages, options)

    # Existing user_id should be preserved
    assert result["metadata"]["user_id"] == "existing_user"


def test_process_stream_event_message_stop(mock_anthropic_client: MagicMock) -> None:
    """Test processing message_stop event."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # message_stop events don't produce output
    mock_event = MagicMock()
    mock_event.type = "message_stop"

    result = client._process_stream_event(mock_event)

    assert result is None


def test_parse_usage_with_cache_tokens(mock_anthropic_client: MagicMock) -> None:
    """Test parsing usage with cache creation and read tokens."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock usage with cache tokens
    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_usage.cache_creation_input_tokens = 20
    mock_usage.cache_read_input_tokens = 30

    result = client._parse_usage_from_anthropic(mock_usage)

    assert result is not None
    assert result["output_token_count"] == 50
    assert result["input_token_count"] == 100
    assert result["anthropic.cache_creation_input_tokens"] == 20
    assert result["anthropic.cache_read_input_tokens"] == 30


# Code Execution Result Tests


def test_parse_code_execution_result_with_error(mock_anthropic_client: MagicMock) -> None:
    """Test parsing code execution result with error."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_code1", "code_execution_tool")

    # Create mock code execution result with error
    from anthropic.types.beta.beta_code_execution_tool_result_error import (
        BetaCodeExecutionToolResultError,
    )

    mock_block = MagicMock()
    mock_block.type = "code_execution_tool_result"
    mock_block.tool_use_id = "call_code1"
    mock_block.content = BetaCodeExecutionToolResultError(
        type="code_execution_tool_result_error", error_code="execution_time_exceeded"
    )

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "code_interpreter_tool_result"


def test_parse_code_execution_result_with_stdout(mock_anthropic_client: MagicMock) -> None:
    """Test parsing code execution result with stdout."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_code2", "code_execution_tool")

    # Create mock code execution result with stdout
    mock_content = MagicMock()
    mock_content.stdout = "Hello, world!"
    mock_content.stderr = None
    mock_content.content = []

    mock_block = MagicMock()
    mock_block.type = "code_execution_tool_result"
    mock_block.tool_use_id = "call_code2"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "code_interpreter_tool_result"


def test_parse_code_execution_result_with_stderr(mock_anthropic_client: MagicMock) -> None:
    """Test parsing code execution result with stderr."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_code3", "code_execution_tool")

    # Create mock code execution result with stderr
    mock_content = MagicMock()
    mock_content.stdout = None
    mock_content.stderr = "Warning message"
    mock_content.content = []

    mock_block = MagicMock()
    mock_block.type = "code_execution_tool_result"
    mock_block.tool_use_id = "call_code3"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "code_interpreter_tool_result"


def test_parse_code_execution_result_with_files(mock_anthropic_client: MagicMock) -> None:
    """Test parsing code execution result with file outputs."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_code4", "code_execution_tool")

    # Create mock file output
    mock_file = MagicMock()
    mock_file.file_id = "file_123"

    # Create mock code execution result with files
    mock_content = MagicMock()
    mock_content.stdout = None
    mock_content.stderr = None
    mock_content.content = [mock_file]

    mock_block = MagicMock()
    mock_block.type = "code_execution_tool_result"
    mock_block.tool_use_id = "call_code4"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "code_interpreter_tool_result"


# Bash Execution Result Tests


def test_parse_bash_execution_result_with_stdout(mock_anthropic_client: MagicMock) -> None:
    """Test parsing bash execution result with stdout."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_bash2", "bash_code_execution")

    # Create mock bash execution result with stdout
    mock_content = MagicMock()
    mock_content.stdout = "Output text"
    mock_content.stderr = None
    mock_content.content = []

    mock_block = MagicMock()
    mock_block.type = "bash_code_execution_tool_result"
    mock_block.tool_use_id = "call_bash2"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


def test_parse_bash_execution_result_with_stderr(mock_anthropic_client: MagicMock) -> None:
    """Test parsing bash execution result with stderr."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_bash3", "bash_code_execution")

    # Create mock bash execution result with stderr
    mock_content = MagicMock()
    mock_content.stdout = None
    mock_content.stderr = "Error output"
    mock_content.content = []

    mock_block = MagicMock()
    mock_block.type = "bash_code_execution_tool_result"
    mock_block.tool_use_id = "call_bash3"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


# Text Editor Result Tests


def test_parse_text_editor_result_error(mock_anthropic_client: MagicMock) -> None:
    """Test parsing text editor result with error."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_editor1", "text_editor_code_execution")

    # Create mock text editor result with error
    mock_content = MagicMock()
    mock_content.type = "text_editor_code_execution_tool_result_error"
    mock_content.error = "File not found"

    mock_block = MagicMock()
    mock_block.type = "text_editor_code_execution_tool_result"
    mock_block.tool_use_id = "call_editor1"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


def test_parse_text_editor_result_view(mock_anthropic_client: MagicMock) -> None:
    """Test parsing text editor view result."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_editor2", "text_editor_code_execution")

    # Create mock text editor view result
    mock_content = MagicMock()
    mock_content.type = "text_editor_code_execution_view_result"
    mock_content.content = "File content"
    mock_content.start_line = 10
    mock_content.num_lines = 5

    mock_block = MagicMock()
    mock_block.type = "text_editor_code_execution_tool_result"
    mock_block.tool_use_id = "call_editor2"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


def test_parse_text_editor_result_str_replace(mock_anthropic_client: MagicMock) -> None:
    """Test parsing text editor string replace result."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_editor3", "text_editor_code_execution")

    # Create mock text editor str_replace result
    mock_content = MagicMock()
    mock_content.type = "text_editor_code_execution_str_replace_result"
    mock_content.old_start = 5
    mock_content.old_lines = 3
    mock_content.new_start = 5
    mock_content.new_lines = 4
    mock_content.lines = ["line1", "line2", "line3", "line4"]

    mock_block = MagicMock()
    mock_block.type = "text_editor_code_execution_tool_result"
    mock_block.tool_use_id = "call_editor3"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


def test_parse_text_editor_result_file_create(mock_anthropic_client: MagicMock) -> None:
    """Test parsing text editor file create result."""
    client = create_test_anthropic_client(mock_anthropic_client)
    client._last_call_id_name = ("call_editor4", "text_editor_code_execution")

    # Create mock text editor create result
    mock_content = MagicMock()
    mock_content.type = "text_editor_code_execution_create_result"
    mock_content.is_file_update = False

    mock_block = MagicMock()
    mock_block.type = "text_editor_code_execution_tool_result"
    mock_block.tool_use_id = "call_editor4"
    mock_block.content = mock_content

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "function_result"


# Thinking Block Tests


def test_parse_thinking_block(mock_anthropic_client: MagicMock) -> None:
    """Test parsing thinking content block."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock thinking block
    mock_block = MagicMock()
    mock_block.type = "thinking"
    mock_block.thinking = "Let me think about this..."
    mock_block.signature = "sig_abc123"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "text_reasoning"
    assert result[0].protected_data == "sig_abc123"


def test_parse_thinking_delta_block(mock_anthropic_client: MagicMock) -> None:
    """Test parsing thinking delta content block."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock thinking delta block
    mock_block = MagicMock()
    mock_block.type = "thinking_delta"
    mock_block.thinking = "more thinking..."

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "text_reasoning"


def test_parse_signature_delta_block(mock_anthropic_client: MagicMock) -> None:
    """Test parsing signature delta content block."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock signature delta block
    mock_block = MagicMock()
    mock_block.type = "signature_delta"
    mock_block.signature = "sig_xyz789"

    result = client._parse_contents_from_anthropic([mock_block])

    assert len(result) == 1
    assert result[0].type == "text_reasoning"
    assert result[0].text is None
    assert result[0].protected_data == "sig_xyz789"


# Citation Tests


def test_parse_citations_char_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with char_location."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock text block with citations
    mock_citation = MagicMock()
    mock_citation.type = "char_location"
    mock_citation.title = "Source Title"
    mock_citation.cited_text = "Citation snippet"
    mock_citation.start_char_index = 0
    mock_citation.end_char_index = 10
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_page_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with page_location."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock citation with page location
    mock_citation = MagicMock()
    mock_citation.type = "page_location"
    mock_citation.document_title = "Document Title"
    mock_citation.cited_text = "Cited text from page"
    mock_citation.start_page_number = 1
    mock_citation.end_page_number = 3
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with page citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_content_block_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with content_block_location."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock citation with content block location
    mock_citation = MagicMock()
    mock_citation.type = "content_block_location"
    mock_citation.document_title = "Document Title"
    mock_citation.cited_text = "Cited text from content blocks"
    mock_citation.start_block_index = 0
    mock_citation.end_block_index = 2
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with block citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_web_search_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with web_search_result_location."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock citation with web search location
    mock_citation = MagicMock()
    mock_citation.type = "web_search_result_location"
    mock_citation.title = "Search Result"
    mock_citation.cited_text = "Cited text from search"
    mock_citation.url = "https://example.com"
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with web citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0


def test_parse_citations_search_result_location(mock_anthropic_client: MagicMock) -> None:
    """Test parsing citations with search_result_location."""
    client = create_test_anthropic_client(mock_anthropic_client)

    # Create mock citation with search result location
    mock_citation = MagicMock()
    mock_citation.type = "search_result_location"
    mock_citation.title = "Search Result"
    mock_citation.cited_text = "Cited text"
    mock_citation.source = "https://source.com"
    mock_citation.start_block_index = 0
    mock_citation.end_block_index = 1
    mock_citation.file_id = None

    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = "Text with search citation"
    mock_block.citations = [mock_citation]

    result = client._parse_citations_from_anthropic(mock_block)

    assert len(result) > 0
