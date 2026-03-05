# Copyright (c) Microsoft. All rights reserved.
import base64
import os
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch

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
from agent_framework._tools import normalize_function_invocation_configuration
from google.genai import types
from pydantic import Field

from agent_framework_google import GoogleAIChatClient
from agent_framework_google._chat_client import GoogleAISettings

# Test constants
VALID_PNG_BASE64 = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

skip_if_google_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("GOOGLE_AI_API_KEY", "") in ("", "test-api-key-12345"),
    reason="No real GOOGLE_AI_API_KEY provided; skipping integration tests.",
)


def create_test_google_client(
    mock_google_client: MagicMock,
    model_id: str | None = None,
    google_settings: GoogleAISettings | None = None,
) -> GoogleAIChatClient:
    """Helper function to create GoogleAIChatClient instances for testing, bypassing normal validation."""
    if google_settings is None:
        google_settings = load_settings(
            GoogleAISettings,
            env_prefix="GOOGLE_AI_",
            api_key="test-api-key-12345",
            chat_model_id="gemini-2.5-flash",
        )

    # Create client instance directly
    client = object.__new__(GoogleAIChatClient)

    # Set attributes directly
    client.google_client = mock_google_client
    client.model_id = model_id or google_settings["chat_model_id"]
    client._last_call_id_name = None
    client._function_name_map = {}
    client.additional_properties = {}
    client.middleware = None
    client.chat_middleware = []
    client.function_middleware = []
    client.function_invocation_configuration = normalize_function_invocation_configuration(None)

    return client


# region Settings Tests


def test_google_ai_settings_init(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings initialization."""
    settings = load_settings(GoogleAISettings, env_prefix="GOOGLE_AI_")

    assert settings["api_key"] is not None
    assert settings["api_key"].get_secret_value() == google_ai_unit_test_env["GOOGLE_AI_API_KEY"]
    assert settings["chat_model_id"] == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


def test_google_ai_settings_init_with_explicit_values() -> None:
    """Test GoogleAISettings initialization with explicit values."""
    settings = load_settings(
        GoogleAISettings,
        env_prefix="GOOGLE_AI_",
        api_key="custom-api-key",
        chat_model_id="gemini-2.5-flash",
    )

    assert settings["api_key"] is not None
    assert settings["api_key"].get_secret_value() == "custom-api-key"
    assert settings["chat_model_id"] == "gemini-2.5-flash"


@pytest.mark.parametrize("exclude_list", [["GOOGLE_AI_API_KEY"]], indirect=True)
def test_google_ai_settings_missing_api_key(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings when API key is missing."""
    settings = load_settings(GoogleAISettings, env_prefix="GOOGLE_AI_")
    assert settings["api_key"] is None
    assert settings["chat_model_id"] == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


# endregion

# region Client Initialization Tests


def test_google_client_init_with_client(mock_google_client: MagicMock) -> None:
    """Test GoogleAIChatClient initialization with existing google_client."""
    client = create_test_google_client(mock_google_client, model_id="gemini-2.5-flash")

    assert client.google_client is mock_google_client
    assert client.model_id == "gemini-2.5-flash"
    assert isinstance(client, SupportsChatGetResponse)


def test_google_client_init_auto_create_client(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAIChatClient initialization with auto-created google_client."""
    client = GoogleAIChatClient(
        api_key=google_ai_unit_test_env["GOOGLE_AI_API_KEY"],
        model_id=google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"],
    )

    assert client.google_client is not None
    assert client.model_id == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


def test_google_client_init_missing_api_key() -> None:
    """Test GoogleAIChatClient initialization when API key is missing."""
    with patch("agent_framework_google._chat_client.load_settings") as mock_load:
        mock_load.return_value = {"api_key": None, "chat_model_id": "gemini-2.5-flash"}

        with pytest.raises(Exception, match="Google AI API key is required"):
            GoogleAIChatClient()


# endregion

# region Message Conversion Tests


def test_prepare_message_for_google_text(mock_google_client: MagicMock) -> None:
    """Test converting text message to Google format."""
    client = create_test_google_client(mock_google_client)
    message = Message(role="user", text="Hello, world!")

    result = client._prepare_message_for_google(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["text"] == "Hello, world!"


def test_prepare_message_for_google_assistant(mock_google_client: MagicMock) -> None:
    """Test converting assistant message to Google format."""
    client = create_test_google_client(mock_google_client)
    message = Message(role="assistant", text="Hello back!")

    result = client._prepare_message_for_google(message)

    assert result["role"] == "model"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["text"] == "Hello back!"


def test_convert_message_function_call(mock_google_client: MagicMock) -> None:
    """Test converting message with function call to Google format."""
    client = create_test_google_client(mock_google_client)
    message = Message(
        role="assistant",
        contents=[
            Content.from_function_call(
                call_id="call_123",
                name="get_weather",
                arguments={"location": "Seattle"},
            )
        ],
    )

    result = client._prepare_message_for_google(message)

    assert result["role"] == "model"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["function_call"]["name"] == "get_weather"
    assert result["parts"][0]["function_call"]["args"]["location"] == "Seattle"


def test_convert_message_function_call_string_arguments(mock_google_client: MagicMock) -> None:
    """Test converting message with string arguments for function call to Google format."""
    client = create_test_google_client(mock_google_client)
    message = Message(
        role="assistant",
        contents=[
            Content.from_function_call(
                call_id="call_456",
                name="search",
                arguments='{"query": "hello"}',
            )
        ],
    )

    result = client._prepare_message_for_google(message)

    assert result["role"] == "model"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["function_call"]["name"] == "search"
    assert result["parts"][0]["function_call"]["args"]["query"] == "hello"


def test_convert_message_function_result(mock_google_client: MagicMock) -> None:
    """Test converting message with function result to Google format."""
    client = create_test_google_client(mock_google_client)
    message = Message(
        role="tool",
        contents=[
            Content.from_function_result(
                call_id="call_123",
                result="72 degrees and sunny",
            )
        ],
    )

    result = client._prepare_message_for_google(message)

    assert result["role"] == "function"
    assert len(result["parts"]) == 1
    # FunctionResultContent uses call_id as the name since Google requires it
    assert result["parts"][0]["function_response"]["name"] == "call_123"
    assert result["parts"][0]["function_response"]["response"]["result"] == "72 degrees and sunny"


def test_convert_message_with_image_data(mock_google_client: MagicMock) -> None:
    """Test converting message with image data to Google format."""
    client = create_test_google_client(mock_google_client)

    # Use valid PNG data
    base64_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    image_bytes = base64.b64decode(base64_image)

    message = Message(
        role="user",
        contents=[Content.from_data(media_type="image/png", data=image_bytes)],
    )

    result = client._prepare_message_for_google(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 1
    assert "inline_data" in result["parts"][0]
    assert result["parts"][0]["inline_data"]["mime_type"] == "image/png"
    assert isinstance(result["parts"][0]["inline_data"]["data"], bytes)


def test_convert_message_with_unsupported_media_type(mock_google_client: MagicMock) -> None:
    """Test converting message with unsupported media type."""
    client = create_test_google_client(mock_google_client)

    message = Message(
        role="user",
        contents=[Content.from_data(media_type="application/pdf", data=b"PDF data")],
    )

    result = client._prepare_message_for_google(message)

    # Unsupported media type should be skipped
    assert result["role"] == "user"
    assert len(result["parts"]) == 0


def test_convert_message_with_image_uri(mock_google_client: MagicMock) -> None:
    """Test converting message with image URI to Google format."""
    client = create_test_google_client(mock_google_client)
    message = Message(
        role="user",
        contents=[Content.from_uri(uri="https://example.com/image.png", media_type="image/png")],
    )
    result = client._prepare_message_for_google(message)
    assert result["role"] == "user"
    assert len(result["parts"]) == 1
    assert "file_data" in result["parts"][0]
    assert result["parts"][0]["file_data"]["mime_type"] == "image/png"
    assert result["parts"][0]["file_data"]["file_uri"] == "https://example.com/image.png"


def test_convert_message_with_unsupported_uri_type(mock_google_client: MagicMock) -> None:
    """Test converting message with unsupported URI content type."""
    client = create_test_google_client(mock_google_client)
    message = Message(
        role="user",
        contents=[Content.from_uri(uri="https://example.com/video.mp4", media_type="video/mp4")],
    )
    result = client._prepare_message_for_google(message)
    assert result["role"] == "user"
    assert len(result["parts"]) == 0


def test_prepare_message_for_google_multiple_text(mock_google_client: MagicMock) -> None:
    """Test converting message with multiple text contents."""
    client = create_test_google_client(mock_google_client)
    message = Message(
        role="user",
        contents=[
            Content.from_text("First part"),
            Content.from_text("Second part"),
        ],
    )

    result = client._prepare_message_for_google(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 2
    assert result["parts"][0]["text"] == "First part"
    assert result["parts"][1]["text"] == "Second part"


def test_prepare_messages_for_google_with_system(mock_google_client: MagicMock) -> None:
    """Test converting messages list with system message."""
    client = create_test_google_client(mock_google_client)
    messages = [
        Message(role="system", text="You are a helpful assistant."),
        Message(role="user", text="Hello!"),
    ]

    result = client._prepare_messages_for_google(messages)

    # System message should be skipped
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["parts"][0]["text"] == "Hello!"


def test_prepare_messages_for_google_without_system(mock_google_client: MagicMock) -> None:
    """Test converting messages list without system message."""
    client = create_test_google_client(mock_google_client)
    messages = [
        Message(role="user", text="Hello!"),
        Message(role="assistant", text="Hi there!"),
    ]

    result = client._prepare_messages_for_google(messages)

    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "model"


def test_convert_messages_all_system_messages_error(mock_google_client: MagicMock) -> None:
    """Test that error is raised when only system messages are provided."""
    client = create_test_google_client(mock_google_client)

    messages = [
        Message(role="system", text="System instruction 1"),
        Message(role="system", text="System instruction 2"),
    ]

    with pytest.raises(ValueError, match="No messages to send to Google AI after filtering"):
        client._prepare_messages_for_google(messages)


# endregion

# region Tool Conversion Tests


def test_convert_tools_to_google_format_with_function_tool(mock_google_client: MagicMock) -> None:
    """Test converting FunctionTool to Google format."""
    client = create_test_google_client(mock_google_client)

    @tool(approval_mode="never_require")
    def get_weather(location: Annotated[str, Field(description="Location to get weather for")]) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    result = client._prepare_tools_for_google({"tools": [get_weather]})

    assert result is not None
    assert len(result) == 1
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "get_weather"
    assert "Get weather for a location" in func_decl.description


def test_convert_tools_to_google_format_empty_list(mock_google_client: MagicMock) -> None:
    """Test converting empty tools list."""
    client = create_test_google_client(mock_google_client)

    result = client._prepare_tools_for_google({"tools": []})

    assert result is None


def test_convert_tools_to_google_format_none(mock_google_client: MagicMock) -> None:
    """Test converting None tools."""
    client = create_test_google_client(mock_google_client)

    result = client._prepare_tools_for_google({})

    assert result is None


def test_convert_tools_to_google_format_unsupported_type(mock_google_client: MagicMock) -> None:
    """Test converting unsupported tool types."""
    client = create_test_google_client(mock_google_client)

    result = client._prepare_tools_for_google({"tools": ["not_a_function", 123]})

    # Should return None when no valid tools
    assert result is None


def test_convert_tools_google_search(mock_google_client: MagicMock) -> None:
    """Test converting a Google Search dict tool to Google format."""
    client = create_test_google_client(mock_google_client)

    # Google search is passed as a dict from get_google_search_tool()
    google_search_tool = GoogleAIChatClient.get_google_search_tool()

    result = client._prepare_tools_for_google({"tools": [google_search_tool]})

    # Dict with "google_search" key should be converted to types.Tool
    assert result is not None
    assert len(result) == 1
    assert isinstance(result[0], types.Tool)


def test_convert_tools_code_execution(mock_google_client: MagicMock) -> None:
    """Test converting a code execution dict tool to Google format."""
    client = create_test_google_client(mock_google_client)

    code_exec_tool = GoogleAIChatClient.get_code_execution_tool()

    result = client._prepare_tools_for_google({"tools": [code_exec_tool]})

    # Dict with "code_execution" key should be converted to types.Tool
    assert result is not None
    assert len(result) == 1
    assert isinstance(result[0], types.Tool)


def test_convert_tools_dict_tool(mock_google_client: MagicMock) -> None:
    """Test converting dict tools to Google format - unknown dicts are passed through."""
    client = create_test_google_client(mock_google_client)

    # Unknown dict-based tools are passed through unchanged
    result = client._prepare_tools_for_google({"tools": [{"type": "custom", "name": "custom_tool"}]})

    assert result is not None
    assert len(result) == 1
    assert result[0] == {"type": "custom", "name": "custom_tool"}


# endregion

# region Tool Choice Tests


def test_prepare_tool_config_auto(mock_google_client: MagicMock) -> None:
    """Test tool_choice auto mode."""
    client = create_test_google_client(mock_google_client)
    result = client._prepare_tool_config({"tool_choice": "auto"})
    assert result is not None
    assert result.function_calling_config.mode == "AUTO"


def test_prepare_tool_config_required(mock_google_client: MagicMock) -> None:
    """Test tool_choice required mode."""
    client = create_test_google_client(mock_google_client)
    result = client._prepare_tool_config({"tool_choice": "required"})
    assert result is not None
    assert result.function_calling_config.mode == "ANY"


def test_prepare_tool_config_required_specific(mock_google_client: MagicMock) -> None:
    """Test tool_choice required mode with specific function."""
    client = create_test_google_client(mock_google_client)
    result = client._prepare_tool_config({"tool_choice": {"mode": "required", "required_function_name": "get_weather"}})
    assert result is not None
    assert result.function_calling_config.mode == "ANY"
    assert result.function_calling_config.allowed_function_names == ["get_weather"]


def test_prepare_tool_config_none(mock_google_client: MagicMock) -> None:
    """Test tool_choice none mode."""
    client = create_test_google_client(mock_google_client)
    result = client._prepare_tool_config({"tool_choice": "none"})
    assert result is not None
    assert result.function_calling_config.mode == "NONE"


# endregion

# region Config Creation Tests


def test_create_config_with_system_message(mock_google_client: MagicMock) -> None:
    """Test config creation extracts system instruction from messages."""
    client = create_test_google_client(mock_google_client)
    messages = [
        Message(role="system", text="You are a helpful assistant."),
        Message(role="user", text="Hello!"),
    ]
    chat_options: ChatOptions = {}

    config = client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.system_instruction == "You are a helpful assistant."


def test_create_config_with_multiple_system_messages(mock_google_client: MagicMock) -> None:
    """Test config creation joins multiple system messages."""
    client = create_test_google_client(mock_google_client)
    messages = [
        Message(role="system", text="You are a helpful assistant."),
        Message(role="system", text="Be concise."),
        Message(role="user", text="Hello!"),
    ]
    chat_options: ChatOptions = {}

    config = client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert "You are a helpful assistant." in config.system_instruction
    assert "Be concise." in config.system_instruction


def test_create_config_without_system_message(mock_google_client: MagicMock) -> None:
    """Test config creation without system message."""
    client = create_test_google_client(mock_google_client)
    messages = [
        Message(role="user", text="Hello!"),
    ]
    chat_options: ChatOptions = {}

    config = client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.system_instruction is None


def test_create_config_with_temperature(mock_google_client: MagicMock) -> None:
    """Test config creation with temperature."""
    client = create_test_google_client(mock_google_client)
    messages = [Message(role="user", text="Hello!")]
    chat_options: ChatOptions = {"temperature": 0.7}

    config = client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.temperature == 0.7


def test_create_config_with_chat_options(mock_google_client: MagicMock) -> None:
    """Test config creation with multiple chat options."""
    client = create_test_google_client(mock_google_client)
    messages = [Message(role="user", text="Hello!")]
    chat_options: ChatOptions = {
        "temperature": 0.7,
        "max_tokens": 100,
        "top_p": 0.9,
    }

    config = client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.temperature == 0.7
    assert config.max_output_tokens == 100
    assert config.top_p == 0.9


def test_create_config_with_stop_sequences(mock_google_client: MagicMock) -> None:
    """Test config creation with stop sequences."""
    client = create_test_google_client(mock_google_client)
    chat_options: ChatOptions = {"stop": ["END", "STOP"]}

    config = client._create_config(chat_options)

    assert config.stop_sequences == ["END", "STOP"]


def test_create_config_with_tools(mock_google_client: MagicMock) -> None:
    """Test config creation includes tools."""
    client = create_test_google_client(mock_google_client)

    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    chat_options: ChatOptions = {"tools": [get_weather]}

    config = client._create_config(chat_options)

    assert config.tools is not None
    assert len(config.tools) == 1


# endregion

# region Response Processing Tests


def test_process_response_with_text(mock_google_client: MagicMock) -> None:
    """Test processing response with text content."""
    client = create_test_google_client(mock_google_client)

    # Create mock response
    mock_part = MagicMock()
    mock_part.text = "Hello, world!"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 10
    mock_usage.candidates_token_count = 5

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = mock_usage

    result = client._process_response(mock_response, {})

    assert len(result.messages) == 1
    assert result.messages[0].role == "assistant"
    # Text content + usage content
    text_contents = [c for c in result.messages[0].contents if c.type == "text"]
    assert len(text_contents) == 1
    assert text_contents[0].text == "Hello, world!"
    assert result.finish_reason == "stop"
    assert result.usage_details is not None
    assert result.usage_details["input_token_count"] == 10
    assert result.usage_details["output_token_count"] == 5


def test_process_response_with_function_call(mock_google_client: MagicMock) -> None:
    """Test processing response with function call."""
    client = create_test_google_client(mock_google_client)

    # Create mock function call part
    mock_fc = MagicMock()
    mock_fc.name = "get_weather"
    mock_fc.args = {"location": "Seattle"}

    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = mock_fc

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    assert len(result.messages) == 1
    assert len(result.messages[0].contents) == 1
    assert result.messages[0].contents[0].type == "function_call"
    assert result.messages[0].contents[0].name == "get_weather"
    assert result.messages[0].contents[0].arguments == {"location": "Seattle"}


def test_process_response_with_multiple_parts(mock_google_client: MagicMock) -> None:
    """Test processing response with multiple text parts."""
    client = create_test_google_client(mock_google_client)

    mock_part1 = MagicMock()
    mock_part1.text = "First part. "

    mock_part2 = MagicMock()
    mock_part2.text = "Second part."

    mock_content = MagicMock()
    mock_content.parts = [mock_part1, mock_part2]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    assert len(result.messages) == 1
    text_contents = [c for c in result.messages[0].contents if c.type == "text"]
    assert len(text_contents) == 2
    assert text_contents[0].text == "First part. "
    assert text_contents[1].text == "Second part."


def test_process_response_finish_reason_stop(mock_google_client: MagicMock) -> None:
    """Test processing response with STOP finish reason."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Complete response"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    assert result.finish_reason == "stop"


def test_process_response_finish_reason_max_tokens(mock_google_client: MagicMock) -> None:
    """Test processing response with MAX_TOKENS finish reason."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Partial response"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "MAX_TOKENS"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    assert result.finish_reason == "length"


def test_process_response_finish_reason_safety(mock_google_client: MagicMock) -> None:
    """Test processing response with SAFETY finish reason."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Blocked content"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "SAFETY"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    assert result.finish_reason == "content_filter"


def test_process_response_finish_reason_recitation(mock_google_client: MagicMock) -> None:
    """Test processing response with RECITATION finish reason."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Recitation content"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "RECITATION"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    assert result.finish_reason == "content_filter"


def test_process_response_usage_none(mock_google_client: MagicMock) -> None:
    """Test processing response with no usage metadata."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Response"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    result = client._process_response(mock_response, {})

    # When usage_metadata is None, no UsageContent is added
    # Only text content should be present
    text_contents = [c for c in result.messages[0].contents if c.type == "text"]
    assert len(text_contents) == 1


# endregion

# region Stream Processing Tests


def test_process_stream_chunk_with_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with text."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Streamed text"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]

    result = client._process_stream_chunk(mock_chunk)

    assert result is not None
    assert isinstance(result, ChatResponseUpdate)
    assert result.role == "assistant"
    text_contents = [c for c in result.contents if c.type == "text"]
    assert len(text_contents) == 1
    assert text_contents[0].text == "Streamed text"


def test_process_stream_chunk_without_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk without text."""
    client = create_test_google_client(mock_google_client)

    mock_chunk = MagicMock()
    mock_chunk.candidates = []
    mock_chunk.usage_metadata = None

    result = client._process_stream_chunk(mock_chunk)

    assert result is None


def test_process_stream_chunk_empty_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with empty text."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = ""
    mock_part.function_call = None

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason = None

    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]
    mock_chunk.usage_metadata = None

    result = client._process_stream_chunk(mock_chunk)

    # Empty text should return None
    assert result is None


def test_process_stream_chunk_none_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with None text."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = None

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason = None

    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]
    mock_chunk.usage_metadata = None

    result = client._process_stream_chunk(mock_chunk)

    # None text should return None
    assert result is None


def test_process_stream_chunk_with_function_call(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with function call."""
    client = create_test_google_client(mock_google_client)
    mock_fc = MagicMock()
    mock_fc.name = "get_weather"
    mock_fc.args = {"location": "Seattle"}
    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = mock_fc
    mock_content = MagicMock()
    mock_content.parts = [mock_part]
    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason = None
    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]
    mock_chunk.usage_metadata = None
    result = client._process_stream_chunk(mock_chunk)
    assert result is not None
    assert isinstance(result, ChatResponseUpdate)
    fc_contents = [c for c in result.contents if c.type == "function_call"]
    assert len(fc_contents) == 1
    assert fc_contents[0].name == "get_weather"


# endregion

# region Async API Tests


async def test_inner_get_response(mock_google_client: MagicMock) -> None:
    """Test _inner_get_response method."""
    client = create_test_google_client(mock_google_client)

    # Setup mock response
    mock_part = MagicMock()
    mock_part.text = "Response text"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    mock_google_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    messages = [Message(role="user", text="Hello!")]
    options: ChatOptions = {"max_tokens": 100}

    result = await client._inner_get_response(messages=messages, options=options)

    assert result is not None
    assert len(result.messages) == 1
    text_contents = [c for c in result.messages[0].contents if c.type == "text"]
    assert text_contents[0].text == "Response text"
    mock_google_client.aio.models.generate_content.assert_called_once()


async def test_inner_get_response_with_system_message(mock_google_client: MagicMock) -> None:
    """Test _inner_get_response passes system instruction through config."""
    client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Response"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    mock_google_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    messages = [
        Message(role="system", text="You are helpful."),
        Message(role="user", text="Hello!"),
    ]
    options: ChatOptions = {}

    result = await client._inner_get_response(messages=messages, options=options)

    assert result is not None
    # Verify generate_content was called with system_instruction in config
    call_kwargs = mock_google_client.aio.models.generate_content.call_args
    config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
    assert config.system_instruction == "You are helpful."


async def test_inner_get_response_streaming(mock_google_client: MagicMock) -> None:
    """Test _inner_get_response method with streaming."""
    client = create_test_google_client(mock_google_client)

    # Create mock chunks
    mock_part1 = MagicMock()
    mock_part1.text = "First "

    mock_content1 = MagicMock()
    mock_content1.parts = [mock_part1]

    mock_candidate1 = MagicMock()
    mock_candidate1.content = mock_content1

    mock_chunk1 = MagicMock()
    mock_chunk1.candidates = [mock_candidate1]

    mock_part2 = MagicMock()
    mock_part2.text = "Second"

    mock_content2 = MagicMock()
    mock_content2.parts = [mock_part2]

    mock_candidate2 = MagicMock()
    mock_candidate2.content = mock_content2

    mock_chunk2 = MagicMock()
    mock_chunk2.candidates = [mock_candidate2]

    # Setup async iterator mock
    async def mock_stream():
        yield mock_chunk1
        yield mock_chunk2

    mock_google_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream())

    messages = [Message(role="user", text="Hello!")]
    options: ChatOptions = {}

    chunks: list[ChatResponseUpdate] = []
    async for chunk in client._inner_get_response(  # type: ignore[attr-defined]
        messages=messages, options=options, stream=True
    ):
        if chunk:
            chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].contents[0].text == "First "
    assert chunks[1].contents[0].text == "Second"


async def test_inner_get_response_with_tools(mock_google_client: MagicMock) -> None:
    """Test _inner_get_response with tools."""
    client = create_test_google_client(mock_google_client)

    mock_fc = MagicMock()
    mock_fc.name = "get_weather"
    mock_fc.args = {"location": "Seattle"}

    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = mock_fc

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_candidate.finish_reason.name = "STOP"

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.usage_metadata = None

    mock_google_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    @tool(approval_mode="never_require")
    def get_weather(location: str) -> str:
        """Get weather for a location."""
        return f"Weather for {location}"

    messages = [Message(role="user", text="What's the weather in Seattle?")]
    options: ChatOptions = {"tools": [get_weather]}

    result = await client._inner_get_response(messages=messages, options=options)

    assert result is not None
    assert len(result.messages) == 1
    function_calls = [c for c in result.messages[0].contents if c.type == "function_call"]
    assert len(function_calls) == 1
    assert function_calls[0].name == "get_weather"


# endregion

# region Integration Tests


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a location."""
    return f"The weather in {location} is sunny and 72 degrees"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_google_integration_tests_disabled
async def test_google_client_integration_basic_chat() -> None:
    """Integration test for basic chat completion."""
    client = GoogleAIChatClient()

    messages = [Message(role="user", text="Say 'Hello, World!' and nothing else.")]

    response = await client.get_response(messages=messages, options={"max_tokens": 50})

    assert response is not None
    assert len(response.messages) > 0
    assert response.messages[0].role == "assistant"
    assert len(response.messages[0].text) > 0


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_google_integration_tests_disabled
async def test_google_client_integration_streaming_chat() -> None:
    """Integration test for streaming chat completion."""
    client = GoogleAIChatClient()

    messages = [Message(role="user", text="Count from 1 to 5.")]

    chunks = []
    async for chunk in client.get_response(messages=messages, stream=True, options={"max_tokens": 50}):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert any(chunk.contents for chunk in chunks)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_google_integration_tests_disabled
async def test_google_client_integration_function_calling() -> None:
    """Integration test for function calling."""
    client = GoogleAIChatClient()

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
@skip_if_google_integration_tests_disabled
async def test_google_client_integration_with_system_message() -> None:
    """Integration test with system message."""
    client = GoogleAIChatClient()

    messages = [
        Message(role="system", text="You are a pirate. Always respond like a pirate."),
        Message(role="user", text="Hello!"),
    ]

    response = await client.get_response(messages=messages, options={"max_tokens": 50})

    assert response is not None
    assert len(response.messages) > 0


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_google_integration_tests_disabled
async def test_google_client_integration_temperature_control() -> None:
    """Integration test with temperature control."""
    client = GoogleAIChatClient()

    messages = [Message(role="user", text="Say hello.")]

    response = await client.get_response(
        messages=messages,
        options={"max_tokens": 20, "temperature": 0.0},
    )

    assert response is not None
    assert response.messages[0].text is not None


# endregion
