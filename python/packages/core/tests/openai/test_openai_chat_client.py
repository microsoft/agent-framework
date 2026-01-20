# Copyright (c) Microsoft. All rights reserved.

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from openai import BadRequestError
from pydantic import BaseModel
from pytest import param

from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    DataContent,
    FunctionResultContent,
    HostedWebSearchTool,
    ToolProtocol,
    ai_function,
    prepare_function_call_results,
)
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.openai import OpenAIChatClient
from agent_framework.openai._exceptions import OpenAIContentFilterException

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient()

    assert open_ai_chat_completion.model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClientProtocol)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(api_key="34523", model_id={"test": "dict"})  # type: ignore


def test_init_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model_id = "test_model_id"
    open_ai_chat_completion = OpenAIChatClient(model_id=model_id)

    assert open_ai_chat_completion.model_id == model_id
    assert isinstance(open_ai_chat_completion, ChatClientProtocol)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient(
        default_headers=default_headers,
    )

    assert open_ai_chat_completion.model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClientProtocol)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in open_ai_chat_completion.client.default_headers
        assert open_ai_chat_completion.client.default_headers[key] == value


def test_init_base_url(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient(base_url="http://localhost:1234/v1")
    assert str(open_ai_chat_completion.client.base_url) == "http://localhost:1234/v1/"


def test_init_base_url_from_settings_env() -> None:
    """Test that base_url from OpenAISettings environment variable is properly used."""
    # Set environment variable for base_url
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "dummy",
            "OPENAI_CHAT_MODEL_ID": "gpt-5",
            "OPENAI_BASE_URL": "https://custom-openai-endpoint.com/v1",
        },
    ):
        client = OpenAIChatClient()
        assert client.model_id == "gpt-5"
        assert str(client.client.base_url) == "https://custom-openai-endpoint.com/v1/"


@pytest.mark.parametrize("exclude_list", [["OPENAI_CHAT_MODEL_ID"]], indirect=True)
def test_init_with_empty_model_id(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            model_id=model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings.get("default_headers", {})


async def test_content_filter_exception_handling(openai_unit_test_env: dict[str, str]) -> None:
    """Test that content filter errors are properly handled."""
    client = OpenAIChatClient()
    messages = [ChatMessage(role="user", text="test message")]

    # Create a mock BadRequestError with content_filter code
    mock_response = MagicMock()
    mock_error = BadRequestError(
        message="Content filter error", response=mock_response, body={"error": {"code": "content_filter"}}
    )
    mock_error.code = "content_filter"

    # Mock the client to raise the content filter error
    with (
        patch.object(client.client.chat.completions, "create", side_effect=mock_error),
        pytest.raises(OpenAIContentFilterException),
    ):
        await client._inner_get_response(messages=messages, options={})  # type: ignore


def test_unsupported_tool_handling(openai_unit_test_env: dict[str, str]) -> None:
    """Test that unsupported tool types are handled correctly."""
    client = OpenAIChatClient()

    # Create a mock ToolProtocol that's not an AIFunction
    unsupported_tool = MagicMock(spec=ToolProtocol)
    unsupported_tool.__class__.__name__ = "UnsupportedAITool"

    # This should ignore the unsupported ToolProtocol and return empty list
    result = client._prepare_tools_for_openai([unsupported_tool])  # type: ignore
    assert result == {}

    # Also test with a non-ToolProtocol that should be converted to dict
    dict_tool = {"type": "function", "name": "test"}
    result = client._prepare_tools_for_openai([dict_tool])  # type: ignore
    assert result["tools"] == [dict_tool]


@ai_function
def get_story_text() -> str:
    """Returns a story about Emily and David."""
    return (
        "Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
        "Bonded by their love for the natural world and shared curiosity, they uncovered a "
        "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
        "of climate change."
    )


@ai_function
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny and 72°F."


async def test_exception_message_includes_original_error_details() -> None:
    """Test that exception messages include original error details in the new format."""
    client = OpenAIChatClient(model_id="test-model", api_key="test-key")
    messages = [ChatMessage(role="user", text="test message")]

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
        pytest.raises(ServiceResponseException) as exc_info,
    ):
        await client._inner_get_response(messages=messages, options={})  # type: ignore

    exception_message = str(exc_info.value)
    assert "service failed to complete the prompt:" in exception_message
    assert original_error_message in exception_message


def test_chat_response_content_order_text_before_tool_calls(openai_unit_test_env: dict[str, str]):
    """Test that text content appears before tool calls in ChatResponse contents."""
    # Import locally to avoid break other tests when the import changes
    from openai.types.chat.chat_completion import ChatCompletion, Choice
    from openai.types.chat.chat_completion_message import ChatCompletionMessage
    from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function

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

    client = OpenAIChatClient()
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
    """Test that falsy values (like empty list) in function result are properly handled."""
    client = OpenAIChatClient()

    # Test with empty list (falsy but not None)
    message_with_empty_list = ChatMessage(role="tool", contents=[FunctionResultContent(call_id="call-123", result=[])])

    openai_messages = client._prepare_message_for_openai(message_with_empty_list)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "[]"  # Empty list should be JSON serialized

    # Test with empty string (falsy but not None)
    message_with_empty_string = ChatMessage(
        role="tool", contents=[FunctionResultContent(call_id="call-456", result="")]
    )

    openai_messages = client._prepare_message_for_openai(message_with_empty_string)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == ""  # Empty string should be preserved

    # Test with False (falsy but not None)
    message_with_false = ChatMessage(role="tool", contents=[FunctionResultContent(call_id="call-789", result=False)])

    openai_messages = client._prepare_message_for_openai(message_with_false)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "false"  # False should be JSON serialized


def test_function_result_exception_handling(openai_unit_test_env: dict[str, str]):
    """Test that exceptions in function result are properly handled.

    Feel free to remove this test in case there's another new behavior.
    """
    client = OpenAIChatClient()

    # Test with exception (no result)
    test_exception = ValueError("Test error message")
    message_with_exception = ChatMessage(
        role="tool",
        contents=[
            FunctionResultContent(call_id="call-123", result="Error: Function failed.", exception=test_exception)
        ],
    )

    openai_messages = client._prepare_message_for_openai(message_with_exception)
    assert len(openai_messages) == 1
    assert openai_messages[0]["content"] == "Error: Function failed."
    assert openai_messages[0]["tool_call_id"] == "call-123"


def test_prepare_function_call_results_string_passthrough():
    """Test that string values are passed through directly without JSON encoding."""
    result = prepare_function_call_results("simple string")
    assert result == "simple string"
    assert isinstance(result, str)


def test_prepare_content_for_openai_data_content_image(openai_unit_test_env: dict[str, str]) -> None:
    """Test _prepare_content_for_openai converts DataContent with image media type to OpenAI format."""
    client = OpenAIChatClient()

    # Test DataContent with image media type
    image_data_content = DataContent(
        uri="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
        media_type="image/png",
    )

    result = client._prepare_content_for_openai(image_data_content)  # type: ignore

    # Should convert to OpenAI image_url format
    assert result["type"] == "image_url"
    assert result["image_url"]["url"] == image_data_content.uri

    # Test DataContent with non-image media type should use default model_dump
    text_data_content = DataContent(uri="data:text/plain;base64,SGVsbG8gV29ybGQ=", media_type="text/plain")

    result = client._prepare_content_for_openai(text_data_content)  # type: ignore

    # Should use default model_dump format
    assert result["type"] == "data"
    assert result["uri"] == text_data_content.uri
    assert result["media_type"] == "text/plain"

    # Test DataContent with audio media type
    audio_data_content = DataContent(
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
    mp3_data_content = DataContent(uri="data:audio/mp3;base64,//uQAAAAWGluZwAAAA8AAAACAAACcQ==", media_type="audio/mp3")

    result = client._prepare_content_for_openai(mp3_data_content)  # type: ignore

    # Should convert to OpenAI input_audio format with mp3
    assert result["type"] == "input_audio"
    # Data should contain just the base64 part, not the full data URI
    assert result["input_audio"]["data"] == "//uQAAAAWGluZwAAAA8AAAACAAACcQ=="
    assert result["input_audio"]["format"] == "mp3"


def test_prepare_content_for_openai_document_file_mapping(openai_unit_test_env: dict[str, str]) -> None:
    """Test _prepare_content_for_openai converts document files (PDF, DOCX, etc.) to OpenAI file format."""
    client = OpenAIChatClient()

    # Test PDF without filename - should omit filename in OpenAI payload
    pdf_data_content = DataContent(
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
    pdf_with_filename = DataContent(
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
        doc_content = DataContent(
            uri=f"data:{case['media_type']};base64,{case['base64']}",
            media_type=case["media_type"],
        )

        result = client._prepare_content_for_openai(doc_content)  # type: ignore

        # All application/* types should now be mapped to file format
        assert result["type"] == "file"
        assert "filename" not in result["file"]  # Should omit filename when not provided
        assert result["file"]["file_data"] == doc_content.uri

        # Test with filename - should now use file format with filename
        doc_with_filename = DataContent(
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
    pdf_empty_props = DataContent(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={},
    )

    result = client._prepare_content_for_openai(pdf_empty_props)  # type: ignore

    assert result["type"] == "file"
    assert "filename" not in result["file"]

    # Test edge case: None filename in additional_properties
    pdf_none_filename = DataContent(
        uri="data:application/pdf;base64,JVBERi0xLjQ=",
        media_type="application/pdf",
        additional_properties={"filename": None},
    )

    result = client._prepare_content_for_openai(pdf_none_filename)  # type: ignore

    assert result["type"] == "file"
    assert "filename" not in result["file"]  # None filename should be omitted


# region Integration Tests


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str | None = None


@pytest.mark.flaky
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
        # OpenAIChatOptions - just verify they don't fail
        param("logit_bias", {"50256": -1}, False, id="logit_bias"),
        param("prediction", {"type": "content", "content": "hello world"}, False, id="prediction"),
        # Complex options requiring output validation
        param("tools", [get_weather], True, id="tools_function"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        param("tool_choice", "required", True, id="tool_choice_required_any"),
        param(
            "tool_choice",
            {"mode": "required", "required_function_name": "get_weather"},
            True,
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
                        "required": ["location", "conditions", "temperature_c", "advisory"],
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
    """Parametrized test covering all ChatOptions and OpenAIChatOptions.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.
    """
    client = OpenAIChatClient()
    # to ensure toolmode required does not endlessly loop
    client.function_invocation_configuration.max_iterations = 1

    for streaming in [False, True]:
        # Prepare test message
        if option_name.startswith("tools") or option_name.startswith("tool_choice"):
            # Use weather-related prompt for tool tests
            messages = [ChatMessage(role="user", text="What is the weather in Seattle?")]
        elif option_name.startswith("response_format"):
            # Use prompt that works well with structured output
            messages = [ChatMessage(role="user", text="The weather in Seattle is sunny")]
            messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))
        else:
            # Generic prompt for simple options
            messages = [ChatMessage(role="user", text="Say 'Hello World' briefly.")]

        # Build options dict
        options: dict[str, Any] = {option_name: option_value}

        # Add tools if testing tool_choice to avoid errors
        if option_name.startswith("tool_choice"):
            options["tools"] = [get_weather]

        if streaming:
            # Test streaming mode
            response_gen = client.get_streaming_response(
                messages=messages,
                options=options,
            )

            output_format = option_value if option_name.startswith("response_format") else None
            response = await ChatResponse.from_chat_response_generator(response_gen, output_format_type=output_format)
        else:
            # Test non-streaming mode
            response = await client.get_response(
                messages=messages,
                options=options,
            )

        assert response is not None
        assert isinstance(response, ChatResponse)
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
                    # Runtime JSON schema
                    assert response.value is None, "No structured output, can't parse any json."
                    response_value = json.loads(response.text)
                    assert isinstance(response_value, dict)
                    assert "location" in response_value
                    assert "seattle" in response_value["location"].lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_integration_web_search() -> None:
    client = OpenAIChatClient(model_id="gpt-4o-search-preview")

    for streaming in [False, True]:
        content = {
            "messages": "Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
            "options": {
                "tool_choice": "auto",
                "tools": [HostedWebSearchTool()],
            },
        }
        if streaming:
            response = await ChatResponse.from_chat_response_generator(client.get_streaming_response(**content))
        else:
            response = await client.get_response(**content)

        assert response is not None
        assert isinstance(response, ChatResponse)
        assert "Rumi" in response.text
        assert "Mira" in response.text
        assert "Zoey" in response.text

        # Test that the client will use the web search tool with location
        additional_properties = {
            "user_location": {
                "country": "US",
                "city": "Seattle",
            }
        }
        content = {
            "messages": "What is the current weather? Do not ask for my current location.",
            "options": {
                "tool_choice": "auto",
                "tools": [HostedWebSearchTool(additional_properties=additional_properties)],
            },
        }
        if streaming:
            response = await ChatResponse.from_chat_response_generator(client.get_streaming_response(**content))
        else:
            response = await client.get_response(**content)
        assert response.text is not None
