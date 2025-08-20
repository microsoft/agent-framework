# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import unittest.mock
from typing import Annotated

import pytest
from openai import BadRequestError
from pydantic import BaseModel

from agent_framework import (
    ChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    FunctionCallContent,
    FunctionResultContent,
    HostedCodeInterpreterTool,
    HostedFileContent,
    HostedFileSearchTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    TextContent,
    TextReasoningContent,
    UriContent,
    ai_function,
)
from agent_framework._types import ChatOptions
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError, ServiceResponseException
from agent_framework.openai import OpenAIResponsesClient
from agent_framework.openai._exceptions import OpenAIContentFilterException

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str


async def create_vector_store(client: OpenAIResponsesClient) -> tuple[str, HostedVectorStoreContent]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."), purpose="user_data"
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(vector_store_id=vector_store.id, file_id=file.id)
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, HostedVectorStoreContent(vector_store_id=vector_store.id)


async def delete_vector_store(client: OpenAIResponsesClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


@ai_function
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient()

    assert openai_responses_client.ai_model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert isinstance(openai_responses_client, ChatClient)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(api_key="34523", ai_model_id={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    openai_responses_client = OpenAIResponsesClient(ai_model_id=ai_model_id)

    assert openai_responses_client.ai_model_id == ai_model_id
    assert isinstance(openai_responses_client, ChatClient)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert openai_responses_client.ai_model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert isinstance(openai_responses_client, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in openai_responses_client.client.default_headers
        assert openai_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["OPENAI_RESPONSES_MODEL_ID"]], indirect=True)
def test_init_with_empty_model_id(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    ai_model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(
            ai_model_id=ai_model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    openai_responses_client = OpenAIResponsesClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    openai_responses_client = OpenAIResponsesClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_filter_options_method(openai_unit_test_env: dict[str, str]) -> None:
    """Test that the _filter_options method filters out None values correctly."""
    client = OpenAIResponsesClient()

    # Test with a mix of None and non-None values
    filtered = client._filter_options(  # type: ignore
        include=["usage"],
        instructions="Test instruction",
        max_tokens=None,
        temperature=0.7,
        seed=None,
        model="test-model",
        store=True,
        top_p=None,
    )

    # Should only contain non-None values
    expected = {
        "include": ["usage"],
        "instructions": "Test instruction",
        "temperature": 0.7,
        "model": "test-model",
        "store": True,
    }

    assert filtered == expected
    assert "max_tokens" not in filtered
    assert "seed" not in filtered
    assert "top_p" not in filtered


def test_get_response_with_invalid_input() -> None:
    """Test get_response with invalid inputs to trigger exception handling."""

    client = OpenAIResponsesClient(ai_model_id="invalid-model", api_key="test-key")

    # Test with empty messages which should trigger ServiceInvalidRequestError
    with pytest.raises(ServiceInvalidRequestError, match="Messages are required"):
        asyncio.run(client.get_response(messages=[]))


def test_get_response_with_all_parameters() -> None:
    """Test get_response with all possible parameters to cover parameter handling logic."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Test with comprehensive parameter set - should fail due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Test message")],
                include=["message.output_text.logprobs"],
                instructions="You are a helpful assistant",
                max_tokens=100,
                parallel_tool_calls=True,
                model="gpt-4",
                previous_response_id="prev-123",
                reasoning={"chain_of_thought": "enabled"},
                service_tier="auto",
                response_format=OutputStruct,
                seed=42,
                store=True,
                temperature=0.7,
                tool_choice="auto",
                tools=[get_weather],
                top_p=0.9,
                user="test-user",
                truncation="auto",
                timeout=30.0,
                additional_properties={"custom": "value"},
            )
        )


def test_web_search_tool_with_location() -> None:
    """Test HostedWebSearchTool with location parameters."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Test web search tool with location
    web_search_tool = HostedWebSearchTool(
        additional_properties={
            "user_location": {"country": "US", "city": "Seattle", "region": "WA", "timezone": "America/Los_Angeles"}
        }
    )

    # Should raise an authentication error due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="What's the weather?")],
                tools=[web_search_tool],
                tool_choice="auto",
            )
        )


def test_file_search_tool_with_invalid_inputs() -> None:
    """Test HostedFileSearchTool with invalid vector store inputs."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Test with invalid inputs type (should trigger ValueError)
    file_search_tool = HostedFileSearchTool(inputs=[HostedFileContent(file_id="invalid")])

    # Should raise an error due to invalid inputs
    with pytest.raises(ValueError, match="HostedFileSearchTool requires inputs to be of type"):
        asyncio.run(
            client.get_response(messages=[ChatMessage(role="user", text="Search files")], tools=[file_search_tool])
        )


def test_code_interpreter_tool_variations() -> None:
    """Test HostedCodeInterpreterTool with and without file inputs."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Test code interpreter without files
    code_tool_empty = HostedCodeInterpreterTool()

    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(messages=[ChatMessage(role="user", text="Run some code")], tools=[code_tool_empty])
        )

    # Test code interpreter with files
    code_tool_with_files = HostedCodeInterpreterTool(
        inputs=[HostedFileContent(file_id="file1"), HostedFileContent(file_id="file2")]
    )

    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Process these files")], tools=[code_tool_with_files]
            )
        )


def test_content_filter_exception() -> None:
    """Test that content filter errors in get_response are properly handled."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Mock a BadRequestError with content_filter code
    mock_error = BadRequestError(
        message="Content filter error",
        response=unittest.mock.MagicMock(),
        body={"error": {"code": "content_filter", "message": "Content filter error"}},
    )
    mock_error.code = "content_filter"

    with unittest.mock.patch.object(client.client.responses, "create", side_effect=mock_error):
        with pytest.raises(OpenAIContentFilterException) as exc_info:
            asyncio.run(client.get_response(messages=[ChatMessage(role="user", text="Test message")]))

        assert "content error" in str(exc_info.value)


def test_hosted_file_search_tool_validation() -> None:
    """Test get_response HostedFileSearchTool validation."""

    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Test HostedFileSearchTool without inputs (should raise ValueError)
    empty_file_search_tool = HostedFileSearchTool()

    with pytest.raises((ValueError, ServiceInvalidRequestError)):
        asyncio.run(
            client.get_response(messages=[ChatMessage(role="user", text="Test")], tools=[empty_file_search_tool])
        )


def test_chat_message_parsing_with_function_calls() -> None:
    """Test get_response message preparation with function call and result content types in conversation flow."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Create messages with function call and result content
    function_call = FunctionCallContent(
        call_id="test-call-id",
        name="test_function",
        arguments='{"param": "value"}',
        additional_properties={"fc_id": "test-fc-id"},
    )

    function_result = FunctionResultContent(call_id="test-call-id", result="Function executed successfully")

    messages = [
        ChatMessage(role="user", text="Call a function"),
        ChatMessage(role="assistant", contents=[function_call]),
        ChatMessage(role="tool", contents=[function_result]),
    ]

    # This should exercise the message parsing logic - will fail due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(client.get_response(messages=messages))


def test_response_format_parse_path() -> None:
    """Test get_response response_format parsing path."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Mock successful parse response
    mock_parsed_response = unittest.mock.MagicMock()
    mock_parsed_response.id = "parsed_response_123"
    mock_parsed_response.text = "Parsed response"
    mock_parsed_response.model = "test-model"
    mock_parsed_response.created_at = 1000000000
    mock_parsed_response.metadata = {}
    mock_parsed_response.output_parsed = None
    mock_parsed_response.usage = None

    with unittest.mock.patch.object(client.client.responses, "parse", return_value=mock_parsed_response):
        response = asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Test message")], response_format=OutputStruct, store=True
            )
        )

        assert response.conversation_id == "parsed_response_123"
        assert response.ai_model_id == "test-model"


def test_bad_request_error_non_content_filter() -> None:
    """Test get_response BadRequestError without content_filter."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Mock a BadRequestError without content_filter code
    mock_error = BadRequestError(
        message="Invalid request",
        response=unittest.mock.MagicMock(),
        body={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )
    mock_error.code = "invalid_request"

    with unittest.mock.patch.object(client.client.responses, "parse", side_effect=mock_error):
        with pytest.raises(ServiceResponseException) as exc_info:
            asyncio.run(
                client.get_response(
                    messages=[ChatMessage(role="user", text="Test message")], response_format=OutputStruct
                )
            )

        assert "failed to complete the prompt" in str(exc_info.value)


async def test_streaming_content_filter_exception_handling() -> None:
    """Test that content filter errors in get_streaming_response are properly handled."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Mock the OpenAI client to raise a BadRequestError with content_filter code
    with unittest.mock.patch.object(client.client.responses, "create") as mock_create:
        mock_create.side_effect = BadRequestError(
            message="Content filtered in stream",
            response=unittest.mock.MagicMock(),
            body={"error": {"code": "content_filter", "message": "Content filtered"}},
        )
        mock_create.side_effect.code = "content_filter"

        with pytest.raises(OpenAIContentFilterException, match="service encountered a content error"):
            response_stream = client.get_streaming_response(messages=[ChatMessage(role="user", text="Test")])
            async for _ in response_stream:
                break


def test_get_streaming_response_with_all_parameters() -> None:
    """Test get_streaming_response with all possible parameters."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    async def run_streaming_test():
        response = client.get_streaming_response(
            messages=[ChatMessage(role="user", text="Test streaming")],
            include=["file_search_call.results"],
            instructions="Stream response test",
            max_tokens=50,
            parallel_tool_calls=False,
            model="gpt-4",
            previous_response_id="stream-prev-123",
            reasoning={"mode": "stream"},
            service_tier="default",
            response_format=OutputStruct,
            seed=123,
            store=False,
            temperature=0.5,
            tool_choice="none",
            tools=[],
            top_p=0.8,
            user="stream-user",
            truncation="last_messages",
            timeout=15.0,
            additional_properties={"stream_custom": "stream_value"},
        )
        # Just iterate once to trigger the logic
        async for _ in response:
            break

    # Should fail due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(run_streaming_test())


def test_response_content_creation_with_annotations() -> None:
    """Test _create_response_content with different annotation types."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Create a mock response with annotated text content
    mock_response = unittest.mock.MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    # Create mock annotation
    mock_annotation = unittest.mock.MagicMock()
    mock_annotation.type = "file_citation"
    mock_annotation.file_id = "file_123"
    mock_annotation.filename = "document.pdf"
    mock_annotation.index = 0

    mock_message_content = unittest.mock.MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Text with annotations."
    mock_message_content.annotations = [mock_annotation]

    mock_message_item = unittest.mock.MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with unittest.mock.patch.object(client, "_get_metadata_from_response", return_value={}):
        response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

        assert len(response.messages[0].contents) >= 1
        assert isinstance(response.messages[0].contents[0], TextContent)
        assert response.messages[0].contents[0].text == "Text with annotations."
        assert response.messages[0].contents[0].annotations is not None


def test_response_content_creation_with_refusal() -> None:
    """Test _create_response_content with refusal content."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Create a mock response with refusal content
    mock_response = unittest.mock.MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_refusal_content = unittest.mock.MagicMock()
    mock_refusal_content.type = "refusal"
    mock_refusal_content.refusal = "I cannot provide that information."

    mock_message_item = unittest.mock.MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_refusal_content]

    mock_response.output = [mock_message_item]

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], TextContent)
    assert response.messages[0].contents[0].text == "I cannot provide that information."


def test_response_content_creation_with_reasoning() -> None:
    """Test _create_response_content with reasoning content."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Create a mock response with reasoning content
    mock_response = unittest.mock.MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_reasoning_content = unittest.mock.MagicMock()
    mock_reasoning_content.text = "Reasoning step"

    mock_reasoning_item = unittest.mock.MagicMock()
    mock_reasoning_item.type = "reasoning"
    mock_reasoning_item.content = [mock_reasoning_content]
    mock_reasoning_item.summary = ["Summary"]

    mock_response.output = [mock_reasoning_item]

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], TextReasoningContent)
    assert response.messages[0].contents[0].text == "Reasoning step"


def test_response_content_creation_with_code_interpreter() -> None:
    """Test _create_response_content with code interpreter outputs."""

    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Create a mock response with code interpreter outputs
    mock_response = unittest.mock.MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_log_output = unittest.mock.MagicMock()
    mock_log_output.type = "logs"
    mock_log_output.logs = "Code execution log"

    mock_image_output = unittest.mock.MagicMock()
    mock_image_output.type = "image"
    mock_image_output.url = "https://example.com/image.png"

    mock_code_interpreter_item = unittest.mock.MagicMock()
    mock_code_interpreter_item.type = "code_interpreter_call"
    mock_code_interpreter_item.outputs = [mock_log_output, mock_image_output]
    mock_code_interpreter_item.code = "print('hello')"

    mock_response.output = [mock_code_interpreter_item]

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert len(response.messages[0].contents) == 2
    assert isinstance(response.messages[0].contents[0], TextContent)
    assert response.messages[0].contents[0].text == "Code execution log"
    assert isinstance(response.messages[0].contents[1], UriContent)
    assert response.messages[0].contents[1].uri == "https://example.com/image.png"
    assert response.messages[0].contents[1].media_type == "image"


def test_response_content_creation_with_function_call() -> None:
    """Test _create_response_content with function call content."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Create a mock response with function call
    mock_response = unittest.mock.MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_function_call_item = unittest.mock.MagicMock()
    mock_function_call_item.type = "function_call"
    mock_function_call_item.call_id = "call_123"
    mock_function_call_item.name = "get_weather"
    mock_function_call_item.arguments = '{"location": "Seattle"}'
    mock_function_call_item.id = "fc_456"

    mock_response.output = [mock_function_call_item]

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    function_call = response.messages[0].contents[0]
    assert function_call.call_id == "call_123"
    assert function_call.name == "get_weather"
    assert function_call.arguments == '{"location": "Seattle"}'


def test_usage_details_basic() -> None:
    """Test _usage_details_from_openai without cached or reasoning tokens."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    mock_usage = unittest.mock.MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_usage.total_tokens = 150
    mock_usage.input_tokens_details = None
    mock_usage.output_tokens_details = None

    details = client._usage_details_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details.input_token_count == 100
    assert details.output_token_count == 50
    assert details.total_token_count == 150


def test_usage_details_with_cached_tokens() -> None:
    """Test _usage_details_from_openai with cached input tokens."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    mock_usage = unittest.mock.MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 75
    mock_usage.total_tokens = 275
    mock_usage.input_tokens_details = unittest.mock.MagicMock()
    mock_usage.input_tokens_details.cached_tokens = 25
    mock_usage.output_tokens_details = None

    details = client._usage_details_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details.input_token_count == 200
    assert details.additional_counts["openai.cached_input_tokens"] == 25


def test_usage_details_with_reasoning_tokens() -> None:
    """Test _usage_details_from_openai with reasoning tokens."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    mock_usage = unittest.mock.MagicMock()
    mock_usage.input_tokens = 150
    mock_usage.output_tokens = 80
    mock_usage.total_tokens = 230
    mock_usage.input_tokens_details = None
    mock_usage.output_tokens_details = unittest.mock.MagicMock()
    mock_usage.output_tokens_details.reasoning_tokens = 30

    details = client._usage_details_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details.output_token_count == 80
    assert details.additional_counts["openai.reasoning_tokens"] == 30


def test_get_metadata_from_response() -> None:
    """Test the _get_metadata_from_response method."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Test with logprobs
    mock_output_with_logprobs = unittest.mock.MagicMock()
    mock_output_with_logprobs.logprobs = {"token": "test", "probability": 0.9}

    metadata = client._get_metadata_from_response(mock_output_with_logprobs)  # type: ignore
    assert "logprobs" in metadata
    assert metadata["logprobs"]["token"] == "test"

    # Test without logprobs
    mock_output_no_logprobs = unittest.mock.MagicMock()
    mock_output_no_logprobs.logprobs = None

    metadata_empty = client._get_metadata_from_response(mock_output_no_logprobs)  # type: ignore
    assert metadata_empty == {}


def test_streaming_response_basic_structure() -> None:
    """Test that _create_streaming_response_content returns proper structure."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")
    chat_options = ChatOptions(store=True)
    function_call_ids: dict[int, tuple[str, str]] = {}

    # Test with a basic mock event to ensure the method returns proper structure
    mock_event = unittest.mock.MagicMock()

    response = client._create_streaming_response_content(mock_event, chat_options, function_call_ids)  # type: ignore

    # Should get a valid ChatResponseUpdate structure
    assert isinstance(response, ChatResponseUpdate)
    assert response.role == ChatRole.ASSISTANT
    assert response.ai_model_id == "test-model"
    assert isinstance(response.contents, list)
    assert response.raw_representation is mock_event


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in Seattle is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        messages=messages,
        response_format=OutputStruct,
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    output = OutputStruct.model_validate_json(response.text)
    assert "seattle" in output.location.lower()
    assert "sunny" in output.weather.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_response_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "sunny" in response.text.lower()

    messages.clear()
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    output = OutputStruct.model_validate_json(response.text)
    assert "seattle" in output.location.lower()
    assert "sunny" in output.weather.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_streaming() -> None:
    """Test Azure OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = openai_responses_client.get_streaming_response(messages=messages)

    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in Seattle is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    response = openai_responses_client.get_streaming_response(
        messages=messages,
        response_format=OutputStruct,
    )
    full_message = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    output = OutputStruct.model_validate_json(full_message)
    assert "seattle" in output.location.lower()
    assert "sunny" in output.weather.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_streaming_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = [ChatMessage(role="user", text="What is the weather in Seattle?")]

    # Test that the client can be used to get a response
    response = openai_responses_client.get_streaming_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
    )
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "sunny" in full_message.lower()

    messages.clear()
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    response = openai_responses_client.get_streaming_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )
    full_message = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    output = OutputStruct.model_validate_json(full_message)
    assert "seattle" in output.location.lower()
    assert "sunny" in output.weather.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_web_search() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    # Test that the client will use the web search tool
    response = await openai_responses_client.get_response(
        messages=[
            ChatMessage(
                role="user",
                text="Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
            )
        ],
        tools=[HostedWebSearchTool()],
        tool_choice="auto",
    )

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
    response = await openai_responses_client.get_response(
        messages=[ChatMessage(role="user", text="What is the current weather? Do not ask for my current location.")],
        tools=[HostedWebSearchTool(additional_properties=additional_properties)],
        tool_choice="auto",
    )
    assert "Seattle" in response.text


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_web_search_streaming() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    # Test that the client will use the web search tool
    response = openai_responses_client.get_streaming_response(
        messages=[
            ChatMessage(
                role="user",
                text="Who are the main characters of Kpop Demon Hunters? Do a web search to find the answer.",
            )
        ],
        tools=[HostedWebSearchTool()],
        tool_choice="auto",
    )

    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text
    assert "Rumi" in full_message
    assert "Mira" in full_message
    assert "Zoey" in full_message

    # Test that the client will use the web search tool with location
    additional_properties = {
        "user_location": {
            "country": "US",
            "city": "Seattle",
        }
    }
    response = openai_responses_client.get_streaming_response(
        messages=[ChatMessage(role="user", text="What is the current weather? Do not ask for my current location.")],
        tools=[HostedWebSearchTool(additional_properties=additional_properties)],
        tool_choice="auto",
    )
    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text
    assert "Seattle" in full_message


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_file_search() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    file_id, vector_store = await create_vector_store(openai_responses_client)
    # Test that the client will use the web search tool
    response = await openai_responses_client.get_response(
        messages=[
            ChatMessage(
                role="user",
                text="What is the weather today? Do a file search to find the answer.",
            )
        ],
        tools=[HostedFileSearchTool(inputs=vector_store)],
        tool_choice="auto",
    )

    await delete_vector_store(openai_responses_client, file_id, vector_store.vector_store_id)
    assert "sunny" in response.text.lower()
    assert "75" in response.text


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_streaming_file_search() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClient)

    file_id, vector_store = await create_vector_store(openai_responses_client)
    # Test that the client will use the web search tool
    response = openai_responses_client.get_streaming_response(
        messages=[
            ChatMessage(
                role="user",
                text="What is the weather today? Do a file search to find the answer.",
            )
        ],
        tools=[HostedFileSearchTool(inputs=vector_store)],
        tool_choice="auto",
    )

    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    await delete_vector_store(openai_responses_client, file_id, vector_store.vector_store_id)

    assert "sunny" in full_message.lower()
    assert "75" in full_message
