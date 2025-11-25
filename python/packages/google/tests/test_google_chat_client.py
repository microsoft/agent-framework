# Copyright (c) Microsoft. All rights reserved.
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponseUpdate,
    FinishReason,
    Role,
    TextContent,
    UsageContent,
)
from agent_framework.exceptions import ServiceInitializationError
from google import genai
from google.genai import types
from pydantic import ValidationError

from agent_framework_google import GoogleAIChatClient
from agent_framework_google._chat_client import GoogleAISettings

skip_if_google_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("GOOGLE_AI_API_KEY", "") in ("", "test-api-key-12345"),
    reason="No real GOOGLE_AI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def create_test_google_client(
    mock_google_client: MagicMock,
    model_id: str | None = None,
    google_settings: GoogleAISettings | None = None,
) -> GoogleAIChatClient:
    """Helper function to create GoogleAIChatClient instances for testing, bypassing normal validation."""
    if google_settings is None:
        google_settings = GoogleAISettings(api_key="test-api-key-12345", chat_model_id="gemini-2.5-flash")

    # Create client instance directly
    client = object.__new__(GoogleAIChatClient)

    # Set attributes directly
    client.google_client = mock_google_client
    client.model_id = model_id or google_settings.chat_model_id
    client._last_call_id_name = None
    client.additional_properties = {}
    client.middleware = None

    return client


# region Settings Tests


def test_google_ai_settings_init(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings initialization."""
    settings = GoogleAISettings()

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == google_ai_unit_test_env["GOOGLE_AI_API_KEY"]
    assert settings.chat_model_id == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


def test_google_ai_settings_init_with_explicit_values() -> None:
    """Test GoogleAISettings initialization with explicit values."""
    settings = GoogleAISettings(
        api_key="custom-api-key",
        chat_model_id="gemini-2.5-flash",
    )

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "custom-api-key"
    assert settings.chat_model_id == "gemini-2.5-flash"


@pytest.mark.parametrize("exclude_list", [["GOOGLE_AI_API_KEY"]], indirect=True)
def test_google_ai_settings_missing_api_key(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings when API key is missing."""
    settings = GoogleAISettings()
    assert settings.api_key is None
    assert settings.chat_model_id == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


# endregion

# region Client Initialization Tests


def test_google_client_init_with_client(mock_google_client: MagicMock) -> None:
    """Test GoogleAIChatClient initialization with existing google_client."""
    chat_client = create_test_google_client(mock_google_client, model_id="gemini-2.5-flash")

    assert chat_client.google_client is mock_google_client
    assert chat_client.model_id == "gemini-2.5-flash"
    assert isinstance(chat_client, ChatClientProtocol)


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
    with patch("agent_framework_google._chat_client.GoogleAISettings") as mock_settings:
        mock_settings.return_value.api_key = None
        mock_settings.return_value.chat_model_id = "gemini-2.5-flash"

        with pytest.raises(ServiceInitializationError, match="Google AI API key is required"):
            GoogleAIChatClient()


def test_google_client_init_validation_error() -> None:
    """Test that ValidationError in GoogleAISettings is properly handled."""
    with patch("agent_framework_google._chat_client.GoogleAISettings") as mock_settings:
        mock_settings.side_effect = ValidationError.from_exception_data("test", [])

        with pytest.raises(ServiceInitializationError, match="Failed to create Google AI settings"):
            GoogleAIChatClient()


# endregion

# region Message Conversion Tests


def test_convert_message_to_google_format_text(mock_google_client: MagicMock) -> None:
    """Test converting text message to Google format."""
    chat_client = create_test_google_client(mock_google_client)
    message = ChatMessage(role=Role.USER, text="Hello, world!")

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["text"] == "Hello, world!"


def test_convert_message_to_google_format_assistant(mock_google_client: MagicMock) -> None:
    """Test converting assistant message to Google format."""
    chat_client = create_test_google_client(mock_google_client)
    message = ChatMessage(role=Role.ASSISTANT, text="Hello back!")

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "model"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["text"] == "Hello back!"


def test_convert_message_function_call(mock_google_client: MagicMock) -> None:
    """Test converting message with function call to Google format."""
    from agent_framework import FunctionCallContent

    chat_client = create_test_google_client(mock_google_client)
    message = ChatMessage(
        role=Role.ASSISTANT,
        contents=[FunctionCallContent(call_id="call_123", name="get_weather", arguments='{"location": "Seattle"}')],
    )

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "model"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["function_call"]["name"] == "get_weather"
    assert result["parts"][0]["function_call"]["args"]["location"] == "Seattle"


def test_convert_message_function_result(mock_google_client: MagicMock) -> None:
    """Test converting message with function result to Google format."""
    from agent_framework import FunctionResultContent

    chat_client = create_test_google_client(mock_google_client)
    message = ChatMessage(
        role=Role.TOOL, contents=[FunctionResultContent(call_id="call_123", result="72 degrees and sunny")]
    )

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "function"
    assert len(result["parts"]) == 1
    # FunctionResultContent only has call_id, which we use as the name
    assert result["parts"][0]["function_response"]["name"] == "call_123"
    assert result["parts"][0]["function_response"]["response"]["result"] == "72 degrees and sunny"


def test_convert_message_with_image_data(mock_google_client: MagicMock) -> None:
    """Test converting message with image data to Google format."""
    import base64

    from agent_framework import DataContent

    chat_client = create_test_google_client(mock_google_client)

    # Create a small test image (1x1 red pixel PNG)
    test_image_data = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()

    message = ChatMessage(
        role=Role.USER, contents=[DataContent(media_type="image/png", uri=f"data:image/png;base64,{test_image_data}")]
    )

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["inline_data"]["mime_type"] == "image/png"
    assert isinstance(result["parts"][0]["inline_data"]["data"], bytes)


def test_convert_messages_all_system_messages_error(mock_google_client: MagicMock) -> None:
    """Test that error is raised when only system messages are provided."""
    chat_client = create_test_google_client(mock_google_client)

    messages = [
        ChatMessage(role=Role.SYSTEM, text="System instruction 1"),
        ChatMessage(role=Role.SYSTEM, text="System instruction 2"),
    ]

    with pytest.raises(ValueError, match="No messages to send to Google AI after filtering"):
        chat_client._convert_messages_to_google_format(messages)


def test_config_with_stop_sequences(mock_google_client: MagicMock) -> None:
    """Test config creation with stop sequences."""
    chat_client = create_test_google_client(mock_google_client)

    chat_options = ChatOptions(stop=["END", "STOP"])
    config = chat_client._create_config(chat_options)

    assert config.stop_sequences == ["END", "STOP"]


def test_config_with_additional_properties(mock_google_client: MagicMock) -> None:
    """Test config creation with additional properties."""
    chat_client = create_test_google_client(mock_google_client)

    chat_options = ChatOptions(additional_properties={"top_k": 40})
    config = chat_client._create_config(chat_options)

    # additional_properties should be merged into config
    assert hasattr(config, "top_k") or "top_k" in str(config)


def test_process_response_with_function_call(mock_google_client: MagicMock) -> None:
    """Test processing response with function call."""
    chat_client = create_test_google_client(mock_google_client)

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

    result = chat_client._process_response(mock_response)

    assert len(result.messages) == 1
    assert len(result.messages[0].contents) == 1
    from agent_framework import FunctionCallContent

    assert isinstance(result.messages[0].contents[0], FunctionCallContent)
    assert result.messages[0].contents[0].name == "get_weather"
    assert '"location"' in result.messages[0].contents[0].arguments
    assert '"Seattle"' in result.messages[0].contents[0].arguments


def test_convert_message_to_google_format_multiple_text(mock_google_client: MagicMock) -> None:
    """Test converting message with multiple text contents."""
    chat_client = create_test_google_client(mock_google_client)
    message = ChatMessage(
        role=Role.USER,
        contents=[
            TextContent(text="First part"),
            TextContent(text="Second part"),
        ],
    )

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 2
    assert result["parts"][0]["text"] == "First part"
    assert result["parts"][1]["text"] == "Second part"


# region Tools Conversion Tests


def test_convert_tools_to_google_format_with_plain_function(mock_google_client: MagicMock) -> None:
    """Test converting plain Python functions to Google format."""
    chat_client = create_test_google_client(mock_google_client)

    def get_weather(city: str, units: str = "celsius") -> str:
        """Get the current weather for a city.

        This is an extended description that should be ignored.
        """
        return f"Weather in {city}"

    result = chat_client._convert_tools_to_google_format([get_weather])

    assert result is not None
    assert len(result) == 1
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "get_weather"
    assert "Get the current weather for a city" in func_decl.description


def test_convert_tools_to_google_format_with_typed_parameters(mock_google_client: MagicMock) -> None:
    """Test converting functions with various type annotations."""
    chat_client = create_test_google_client(mock_google_client)

    def calculate(value: int, multiplier: float, enabled: bool, name: str) -> float:
        """Calculate a value."""
        return value * multiplier

    result = chat_client._convert_tools_to_google_format([calculate])

    assert result is not None
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "calculate"
    # Verify parameters exist (Schema object structure varies)
    assert func_decl.parameters is not None


def test_convert_tools_to_google_format_with_complex_types(mock_google_client: MagicMock) -> None:
    """Test converting functions with list/dict type annotations."""
    chat_client = create_test_google_client(mock_google_client)

    def process_data(items: list, config: dict) -> str:
        """Process data with complex types."""
        return "done"

    result = chat_client._convert_tools_to_google_format([process_data])

    assert result is not None
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "process_data"
    assert func_decl.parameters is not None


def test_convert_tools_to_google_format_with_no_annotations(mock_google_client: MagicMock) -> None:
    """Test converting functions without type annotations."""
    chat_client = create_test_google_client(mock_google_client)

    def simple_func(arg1, arg2):
        """A simple function."""
        pass

    result = chat_client._convert_tools_to_google_format([simple_func])

    assert result is not None
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "simple_func"
    assert func_decl.parameters is not None


def test_convert_tools_to_google_format_with_no_docstring(mock_google_client: MagicMock) -> None:
    """Test converting functions without docstrings."""
    chat_client = create_test_google_client(mock_google_client)

    def no_doc_func(x: int) -> int:
        return x

    result = chat_client._convert_tools_to_google_format([no_doc_func])

    assert result is not None
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "no_doc_func"
    assert func_decl.description == ""


def test_convert_tools_to_google_format_empty_list(mock_google_client: MagicMock) -> None:
    """Test converting empty tools list."""
    chat_client = create_test_google_client(mock_google_client)

    result = chat_client._convert_tools_to_google_format([])

    assert result is None


def test_convert_tools_to_google_format_none(mock_google_client: MagicMock) -> None:
    """Test converting None tools."""
    chat_client = create_test_google_client(mock_google_client)

    result = chat_client._convert_tools_to_google_format(None)

    assert result is None


def test_convert_tools_to_google_format_unsupported_type(mock_google_client: MagicMock) -> None:
    """Test converting unsupported tool types."""
    chat_client = create_test_google_client(mock_google_client)

    result = chat_client._convert_tools_to_google_format(["not_a_function", 123])

    # Should return None when no valid tools
    assert result is None


def test_convert_tools_to_google_format_mixed_valid_invalid(mock_google_client: MagicMock) -> None:
    """Test converting mix of valid and invalid tools."""
    chat_client = create_test_google_client(mock_google_client)

    def valid_func(x: str) -> str:
        """A valid function."""
        return x

    result = chat_client._convert_tools_to_google_format([valid_func, "invalid", 123])

    assert result is not None
    assert len(result[0].function_declarations) == 1
    assert result[0].function_declarations[0].name == "valid_func"


def test_convert_tools_to_google_format_with_self_param(mock_google_client: MagicMock) -> None:
    """Test that 'self' parameter is skipped."""
    chat_client = create_test_google_client(mock_google_client)

    class MyClass:
        def method(self, value: str) -> str:
            """A method with self."""
            return value

    obj = MyClass()
    result = chat_client._convert_tools_to_google_format([obj.method])

    assert result is not None
    func_decl = result[0].function_declarations[0]
    assert func_decl.name == "method"
    # Verify parameters exist - 'self' should be filtered out
    assert func_decl.parameters is not None


# endregion

# region Image/Multimodal Content Tests


def test_convert_message_with_base64_image(mock_google_client: MagicMock) -> None:
    """Test converting message with image data content."""
    from agent_framework import DataContent

    chat_client = create_test_google_client(mock_google_client)

    # Create a simple base64 encoded image (1x1 red PNG)
    base64_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    message = ChatMessage(
        role=Role.USER,
        contents=[
            DataContent(uri=f"data:image/png;base64,{base64_image}", media_type="image/png"),
        ],
    )

    result = chat_client._convert_message_to_google_format(message)

    assert result["role"] == "user"
    assert len(result["parts"]) == 1
    assert "inline_data" in result["parts"][0]
    assert result["parts"][0]["inline_data"]["mime_type"] == "image/png"


def test_convert_message_with_unsupported_media_type(mock_google_client: MagicMock) -> None:
    """Test converting message with unsupported media type."""
    from agent_framework import DataContent

    chat_client = create_test_google_client(mock_google_client)

    message = ChatMessage(
        role=Role.USER,
        contents=[
            DataContent(uri="data:application/pdf;base64,dGVzdA==", media_type="application/pdf"),
        ],
    )

    result = chat_client._convert_message_to_google_format(message)

    # Unsupported media type should be ignored
    assert result["role"] == "user"
    assert len(result["parts"]) == 0


# endregion

# region Streaming Edge Cases


def test_process_stream_chunk_empty_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with empty text."""
    chat_client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = ""

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]

    result = chat_client._process_stream_chunk(mock_chunk)

    # Empty text should return None
    assert result is None


def test_process_stream_chunk_none_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with None text."""
    chat_client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = None

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]

    result = chat_client._process_stream_chunk(mock_chunk)

    # None text should return None
    assert result is None

    # endregion
    """Test converting messages list with system message."""
    chat_client = create_test_google_client(mock_google_client)
    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant."),
        ChatMessage(role=Role.USER, text="Hello!"),
    ]

    result = chat_client._convert_messages_to_google_format(messages)

    # System message should be skipped
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["parts"][0]["text"] == "Hello!"


def test_convert_messages_to_google_format_without_system(mock_google_client: MagicMock) -> None:
    """Test converting messages list without system message."""
    chat_client = create_test_google_client(mock_google_client)
    messages = [
        ChatMessage(role=Role.USER, text="Hello!"),
        ChatMessage(role=Role.ASSISTANT, text="Hi there!"),
    ]

    result = chat_client._convert_messages_to_google_format(messages)

    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "model"


# endregion

# region Config Creation Tests


def test_create_config_with_system_message(mock_google_client: MagicMock) -> None:
    """Test config creation extracts system instruction from first message."""
    chat_client = create_test_google_client(mock_google_client)
    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant."),
        ChatMessage(role=Role.USER, text="Hello!"),
    ]
    chat_options = ChatOptions(model_id="gemini-2.5-flash")

    config = chat_client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.system_instruction == "You are a helpful assistant."


def test_create_config_without_system_message(mock_google_client: MagicMock) -> None:
    """Test config creation without system message."""
    chat_client = create_test_google_client(mock_google_client)
    messages = [
        ChatMessage(role=Role.USER, text="Hello!"),
    ]
    chat_options = ChatOptions(model_id="gemini-2.5-flash")

    config = chat_client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.system_instruction is None


def test_create_config_with_chat_options(mock_google_client: MagicMock) -> None:
    """Test config creation with chat options."""
    chat_client = create_test_google_client(mock_google_client)
    messages = [ChatMessage(role=Role.USER, text="Hello!")]
    chat_options = ChatOptions(
        model_id="gemini-2.5-flash",
        temperature=0.7,
        max_tokens=100,
        top_p=0.9,
    )

    config = chat_client._create_config(chat_options, messages)

    assert isinstance(config, types.GenerateContentConfig)
    assert config.temperature == 0.7
    assert config.max_output_tokens == 100
    assert config.top_p == 0.9


# endregion

# region Response Processing Tests


def test_process_response_with_text(mock_google_client: MagicMock) -> None:
    """Test processing response with text content."""
    chat_client = create_test_google_client(mock_google_client)

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

    result = chat_client._process_response(mock_response)

    assert len(result.messages) == 1
    assert result.messages[0].role == Role.ASSISTANT
    assert len(result.messages[0].contents) == 2  # Text + Usage
    assert isinstance(result.messages[0].contents[0], TextContent)
    assert result.messages[0].contents[0].text == "Hello, world!"
    assert isinstance(result.messages[0].contents[1], UsageContent)
    assert result.messages[0].contents[1].details.input_token_count == 10
    assert result.messages[0].contents[1].details.output_token_count == 5
    assert result.finish_reason == FinishReason.STOP


def test_process_response_with_multiple_parts(mock_google_client: MagicMock) -> None:
    """Test processing response with multiple text parts."""
    chat_client = create_test_google_client(mock_google_client)

    # Create mock response with multiple parts
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

    result = chat_client._process_response(mock_response)

    assert len(result.messages) == 1
    # Multiple text parts create separate TextContent objects
    assert len(result.messages[0].contents) == 2
    assert result.messages[0].contents[0].text == "First part. "
    assert result.messages[0].contents[1].text == "Second part."


def test_process_response_finish_reason_max_tokens(mock_google_client: MagicMock) -> None:
    """Test processing response with MAX_TOKENS finish reason."""
    chat_client = create_test_google_client(mock_google_client)

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

    result = chat_client._process_response(mock_response)

    assert result.finish_reason == FinishReason.LENGTH


def test_process_response_finish_reason_safety(mock_google_client: MagicMock) -> None:
    """Test processing response with SAFETY finish reason."""
    chat_client = create_test_google_client(mock_google_client)

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

    result = chat_client._process_response(mock_response)

    assert result.finish_reason == FinishReason.CONTENT_FILTER


def test_extract_text_from_response(mock_google_client: MagicMock) -> None:
    """Test text extraction helper method."""
    chat_client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Extracted text"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]

    text = chat_client._extract_text_from_response(mock_response)

    assert text == "Extracted text"


def test_extract_text_from_response_empty(mock_google_client: MagicMock) -> None:
    """Test text extraction with no candidates."""
    chat_client = create_test_google_client(mock_google_client)

    mock_response = MagicMock()
    mock_response.candidates = []

    text = chat_client._extract_text_from_response(mock_response)

    assert text == ""


# endregion

# region Stream Processing Tests


def test_process_stream_chunk_with_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk with text."""
    chat_client = create_test_google_client(mock_google_client)

    mock_part = MagicMock()
    mock_part.text = "Streamed text"

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_chunk = MagicMock()
    mock_chunk.candidates = [mock_candidate]

    result = chat_client._process_stream_chunk(mock_chunk)

    assert result is not None
    assert isinstance(result, ChatResponseUpdate)
    assert result.text == "Streamed text"


def test_process_stream_chunk_without_text(mock_google_client: MagicMock) -> None:
    """Test processing streaming chunk without text."""
    chat_client = create_test_google_client(mock_google_client)

    mock_chunk = MagicMock()
    mock_chunk.candidates = []

    result = chat_client._process_stream_chunk(mock_chunk)

    assert result is None


# endregion

# region Async API Tests


@pytest.mark.asyncio
async def test_inner_get_response(mock_google_client: MagicMock) -> None:
    """Test async get response method."""
    chat_client = create_test_google_client(mock_google_client)

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

    # Setup async mock
    mock_google_client.aio = MagicMock()
    mock_google_client.aio.models = MagicMock()
    mock_google_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    messages = [ChatMessage(role=Role.USER, text="Hello!")]
    chat_options = ChatOptions(model_id="gemini-2.5-flash")

    result = await chat_client._inner_get_response(messages=messages, chat_options=chat_options)

    assert len(result.messages) == 1
    assert result.messages[0].contents[0].text == "Response text"
    mock_google_client.aio.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_inner_get_streaming_response(mock_google_client: MagicMock) -> None:
    """Test async streaming response method."""
    chat_client = create_test_google_client(mock_google_client)

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

    mock_google_client.aio = MagicMock()
    mock_google_client.aio.models = MagicMock()
    mock_google_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream())

    messages = [ChatMessage(role=Role.USER, text="Hello!")]
    chat_options = ChatOptions(model_id="gemini-2.5-flash")

    chunks = []
    async for chunk in chat_client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].text == "First "
    assert chunks[1].text == "Second"


# endregion

# region Integration Tests


@skip_if_google_integration_tests_disabled
@pytest.mark.asyncio
async def test_integration_basic_chat() -> None:
    """Integration test: Basic chat completion."""
    client = GoogleAIChatClient()

    messages = [ChatMessage(role=Role.USER, text="Say 'Hello, World!' and nothing else.")]
    chat_options = ChatOptions()

    response = await client._inner_get_response(messages=messages, chat_options=chat_options)

    assert response is not None
    assert len(response.messages) > 0
    assert response.messages[0].role == Role.ASSISTANT
    assert len(response.messages[0].contents) > 0


@skip_if_google_integration_tests_disabled
@pytest.mark.asyncio
async def test_integration_streaming_chat() -> None:
    """Integration test: Streaming chat completion."""
    client = GoogleAIChatClient()

    messages = [ChatMessage(role=Role.USER, text="Count from 1 to 3.")]
    chat_options = ChatOptions()

    chunks = []
    async for chunk in client._inner_get_streaming_response(messages=messages, chat_options=chat_options):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert all(isinstance(chunk, ChatResponseUpdate) for chunk in chunks)


@skip_if_google_integration_tests_disabled
@pytest.mark.asyncio
async def test_integration_system_instruction() -> None:
    """Integration test: Chat with system instruction."""
    client = GoogleAIChatClient()

    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a pirate. Always talk like a pirate."),
        ChatMessage(role=Role.USER, text="Hello!"),
    ]
    chat_options = ChatOptions()

    response = await client._inner_get_response(messages=messages, chat_options=chat_options)

    assert response is not None
    assert len(response.messages) > 0
    # Response should reflect pirate personality (though we can't validate content exactly)


# endregion

# region Fixtures


@pytest.fixture
def mock_google_client() -> MagicMock:
    """Fixture that returns a mock Google AI client."""
    return MagicMock(spec=genai.Client)


# endregion
