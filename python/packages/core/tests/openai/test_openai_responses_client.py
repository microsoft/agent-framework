# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from typing import Annotated, Any
from unittest.mock import MagicMock, patch

import pytest
from openai import BadRequestError
from openai.types.responses.response_reasoning_item import Summary
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_summary_text_done_event import (
    ResponseReasoningSummaryTextDoneEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import (
    ResponseReasoningTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_done_event import (
    ResponseReasoningTextDoneEvent,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from pydantic import BaseModel
from pytest import param

from agent_framework import (
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedImageGenerationTool,
    HostedMCPTool,
    HostedWebSearchTool,
    Role,
    tool,
)
from agent_framework.exceptions import (
    ServiceInitializationError,
    ServiceInvalidRequestError,
    ServiceResponseException,
)
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
    weather: str | None = None


async def create_vector_store(
    client: OpenAIResponsesClient,
) -> tuple[str, Content]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."),
        purpose="user_data",
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store.id,
        file_id=file.id,
        poll_interval_ms=1000,
    )
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, Content.from_hosted_vector_store(vector_store_id=vector_store.id)


async def delete_vector_store(client: OpenAIResponsesClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


@tool(approval_mode="never_require")
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient()

    assert openai_responses_client.model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert isinstance(openai_responses_client, ChatClientProtocol)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(api_key="34523", model_id={"test": "dict"})  # type: ignore


def test_init_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model_id = "test_model_id"
    openai_responses_client = OpenAIResponsesClient(model_id=model_id)

    assert openai_responses_client.model_id == model_id
    assert isinstance(openai_responses_client, ChatClientProtocol)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert openai_responses_client.model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert isinstance(openai_responses_client, ChatClientProtocol)

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
    model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(
            model_id=model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "model_id": openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    openai_responses_client = OpenAIResponsesClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["model_id"] == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "model_id": openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    openai_responses_client = OpenAIResponsesClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["model_id"] == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings.get("default_headers", {})


def test_get_response_with_invalid_input() -> None:
    """Test get_response with invalid inputs to trigger exception handling."""

    client = OpenAIResponsesClient(model_id="invalid-model", api_key="test-key")

    # Test with empty messages which should trigger ServiceInvalidRequestError
    with pytest.raises(ServiceInvalidRequestError, match="Messages are required"):
        asyncio.run(client.get_response(messages=[]))


def test_get_response_with_all_parameters() -> None:
    """Test get_response with all possible parameters to cover parameter handling logic."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test with comprehensive parameter set - should fail due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Test message")],
                options={
                    "include": ["message.output_text.logprobs"],
                    "instructions": "You are a helpful assistant",
                    "max_tokens": 100,
                    "parallel_tool_calls": True,
                    "model_id": "gpt-4",
                    "previous_response_id": "prev-123",
                    "reasoning": {"chain_of_thought": "enabled"},
                    "service_tier": "auto",
                    "response_format": OutputStruct,
                    "seed": 42,
                    "store": True,
                    "temperature": 0.7,
                    "tool_choice": "auto",
                    "tools": [get_weather],
                    "top_p": 0.9,
                    "user": "test-user",
                    "truncation": "auto",
                    "timeout": 30.0,
                    "additional_properties": {"custom": "value"},
                },
            )
        )


def test_web_search_tool_with_location() -> None:
    """Test HostedWebSearchTool with location parameters."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test web search tool with location
    web_search_tool = HostedWebSearchTool(
        additional_properties={
            "user_location": {
                "country": "US",
                "city": "Seattle",
                "region": "WA",
                "timezone": "America/Los_Angeles",
            }
        }
    )

    # Should raise an authentication error due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="What's the weather?")],
                options={"tools": [web_search_tool], "tool_choice": "auto"},
            )
        )


def test_file_search_tool_with_invalid_inputs() -> None:
    """Test HostedFileSearchTool with invalid vector store inputs."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test with invalid inputs type (should trigger ValueError)
    file_search_tool = HostedFileSearchTool(inputs=[Content.from_hosted_file(file_id="invalid")])

    # Should raise an error due to invalid inputs
    with pytest.raises(ValueError, match="HostedFileSearchTool requires inputs to be of type"):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Search files")],
                options={"tools": [file_search_tool]},
            )
        )


def test_code_interpreter_tool_variations() -> None:
    """Test HostedCodeInterpreterTool with and without file inputs."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test code interpreter without files
    code_tool_empty = HostedCodeInterpreterTool()

    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Run some code")],
                options={"tools": [code_tool_empty]},
            )
        )

    # Test code interpreter with files
    code_tool_with_files = HostedCodeInterpreterTool(
        inputs=[Content.from_hosted_file(file_id="file1"), Content.from_hosted_file(file_id="file2")]
    )

    with pytest.raises(ServiceResponseException):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Process these files")],
                options={"tools": [code_tool_with_files]},
            )
        )


def test_content_filter_exception() -> None:
    """Test that content filter errors in get_response are properly handled."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock a BadRequestError with content_filter code
    mock_error = BadRequestError(
        message="Content filter error",
        response=MagicMock(),
        body={"error": {"code": "content_filter", "message": "Content filter error"}},
    )
    mock_error.code = "content_filter"

    with patch.object(client.client.responses, "create", side_effect=mock_error):
        with pytest.raises(OpenAIContentFilterException) as exc_info:
            asyncio.run(client.get_response(messages=[ChatMessage(role="user", text="Test message")]))

        assert "content error" in str(exc_info.value)


def test_hosted_file_search_tool_validation() -> None:
    """Test get_response HostedFileSearchTool validation."""

    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test HostedFileSearchTool without inputs (should raise ValueError)
    empty_file_search_tool = HostedFileSearchTool()

    with pytest.raises((ValueError, ServiceInvalidRequestError)):
        asyncio.run(
            client.get_response(
                messages=[ChatMessage(role="user", text="Test")],
                options={"tools": [empty_file_search_tool]},
            )
        )


def test_chat_message_parsing_with_function_calls() -> None:
    """Test get_response message preparation with function call and result content types in conversation flow."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create messages with function call and result content
    function_call = Content.from_function_call(
        call_id="test-call-id",
        name="test_function",
        arguments='{"param": "value"}',
        additional_properties={"fc_id": "test-fc-id"},
    )

    function_result = Content.from_function_result(call_id="test-call-id", result="Function executed successfully")

    messages = [
        ChatMessage(role="user", text="Call a function"),
        ChatMessage(role="assistant", contents=[function_call]),
        ChatMessage(role="tool", contents=[function_result]),
    ]

    # This should exercise the message parsing logic - will fail due to invalid API key
    with pytest.raises(ServiceResponseException):
        asyncio.run(client.get_response(messages=messages))


async def test_response_format_parse_path() -> None:
    """Test get_response response_format parsing path."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock successful parse response
    mock_parsed_response = MagicMock()
    mock_parsed_response.id = "parsed_response_123"
    mock_parsed_response.text = "Parsed response"
    mock_parsed_response.model = "test-model"
    mock_parsed_response.created_at = 1000000000
    mock_parsed_response.metadata = {}
    mock_parsed_response.output_parsed = None
    mock_parsed_response.usage = None
    mock_parsed_response.finish_reason = None
    mock_parsed_response.conversation = None  # No conversation object

    with patch.object(client.client.responses, "parse", return_value=mock_parsed_response):
        response = await client.get_response(
            messages=[ChatMessage(role="user", text="Test message")],
            options={"response_format": OutputStruct, "store": True},
        )
        assert response.response_id == "parsed_response_123"
        assert response.conversation_id == "parsed_response_123"
        assert response.model_id == "test-model"


async def test_response_format_parse_path_with_conversation_id() -> None:
    """Test get_response response_format parsing path with set conversation ID."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock successful parse response
    mock_parsed_response = MagicMock()
    mock_parsed_response.id = "parsed_response_123"
    mock_parsed_response.text = "Parsed response"
    mock_parsed_response.model = "test-model"
    mock_parsed_response.created_at = 1000000000
    mock_parsed_response.metadata = {}
    mock_parsed_response.output_parsed = None
    mock_parsed_response.usage = None
    mock_parsed_response.finish_reason = None
    mock_parsed_response.conversation = MagicMock()
    mock_parsed_response.conversation.id = "conversation_456"

    with patch.object(client.client.responses, "parse", return_value=mock_parsed_response):
        response = await client.get_response(
            messages=[ChatMessage(role="user", text="Test message")],
            options={"response_format": OutputStruct, "store": True},
        )
        assert response.response_id == "parsed_response_123"
        assert response.conversation_id == "conversation_456"
        assert response.model_id == "test-model"


async def test_bad_request_error_non_content_filter() -> None:
    """Test get_response BadRequestError without content_filter."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock a BadRequestError without content_filter code
    mock_error = BadRequestError(
        message="Invalid request",
        response=MagicMock(),
        body={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )
    mock_error.code = "invalid_request"

    with patch.object(client.client.responses, "parse", side_effect=mock_error):
        with pytest.raises(ServiceResponseException) as exc_info:
            await client.get_response(
                messages=[ChatMessage(role="user", text="Test message")],
                options={"response_format": OutputStruct},
            )

        assert "failed to complete the prompt" in str(exc_info.value)


async def test_streaming_content_filter_exception_handling() -> None:
    """Test that content filter errors in get_streaming_response are properly handled."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock the OpenAI client to raise a BadRequestError with content_filter code
    with patch.object(client.client.responses, "create") as mock_create:
        mock_create.side_effect = BadRequestError(
            message="Content filtered in stream",
            response=MagicMock(),
            body={"error": {"code": "content_filter", "message": "Content filtered"}},
        )
        mock_create.side_effect.code = "content_filter"

        with pytest.raises(OpenAIContentFilterException, match="service encountered a content error"):
            response_stream = client.get_streaming_response(messages=[ChatMessage(role="user", text="Test")])
            async for _ in response_stream:
                break


def test_response_content_creation_with_annotations() -> None:
    """Test _parse_response_from_openai with different annotation types."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with annotated text content
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    # Create mock annotation
    mock_annotation = MagicMock()
    mock_annotation.type = "file_citation"
    mock_annotation.file_id = "file_123"
    mock_annotation.filename = "document.pdf"
    mock_annotation.index = 0

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Text with annotations."
    mock_message_content.annotations = [mock_annotation]

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

        assert len(response.messages[0].contents) >= 1
        assert response.messages[0].contents[0].type == "text"
        assert response.messages[0].contents[0].text == "Text with annotations."
        assert response.messages[0].contents[0].annotations is not None


def test_response_content_creation_with_refusal() -> None:
    """Test _parse_response_from_openai with refusal content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with refusal content
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_refusal_content = MagicMock()
    mock_refusal_content.type = "refusal"
    mock_refusal_content.refusal = "I cannot provide that information."

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_refusal_content]

    mock_response.output = [mock_message_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert response.messages[0].contents[0].type == "text"
    assert response.messages[0].contents[0].text == "I cannot provide that information."


def test_response_content_creation_with_reasoning() -> None:
    """Test _parse_response_from_openai with reasoning content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with reasoning content
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_reasoning_content = MagicMock()
    mock_reasoning_content.text = "Reasoning step"

    mock_reasoning_item = MagicMock()
    mock_reasoning_item.type = "reasoning"
    mock_reasoning_item.content = [mock_reasoning_content]
    mock_reasoning_item.summary = [Summary(text="Summary", type="summary_text")]

    mock_response.output = [mock_reasoning_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 2
    assert response.messages[0].contents[0].type == "text_reasoning"
    assert response.messages[0].contents[0].text == "Reasoning step"


def test_response_content_creation_with_code_interpreter() -> None:
    """Test _parse_response_from_openai with code interpreter outputs."""

    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with code interpreter outputs
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_log_output = MagicMock()
    mock_log_output.type = "logs"
    mock_log_output.logs = "Code execution log"

    mock_image_output = MagicMock()
    mock_image_output.type = "image"
    mock_image_output.url = "https://example.com/image.png"

    mock_code_interpreter_item = MagicMock()
    mock_code_interpreter_item.type = "code_interpreter_call"
    mock_code_interpreter_item.outputs = [mock_log_output, mock_image_output]
    mock_code_interpreter_item.code = "print('hello')"

    mock_response.output = [mock_code_interpreter_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 2
    call_content, result_content = response.messages[0].contents
    assert call_content.type == "code_interpreter_tool_call"
    assert call_content.inputs is not None
    assert call_content.inputs[0].type == "text"
    assert result_content.type == "code_interpreter_tool_result"
    assert result_content.outputs is not None
    assert any(out.type == "text" for out in result_content.outputs)
    assert any(out.type == "uri" for out in result_content.outputs)


def test_response_content_creation_with_function_call() -> None:
    """Test _parse_response_from_openai with function call content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with function call
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_function_call_item = MagicMock()
    mock_function_call_item.type = "function_call"
    mock_function_call_item.call_id = "call_123"
    mock_function_call_item.name = "get_weather"
    mock_function_call_item.arguments = '{"location": "Seattle"}'
    mock_function_call_item.id = "fc_456"

    mock_response.output = [mock_function_call_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert response.messages[0].contents[0].type == "function_call"
    function_call = response.messages[0].contents[0]
    assert function_call.call_id == "call_123"
    assert function_call.name == "get_weather"
    assert function_call.arguments == '{"location": "Seattle"}'


def test_prepare_content_for_opentool_approval_response() -> None:
    """Test _prepare_content_for_openai with function approval response content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test approved response
    function_call = Content.from_function_call(
        call_id="call_123",
        name="send_email",
        arguments='{"to": "user@example.com"}',
    )
    approval_response = Content.from_function_approval_response(
        approved=True,
        id="approval_001",
        function_call=function_call,
    )

    result = client._prepare_content_for_openai(Role.ASSISTANT, approval_response, {})

    assert result["type"] == "mcp_approval_response"
    assert result["approval_request_id"] == "approval_001"
    assert result["approve"] is True


def test_prepare_content_for_openai_error_content() -> None:
    """Test _prepare_content_for_openai with error content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    error_content = Content.from_error(
        message="Operation failed",
        error_code="ERR_123",
        error_details="Invalid parameter",
    )

    result = client._prepare_content_for_openai(Role.ASSISTANT, error_content, {})

    # ErrorContent should return empty dict (logged but not sent)
    assert result == {}


def test_prepare_content_for_openai_usage_content() -> None:
    """Test _prepare_content_for_openai with usage content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    usage_content = Content.from_usage(
        usage_details={
            "input_token_count": 100,
            "output_token_count": 50,
            "total_token_count": 150,
        }
    )

    result = client._prepare_content_for_openai(Role.ASSISTANT, usage_content, {})

    # UsageContent should return empty dict (logged but not sent)
    assert result == {}


def test_prepare_content_for_openai_hosted_vector_store_content() -> None:
    """Test _prepare_content_for_openai with hosted vector store content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    vector_store_content = Content.from_hosted_vector_store(
        vector_store_id="vs_123",
    )

    result = client._prepare_content_for_openai(Role.ASSISTANT, vector_store_content, {})

    # HostedVectorStoreContent should return empty dict (logged but not sent)
    assert result == {}


def test_parse_response_from_openai_with_mcp_server_tool_result() -> None:
    """Test _parse_response_from_openai with MCP server tool result."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    # Mock MCP call item with result
    mock_mcp_item = MagicMock()
    mock_mcp_item.type = "mcp_call"
    mock_mcp_item.id = "mcp_call_123"
    mock_mcp_item.name = "get_data"
    mock_mcp_item.arguments = {"key": "value"}
    mock_mcp_item.server_label = "TestServer"
    mock_mcp_item.result = [{"content": [{"type": "text", "text": "MCP result"}]}]

    mock_response.output = [mock_mcp_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    # Should have both call and result content
    assert len(response.messages[0].contents) == 2
    call_content, result_content = response.messages[0].contents

    assert call_content.type == "mcp_server_tool_call"
    assert call_content.call_id == "mcp_call_123"
    assert call_content.tool_name == "get_data"
    assert call_content.server_name == "TestServer"

    assert result_content.type == "mcp_server_tool_result"
    assert result_content.call_id == "mcp_call_123"
    assert result_content.output is not None


def test_parse_chunk_from_openai_with_mcp_call_result() -> None:
    """Test _parse_chunk_from_openai with MCP call output."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock event with MCP call that has output
    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"

    mock_item = MagicMock()
    mock_item.type = "mcp_call"
    mock_item.id = "mcp_call_456"
    mock_item.call_id = "call_456"
    mock_item.name = "fetch_resource"
    mock_item.server_label = "ResourceServer"
    mock_item.arguments = {"resource_id": "123"}
    # Use proper content structure that _parse_content can handle
    mock_item.result = [{"type": "text", "text": "test result"}]

    mock_event.item = mock_item
    mock_event.output_index = 0

    function_call_ids: dict[int, tuple[str, str]] = {}

    update = client._parse_chunk_from_openai(mock_event, options={}, function_call_ids=function_call_ids)

    # Should have both call and result in contents
    assert len(update.contents) == 2
    call_content, result_content = update.contents

    assert call_content.type == "mcp_server_tool_call"
    assert call_content.call_id in ["mcp_call_456", "call_456"]
    assert call_content.tool_name == "fetch_resource"

    assert result_content.type == "mcp_server_tool_result"
    assert result_content.call_id in ["mcp_call_456", "call_456"]
    # Verify the output was parsed
    assert result_content.output is not None


def test_prepare_message_for_openai_with_function_approval_response() -> None:
    """Test _prepare_message_for_openai with function approval response content in messages."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    function_call = Content.from_function_call(
        call_id="call_789",
        name="execute_command",
        arguments='{"command": "ls"}',
    )

    approval_response = Content.from_function_approval_response(
        approved=True,
        id="approval_003",
        function_call=function_call,
    )

    message = ChatMessage(role="user", contents=[approval_response])
    call_id_to_id: dict[str, str] = {}

    result = client._prepare_message_for_openai(message, call_id_to_id)

    # FunctionApprovalResponseContent is added directly, not nested in args with role
    assert len(result) == 1
    prepared_message = result[0]
    assert prepared_message["type"] == "mcp_approval_response"
    assert prepared_message["approval_request_id"] == "approval_003"
    assert prepared_message["approve"] is True


def test_chat_message_with_error_content() -> None:
    """Test that error content in messages is handled properly."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    error_content = Content.from_error(
        message="Test error",
        error_code="TEST_ERR",
    )

    message = ChatMessage(role="assistant", contents=[error_content])
    call_id_to_id: dict[str, str] = {}

    result = client._prepare_message_for_openai(message, call_id_to_id)

    # Message should be prepared with empty content list since ErrorContent returns {}
    assert len(result) == 1
    prepared_message = result[0]
    assert prepared_message["role"] == "assistant"
    # Content should be a list with empty dict since ErrorContent returns {}
    assert prepared_message.get("content") == [{}]


def test_chat_message_with_usage_content() -> None:
    """Test that usage content in messages is handled properly."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    usage_content = Content.from_usage(
        usage_details={
            "input_token_count": 200,
            "output_token_count": 100,
            "total_token_count": 300,
        }
    )

    message = ChatMessage(role="assistant", contents=[usage_content])
    call_id_to_id: dict[str, str] = {}

    result = client._prepare_message_for_openai(message, call_id_to_id)

    # Message should be prepared with empty content list since UsageContent returns {}
    assert len(result) == 1
    prepared_message = result[0]
    assert prepared_message["role"] == "assistant"
    # Content should be a list with empty dict since UsageContent returns {}
    assert prepared_message.get("content") == [{}]


def test_hosted_file_content_preparation() -> None:
    """Test _prepare_content_for_openai with hosted file content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    hosted_file = Content.from_hosted_file(
        file_id="file_abc123",
        media_type="application/pdf",
        name="document.pdf",
    )

    result = client._prepare_content_for_openai(Role.USER, hosted_file, {})

    assert result["type"] == "input_file"
    assert result["file_id"] == "file_abc123"


def test_function_approval_response_with_mcp_tool_call() -> None:
    """Test function approval response content with MCP server tool call content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mcp_call = Content.from_mcp_server_tool_call(
        call_id="mcp_call_999",
        tool_name="sensitive_action",
        server_name="SecureServer",
        arguments={"action": "delete"},
    )

    approval_response = Content.from_function_approval_response(
        approved=False,
        id="approval_mcp_001",
        function_call=mcp_call,
    )

    result = client._prepare_content_for_openai(Role.ASSISTANT, approval_response, {})

    assert result["type"] == "mcp_approval_response"
    assert result["approval_request_id"] == "approval_mcp_001"
    assert result["approve"] is False


def test_response_format_with_conflicting_definitions() -> None:
    """Test that conflicting response_format definitions raise an error."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Mock response_format and text_config that conflict
    response_format = {"type": "json_schema", "format": {"type": "json_schema", "name": "Test", "schema": {}}}
    text_config = {"format": {"type": "json_object"}}

    with pytest.raises(ServiceInvalidRequestError, match="Conflicting response_format definitions"):
        client._prepare_response_and_text_format(response_format=response_format, text_config=text_config)


def test_response_format_json_object_type() -> None:
    """Test response_format with json_object type."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {"type": "json_object"}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "json_object"


def test_response_format_text_type() -> None:
    """Test response_format with text type."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {"type": "text"}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "text"


def test_response_format_with_format_key() -> None:
    """Test response_format that already has a format key."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {"format": {"type": "json_schema", "name": "MySchema", "schema": {"type": "object"}}}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "json_schema"
    assert text_config["format"]["name"] == "MySchema"


def test_response_format_json_schema_no_name_uses_title() -> None:
    """Test json_schema response_format without name uses title from schema."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {
        "type": "json_schema",
        "json_schema": {"schema": {"title": "MyTitle", "type": "object", "properties": {}}},
    }

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["name"] == "MyTitle"


def test_response_format_json_schema_with_strict() -> None:
    """Test json_schema response_format with strict mode."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "StrictSchema", "schema": {"type": "object"}, "strict": True},
    }

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["strict"] is True


def test_response_format_json_schema_with_description() -> None:
    """Test json_schema response_format with description."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "DescribedSchema",
            "schema": {"type": "object"},
            "description": "A test schema",
        },
    }

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["description"] == "A test schema"


def test_response_format_json_schema_missing_schema() -> None:
    """Test json_schema response_format without schema raises error."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {"type": "json_schema", "json_schema": {"name": "NoSchema"}}

    with pytest.raises(ServiceInvalidRequestError, match="json_schema response_format requires a schema"):
        client._prepare_response_and_text_format(response_format=response_format, text_config=None)


def test_response_format_unsupported_type() -> None:
    """Test unsupported response_format type raises error."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = {"type": "unsupported_format"}

    with pytest.raises(ServiceInvalidRequestError, match="Unsupported response_format"):
        client._prepare_response_and_text_format(response_format=response_format, text_config=None)


def test_response_format_invalid_type() -> None:
    """Test invalid response_format type raises error."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    response_format = "invalid"  # Not a Pydantic model or mapping

    with pytest.raises(ServiceInvalidRequestError, match="response_format must be a Pydantic model or mapping"):
        client._prepare_response_and_text_format(response_format=response_format, text_config=None)  # type: ignore


def test_parse_response_with_store_false() -> None:
    """Test _get_conversation_id returns None when store is False."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_123"
    mock_response.conversation = MagicMock()
    mock_response.conversation.id = "conv_456"

    conversation_id = client._get_conversation_id(mock_response, store=False)

    assert conversation_id is None


def test_parse_response_uses_response_id_when_no_conversation() -> None:
    """Test _get_conversation_id returns response ID when no conversation exists."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_789"
    mock_response.conversation = None

    conversation_id = client._get_conversation_id(mock_response, store=True)

    assert conversation_id == "resp_789"


def test_streaming_chunk_with_usage_only() -> None:
    """Test streaming chunk that only contains usage info."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.completed"
    mock_event.response = MagicMock()
    mock_event.response.id = "resp_usage"
    mock_event.response.model = "test-model"
    mock_event.response.conversation = None
    mock_event.response.usage = MagicMock()
    mock_event.response.usage.input_tokens = 50
    mock_event.response.usage.output_tokens = 25
    mock_event.response.usage.total_tokens = 75
    mock_event.response.usage.input_tokens_details = None
    mock_event.response.usage.output_tokens_details = None

    update = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    # Should have usage content
    assert len(update.contents) == 1
    assert update.contents[0].type == "usage"
    assert update.contents[0].usage_details["total_token_count"] == 75


def test_prepare_tools_for_openai_with_hosted_mcp() -> None:
    """Test that HostedMCPTool is converted to the correct response tool dict."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    tool = HostedMCPTool(
        name="My MCP",
        url="https://mcp.example",
        description="An MCP server",
        approval_mode={"always_require_approval": ["tool_a", "tool_b"]},
        allowed_tools={"tool_a", "tool_b"},
        headers={"X-Test": "yes"},
        additional_properties={"custom": "value"},
    )

    resp_tools = client._prepare_tools_for_openai([tool])
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 1
    mcp = resp_tools[0]
    assert isinstance(mcp, dict)
    assert mcp["type"] == "mcp"
    assert mcp["server_label"] == "My_MCP"
    # server_url may be normalized to include a trailing slash by the client
    assert str(mcp["server_url"]).rstrip("/") == "https://mcp.example"
    assert mcp["server_description"] == "An MCP server"
    assert mcp["headers"]["X-Test"] == "yes"
    assert set(mcp["allowed_tools"]) == {"tool_a", "tool_b"}
    # approval mapping created from approval_mode dict
    assert "require_approval" in mcp


def test_parse_response_from_openai_with_mcp_approval_request() -> None:
    """Test that a non-streaming mcp_approval_request is parsed into FunctionApprovalRequestContent."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_item = MagicMock()
    mock_item.type = "mcp_approval_request"
    mock_item.id = "approval-1"
    mock_item.name = "do_sensitive_action"
    mock_item.arguments = {"arg": 1}
    mock_item.server_label = "My_MCP"

    mock_response.output = [mock_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert response.messages[0].contents[0].type == "function_approval_request"
    req = response.messages[0].contents[0]
    assert req.id == "approval-1"
    assert req.function_call.name == "do_sensitive_action"
    assert req.function_call.arguments == {"arg": 1}
    assert req.function_call.additional_properties["server_label"] == "My_MCP"


def test_responses_client_created_at_uses_utc(
    openai_unit_test_env: dict[str, str],
) -> None:
    """Test that ChatResponse from responses client uses UTC timestamp.

    This is a regression test for the issue where created_at was using local time
    but labeling it as UTC (with 'Z' suffix).
    """
    client = OpenAIResponsesClient()

    # Use a specific Unix timestamp: 1733011890 = 2024-12-01T00:31:30Z (UTC)
    utc_timestamp = 1733011890

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = utc_timestamp

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Test response"
    mock_message_content.annotations = None

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    # Verify that created_at is correctly formatted as UTC
    assert response.created_at is not None
    assert response.created_at.endswith("Z"), "Timestamp should end with 'Z' for UTC"

    # Parse the timestamp and verify it matches UTC time
    expected_utc_time = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    expected_formatted = expected_utc_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert response.created_at == expected_formatted, (
        f"Expected UTC timestamp {expected_formatted}, got {response.created_at}"
    )


def test_prepare_tools_for_openai_with_raw_image_generation() -> None:
    """Test that raw image_generation tool dict is handled correctly with parameter mapping."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test with raw tool dict using OpenAI parameters directly
    tool = {
        "type": "image_generation",
        "size": "1536x1024",
        "quality": "high",
        "output_format": "webp",
        "output_quality": 75,
    }

    resp_tools = client._prepare_tools_for_openai([tool])
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 1

    image_tool = resp_tools[0]
    assert isinstance(image_tool, dict)
    assert image_tool["type"] == "image_generation"
    assert image_tool["size"] == "1536x1024"
    assert image_tool["quality"] == "high"
    assert image_tool["output_format"] == "webp"
    assert image_tool["output_quality"] == 75


def test_prepare_tools_for_openai_with_raw_image_generation_openai_responses_params() -> None:
    """Test raw image_generation tool with OpenAI-specific parameters."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test with OpenAI-specific parameters
    tool = {
        "type": "image_generation",
        "size": "1024x1024",
        "model": "gpt-image-1",
        "input_fidelity": "high",
        "moderation": "strict",
        "output_format": "png",
    }

    resp_tools = client._prepare_tools_for_openai([tool])
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 1

    image_tool = resp_tools[0]
    assert isinstance(image_tool, dict)
    assert image_tool["type"] == "image_generation"

    # Cast to dict for easier access to ImageGeneration-specific fields
    tool_dict = dict(image_tool)
    assert tool_dict["size"] == "1024x1024"
    # Check OpenAI-specific parameters are included
    assert tool_dict["model"] == "gpt-image-1"
    assert tool_dict["input_fidelity"] == "high"
    assert tool_dict["moderation"] == "strict"
    assert tool_dict["output_format"] == "png"


def test_prepare_tools_for_openai_with_raw_image_generation_minimal() -> None:
    """Test raw image_generation tool with minimal configuration."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test with minimal parameters (just type)
    tool = {"type": "image_generation"}

    resp_tools = client._prepare_tools_for_openai([tool])
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 1

    image_tool = resp_tools[0]
    assert isinstance(image_tool, dict)
    assert image_tool["type"] == "image_generation"
    # Should only have the type parameter when created with minimal config
    assert len(image_tool) == 1


def test_prepare_tools_for_openai_with_hosted_image_generation() -> None:
    """Test HostedImageGenerationTool conversion."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    tool = HostedImageGenerationTool(
        description="Generate images",
        options={"output_format": "png", "size": "512x512"},
        additional_properties={"quality": "high"},
    )

    resp_tools = client._prepare_tools_for_openai([tool])
    assert len(resp_tools) == 1
    image_tool = resp_tools[0]
    assert image_tool["type"] == "image_generation"
    assert image_tool["output_format"] == "png"
    assert image_tool["size"] == "512x512"
    assert image_tool["quality"] == "high"


def test_parse_chunk_from_openai_with_mcp_approval_request() -> None:
    """Test that a streaming mcp_approval_request event is parsed into FunctionApprovalRequestContent."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"
    mock_item = MagicMock()
    mock_item.type = "mcp_approval_request"
    mock_item.id = "approval-stream-1"
    mock_item.name = "do_stream_action"
    mock_item.arguments = {"x": 2}
    mock_item.server_label = "My_MCP"
    mock_event.item = mock_item

    update = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)
    assert any(c.type == "function_approval_request" for c in update.contents)
    fa = next(c for c in update.contents if c.type == "function_approval_request")
    assert fa.id == "approval-stream-1"
    assert fa.function_call.name == "do_stream_action"


@pytest.mark.parametrize("enable_instrumentation", [False], indirect=True)
@pytest.mark.parametrize("enable_sensitive_data", [False], indirect=True)
async def test_end_to_end_mcp_approval_flow(span_exporter) -> None:
    """End-to-end mocked test:
    model issues an mcp_approval_request, user approves, client sends mcp_approval_response.
    """
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # First mocked response: model issues an mcp_approval_request
    mock_response1 = MagicMock()
    mock_response1.output_parsed = None
    mock_response1.metadata = {}
    mock_response1.usage = None
    mock_response1.id = "resp-1"
    mock_response1.model = "test-model"
    mock_response1.created_at = 1000000000

    mock_item = MagicMock()
    mock_item.type = "mcp_approval_request"
    mock_item.id = "approval-1"
    mock_item.name = "do_sensitive_action"
    mock_item.arguments = {"arg": "value"}
    mock_item.server_label = "My_MCP"
    mock_response1.output = [mock_item]

    # Second mocked response: simple assistant acknowledgement after approval
    mock_response2 = MagicMock()
    mock_response2.output_parsed = None
    mock_response2.metadata = {}
    mock_response2.usage = None
    mock_response2.id = "resp-2"
    mock_response2.model = "test-model"
    mock_response2.created_at = 1000000001
    mock_text_item = MagicMock()
    mock_text_item.type = "message"
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "Approved."
    mock_text_item.content = [mock_text_content]
    mock_response2.output = [mock_text_item]

    # Patch the create call to return the two mocked responses in sequence
    with patch.object(client.client.responses, "create", side_effect=[mock_response1, mock_response2]) as mock_create:
        # First call: get the approval request
        response = await client.get_response(messages=[ChatMessage(role="user", text="Trigger approval")])
        assert response.messages[0].contents[0].type == "function_approval_request"
        req = response.messages[0].contents[0]
        assert req.id == "approval-1"

        # Build a user approval and send it (include required function_call)
        approval = Content.from_function_approval_response(approved=True, id=req.id, function_call=req.function_call)
        approval_message = ChatMessage(role="user", contents=[approval])
        _ = await client.get_response(messages=[approval_message])

        # Ensure two calls were made and the second includes the mcp_approval_response
        assert mock_create.call_count == 2
        _, kwargs = mock_create.call_args_list[1]
        sent_input = kwargs.get("input")
        assert isinstance(sent_input, list)
        found = False
        for item in sent_input:
            if isinstance(item, dict) and item.get("type") == "mcp_approval_response":
                assert item["approval_request_id"] == "approval-1"
                assert item["approve"] is True
                found = True
        assert found


def test_usage_details_basic() -> None:
    """Test _parse_usage_from_openai without cached or reasoning tokens."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_usage.total_tokens = 150
    mock_usage.input_tokens_details = None
    mock_usage.output_tokens_details = None

    details = client._parse_usage_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details["input_token_count"] == 100
    assert details["output_token_count"] == 50
    assert details["total_token_count"] == 150


def test_usage_details_with_cached_tokens() -> None:
    """Test _parse_usage_from_openai with cached input tokens."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_usage = MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 75
    mock_usage.total_tokens = 275
    mock_usage.input_tokens_details = MagicMock()
    mock_usage.input_tokens_details.cached_tokens = 25
    mock_usage.output_tokens_details = None

    details = client._parse_usage_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details["input_token_count"] == 200
    assert details["openai.cached_input_tokens"] == 25


def test_usage_details_with_reasoning_tokens() -> None:
    """Test _parse_usage_from_openai with reasoning tokens."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    mock_usage = MagicMock()
    mock_usage.input_tokens = 150
    mock_usage.output_tokens = 80
    mock_usage.total_tokens = 230
    mock_usage.input_tokens_details = None
    mock_usage.output_tokens_details = MagicMock()
    mock_usage.output_tokens_details.reasoning_tokens = 30

    details = client._parse_usage_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details["output_token_count"] == 80
    assert details["openai.reasoning_tokens"] == 30


def test_get_metadata_from_response() -> None:
    """Test the _get_metadata_from_response method."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test with logprobs
    mock_output_with_logprobs = MagicMock()
    mock_output_with_logprobs.logprobs = {"token": "test", "probability": 0.9}

    metadata = client._get_metadata_from_response(mock_output_with_logprobs)  # type: ignore
    assert "logprobs" in metadata
    assert metadata["logprobs"]["token"] == "test"

    # Test without logprobs
    mock_output_no_logprobs = MagicMock()
    mock_output_no_logprobs.logprobs = None

    metadata_empty = client._get_metadata_from_response(mock_output_no_logprobs)  # type: ignore
    assert metadata_empty == {}


def test_streaming_response_basic_structure() -> None:
    """Test that _parse_chunk_from_openai returns proper structure."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions(store=True)
    function_call_ids: dict[int, tuple[str, str]] = {}

    # Test with a basic mock event to ensure the method returns proper structure
    mock_event = MagicMock()

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)  # type: ignore

    # Should get a valid ChatResponseUpdate structure
    assert isinstance(response, ChatResponseUpdate)
    assert response.role == Role.ASSISTANT
    assert response.model_id == "test-model"
    assert isinstance(response.contents, list)
    assert response.raw_representation is mock_event


def test_streaming_response_created_type() -> None:
    """Test streaming response with created type"""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.created"
    mock_event.response = MagicMock()
    mock_event.response.id = "resp_1234"
    mock_event.response.conversation = MagicMock()
    mock_event.response.conversation.id = "conv_5678"

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert response.response_id == "resp_1234"
    assert response.conversation_id == "conv_5678"


def test_streaming_response_in_progress_type() -> None:
    """Test streaming response with in_progress type"""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.in_progress"
    mock_event.response = MagicMock()
    mock_event.response.id = "resp_1234"
    mock_event.response.conversation = MagicMock()
    mock_event.response.conversation.id = "conv_5678"

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert response.response_id == "resp_1234"
    assert response.conversation_id == "conv_5678"


def test_streaming_annotation_added_with_file_path() -> None:
    """Test streaming annotation added event with file_path type extracts HostedFileContent."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 0
    mock_event.annotation = {
        "type": "file_path",
        "file_id": "file-abc123",
        "index": 42,
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 1
    content = response.contents[0]
    assert content.type == "hosted_file"
    assert content.file_id == "file-abc123"
    assert content.additional_properties is not None
    assert content.additional_properties.get("annotation_index") == 0
    assert content.additional_properties.get("index") == 42


def test_streaming_annotation_added_with_file_citation() -> None:
    """Test streaming annotation added event with file_citation type extracts HostedFileContent."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 1
    mock_event.annotation = {
        "type": "file_citation",
        "file_id": "file-xyz789",
        "filename": "sample.txt",
        "index": 15,
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 1
    content = response.contents[0]
    assert content.type == "hosted_file"
    assert content.file_id == "file-xyz789"
    assert content.additional_properties is not None
    assert content.additional_properties.get("filename") == "sample.txt"
    assert content.additional_properties.get("index") == 15


def test_streaming_annotation_added_with_container_file_citation() -> None:
    """Test streaming annotation added event with container_file_citation type."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 2
    mock_event.annotation = {
        "type": "container_file_citation",
        "file_id": "file-container123",
        "container_id": "container-456",
        "filename": "data.csv",
        "start_index": 10,
        "end_index": 50,
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 1
    content = response.contents[0]
    assert content.type == "hosted_file"
    assert content.file_id == "file-container123"
    assert content.additional_properties is not None
    assert content.additional_properties.get("container_id") == "container-456"
    assert content.additional_properties.get("filename") == "data.csv"
    assert content.additional_properties.get("start_index") == 10
    assert content.additional_properties.get("end_index") == 50


def test_streaming_annotation_added_with_unknown_type() -> None:
    """Test streaming annotation added event with unknown type is ignored."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 0
    mock_event.annotation = {
        "type": "url_citation",
        "url": "https://example.com",
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    # url_citation should not produce HostedFileContent
    assert len(response.contents) == 0


def test_service_response_exception_includes_original_error_details() -> None:
    """Test that ServiceResponseException messages include original error details in the new format."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    messages = [ChatMessage(role="user", text="test message")]

    mock_response = MagicMock()
    original_error_message = "Request rate limit exceeded"
    mock_error = BadRequestError(
        message=original_error_message,
        response=mock_response,
        body={"error": {"code": "rate_limit", "message": original_error_message}},
    )
    mock_error.code = "rate_limit"

    with (
        patch.object(client.client.responses, "parse", side_effect=mock_error),
        pytest.raises(ServiceResponseException) as exc_info,
    ):
        asyncio.run(client.get_response(messages=messages, options={"response_format": OutputStruct}))

    exception_message = str(exc_info.value)
    assert "service failed to complete the prompt:" in exception_message
    assert original_error_message in exception_message


def test_get_streaming_response_with_response_format() -> None:
    """Test get_streaming_response with response_format."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    messages = [ChatMessage(role="user", text="Test streaming with format")]

    # It will fail due to invalid API key, but exercises the code path
    with pytest.raises(ServiceResponseException):

        async def run_streaming():
            async for _ in client.get_streaming_response(messages=messages, options={"response_format": OutputStruct}):
                pass

        asyncio.run(run_streaming())


def test_prepare_content_for_openai_image_content() -> None:
    """Test _prepare_content_for_openai with image content variations."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test image content with detail parameter and file_id
    image_content_with_detail = Content.from_uri(
        uri="https://example.com/image.jpg",
        media_type="image/jpeg",
        additional_properties={"detail": "high", "file_id": "file_123"},
    )
    result = client._prepare_content_for_openai(Role.USER, image_content_with_detail, {})  # type: ignore
    assert result["type"] == "input_image"
    assert result["image_url"] == "https://example.com/image.jpg"
    assert result["detail"] == "high"
    assert result["file_id"] == "file_123"

    # Test image content without additional properties (defaults)
    image_content_basic = Content.from_uri(uri="https://example.com/basic.png", media_type="image/png")
    result = client._prepare_content_for_openai(Role.USER, image_content_basic, {})  # type: ignore
    assert result["type"] == "input_image"
    assert result["detail"] == "auto"
    assert result["file_id"] is None


def test_prepare_content_for_openai_audio_content() -> None:
    """Test _prepare_content_for_openai with audio content variations."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test WAV audio content
    wav_content = Content.from_uri(uri="data:audio/wav;base64,abc123", media_type="audio/wav")
    result = client._prepare_content_for_openai(Role.USER, wav_content, {})  # type: ignore
    assert result["type"] == "input_audio"
    assert result["input_audio"]["data"] == "data:audio/wav;base64,abc123"
    assert result["input_audio"]["format"] == "wav"

    # Test MP3 audio content
    mp3_content = Content.from_uri(uri="data:audio/mp3;base64,def456", media_type="audio/mp3")
    result = client._prepare_content_for_openai(Role.USER, mp3_content, {})  # type: ignore
    assert result["type"] == "input_audio"
    assert result["input_audio"]["format"] == "mp3"


def test_prepare_content_for_openai_unsupported_content() -> None:
    """Test _prepare_content_for_openai with unsupported content types."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test unsupported audio format
    unsupported_audio = Content.from_uri(uri="data:audio/ogg;base64,ghi789", media_type="audio/ogg")
    result = client._prepare_content_for_openai(Role.USER, unsupported_audio, {})  # type: ignore
    assert result == {}

    # Test non-media content
    text_uri_content = Content.from_uri(uri="https://example.com/document.txt", media_type="text/plain")
    result = client._prepare_content_for_openai(Role.USER, text_uri_content, {})  # type: ignore
    assert result == {}


def test_parse_chunk_from_openai_code_interpreter() -> None:
    """Test _parse_chunk_from_openai with code_interpreter_call."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event_image = MagicMock()
    mock_event_image.type = "response.output_item.added"
    mock_item_image = MagicMock()
    mock_item_image.type = "code_interpreter_call"
    mock_image_output = MagicMock()
    mock_image_output.type = "image"
    mock_image_output.url = "https://example.com/plot.png"
    mock_item_image.outputs = [mock_image_output]
    mock_item_image.code = None
    mock_event_image.item = mock_item_image

    result = client._parse_chunk_from_openai(mock_event_image, chat_options, function_call_ids)  # type: ignore
    assert len(result.contents) == 1
    assert result.contents[0].type == "code_interpreter_tool_result"
    assert result.contents[0].outputs
    assert any(out.type == "uri" and out.uri == "https://example.com/plot.png" for out in result.contents[0].outputs)


def test_parse_chunk_from_openai_reasoning() -> None:
    """Test _parse_chunk_from_openai with reasoning content."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event_reasoning = MagicMock()
    mock_event_reasoning.type = "response.output_item.added"
    mock_item_reasoning = MagicMock()
    mock_item_reasoning.type = "reasoning"
    mock_reasoning_content = MagicMock()
    mock_reasoning_content.text = "Analyzing the problem step by step..."
    mock_item_reasoning.content = [mock_reasoning_content]
    mock_item_reasoning.summary = ["Problem analysis summary"]
    mock_event_reasoning.item = mock_item_reasoning

    result = client._parse_chunk_from_openai(mock_event_reasoning, chat_options, function_call_ids)  # type: ignore
    assert len(result.contents) == 1
    assert result.contents[0].type == "text_reasoning"
    assert result.contents[0].text == "Analyzing the problem step by step..."
    if result.contents[0].additional_properties:
        assert result.contents[0].additional_properties["summary"] == "Problem analysis summary"


def test_prepare_content_for_openai_text_reasoning_comprehensive() -> None:
    """Test _prepare_content_for_openai with TextReasoningContent all additional properties."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test TextReasoningContent with all additional properties
    comprehensive_reasoning = Content.from_text_reasoning(
        text="Comprehensive reasoning summary",
        additional_properties={
            "status": "in_progress",
            "reasoning_text": "Step-by-step analysis",
            "encrypted_content": "secure_data_456",
        },
    )
    result = client._prepare_content_for_openai(Role.ASSISTANT, comprehensive_reasoning, {})  # type: ignore
    assert result["type"] == "reasoning"
    assert result["summary"]["text"] == "Comprehensive reasoning summary"
    assert result["status"] == "in_progress"
    assert result["content"]["type"] == "reasoning_text"
    assert result["content"]["text"] == "Step-by-step analysis"
    assert result["encrypted_content"] == "secure_data_456"


def test_streaming_reasoning_text_delta_event() -> None:
    """Test reasoning text delta event creates TextReasoningContent."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    event = ResponseReasoningTextDeltaEvent(
        type="response.reasoning_text.delta",
        content_index=0,
        item_id="reasoning_123",
        output_index=0,
        sequence_number=1,
        delta="reasoning delta",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={}) as mock_metadata:
        response = client._parse_chunk_from_openai(event, chat_options, function_call_ids)  # type: ignore

        assert len(response.contents) == 1
        assert response.contents[0].type == "text_reasoning"
        assert response.contents[0].text == "reasoning delta"
        assert response.contents[0].raw_representation == event
        mock_metadata.assert_called_once_with(event)


def test_streaming_reasoning_text_done_event() -> None:
    """Test reasoning text done event creates TextReasoningContent with complete text."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    event = ResponseReasoningTextDoneEvent(
        type="response.reasoning_text.done",
        content_index=0,
        item_id="reasoning_456",
        output_index=0,
        sequence_number=2,
        text="complete reasoning",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"test": "data"}) as mock_metadata:
        response = client._parse_chunk_from_openai(event, chat_options, function_call_ids)  # type: ignore

        assert len(response.contents) == 1
        assert response.contents[0].type == "text_reasoning"
        assert response.contents[0].text == "complete reasoning"
        assert response.contents[0].raw_representation == event
        mock_metadata.assert_called_once_with(event)
        assert response.additional_properties == {"test": "data"}


def test_streaming_reasoning_summary_text_delta_event() -> None:
    """Test reasoning summary text delta event creates TextReasoningContent."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    event = ResponseReasoningSummaryTextDeltaEvent(
        type="response.reasoning_summary_text.delta",
        item_id="summary_789",
        output_index=0,
        sequence_number=3,
        summary_index=0,
        delta="summary delta",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={}) as mock_metadata:
        response = client._parse_chunk_from_openai(event, chat_options, function_call_ids)  # type: ignore

        assert len(response.contents) == 1
        assert response.contents[0].type == "text_reasoning"
        assert response.contents[0].text == "summary delta"
        assert response.contents[0].raw_representation == event
        mock_metadata.assert_called_once_with(event)


def test_streaming_reasoning_summary_text_done_event() -> None:
    """Test reasoning summary text done event creates TextReasoningContent with complete text."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    event = ResponseReasoningSummaryTextDoneEvent(
        type="response.reasoning_summary_text.done",
        item_id="summary_012",
        output_index=0,
        sequence_number=4,
        summary_index=0,
        text="complete summary",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"custom": "meta"}) as mock_metadata:
        response = client._parse_chunk_from_openai(event, chat_options, function_call_ids)  # type: ignore

        assert len(response.contents) == 1
        assert response.contents[0].type == "text_reasoning"
        assert response.contents[0].text == "complete summary"
        assert response.contents[0].raw_representation == event
        mock_metadata.assert_called_once_with(event)
        assert response.additional_properties == {"custom": "meta"}


def test_streaming_reasoning_events_preserve_metadata() -> None:
    """Test that reasoning events preserve metadata like regular text events."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    text_event = ResponseTextDeltaEvent(
        type="response.output_text.delta",
        content_index=0,
        item_id="text_item",
        output_index=0,
        sequence_number=1,
        logprobs=[],
        delta="text",
    )

    reasoning_event = ResponseReasoningTextDeltaEvent(
        type="response.reasoning_text.delta",
        content_index=0,
        item_id="reasoning_item",
        output_index=0,
        sequence_number=2,
        delta="reasoning",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"test": "metadata"}):
        text_response = client._parse_chunk_from_openai(text_event, chat_options, function_call_ids)  # type: ignore
        reasoning_response = client._parse_chunk_from_openai(reasoning_event, chat_options, function_call_ids)  # type: ignore

        # Both should preserve metadata
        assert text_response.additional_properties == {"test": "metadata"}
        assert reasoning_response.additional_properties == {"test": "metadata"}

        # Content types should be different
        assert text_response.contents[0].type == "text"
        assert reasoning_response.contents[0].type == "text_reasoning"


def test_parse_response_from_openai_image_generation_raw_base64():
    """Test image generation response parsing with raw base64 string."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with raw base64 image data (PNG signature)
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-response-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1234567890

    # Mock image generation output item with raw base64 (PNG format)
    png_signature = b"\x89PNG\r\n\x1a\n"
    mock_base64 = base64.b64encode(png_signature + b"fake_png_data_here").decode()

    mock_item = MagicMock()
    mock_item.type = "image_generation_call"
    mock_item.result = mock_base64

    mock_response.output = [mock_item]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    # Verify the response contains call + result with DataContent output
    assert len(response.messages[0].contents) == 2
    call_content, result_content = response.messages[0].contents
    assert call_content.type == "image_generation_tool_call"
    assert result_content.type == "image_generation_tool_result"
    assert result_content.outputs
    data_out = result_content.outputs
    assert data_out.type == "data"
    assert data_out.uri.startswith("data:image/png;base64,")
    assert data_out.media_type == "image/png"


def test_parse_response_from_openai_image_generation_existing_data_uri():
    """Test image generation response parsing with existing data URI."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with existing data URI
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-response-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1234567890

    # Mock image generation output item with existing data URI (valid WEBP header)
    webp_signature = b"RIFF" + b"\x12\x00\x00\x00" + b"WEBP"
    valid_webp_base64 = base64.b64encode(webp_signature + b"VP8 fake_data").decode()
    mock_item = MagicMock()
    mock_item.type = "image_generation_call"
    mock_item.result = valid_webp_base64

    mock_response.output = [mock_item]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    # Verify the response contains call + result with DataContent output
    assert len(response.messages[0].contents) == 2
    call_content, result_content = response.messages[0].contents
    assert call_content.type == "image_generation_tool_call"
    assert result_content.type == "image_generation_tool_result"
    assert result_content.outputs
    data_out = result_content.outputs
    assert data_out.type == "data"
    assert data_out.uri == f"data:image/webp;base64,{valid_webp_base64}"
    assert data_out.media_type == "image/webp"


def test_parse_response_from_openai_image_generation_format_detection():
    """Test different image format detection from base64 data."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Test JPEG detection
    jpeg_signature = b"\xff\xd8\xff"
    mock_base64_jpeg = base64.b64encode(jpeg_signature + b"fake_jpeg_data").decode()

    mock_response_jpeg = MagicMock()
    mock_response_jpeg.output_parsed = None
    mock_response_jpeg.metadata = {}
    mock_response_jpeg.usage = None
    mock_response_jpeg.id = "test-id"
    mock_response_jpeg.model = "test-model"
    mock_response_jpeg.created_at = 1234567890

    mock_item_jpeg = MagicMock()
    mock_item_jpeg.type = "image_generation_call"
    mock_item_jpeg.result = mock_base64_jpeg
    mock_response_jpeg.output = [mock_item_jpeg]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response_jpeg = client._parse_response_from_openai(mock_response_jpeg, options={})  # type: ignore
    result_contents = response_jpeg.messages[0].contents
    assert result_contents[1].type == "image_generation_tool_result"
    outputs = result_contents[1].outputs
    assert outputs and outputs.type == "data"
    assert outputs.media_type == "image/jpeg"
    assert "data:image/jpeg;base64," in outputs.uri

    # Test WEBP detection
    webp_signature = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"
    mock_base64_webp = base64.b64encode(webp_signature + b"fake_webp_data").decode()

    mock_response_webp = MagicMock()
    mock_response_webp.output_parsed = None
    mock_response_webp.metadata = {}
    mock_response_webp.usage = None
    mock_response_webp.id = "test-id"
    mock_response_webp.model = "test-model"
    mock_response_webp.created_at = 1234567890

    mock_item_webp = MagicMock()
    mock_item_webp.type = "image_generation_call"
    mock_item_webp.result = mock_base64_webp
    mock_response_webp.output = [mock_item_webp]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response_webp = client._parse_response_from_openai(mock_response_webp, options={})  # type: ignore
    outputs_webp = response_webp.messages[0].contents[1].outputs
    assert outputs_webp and outputs_webp.type == "data"
    assert outputs_webp.media_type == "image/webp"
    assert "data:image/webp;base64," in outputs_webp.uri


def test_parse_response_from_openai_image_generation_fallback():
    """Test image generation with invalid base64 falls back to PNG."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")

    # Create a mock response with invalid base64
    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-response-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1234567890

    # Mock image generation output item with unrecognized format (should fall back to PNG)
    unrecognized_data = b"UNKNOWN_FORMAT" + b"some_binary_data"
    unrecognized_base64 = base64.b64encode(unrecognized_data).decode()
    mock_item = MagicMock()
    mock_item.type = "image_generation_call"
    mock_item.result = unrecognized_base64

    mock_response.output = [mock_item]

    with patch.object(client, "_get_metadata_from_response", return_value={}):
        response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    # Verify it falls back to PNG format for unrecognized binary data
    assert len(response.messages[0].contents) == 2
    result_content = response.messages[0].contents[1]
    assert result_content.type == "image_generation_tool_result"
    assert result_content.outputs
    content = result_content.outputs
    assert content.media_type == "image/png"
    assert f"data:image/png;base64,{unrecognized_base64}" == content.uri


async def test_prepare_options_store_parameter_handling() -> None:
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    messages = [ChatMessage(role="user", text="Test message")]

    test_conversation_id = "test-conversation-123"
    chat_options = ChatOptions(store=True, conversation_id=test_conversation_id)
    options = await client._prepare_options(messages, chat_options)  # type: ignore
    assert options["store"] is True
    assert options["previous_response_id"] == test_conversation_id

    chat_options = ChatOptions(store=False, conversation_id="")
    options = await client._prepare_options(messages, chat_options)  # type: ignore
    assert options["store"] is False

    chat_options = ChatOptions(store=None, conversation_id=None)
    options = await client._prepare_options(messages, chat_options)  # type: ignore
    assert "store" not in options
    assert "previous_response_id" not in options

    chat_options = ChatOptions()
    options = await client._prepare_options(messages, chat_options)  # type: ignore
    assert "store" not in options
    assert "previous_response_id" not in options


async def test_conversation_id_precedence_kwargs_over_options() -> None:
    """When both kwargs and options contain conversation_id, kwargs wins."""
    client = OpenAIResponsesClient(model_id="test-model", api_key="test-key")
    messages = [ChatMessage(role="user", text="Hello")]

    # options has a stale response id, kwargs carries the freshest one
    opts = {"conversation_id": "resp_old_123"}
    run_opts = await client._prepare_options(messages, opts, conversation_id="resp_new_456")  # type: ignore

    # Verify kwargs takes precedence and maps to previous_response_id for resp_* IDs
    assert run_opts.get("previous_response_id") == "resp_new_456"
    assert "conversation" not in run_opts


def test_with_callable_api_key() -> None:
    """Test OpenAIResponsesClient initialization with callable API key."""

    async def get_api_key() -> str:
        return "test-api-key-123"

    client = OpenAIResponsesClient(model_id="gpt-4o", api_key=get_api_key)

    # Verify client was created successfully
    assert client.model_id == "gpt-4o"
    # OpenAI SDK now manages callable API keys internally
    assert client.client is not None


# region Integration Tests


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
        param("metadata", {"test_key": "test_value"}, False, id="metadata"),
        param("frequency_penalty", 0.5, False, id="frequency_penalty"),
        param("presence_penalty", 0.3, False, id="presence_penalty"),
        param("stop", ["END"], False, id="stop"),
        param("allow_multiple_tool_calls", True, False, id="allow_multiple_tool_calls"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        # OpenAIResponsesOptions - just verify they don't fail
        param("safety_identifier", "user-hash-abc123", False, id="safety_identifier"),
        param("truncation", "auto", False, id="truncation"),
        param("top_logprobs", 5, False, id="top_logprobs"),
        param("prompt_cache_key", "test-cache-key", False, id="prompt_cache_key"),
        param("max_tool_calls", 3, False, id="max_tool_calls"),
        # Complex options requiring output validation
        param("tools", [get_weather], True, id="tools_function"),
        param("tool_choice", "auto", True, id="tool_choice_auto"),
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
    """Parametrized test covering all ChatOptions and OpenAIResponsesOptions.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.
    """
    openai_responses_client = OpenAIResponsesClient()
    # to ensure toolmode required does not endlessly loop
    openai_responses_client.function_invocation_configuration.max_iterations = 1

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
            response_gen = openai_responses_client.get_streaming_response(
                messages=messages,
                options=options,
            )

            output_format = option_value if option_name.startswith("response_format") else None
            response = await ChatResponse.from_chat_response_generator(response_gen, output_format_type=output_format)
        else:
            # Test non-streaming mode
            response = await openai_responses_client.get_response(
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
    client = OpenAIResponsesClient(model_id="gpt-5")

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


@pytest.mark.skip(
    reason="Unreliable due to OpenAI vector store indexing potential "
    "race condition. See https://github.com/microsoft/agent-framework/issues/1669"
)
@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_integration_file_search() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

    file_id, vector_store = await create_vector_store(openai_responses_client)
    # Test that the client will use the web search tool
    response = await openai_responses_client.get_response(
        messages=[
            ChatMessage(
                role="user",
                text="What is the weather today? Do a file search to find the answer.",
            )
        ],
        options={
            "tool_choice": "auto",
            "tools": [HostedFileSearchTool(inputs=vector_store)],
        },
    )

    await delete_vector_store(openai_responses_client, file_id, vector_store.vector_store_id)
    assert "sunny" in response.text.lower()
    assert "75" in response.text


@pytest.mark.skip(
    reason="Unreliable due to OpenAI vector store indexing "
    "potential race condition. See https://github.com/microsoft/agent-framework/issues/1669"
)
@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_integration_streaming_file_search() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

    file_id, vector_store = await create_vector_store(openai_responses_client)
    # Test that the client will use the web search tool
    response = openai_responses_client.get_streaming_response(
        messages=[
            ChatMessage(
                role="user",
                text="What is the weather today? Do a file search to find the answer.",
            )
        ],
        options={
            "tool_choice": "auto",
            "tools": [HostedFileSearchTool(inputs=vector_store)],
        },
    )

    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if content.type == "text" and content.text:
                full_message += content.text

    await delete_vector_store(openai_responses_client, file_id, vector_store.vector_store_id)

    assert "sunny" in full_message.lower()
    assert "75" in full_message
