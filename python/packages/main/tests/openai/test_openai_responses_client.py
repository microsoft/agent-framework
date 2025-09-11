# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
from openai import BadRequestError
from pydantic import BaseModel

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedCodeInterpreterTool,
    HostedFileContent,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    Role,
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
    weather: str | None = None


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
    assert isinstance(openai_responses_client, ChatClientProtocol)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIResponsesClient(api_key="34523", ai_model_id={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    openai_responses_client = OpenAIResponsesClient(ai_model_id=ai_model_id)

    assert openai_responses_client.ai_model_id == ai_model_id
    assert isinstance(openai_responses_client, ChatClientProtocol)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    openai_responses_client = OpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert openai_responses_client.ai_model_id == openai_unit_test_env["OPENAI_RESPONSES_MODEL_ID"]
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


async def test_response_format_parse_path() -> None:
    """Test get_response response_format parsing path."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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

    with patch.object(client.client.responses, "parse", return_value=mock_parsed_response):
        response = await client.get_response(
            messages=[ChatMessage(role="user", text="Test message")], response_format=OutputStruct, store=True
        )

        assert response.conversation_id == "parsed_response_123"
        assert response.ai_model_id == "test-model"


async def test_bad_request_error_non_content_filter() -> None:
    """Test get_response BadRequestError without content_filter."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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
                messages=[ChatMessage(role="user", text="Test message")], response_format=OutputStruct
            )

        assert "failed to complete the prompt" in str(exc_info.value)


async def test_streaming_content_filter_exception_handling() -> None:
    """Test that content filter errors in get_streaming_response are properly handled."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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


@skip_if_openai_integration_tests_disabled
async def test_get_streaming_response_with_all_parameters() -> None:
    """Test get_streaming_response with all possible parameters."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    # Should fail due to invalid API key
    with pytest.raises(ServiceResponseException):
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


def test_response_content_creation_with_annotations() -> None:
    """Test _create_response_content with different annotation types."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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
        response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

        assert len(response.messages[0].contents) >= 1
        assert isinstance(response.messages[0].contents[0], TextContent)
        assert response.messages[0].contents[0].text == "Text with annotations."
        assert response.messages[0].contents[0].annotations is not None


def test_response_content_creation_with_refusal() -> None:
    """Test _create_response_content with refusal content."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], TextContent)
    assert response.messages[0].contents[0].text == "I cannot provide that information."


def test_response_content_creation_with_reasoning() -> None:
    """Test _create_response_content with reasoning content."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert len(response.messages[0].contents) == 1
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    function_call = response.messages[0].contents[0]
    assert function_call.call_id == "call_123"
    assert function_call.name == "get_weather"
    assert function_call.arguments == '{"location": "Seattle"}'


def test_tools_to_response_tools_with_hosted_mcp() -> None:
    """Test that HostedMCPTool is converted to the correct response tool dict."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    tool = HostedMCPTool(
        name="My MCP",
        url="https://mcp.example",
        description="An MCP server",
        approval_mode={"always_require_approval": ["tool_a", "tool_b"]},
        allowed_tools={"tool_a", "tool_b"},
        headers={"X-Test": "yes"},
        additional_properties={"custom": "value"},
    )

    resp_tools = client._tools_to_response_tools([tool])
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


def test_create_response_content_with_mcp_approval_request() -> None:
    """Test that a non-streaming mcp_approval_request is parsed into FunctionApprovalRequestContent."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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

    response = client._create_response_content(mock_response, chat_options=ChatOptions())  # type: ignore

    assert isinstance(response.messages[0].contents[0], FunctionApprovalRequestContent)
    req = response.messages[0].contents[0]
    assert req.id == "approval-1"
    assert req.function_call.name == "do_sensitive_action"
    assert req.function_call.arguments == {"arg": 1}
    assert req.function_call.additional_properties["server_label"] == "My_MCP"


def test_create_streaming_response_content_with_mcp_approval_request() -> None:
    """Test that a streaming mcp_approval_request event is parsed into FunctionApprovalRequestContent."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")
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

    update = client._create_streaming_response_content(mock_event, chat_options, function_call_ids)
    assert any(isinstance(c, FunctionApprovalRequestContent) for c in update.contents)
    fa = next(c for c in update.contents if isinstance(c, FunctionApprovalRequestContent))
    assert fa.id == "approval-stream-1"
    assert fa.function_call.name == "do_stream_action"


@pytest.mark.parametrize("enable_otel", [False], indirect=True)
@pytest.mark.parametrize("enable_sensitive_data", [False], indirect=True)
def test_end_to_end_mcp_approval_flow(otel_settings) -> None:
    """End-to-end mocked test:
    model issues an mcp_approval_request, user approves, client sends mcp_approval_response.
    """
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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
        response = asyncio.run(client.get_response(messages=[ChatMessage(role="user", text="Trigger approval")]))
        assert isinstance(response.messages[0].contents[0], FunctionApprovalRequestContent)
        req = response.messages[0].contents[0]
        assert req.id == "approval-1"

        # Build a user approval and send it (include required function_call)
        approval = FunctionApprovalResponseContent(approved=True, id=req.id, function_call=req.function_call)
        approval_message = ChatMessage(role="user", contents=[approval])
        _ = asyncio.run(client.get_response(messages=[approval_message]))

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
    """Test _usage_details_from_openai without cached or reasoning tokens."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    mock_usage = MagicMock()
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

    mock_usage = MagicMock()
    mock_usage.input_tokens = 200
    mock_usage.output_tokens = 75
    mock_usage.total_tokens = 275
    mock_usage.input_tokens_details = MagicMock()
    mock_usage.input_tokens_details.cached_tokens = 25
    mock_usage.output_tokens_details = None

    details = client._usage_details_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details.input_token_count == 200
    assert details.additional_counts["openai.cached_input_tokens"] == 25


def test_usage_details_with_reasoning_tokens() -> None:
    """Test _usage_details_from_openai with reasoning tokens."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

    mock_usage = MagicMock()
    mock_usage.input_tokens = 150
    mock_usage.output_tokens = 80
    mock_usage.total_tokens = 230
    mock_usage.input_tokens_details = None
    mock_usage.output_tokens_details = MagicMock()
    mock_usage.output_tokens_details.reasoning_tokens = 30

    details = client._usage_details_from_openai(mock_usage)  # type: ignore
    assert details is not None
    assert details.output_token_count == 80
    assert details.additional_counts["openai.reasoning_tokens"] == 30


def test_get_metadata_from_response() -> None:
    """Test the _get_metadata_from_response method."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")

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
    """Test that _create_streaming_response_content returns proper structure."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")
    chat_options = ChatOptions(store=True)
    function_call_ids: dict[int, tuple[str, str]] = {}

    # Test with a basic mock event to ensure the method returns proper structure
    mock_event = MagicMock()

    response = client._create_streaming_response_content(mock_event, chat_options, function_call_ids)  # type: ignore

    # Should get a valid ChatResponseUpdate structure
    assert isinstance(response, ChatResponseUpdate)
    assert response.role == Role.ASSISTANT
    assert response.ai_model_id == "test-model"
    assert isinstance(response.contents, list)
    assert response.raw_representation is mock_event


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

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
    output = response.value
    assert output is not None, "Response value is None"
    assert "seattle" in output.location.lower()
    assert output.weather is not None


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_response_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

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

    assert isinstance(openai_responses_client, ChatClientProtocol)

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
    response = await ChatResponse.from_chat_response_generator(
        openai_responses_client.get_streaming_response(messages=messages)
    )

    assert "scientists" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in Seattle is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    response = openai_responses_client.get_streaming_response(
        messages=messages,
        response_format=OutputStruct,
    )
    chunks = []
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        chunks.append(chunk)
    full_message = ChatResponse.from_chat_response_updates(chunks, output_format_type=OutputStruct)
    output = full_message.value
    assert output is not None, "Response value is None"
    assert "seattle" in output.location.lower()
    assert output.weather is not None


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_streaming_tools() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

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
    chunks = []
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        chunks.append(chunk)

    full_message = ChatResponse.from_chat_response_updates(chunks, output_format_type=OutputStruct)
    output = full_message.value
    assert output is not None, "Response value is None"
    assert "seattle" in output.location.lower()
    assert "sunny" in output.weather.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_web_search() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

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
    assert response.text is not None


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_web_search_streaming() -> None:
    openai_responses_client = OpenAIResponsesClient()

    assert isinstance(openai_responses_client, ChatClientProtocol)

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
    assert full_message is not None


@skip_if_openai_integration_tests_disabled
@pytest.mark.skip(reason="OpenAI file search functionality is currently broken - tracked in GitHub issue")
async def test_openai_responses_client_file_search() -> None:
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
        tools=[HostedFileSearchTool(inputs=vector_store)],
        tool_choice="auto",
    )

    await delete_vector_store(openai_responses_client, file_id, vector_store.vector_store_id)
    assert "sunny" in response.text.lower()
    assert "75" in response.text


@skip_if_openai_integration_tests_disabled
@pytest.mark.skip(reason="OpenAI file search functionality is currently broken - tracked in GitHub issue")
async def test_openai_responses_client_streaming_file_search() -> None:
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


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_basic_run():
    """Test OpenAI Responses Client agent basic run functionality with OpenAIResponsesClient."""
    agent = OpenAIResponsesClient().create_agent(
        instructions="You are a helpful assistant.",
    )

    # Test basic run
    response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

    assert isinstance(response, AgentRunResponse)
    assert response.text is not None
    assert len(response.text) > 0
    assert "hello world" in response.text.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_basic_run_streaming():
    """Test OpenAI Responses Client agent basic streaming functionality with OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
    ) as agent:
        # Test streaming run
        full_text = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert isinstance(chunk, AgentRunResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert len(full_text) > 0
        assert "streaming response test" in full_text.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_thread_persistence():
    """Test OpenAI Responses Client agent thread persistence across runs with OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First interaction
        first_response = await agent.run("My favorite programming language is Python. Remember this.", thread=thread)

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None

        # Second interaction - test memory
        second_response = await agent.run("What is my favorite programming language?", thread=thread)

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_thread_storage_with_store_true():
    """Test OpenAI Responses Client agent with store=True to verify service_thread_id is returned."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant.",
    ) as agent:
        # Create a new thread
        thread = AgentThread()

        # Initially, service_thread_id should be None
        assert thread.service_thread_id is None

        # Run with store=True to store messages on OpenAI side
        response = await agent.run(
            "Hello! Please remember that my name is Alex.",
            thread=thread,
            store=True,
        )

        # Validate response
        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0

        # After store=True, service_thread_id should be populated
        assert thread.service_thread_id is not None
        assert isinstance(thread.service_thread_id, str)
        assert len(thread.service_thread_id) > 0


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_existing_thread():
    """Test OpenAI Responses Client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and capture the thread
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My hobby is photography. Remember this.", thread=thread)

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None

        # Preserve the thread for reuse
        preserved_thread = thread

    # Second conversation - reuse the thread in a new agent instance
    if preserved_thread:
        async with ChatAgent(
            chat_client=OpenAIResponsesClient(),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my hobby?", thread=preserved_thread)

            assert isinstance(second_response, AgentRunResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_hosted_code_interpreter_tool():
    """Test OpenAI Responses Client agent with HostedCodeInterpreterTool through OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can execute Python code.",
        tools=[HostedCodeInterpreterTool()],
    ) as agent:
        # Test code interpreter functionality
        response = await agent.run("Calculate the sum of numbers from 1 to 10 using Python code.")

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0
        # Should contain calculation result (sum of 1-10 = 55) or code execution content
        contains_relevant_content = any(
            term in response.text.lower() for term in ["55", "sum", "code", "python", "calculate", "10"]
        )
        assert contains_relevant_content or len(response.text.strip()) > 10


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with OpenAI Responses Client."""

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],  # Agent-level tool
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "72"])


@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_run_level_tool_isolation():
    """Test that run-level tools are isolated to specific runs and don't persist with OpenAI Responses Client."""
    # Counter to track how many times the weather tool is called
    call_count = 0

    @ai_function
    async def get_weather_with_counter(location: Annotated[str, "The location as a city name"]) -> str:
        """Get the current weather in a given location."""
        nonlocal call_count
        call_count += 1
        return f"The weather in {location} is sunny and 72°F."

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant.",
    ) as agent:
        # First run - use run-level tool
        first_response = await agent.run(
            "What's the weather like in Chicago?",
            tools=[get_weather_with_counter],  # Run-level tool
        )

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the run-level weather tool (call count should be 1)
        assert call_count == 1
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - run-level tool should NOT persist (key isolation test)
        second_response = await agent.run("What's the weather like in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should NOT use the weather tool since it was only run-level in previous call
        # Call count should still be 1 (no additional calls)
        assert call_count == 1


def test_service_response_exception_includes_original_error_details() -> None:
    """Test that ServiceResponseException messages include original error details in the new format."""
    client = OpenAIResponsesClient(ai_model_id="test-model", api_key="test-key")
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
        asyncio.run(client.get_response(messages=messages, response_format=OutputStruct))

    exception_message = str(exc_info.value)
    assert "service failed to complete the prompt:" in exception_message
    assert original_error_message in exception_message
