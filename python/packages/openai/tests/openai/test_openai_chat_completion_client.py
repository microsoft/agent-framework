# Copyright (c) Microsoft. All rights reserved.

import inspect
import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    ChatResponse,
    Content,
    Message,
    SupportsChatGetResponse,
    SupportsCodeInterpreterTool,
    SupportsFileSearchTool,
    SupportsImageGenerationTool,
    SupportsMCPTool,
    SupportsWebSearchTool,
    tool,
)
from agent_framework.exceptions import ChatClientException, SettingNotFoundError
from openai import BadRequestError
from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from pydantic import BaseModel
from pytest import param

from agent_framework_openai import OpenAIChatCompletionClient, RawOpenAIChatCompletionClient
from agent_framework_openai._exceptions import OpenAIContentFilterException

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests.",
)


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatCompletionClient()

    assert open_ai_chat_completion.model == openai_unit_test_env["OPENAI_MODEL"]
    assert isinstance(open_ai_chat_completion, SupportsChatGetResponse)


def test_get_response_docstring_surfaces_layered_runtime_docs() -> None:
    docstring = inspect.getdoc(OpenAIChatCompletionClient.get_response)

    assert docstring is not None
    assert "Get a response from a chat client." in docstring
    assert "function_invocation_kwargs" in docstring
    assert "middleware: Optional per-call chat and function middleware." in docstring
    assert "function_middleware: Optional per-call function middleware." not in docstring


def test_get_response_is_defined_on_openai_class() -> None:
    signature = inspect.signature(OpenAIChatCompletionClient.get_response)

    assert OpenAIChatCompletionClient.get_response.__qualname__ == "OpenAIChatCompletionClient.get_response"
    assert "middleware" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(RawOpenAIChatCompletionClient.__init__)

    assert "additional_properties" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_supports_web_search_only() -> None:
    assert not isinstance(OpenAIChatCompletionClient, SupportsCodeInterpreterTool)
    assert isinstance(OpenAIChatCompletionClient, SupportsWebSearchTool)
    assert not isinstance(OpenAIChatCompletionClient, SupportsImageGenerationTool)
    assert not isinstance(OpenAIChatCompletionClient, SupportsMCPTool)
    assert not isinstance(OpenAIChatCompletionClient, SupportsFileSearchTool)


def test_init_prefers_openai_chat_model(monkeypatch, openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_CHAT_COMPLETION_MODEL", "test_chat_model")

    open_ai_chat_completion = OpenAIChatCompletionClient()

    assert open_ai_chat_completion.model == "test_chat_model"


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ValueError):
        OpenAIChatCompletionClient(api_key="34523", model={"test": "dict"})  # type: ignore


def test_init_model_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model = "test_model"
    open_ai_chat_completion = OpenAIChatCompletionClient(model=model)

    assert open_ai_chat_completion.model == model
    assert isinstance(open_ai_chat_completion, SupportsChatGetResponse)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    open_ai_chat_completion = OpenAIChatCompletionClient(
        default_headers=default_headers,
    )

    assert open_ai_chat_completion.model == openai_unit_test_env["OPENAI_MODEL"]
    assert isinstance(open_ai_chat_completion, SupportsChatGetResponse)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in open_ai_chat_completion.client.default_headers
        assert open_ai_chat_completion.client.default_headers[key] == value


def test_init_base_url(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatCompletionClient(base_url="http://localhost:1234/v1")
    assert str(open_ai_chat_completion.client.base_url) == "http://localhost:1234/v1/"


def test_init_base_url_from_settings_env() -> None:
    """Test that base_url from OpenAISettings environment variable is properly used."""
    # Set environment variable for base_url
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "dummy",
            "OPENAI_MODEL": "gpt-5",
            "OPENAI_BASE_URL": "https://custom-openai-endpoint.com/v1",
        },
    ):
        client = OpenAIChatCompletionClient()
        assert client.model == "gpt-5"
        assert str(client.client.base_url) == "https://custom-openai-endpoint.com/v1/"


@pytest.mark.parametrize("exclude_list", [["OPENAI_MODEL"]], indirect=True)
def test_init_with_empty_model(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(SettingNotFoundError):
        OpenAIChatCompletionClient()


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    model = "test_model"

    with pytest.raises(SettingNotFoundError):
        OpenAIChatCompletionClient(
            model=model,
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "model": openai_unit_test_env["OPENAI_MODEL"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    open_ai_chat_completion = OpenAIChatCompletionClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["model"] == openai_unit_test_env["OPENAI_MODEL"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "model": openai_unit_test_env["OPENAI_MODEL"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    open_ai_chat_completion = OpenAIChatCompletionClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["model"] == openai_unit_test_env["OPENAI_MODEL"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings.get("default_headers", {})


async def test_content_filter_exception_handling(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that content filter errors are properly handled."""
    client = OpenAIChatCompletionClient()
    messages = [Message(role="user", contents=["test message"])]

    # Create a mock BadRequestError with content_filter code
    mock_response = MagicMock()
    mock_error = BadRequestError(
        message="Content filter error",
        response=mock_response,
        body={"error": {"code": "content_filter"}},
    )
    mock_error.code = "content_filter"

    # Mock the client to raise the content filter error
    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(OpenAIContentFilterException),
    ):
        await client._inner_get_response(messages=messages, options={})  # type: ignore


def test_unsupported_tool_handling(openai_unit_test_env: dict[str, str]) -> None:
    """Test that unsupported tool types are passed through unchanged."""
    client = OpenAIChatCompletionClient()

    # Create a random object that's not a FunctionTool, dict, or callable
    # This simulates an unsupported tool type that gets passed through
    class UnsupportedTool:
        pass

    unsupported_tool = UnsupportedTool()

    # Unsupported tools are passed through for the API to handle/reject
    result = client._prepare_tools_for_openai([unsupported_tool])  # type: ignore
    assert "tools" in result
    assert len(result["tools"]) == 1

    # Also test with a dict-based tool that should be passed through
    dict_tool = {"type": "function", "name": "test"}
    result = client._prepare_tools_for_openai([dict_tool])  # type: ignore
    assert result["tools"] == [dict_tool]


def test_mcp_tool_dict_passed_through_to_chat_api(openai_unit_test_env: dict[str, str]) -> None:
    """Test that MCP tool dicts are passed through unchanged by the chat client.

    The Chat Completions API does not support "type": "mcp" tools. MCP tools
    should be used with the Responses API client instead. This test documents
    that the chat client passes dict-based tools through without filtering,
    so callers must use the correct client for MCP tools.
    """
    client = OpenAIChatCompletionClient()

    mcp_tool = {
        "type": "mcp",
        "server_label": "Microsoft_Learn_MCP",
        "server_url": "https://learn.microsoft.com/api/mcp",
    }

    result = client._prepare_tools_for_openai(mcp_tool)
    assert "tools" in result
    assert len(result["tools"]) == 1
    # The chat client passes dict tools through unchanged, including unsupported types
    assert result["tools"][0]["type"] == "mcp"


@pytest.mark.asyncio
async def test_mcp_tool_dict_causes_api_rejection(openai_unit_test_env: dict[str, str]) -> None:
    """Test that MCP tool dicts passed to the Chat Completions API cause a rejection.

    The Chat Completions API only supports "type": "function" tools.
    When an MCP tool dict reaches the API, it returns a 400 error.
    This regression test for #4861 verifies the chat client does not
    silently drop or transform MCP dicts, so callers get a clear error
    rather than a silent no-op.
    """
    client = OpenAIChatCompletionClient()
    messages = [Message(role="user", contents=["test message"])]

    mcp_tool = {
        "type": "mcp",
        "server_label": "Microsoft_Learn_MCP",
        "server_url": "https://learn.microsoft.com/api/mcp",
    }

    mock_response = MagicMock()
    mock_error = BadRequestError(
        message="Invalid tool type: mcp",
        response=mock_response,
        body={"error": {"code": "invalid_request", "message": "Invalid tool type: mcp"}},
    )
    mock_error.code = "invalid_request"

    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(ChatClientException),
    ):
        await client._inner_get_response(messages=messages, options={"tools": mcp_tool})  # type: ignore


def test_prepare_tools_with_single_function_tool(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that a single FunctionTool is accepted for tool preparation."""
    client = OpenAIChatCompletionClient()

    @tool(approval_mode="never_require")
    def test_function(query: str) -> str:
        """A test function."""
        return f"Result for {query}"

    result = client._prepare_tools_for_openai(test_function)
    assert "tools" in result
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "function"


@tool(approval_mode="never_require")
def get_story_text() -> str:
    """Returns a story about Emily and David."""
    return (
        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
        "of climate change."
    )


@tool(approval_mode="never_require")
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny and 72°F."


async def test_exception_message_includes_original_error_details() -> None:
    """Test that exception messages include original error details in the new format."""
    client = OpenAIChatCompletionClient(model="test-model", api_key="test-key")
    messages = [Message(role="user", contents=["test message"])]

    mock_response = MagicMock()
    original_error_message = "Invalid API request format"
    mock_error = BadRequestError(
        message=original_error_message,
        response=mock_response,
        body={"error": {"code": "invalid_request", "message": original_error_message}},
    )
    mock_error.code = "invalid_request"

    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(ChatClientException) as exc_info,
    ):
        await client._inner_get_response(messages=messages, options={})  # type: ignore

    exception_message = str(exc_info.value)
    assert "service failed to complete the prompt:" in exception_message
    assert original_error_message in exception_message


def test_chat_response_content_order_text_before_tool_calls(
    openai_unit_test_env: dict[str, str],
):
    """Test that text content appears before tool calls in ChatResponse contents."""
    # Import locally to avoid break other tests when the import changes
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage
    from openai.types.chat.chat_completion_message_tool_call import (
        ChatCompletionMessageToolCall,
        Function,
    )

    # Create a mock OpenAI response with both text and tool calls
    mock_response = ChatCompletion(
        id="test-response",
        object="chat.completion",
        created=1234567890,
        model="gpt-4o-mini",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content="I'll help you with that calculation.",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call-123",
                            type="function",
                            function=Function(name="calculate", arguments='{"x": 5, "y": 3}'),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
    )

    client = OpenAIChatCompletionClient()
    response = client._parse_response_from_openai(mock_response, {})

    # Verify we have both text and tool call content
    assert len(response.messages) == 1
    message = response.messages[0]
    assert len(message.contents) == 2

    # Verify text content comes first, tool call comes second
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "I'll help you with that calculation."
    assert message.contents[1].type == "function_call"
    assert message.contents[1].name == "calculate"


def test_function_result_falsy_values_handling(openai_unit_test_env: dict[str, str]):
    """Test that falsy values (like empty list) in function result are properly handled.

    Note: In practice, FunctionTool.invoke() always returns a pre-parsed string.
    These tests verify that the OpenAI client correctly passes through string results.
    """
    client = OpenAIChatCompletionClient()

    # Test with empty list serialized as JSON string (pre-serialized result passed to from_function_result)
    message_with_empty_list = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-123", result="[]")],
    )

    openai_messages = client._prepare_message_for_openai(message_with_empty_list)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "[]"  # Empty list JSON string

    # Test with empty string (falsy but not None)
    message_with_empty_string = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-456", result="")],
    )

    openai_messages = client._prepare_message_for_openai(message_with_empty_string)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == ""  # Empty string should be preserved

    # Test with False serialized as JSON string (pre-serialized result passed to from_function_result)
    message_with_false = Message(
        role="tool",
        contents=[Content.from_function_result(call_id="call-789", result="false")],
    )

    openai_messages = client._prepare_message_for_openai(message_with_false)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "false"  # False JSON string


def test_function_result_exception_handling(openai_unit_test_env: dict[str, str]):
    """Test that exceptions in function result are properly handled.

    Feel free to remove this test in case there's another new behavior.
    """
    client = OpenAIChatCompletionClient()

    # Test with exception (no result)
    test_exception = ValueError("Test error message")
    message_with_exception = Message(
        role="tool",
        contents=[
            Content.from_function_result(
                call_id="call-123",
                result="Error: Function failed.",
                exception=test_exception,
            )
        ],
    )

    openai_messages = client._prepare_message_for_openai(message_with_exception)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "Error: Function failed."
    assert openai_messages[0]["tool_call_id"] == "call-123"


def test_function_result_with_rich_items_warns_and_omits(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that function_result with items logs a warning and omits rich items."""

    client = OpenAIChatCompletionClient()
    image_content = Content.from_data(data=b"image_bytes", media_type="image/png")
    message = Message(
        role="tool",
        contents=[
            Content.from_function_result(
                call_id="call_rich",
                result=[Content.from_text("Result text"), image_content],
            )
        ],
    )

    with patch("agent_framework_openai._chat_completion_client.logger") as mock_logger:
        openai_messages = client._prepare_message_for_openai(message)

    # Warning should be logged
    mock_logger.warning.assert_called_once()
    assert "does not support rich content" in mock_logger.warning.call_args[0][0]

    # Tool message should still be emitted with text result
    assert len(openai_messages) == 1
    assert openai_messages[0]["role"] == "tool"
    assert openai_messages[0]["tool_call_id"] == "call_rich"
    assert openai_messages[0]["content"] == "Result text"


def test_parse_result_string_passthrough():
    """Test that string values are wrapped in Content."""
    from agent_framework import FunctionTool

    result = FunctionTool.parse_result("simple string")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].text == "simple string"


def test_prepare_content_for_openai_data_content_image(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test _prepare_content_for_openai converts DataContent with image media type to OpenAI format."""
    client = OpenAIChatCompletionClient()

    # Test DataContent with image media type
    image_data_content = Content.from_uri(
        uri="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
        media_type="image/png",
    )

    result = client._prepare_content_for_openai(image_data_content)  # type: ignore

    # Should convert to OpenAI image_url format
    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == image_data_content.uri

    # Test DataContent with non-image media type should use default model_dump
    text_data_content = Content.from_uri(uri="data:text/plain;base64,SGVsbG8gV29ybGQ=", media_type="text/plain")

    result = client._prepare_content_for_openai(text_data_content)  # type: ignore

    # Should use default model_dump format
    assert result["type"] == "data"
    assert result["uri"] == text_data_content.uri
    assert result["media_type"] == "text/plain"

    # Test DataContent with audio media type
    audio_data_content = Content.from_uri(
        uri="data:audio/wav;base64,UklGRjBEAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQwEAAAAAAAAAAAA",
        media_type="audio/wav",
    )

    result = client._prepare_content_for_openai(audio_data_content)  # type: ignore

    # Should convert to OpenAI input_audio format
    assert result["type"] == "input_audio"
    # Data should contain just the base64 part, not the full data URI
    assert result["input_audio"]["data"] == "UklGRjBEAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQwEAAAAAAAAAAAA"
    assert result["input_audio"]["format"] == "wav"

    # Test DataContent with MP3 audio
    mp3_data_content = Content.from_uri(
        uri="data:audio/mp3;base64,//uQAAAAWGluZwAAAA8AAAACAAACcQ==",
        media_type="audio/mp3",
    )

    result = client._prepare_content_for_openai(mp3_data_content)  # type: ignore

    # Should convert to OpenAI input_audio format with mp3
    assert result["type"] == "input_audio"
    # Data should contain just the base64 part, not the full data URI
    assert result["input_audio"]["data"] == "//uQAAAAWGluZwAAAA8AAAACAAACcQ=="
    assert result["input_audio"]["format"] == "mp3"


def test_prepare_content_for_openai_image_url_detail(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test _prepare_content_for_openai includes the detail field in image_url when specified."""
    client = OpenAIChatCompletionClient()

    # Test image with detail set to "high"
    image_with_detail = Content.from_uri(
        uri="https://example.com/image.png",
        media_type="image/png",
        additional_properties={"detail": "high"},
    )

    result = client._prepare_content_for_openai(image_with_detail)  # type: ignore

    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == "https://example.com/image.png"
    assert result["image_url"]["detail"] == "high"

    # Test image with detail set to "low"
    image_low_detail = Content.from_uri(
        uri="https://example.com/image.png",
        media_type="image/png",
        additional_properties={"detail": "low"},
    )

    result = client._prepare_content_for_openai(image_low_detail)  # type: ignore

    assert result["image_url"]["detail"] == "low"

    # Test image with detail set to "auto"
    image_auto_detail = Content.from_uri(
        uri="https://example.com/image.png",
        media_type="image/png",
        additional_properties={"detail": "auto"},
    )

    result = client._prepare_content_for_openai(image_auto_detail)  # type: ignore

    assert result["image_url"]["detail"] == "auto"

    # Test image without detail should not include it
    image_no_detail = Content.from_uri(
        uri="https://example.com/image.png",
        media_type="image/png",
    )

    result = client._prepare_content_for_openai(image_no_detail)  # type: ignore

    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == "https://example.com/image.png"
    assert "detail" not in result["image_url"]

    # Test image with a future/unknown string detail value should pass it through
    image_future_detail = Content.from_uri(
        uri="https://example.com/image.png",
        media_type="image/png",
        additional_properties={"detail": "ultra"},
    )

    result = client._prepare_content_for_openai(image_future_detail)  # type: ignore

    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == "https://example.com/image.png"
    assert result["image_url"]["detail"] == "ultra"

    # Test image with data URI should include detail
    image_data_uri = Content.from_uri(
        uri="data:image/png;base64,iVBORw0KGgo",
        media_type="image/png",
        additional_properties={"detail": "high"},
    )

    result = client._prepare_content_for_openai(image_data_uri)  # type: ignore

    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == "data:image/png;base64,iVBORw0KGgo"
    assert result["image_url"]["detail"] == "high"

    # Test image with non-string detail value should not include it
    image_non_string_detail = Content.from_uri(
        uri="https://example.com/image.png",
        media_type="image/png",
        additional_properties={"detail": 123},
    )

    result = client._prepare_content_for_openai(image_non_string_detail)  # type: ignore

    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == "https://example.com/image.png"
    assert "detail" not in result["image_url"]


def test_prepare_content_for_openai_document_file_mapping(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test _prepare_content_for_openai converts document files (PDF, DOCX, etc.) to OpenAI file format."""
    client = OpenAIChatCompletionClient()

    # Test PDF without filename - should omit filename in OpenAI payload
    pdf_data_content = Content.from_uri(
        uri="data:application/pdf;base64,JVBERi0xLjQKJcfsj6IKNSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXS9QYXJlbnQgMiAwIFIvUmVzb3VyY2VzPDwvRm9udDw8L0YxIDQgMCBSPj4+Pi9Db250ZW50cyA1IDAgUj4+CmVuZG9iago0IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYT4+CmVuZG9iago1IDAgb2JqCjw8L0xlbmd0aCA0ND4+CnN0cmVhbQpCVApxCjcwIDUwIFRECi9GMSA4IFRmCihIZWxsbyBXb3JsZCEpIFRqCkVUCmVuZHN0cmVhbQplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwNTggMDAwMDAgbiAKMDAwMDAwMDExNSAwMDAwMCBuIAowMDAwMDAwMjQ1IDAwMDAwIG4gCjAwMDAwMDAzMDcgMDAwMDAgbiAKdHJhaWxlcgo8PC9TaXplIDYvUm9vdCAxIDAgUj4+CnN0YXJ0eHJlZgo0MDUKJSVFT0Y=",
        media_type="application/pdf",
    )

    result = client._prepare_content_for_openai(pdf_data_content)  # type: ignore

    # Should convert to OpenAI file format without filename
    assert result["type"] == "file"
    assert "filename" not in result["file"]  # No filename provided, so none should be set
    assert "file_data" in result["file"]
    # Base64 data should be the full data URI (OpenAI requirement)
    assert result["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert result["file"]["file_data"] == pdf_data_content.uri

    # Test PDF with custom filename via additional_properties
    pdf_with_filename = Content.from_uri(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={"filename": "report.pdf"},
    )

    result = client._prepare_content_for_openai(pdf_with_filename)  # type: ignore

    # Should use custom filename
    assert result["type"] == "file"
    assert result["file"]["filename"] == "report.pdf"
    assert result["file"]["file_data"] == "data:application/pdf;base64,JVBERi0xLjQ="

    # Test different application/* media types - all should now be mapped to file format
    test_cases = [
        {
            "media_type": "application/json",
            "filename": "data.json",
            "base64": "eyJrZXkiOiJ2YWx1ZSJ9",
        },
        {
            "media_type": "application/xml",
            "filename": "config.xml",
            "base64": "PD94bWwgdmVyc2lvbj0iMS4wIj8+",
        },
        {
            "media_type": "application/octet-stream",
            "filename": "binary.bin",
            "base64": "AQIDBAUGBwgJCg==",
        },
    ]

    for case in test_cases:
        # Test without filename
        doc_content = Content.from_uri(
            uri=f"data:{case['media_type']};base64,{case['base64']}",
            media_type=case["media_type"],
        )

        result = client._prepare_content_for_openai(doc_content)  # type: ignore

        # All application/* types should now be mapped to file format
        assert result["type"] == "file"
        assert "filename" not in result["file"]  # Should omit filename when not provided
        assert result["file"]["file_data"] == doc_content.uri

        # Test with filename - should now use file format with filename
        doc_with_filename = Content.from_uri(
            uri=f"data:{case['media_type']};base64,{case['base64']}",
            media_type=case["media_type"],
            additional_properties={"filename": case["filename"]},
        )

        result = client._prepare_content_for_openai(doc_with_filename)  # type: ignore

        # Should now use file format with filename
        assert result["type"] == "file"
        assert result["file"]["filename"] == case["filename"]
        assert result["file"]["file_data"] == doc_with_filename.uri

    # Test edge case: empty additional_properties dict
    pdf_empty_props = Content.from_uri(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={},
    )

    result = client._prepare_content_for_openai(pdf_empty_props)  # type: ignore

    assert result["type"] == "file"
    assert "filename" not in result["file"]

    # Test edge case: None filename in additional_properties
    pdf_none_filename = Content.from_uri(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={"filename": None},
    )

    result = client._prepare_content_for_openai(pdf_none_filename)  # type: ignore

    assert result["type"] == "file"
    assert "filename" not in result["file"]  # None filename should be omitted


def test_parse_text_reasoning_content_from_response(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that TextReasoningContent is correctly parsed from OpenAI response with reasoning_details."""

    client = OpenAIChatCompletionClient()

    # Mock response with reasoning_details
    mock_reasoning_details = {
        "effort": "high",
        "summary": "Analyzed the problem carefully",
        "content": [{"type": "reasoning_text", "text": "Step-by-step thinking..."}],
    }

    mock_response = ChatCompletion(
        id="test-response",
        object="chat.completion",
        created=1234567890,
        model="gpt-5",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content="The answer is 42.",
                    reasoning_details=mock_reasoning_details,
                ),
                finish_reason="stop",
            )
        ],
    )

    response = client._parse_response_from_openai(mock_response, {})

    # Should have both text and reasoning content
    assert len(response.messages) == 1
    message = response.messages[0]
    assert len(message.contents) == 2

    # First should be text content
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "The answer is 42."

    # Second should be reasoning content with protected_data
    assert message.contents[1].type == "text_reasoning"
    assert message.contents[1].protected_data is not None
    parsed_details = json.loads(message.contents[1].protected_data)
    assert parsed_details == mock_reasoning_details


def test_parse_text_reasoning_content_from_streaming_chunk(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that TextReasoningContent is correctly parsed from streaming OpenAI chunk with reasoning_details."""
    from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
    from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
    from openai.types.chat.chat_completion_chunk import ChoiceDelta as ChunkChoiceDelta

    client = OpenAIChatCompletionClient()

    # Mock streaming chunk with reasoning_details
    mock_reasoning_details = {
        "type": "reasoning",
        "content": "Analyzing the question...",
    }

    mock_chunk = ChatCompletionChunk(
        id="test-chunk",
        object="chat.completion.chunk",
        created=1234567890,
        model="gpt-5",
        choices=[
            ChunkChoice(
                index=0,
                delta=ChunkChoiceDelta(
                    role="assistant",
                    content="Partial answer",
                    reasoning_details=mock_reasoning_details,
                ),
                finish_reason=None,
            )
        ],
    )

    update = client._parse_response_update_from_openai(mock_chunk)

    # Should have both text and reasoning content
    assert len(update.contents) == 2

    # First should be text content
    assert update.contents[0].type == "text"
    assert update.contents[0].text == "Partial answer"

    # Second should be reasoning content
    assert update.contents[1].type == "text_reasoning"
    assert update.contents[1].protected_data is not None
    parsed_details = json.loads(update.contents[1].protected_data)
    assert parsed_details == mock_reasoning_details


def test_prepare_message_with_text_reasoning_content(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that TextReasoningContent with protected_data is correctly prepared for OpenAI."""
    client = OpenAIChatCompletionClient()

    # Create message with text_reasoning content that has protected_data
    # text_reasoning is meant to be added to an existing message, so include text content first
    mock_reasoning_data = {
        "effort": "medium",
        "summary": "Quick analysis",
    }

    reasoning_content = Content.from_text_reasoning(text=None, protected_data=json.dumps(mock_reasoning_data))

    # Message must have other content first for reasoning to attach to
    message = Message(
        role="assistant",
        contents=[
            Content.from_text(text="The answer is 42."),
            reasoning_content,
        ],
    )

    prepared = client._prepare_message_for_openai(message)

    # Should have one message with reasoning_details attached
    assert len(prepared) == 1
    assert "reasoning_details" in prepared[0]
    assert prepared[0]["reasoning_details"] == mock_reasoning_data
    # Should also have the text content (flattened to string for text-only)
    assert prepared[0]["content"] == "The answer is 42."


def test_prepare_message_with_only_text_reasoning_content(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that a message with only text_reasoning content does not raise IndexError.

    Regression test for https://github.com/microsoft/agent-framework/issues/4384
    Reasoning models (e.g. gpt-5-mini) may produce reasoning_details without text content,
    which previously caused an IndexError when preparing messages.
    """
    client = OpenAIChatCompletionClient()

    mock_reasoning_data = {
        "effort": "high",
        "summary": "Deep analysis of the problem",
    }

    reasoning_content = Content.from_text_reasoning(text=None, protected_data=json.dumps(mock_reasoning_data))

    # Message with only reasoning content and no text
    message = Message(
        role="assistant",
        contents=[reasoning_content],
    )

    prepared = client._prepare_message_for_openai(message)

    # Should have one message with reasoning_details
    assert len(prepared) == 1
    assert prepared[0]["role"] == "assistant"
    assert "reasoning_details" in prepared[0]
    assert prepared[0]["reasoning_details"] == mock_reasoning_data
    # Message should also include a content field to be a valid Chat Completions payload
    assert "content" in prepared[0]
    assert prepared[0]["content"] == ""


def test_prepare_message_with_text_reasoning_before_text(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that text_reasoning content appearing before text content is handled correctly.

    Regression test for https://github.com/microsoft/agent-framework/issues/4384
    """
    client = OpenAIChatCompletionClient()

    mock_reasoning_data = {
        "effort": "medium",
        "summary": "Quick analysis",
    }

    reasoning_content = Content.from_text_reasoning(text=None, protected_data=json.dumps(mock_reasoning_data))

    # Reasoning appears before text content
    message = Message(
        role="assistant",
        contents=[
            reasoning_content,
            Content.from_text(text="The answer is 42."),
        ],
    )

    prepared = client._prepare_message_for_openai(message)

    # Should produce exactly one message without raising IndexError
    assert len(prepared) == 1

    # Reasoning details should be present on the message
    assert "reasoning_details" in prepared[0]
    assert prepared[0]["reasoning_details"] == mock_reasoning_data
    assert prepared[0]["content"] == "The answer is 42."


def test_prepare_message_with_text_reasoning_before_function_call(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that text_reasoning content appearing before a function call is handled correctly.

    Regression test for https://github.com/microsoft/agent-framework/issues/4384
    """
    client = OpenAIChatCompletionClient()

    mock_reasoning_data = {
        "effort": "medium",
        "summary": "Deciding to call a function",
    }

    reasoning_content = Content.from_text_reasoning(text=None, protected_data=json.dumps(mock_reasoning_data))

    # Reasoning appears before function call content
    message = Message(
        role="assistant",
        contents=[
            reasoning_content,
            Content.from_function_call(call_id="call_abc", name="get_weather", arguments='{"city": "Seattle"}'),
        ],
    )

    prepared = client._prepare_message_for_openai(message)

    # Should produce exactly one message
    assert len(prepared) == 1

    # The message should carry the reasoning details and tool_calls
    assert "reasoning_details" in prepared[0]
    assert prepared[0]["reasoning_details"] == mock_reasoning_data
    assert "tool_calls" in prepared[0]
    assert prepared[0]["tool_calls"][0]["function"]["name"] == "get_weather"
    assert prepared[0]["role"] == "assistant"


def test_function_approval_content_is_skipped_in_preparation(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that function approval request and response content are skipped."""
    client = OpenAIChatCompletionClient()

    # Create approval request
    function_call = Content.from_function_call(
        call_id="call_123",
        name="dangerous_action",
        arguments='{"confirm": true}',
    )

    approval_request = Content.from_function_approval_request(
        id="approval_001",
        function_call=function_call,
    )

    # Create approval response
    approval_response = Content.from_function_approval_response(
        approved=False,
        id="approval_001",
        function_call=function_call,
    )

    # Test that approval request is skipped
    message_with_request = Message(role="assistant", contents=[approval_request])
    prepared_request = client._prepare_message_for_openai(message_with_request)
    assert len(prepared_request) == 0  # Should be empty - approval content is skipped

    # Test that approval response is skipped
    message_with_response = Message(role="user", contents=[approval_response])
    prepared_response = client._prepare_message_for_openai(message_with_response)
    assert len(prepared_response) == 0  # Should be empty - approval content is skipped

    # Test with mixed content - approval should be skipped, text should remain
    mixed_message = Message(
        role="assistant",
        contents=[
            Content.from_text(text="I need approval for this action."),
            approval_request,
        ],
    )
    prepared_mixed = client._prepare_message_for_openai(mixed_message)
    assert len(prepared_mixed) == 1  # Only text content should remain
    assert prepared_mixed[0]["content"] == "I need approval for this action."


def test_usage_content_in_streaming_response(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that UsageContent is correctly parsed from streaming response with usage data."""
    from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
    from openai.types.completion_usage import CompletionUsage

    client = OpenAIChatCompletionClient()

    # Mock streaming chunk with usage data (typically last chunk)
    mock_usage = CompletionUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )

    mock_chunk = ChatCompletionChunk(
        id="test-chunk",
        object="chat.completion.chunk",
        created=1234567890,
        model="gpt-4o",
        choices=[],  # Empty choices when sending usage
        usage=mock_usage,
    )

    update = client._parse_response_update_from_openai(mock_chunk)

    # Should have usage content
    assert len(update.contents) == 1
    assert update.contents[0].type == "usage"

    usage_content = update.contents[0]
    assert isinstance(usage_content.usage_details, dict)
    assert usage_content.usage_details["input_token_count"] == 100
    assert usage_content.usage_details["output_token_count"] == 50
    assert usage_content.usage_details["total_token_count"] == 150


def test_streaming_chunk_with_usage_and_text(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that text content is not lost when usage data is in the same chunk.

    Some providers (e.g. Gemini) include both usage and text content in the
    same streaming chunk. See https://github.com/microsoft/agent-framework/issues/3434
    """
    from openai.types.chat.chat_completion_chunk import (
        ChatCompletionChunk,
        Choice,
        ChoiceDelta,
    )
    from openai.types.completion_usage import CompletionUsage

    client = OpenAIChatCompletionClient()

    mock_chunk = ChatCompletionChunk(
        id="test-chunk",
        object="chat.completion.chunk",
        created=1234567890,
        model="gemini-2.0-flash-lite",
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(content="Hello world", role="assistant"),
                finish_reason=None,
            )
        ],
        usage=CompletionUsage(prompt_tokens=18, completion_tokens=5, total_tokens=23),
    )

    update = client._parse_response_update_from_openai(mock_chunk)

    # Should have BOTH text and usage content
    content_types = [c.type for c in update.contents]
    assert "text" in content_types, "Text content should not be lost when usage is present"
    assert "usage" in content_types, "Usage content should still be present"

    text_content = next(c for c in update.contents if c.type == "text")
    assert text_content.text == "Hello world"


def test_parse_text_with_refusal(openai_unit_test_env: dict[str, str]) -> None:
    """Test that refusal content is parsed correctly."""
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage

    client = OpenAIChatCompletionClient()

    # Mock response with refusal
    mock_response = ChatCompletion(
        id="test-response",
        object="chat.completion",
        created=1234567890,
        model="gpt-4o",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=None,
                    refusal="I cannot provide that information.",
                ),
                finish_reason="stop",
            )
        ],
    )

    response = client._parse_response_from_openai(mock_response, {})

    # Should have text content with refusal message
    assert len(response.messages) == 1
    message = response.messages[0]
    assert len(message.contents) == 1
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "I cannot provide that information."


def test_prepare_options_without_model(openai_unit_test_env: dict[str, str]) -> None:
    """Test that prepare_options raises error when model is not set."""
    client = OpenAIChatCompletionClient()
    client.model = None  # Remove model

    messages = [Message(role="user", contents=["test"])]

    with pytest.raises(ValueError, match="model must be a non-empty string"):
        client._prepare_options(messages, {})


def test_prepare_options_without_messages(openai_unit_test_env: dict[str, str]) -> None:
    """Test that prepare_options raises error when messages are missing."""
    from agent_framework.exceptions import ChatClientInvalidRequestException

    client = OpenAIChatCompletionClient()

    with pytest.raises(ChatClientInvalidRequestException, match="Messages are required"):
        client._prepare_options([], {})


def test_prepare_tools_with_web_search_no_location(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test preparing web search tool without user location."""
    client = OpenAIChatCompletionClient()

    # Web search tool using static method
    web_search_tool = OpenAIChatCompletionClient.get_web_search_tool()

    result = client._prepare_tools_for_openai([web_search_tool])

    # Should have empty web_search_options (no location)
    assert "web_search_options" in result
    assert result["web_search_options"] == {}


def test_prepare_options_with_instructions(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that instructions are prepended as system message."""
    client = OpenAIChatCompletionClient()

    messages = [Message(role="user", contents=["Hello"])]
    options = {"instructions": "You are a helpful assistant."}

    prepared_options = client._prepare_options(messages, options)

    # Should have messages with system message prepended
    assert "messages" in prepared_options
    assert len(prepared_options["messages"]) == 2
    assert prepared_options["messages"][0]["role"] == "system"
    assert prepared_options["messages"][0]["content"] == "You are a helpful assistant."


def test_prepare_options_with_instructions_no_duplicate(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that duplicate system message from instructions is not added again.

    Regression test for https://github.com/microsoft/agent-framework/issues/5049
    """
    client = OpenAIChatCompletionClient()

    # Simulate messages that already contain the system instruction
    messages = [
        Message(role="system", contents=["You are a helpful assistant."]),
        Message(role="user", contents=["Hello"]),
    ]
    options = {"instructions": "You are a helpful assistant."}

    prepared_options = client._prepare_options(messages, options)

    # Should NOT duplicate the system message
    assert "messages" in prepared_options
    assert len(prepared_options["messages"]) == 2
    assert prepared_options["messages"][0]["role"] == "system"
    assert prepared_options["messages"][0]["content"] == "You are a helpful assistant."
    assert prepared_options["messages"][1]["role"] == "user"


def test_prepare_message_with_author_name(openai_unit_test_env: dict[str, str]) -> None:
    """Test that author_name is included in prepared message."""
    client = OpenAIChatCompletionClient()

    message = Message(
        role="user",
        author_name="TestUser",
        contents=[Content.from_text(text="Hello")],
    )

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    assert prepared[0]["name"] == "TestUser"


def test_prepare_message_with_tool_result_author_name(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that author_name is not included for TOOL role messages."""
    client = OpenAIChatCompletionClient()

    # Tool messages should not have 'name' field (it's for function name instead)
    message = Message(
        role="tool",
        author_name="ShouldNotAppear",
        contents=[Content.from_function_result(call_id="call_123", result="result")],
    )

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    # Should not have 'name' field for tool messages
    assert "name" not in prepared[0]


def test_prepare_system_message_content_is_string(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that system message content is a plain string, not a list.

    Some OpenAI-compatible endpoints (e.g. NVIDIA NIM) reject system messages
    with list content. See https://github.com/microsoft/agent-framework/issues/1407
    """
    client = OpenAIChatCompletionClient()

    message = Message(role="system", contents=[Content.from_text(text="You are a helpful assistant.")])

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    assert prepared[0]["role"] == "system"
    assert isinstance(prepared[0]["content"], str)
    assert prepared[0]["content"] == "You are a helpful assistant."


def test_prepare_developer_message_content_is_string(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that developer message content is a plain string, not a list."""
    client = OpenAIChatCompletionClient()

    message = Message(role="developer", contents=[Content.from_text(text="Follow these rules.")])

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    assert prepared[0]["role"] == "developer"
    assert isinstance(prepared[0]["content"], str)
    assert prepared[0]["content"] == "Follow these rules."


def test_prepare_system_message_multiple_text_contents_joined(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that system messages with multiple text contents are joined into a single string."""
    client = OpenAIChatCompletionClient()

    message = Message(
        role="system",
        contents=[
            Content.from_text(text="You are a helpful assistant."),
            Content.from_text(text="Be concise."),
        ],
    )

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    assert prepared[0]["role"] == "system"
    assert isinstance(prepared[0]["content"], str)
    assert prepared[0]["content"] == "You are a helpful assistant.\nBe concise."


def test_prepare_user_message_text_content_is_string(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that text-only user message content is flattened to a plain string.

    Some OpenAI-compatible endpoints (e.g. Foundry Local) cannot deserialize
    the list format. See https://github.com/microsoft/agent-framework/issues/4084
    """
    client = OpenAIChatCompletionClient()

    message = Message(role="user", contents=[Content.from_text(text="Hello")])

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    assert prepared[0]["role"] == "user"
    assert isinstance(prepared[0]["content"], str)
    assert prepared[0]["content"] == "Hello"


def test_prepare_user_message_multimodal_content_remains_list(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that multimodal user message content remains a list."""
    client = OpenAIChatCompletionClient()

    message = Message(
        role="user",
        contents=[
            Content.from_text(text="What's in this image?"),
            Content.from_uri(uri="https://example.com/image.png", media_type="image/png"),
        ],
    )

    prepared = client._prepare_message_for_openai(message)

    # Multimodal content must stay as list for the API
    has_list_content = any(isinstance(m.get("content"), list) for m in prepared)
    assert has_list_content


def test_prepare_assistant_message_text_content_is_string(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that text-only assistant message content is flattened to a plain string."""
    client = OpenAIChatCompletionClient()

    message = Message(role="assistant", contents=[Content.from_text(text="Sure, I can help.")])

    prepared = client._prepare_message_for_openai(message)

    assert len(prepared) == 1
    assert prepared[0]["role"] == "assistant"
    assert isinstance(prepared[0]["content"], str)
    assert prepared[0]["content"] == "Sure, I can help."


def test_tool_choice_required_with_function_name(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that tool_choice with required mode and function name is correctly prepared."""
    client = OpenAIChatCompletionClient()

    messages = [Message(role="user", contents=["test"])]
    options = {
        "tools": [get_weather],
        "tool_choice": {"mode": "required", "required_function_name": "get_weather"},
    }

    prepared_options = client._prepare_options(messages, options)

    # Should format tool_choice correctly
    assert "tool_choice" in prepared_options
    assert prepared_options["tool_choice"]["type"] == "function"
    assert prepared_options["tool_choice"]["function"]["name"] == "get_weather"


def test_response_format_dict_passthrough(openai_unit_test_env: dict[str, str]) -> None:
    """Test that response_format as dict is passed through directly."""
    client = OpenAIChatCompletionClient()

    messages = [Message(role="user", contents=["test"])]
    custom_format = {
        "type": "json_schema",
        "json_schema": {"name": "Test", "schema": {"type": "object"}},
    }
    options = {"response_format": custom_format}

    prepared_options = client._prepare_options(messages, options)

    # Should pass through the dict directly
    assert prepared_options["response_format"] == custom_format


def test_parse_response_with_dict_response_format(openai_unit_test_env: dict[str, str]) -> None:
    """Chat completions should parse dict response_format values into response.value."""
    client = OpenAIChatCompletionClient()
    response = client._parse_response_from_openai(
        ChatCompletion(
            id="test-response",
            object="chat.completion",
            created=1234567890,
            model="gpt-4o-mini",
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(role="assistant", content='{"answer": "Hello"}'),
                    finish_reason="stop",
                )
            ],
        ),
        options={"response_format": {"type": "object", "properties": {"answer": {"type": "string"}}}},
    )

    assert response.value is not None
    assert isinstance(response.value, dict)
    assert response.value["answer"] == "Hello"


def test_multiple_function_calls_in_single_message(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that multiple function calls in a message are correctly prepared."""
    client = OpenAIChatCompletionClient()

    # Create message with multiple function calls
    message = Message(
        role="assistant",
        contents=[
            Content.from_function_call(call_id="call_1", name="func_1", arguments='{"a": 1}'),
            Content.from_function_call(call_id="call_2", name="func_2", arguments='{"b": 2}'),
        ],
    )

    prepared = client._prepare_message_for_openai(message)

    # Should have one message with multiple tool_calls
    assert len(prepared) == 1
    assert "tool_calls" in prepared[0]
    assert len(prepared[0]["tool_calls"]) == 2
    assert prepared[0]["tool_calls"][0]["id"] == "call_1"
    assert prepared[0]["tool_calls"][1]["id"] == "call_2"


def test_prepare_options_removes_parallel_tool_calls_when_no_tools(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that parallel_tool_calls is removed when no tools are present."""
    client = OpenAIChatCompletionClient()

    messages = [Message(role="user", contents=["test"])]
    options = {"allow_multiple_tool_calls": True}

    prepared_options = client._prepare_options(messages, options)

    # Should not have parallel_tool_calls when no tools
    assert "parallel_tool_calls" not in prepared_options


def test_prepare_options_excludes_conversation_id(openai_unit_test_env: dict[str, str]) -> None:
    """Test that conversation_id is excluded from prepared options for chat completions."""
    client = OpenAIChatCompletionClient()

    messages = [Message(role="user", contents=["test"])]
    options = {"conversation_id": "12345", "temperature": 0.7}

    prepared_options = client._prepare_options(messages, options)

    # conversation_id is not a valid parameter for AsyncCompletions.create()
    assert "conversation_id" not in prepared_options
    # Other options should still be present
    assert prepared_options["temperature"] == 0.7


async def test_streaming_exception_handling(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that streaming errors are properly handled."""
    client = OpenAIChatCompletionClient()
    messages = [Message(role="user", contents=["test"])]

    # Create a mock error during streaming
    mock_error = Exception("Streaming error")

    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(ChatClientException),
    ):
        async for _ in client._inner_get_response(messages=messages, stream=True, options={}):  # type: ignore
            pass


# region Integration Tests


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str | None = None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        # Simple ChatOptions - just verify they don't fail
        param("temperature", 0.7, False, id="temperature"),
        param("top_p", 0.9, False, id="top_p"),
        param("max_tokens", 500, False, id="max_tokens"),
        param("seed", 123, False, id="seed"),
        param("user", "test-user-id", False, id="user"),
        param("frequency_penalty", 0.5, False, id="frequency_penalty"),
        param("presence_penalty", 0.3, False, id="presence_penalty"),
        param("stop", ["END"], False, id="stop"),
        param("allow_multiple_tool_calls", True, False, id="allow_multiple_tool_calls"),
        # OpenAIChatCompletionOptions - just verify they don't fail
        param("logit_bias", {"50256": -1}, False, id="logit_bias"),
        param(
            "prediction",
            {"type": "content", "content": "hello world"},
            False,
            id="prediction",
        ),
        # Complex options requiring output validation
        param("tools", [get_weather], True, id="tools_function"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        param("tool_choice", "required", False, id="tool_choice_required_any"),
        param(
            "tool_choice",
            {"mode": "required", "required_function_name": "get_weather"},
            False,
            id="tool_choice_required",
        ),
        param("response_format", OutputStruct, True, id="response_format_pydantic"),
        param(
            "response_format",
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "WeatherDigest",
                    "strict": True,
                    "schema": {
                        "title": "WeatherDigest",
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                            "conditions": {"type": "string"},
                            "temperature_c": {"type": "number"},
                            "advisory": {"type": "string"},
                        },
                        "required": [
                            "location",
                            "conditions",
                            "temperature_c",
                            "advisory",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            True,
            id="response_format_runtime_json_schema",
        ),
    ],
)
async def test_integration_options(
    option_name: str,
    option_value: Any,
    needs_validation: bool,
) -> None:
    """Parametrized test covering all ChatOptions and OpenAIChatCompletionOptions.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.
    """
    client = OpenAIChatCompletionClient()
    # Need at least 2 iterations for tool_choice tests: one to get function call, one to get final response
    client.function_invocation_configuration["max_iterations"] = 2

    # Prepare test message
    if option_name.startswith("tools") or option_name.startswith("tool_choice"):
        # Use weather-related prompt for tool tests
        messages = [Message(role="user", contents=["What is the weather in Seattle?"])]
    elif option_name.startswith("response_format"):
        # Use prompt that works well with structured output
        messages = [Message(role="user", contents=["The weather in Seattle is sunny"])]
        messages.append(Message(role="user", contents=["What is the weather in Seattle?"]))
    else:
        # Generic prompt for simple options
        messages = [Message(role="user", contents=["Say 'Hello World' briefly."])]

    # Build options dict
    options: dict[str, Any] = {option_name: option_value}

    # Add tools if testing tool_choice to avoid errors
    if option_name.startswith("tool_choice"):
        options["tools"] = [get_weather]

    # Test streaming mode
    response = await client.get_response(
        messages=messages,
        stream=True,
        options=options,
    ).get_final_response()

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert response.messages is not None
    if not option_name.startswith("tool_choice") and (
        (isinstance(option_value, str) and option_value != "required")
        or (isinstance(option_value, dict) and option_value.get("mode") != "required")
    ):
        assert response.text is not None, f"No text in response for option '{option_name}'"
        assert len(response.text) > 0, f"Empty response for option '{option_name}'"

    # Validate based on option type
    if needs_validation:
        if option_name.startswith("tools") or option_name.startswith("tool_choice"):
            # Should have called the weather function
            text = response.text.lower()
            assert "sunny" in text or "seattle" in text, f"Tool not invoked for {option_name}"
        elif option_name.startswith("response_format"):
            if option_value == OutputStruct:
                # Should have structured output
                assert response.value is not None, "No structured output"
                assert isinstance(response.value, OutputStruct)
                assert "seattle" in response.value.location.lower()
            else:
                assert response.value is not None
                assert isinstance(response.value, dict)
                assert "location" in response.value
                assert "seattle" in response.value["location"].lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_integration_web_search() -> None:
    client = OpenAIChatCompletionClient(model="gpt-4o-search-preview")

    for streaming in [False, True]:
        # Use static method for web search tool
        web_search_tool = OpenAIChatCompletionClient.get_web_search_tool()
        content = {
            "messages": [
                Message(
                    role="user",
                    contents=["Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer."],
                )
            ],
            "options": {
                "tool_choice": "auto",
                "tools": [web_search_tool],
            },
        }
        if streaming:
            response = await client.get_response(stream=True, **content).get_final_response()
        else:
            response = await client.get_response(**content)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert "Rumi" in response.text
        assert "Mira" in response.text
        assert "Zoey" in response.text

        # Test that the client will use the web search tool with location
        web_search_tool_with_location = OpenAIChatCompletionClient.get_web_search_tool(
            web_search_options={
                "user_location": {
                    "type": "approximate",
                    "approximate": {"country": "US", "city": "Seattle"},
                },
            }
        )
        content = {
            "messages": [
                Message(
                    role="user",
                    contents=["What is the current weather? Do not ask for my current location."],
                )
            ],
            "options": {
                "tool_choice": "auto",
                "tools": [web_search_tool_with_location],
            },
        }
        if streaming:
            response = await client.get_response(stream=True, **content).get_final_response()
        else:
            response = await client.get_response(**content)
        assert response.text is not None
