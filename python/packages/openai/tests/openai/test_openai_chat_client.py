# Copyright (c) Microsoft. All rights reserved.

import base64
import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    Agent,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionTool,
    Message,
    SupportsChatGetResponse,
    SupportsCodeInterpreterTool,
    SupportsFileSearchTool,
    SupportsImageGenerationTool,
    SupportsMCPTool,
    SupportsWebSearchTool,
    tool,
)
from agent_framework._sessions import (
    AgentSession,
    InMemoryHistoryProvider,
    SessionContext,
)
from agent_framework.exceptions import (
    ChatClientException,
    ChatClientInvalidRequestException,
    SettingNotFoundError,
)
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

from agent_framework_openai import OpenAIChatClient
from agent_framework_openai._chat_client import OPENAI_LOCAL_SHELL_CALL_ITEM_ID_KEY
from agent_framework_openai._exceptions import OpenAIContentFilterException

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests.",
)


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str | None = None


class _FakeAsyncEventStream:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self._iterator = iter(())

    def __aiter__(self) -> "_FakeAsyncEventStream":
        self._iterator = iter(self._events)
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeAsyncEventStreamContext(_FakeAsyncEventStream):
    async def __aenter__(self) -> "_FakeAsyncEventStreamContext":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        return None


async def create_vector_store(
    client: OpenAIChatClient,
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


async def delete_vector_store(client: OpenAIChatClient, file_id: str, vector_store_id: str) -> None:
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
    openai_responses_client = OpenAIChatClient()

    assert openai_responses_client.model == openai_unit_test_env["OPENAI_MODEL"]
    assert isinstance(openai_responses_client, SupportsChatGetResponse)


def test_init_uses_explicit_parameters() -> None:
    signature = inspect.signature(OpenAIChatClient.__init__)

    assert "additional_properties" in signature.parameters
    assert "compaction_strategy" in signature.parameters
    assert "tokenizer" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_openai_chat_client_supports_all_tool_protocols() -> None:
    assert isinstance(OpenAIChatClient, SupportsCodeInterpreterTool)
    assert isinstance(OpenAIChatClient, SupportsWebSearchTool)
    assert isinstance(OpenAIChatClient, SupportsImageGenerationTool)
    assert isinstance(OpenAIChatClient, SupportsMCPTool)
    assert isinstance(OpenAIChatClient, SupportsFileSearchTool)


def test_protocol_isinstance_with_openai_chat_client_instance() -> None:
    client = object.__new__(OpenAIChatClient)

    assert isinstance(client, SupportsCodeInterpreterTool)
    assert isinstance(client, SupportsWebSearchTool)


def test_openai_chat_client_tool_methods_return_dict() -> None:
    code_tool = OpenAIChatClient.get_code_interpreter_tool()
    assert isinstance(code_tool, dict)
    assert code_tool.get("type") == "code_interpreter"

    web_tool = OpenAIChatClient.get_web_search_tool()
    assert isinstance(web_tool, dict)
    assert web_tool.get("type") == "web_search"


def test_init_prefers_openai_chat_model(monkeypatch, openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "test_chat_model")

    openai_responses_client = OpenAIChatClient()

    assert openai_responses_client.model == "test_chat_model"


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ValueError):
        OpenAIChatClient(api_key="34523", model={"test": "dict"})  # type: ignore


def test_init_model_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model = "test_model"
    openai_responses_client = OpenAIChatClient(model=model)

    assert openai_responses_client.model == model
    assert isinstance(openai_responses_client, SupportsChatGetResponse)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    openai_responses_client = OpenAIChatClient(
        default_headers=default_headers,
    )

    assert openai_responses_client.model == openai_unit_test_env["OPENAI_MODEL"]
    assert isinstance(openai_responses_client, SupportsChatGetResponse)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in openai_responses_client.client.default_headers
        assert openai_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["OPENAI_MODEL"]], indirect=True)
def test_init_with_empty_model(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(SettingNotFoundError):
        OpenAIChatClient()


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    model = "test_model"

    with pytest.raises(SettingNotFoundError):
        OpenAIChatClient(
            model=model,
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "model": openai_unit_test_env["OPENAI_MODEL"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    openai_responses_client = OpenAIChatClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
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

    openai_responses_client = OpenAIChatClient.from_dict(settings)
    dumped_settings = openai_responses_client.to_dict()
    assert dumped_settings["model"] == openai_unit_test_env["OPENAI_MODEL"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings.get("default_headers", {})


async def test_get_response_with_invalid_input() -> None:
    """Test get_response with invalid inputs to trigger exception handling."""

    client = OpenAIChatClient(model="invalid-model", api_key="test-key")

    # Test with empty messages which should trigger ChatClientInvalidRequestException
    with pytest.raises(ChatClientInvalidRequestException, match="Messages are required"):
        await client.get_response(messages=[])


async def test_get_response_with_all_parameters() -> None:
    """Test request preparation with a comprehensive parameter set."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    _, run_options, _ = await client._prepare_request(
        messages=[Message(role="user", contents=["Test message"])],
        options={
            "include": ["message.output_text.logprobs"],
            "instructions": "You are a helpful assistant",
            "max_tokens": 100,
            "parallel_tool_calls": True,
            "model": "gpt-4",
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

    assert run_options["include"] == ["message.output_text.logprobs"]
    assert run_options["max_output_tokens"] == 100
    assert run_options["parallel_tool_calls"] is True
    assert run_options["model"] == "gpt-4"
    assert run_options["previous_response_id"] == "prev-123"
    assert run_options["reasoning"] == {"chain_of_thought": "enabled"}
    assert run_options["service_tier"] == "auto"
    assert run_options["text_format"] is OutputStruct
    assert run_options["store"] is True
    assert run_options["temperature"] == 0.7
    assert run_options["tool_choice"] == "auto"
    assert run_options["top_p"] == 0.9
    assert run_options["user"] == "test-user"
    assert run_options["truncation"] == "auto"
    assert run_options["timeout"] == 30.0
    assert run_options["additional_properties"] == {"custom": "value"}
    assert len(run_options["tools"]) == 1
    assert run_options["tools"][0]["type"] == "function"
    assert run_options["tools"][0]["name"] == "get_weather"
    assert run_options["input"][0]["role"] == "system"
    assert run_options["input"][0]["content"][0]["text"] == "You are a helpful assistant"
    assert run_options["input"][1]["role"] == "user"
    assert run_options["input"][1]["content"][0]["text"] == "Test message"


@pytest.mark.asyncio
async def test_web_search_tool_with_location() -> None:
    """Test web search tool with location parameters."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test web search tool with location using static method
    web_search_tool = OpenAIChatClient.get_web_search_tool(
        user_location={
            "city": "Seattle",
            "country": "US",
            "region": "WA",
            "timezone": "America/Los_Angeles",
        }
    )

    _, run_options, _ = await client._prepare_request(
        messages=[Message(role="user", contents=["What's the weather?"])],
        options={"tools": [web_search_tool], "tool_choice": "auto"},
    )

    assert run_options["tools"] == [web_search_tool]
    assert run_options["tool_choice"] == "auto"


async def test_code_interpreter_tool_variations() -> None:
    """Test HostedCodeInterpreterTool with and without file inputs."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test code interpreter using static method
    code_tool = OpenAIChatClient.get_code_interpreter_tool()

    _, run_options, _ = await client._prepare_request(
        messages=[Message("user", ["Run some code"])],
        options={"tools": [code_tool]},
    )

    assert run_options["tools"] == [code_tool]

    # Test code interpreter with files using static method
    code_tool_with_files = OpenAIChatClient.get_code_interpreter_tool(file_ids=["file1", "file2"])

    _, run_options, _ = await client._prepare_request(
        messages=[Message(role="user", contents=["Process these files"])],
        options={"tools": [code_tool_with_files]},
    )

    assert run_options["tools"] == [code_tool_with_files]


async def test_content_filter_exception() -> None:
    """Test that content filter errors in get_response are properly handled."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Mock a BadRequestError with content_filter code
    mock_error = BadRequestError(
        message="Content filter error",
        response=MagicMock(),
        body={"error": {"code": "content_filter", "message": "Content filter error"}},
    )
    mock_error.code = "content_filter"

    with patch.object(client.client.responses, "create", side_effect=mock_error):
        with pytest.raises(OpenAIContentFilterException) as exc_info:
            await client.get_response(messages=[Message(role="user", contents=["Test message"])])

        assert "content error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_hosted_file_search_tool_validation() -> None:
    """Test HostedFileSearchTool validation and request preparation."""

    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test file search tool with vector store IDs
    file_search_tool = OpenAIChatClient.get_file_search_tool(vector_store_ids=["vs_123"])

    _, run_options, _ = await client._prepare_request(
        messages=[Message("user", ["Test"])],
        options={"tools": [file_search_tool]},
    )

    assert run_options["tools"] == [file_search_tool]


async def test_chat_message_parsing_with_function_calls() -> None:
    """Test message preparation with function call and function result content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Create messages with function call and result content
    function_call = Content.from_function_call(
        call_id="test-call-id",
        name="test_function",
        arguments='{"param": "value"}',
        additional_properties={"fc_id": "test-fc-id"},
    )

    function_result = Content.from_function_result(call_id="test-call-id", result="Function executed successfully")

    messages = [
        Message(role="user", contents=["Call a function"]),
        Message(role="assistant", contents=[function_call]),
        Message(role="tool", contents=[function_result]),
    ]

    prepared_messages = client._prepare_messages_for_openai(messages)

    assert prepared_messages == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Call a function"}],
        },
        {
            "call_id": "test-call-id",
            "id": "fc_test-fc-id",
            "type": "function_call",
            "name": "test_function",
            "arguments": '{"param": "value"}',
        },
        {
            "call_id": "test-call-id",
            "type": "function_call_output",
            "output": "Function executed successfully",
        },
    ]


async def test_response_format_parse_path() -> None:
    """Test get_response response_format parsing path."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
            messages=[Message(role="user", contents=["Test message"])],
            options={"response_format": OutputStruct, "store": True},
        )
        assert response.response_id == "parsed_response_123"
        assert response.conversation_id == "parsed_response_123"
        assert response.model == "test-model"


async def test_response_format_parse_path_with_conversation_id() -> None:
    """Test get_response response_format parsing path with set conversation ID."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
            messages=[Message(role="user", contents=["Test message"])],
            options={"response_format": OutputStruct, "store": True},
        )
        assert response.response_id == "parsed_response_123"
        assert response.conversation_id == "conversation_456"
        assert response.model == "test-model"


async def test_response_format_dict_parse_path() -> None:
    """Test get_response response_format parsing path for runtime JSON schema mappings."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    response_format = {"type": "object", "properties": {"answer": {"type": "string"}}}

    mock_response = MagicMock()
    mock_response.id = "response_123"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.metadata = {}
    mock_response.output_parsed = None
    mock_response.output = []
    mock_response.usage = None
    mock_response.finish_reason = None
    mock_response.conversation = None
    mock_response.status = "completed"

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = '{"answer": "Parsed"}'
    mock_message_content.annotations = []
    mock_message_content.logprobs = None

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]
    mock_response.output = [mock_message_item]

    with patch.object(client.client.responses, "create", return_value=mock_response):
        response = await client.get_response(
            messages=[Message(role="user", contents=["Test message"])],
            options={"response_format": response_format},
        )

    assert response.response_id == "response_123"
    assert response.value is not None
    assert isinstance(response.value, dict)
    assert response.value["answer"] == "Parsed"


async def test_bad_request_error_non_content_filter() -> None:
    """Test get_response BadRequestError without content_filter."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Mock a BadRequestError without content_filter code
    mock_error = BadRequestError(
        message="Invalid request",
        response=MagicMock(),
        body={"error": {"code": "invalid_request", "message": "Invalid request"}},
    )
    mock_error.code = "invalid_request"

    with patch.object(client.client.responses, "parse", side_effect=mock_error):
        with pytest.raises(ChatClientException) as exc_info:
            await client.get_response(
                messages=[Message(role="user", contents=["Test message"])],
                options={"response_format": OutputStruct},
            )

        assert "failed to complete the prompt" in str(exc_info.value)


async def test_streaming_content_filter_exception_handling() -> None:
    """Test that content filter errors in get_response(..., stream=True) are properly handled."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Mock the OpenAI client to raise a BadRequestError with content_filter code
    with patch.object(client.client.responses, "create") as mock_create:
        mock_create.side_effect = BadRequestError(
            message="Content filtered in stream",
            response=MagicMock(),
            body={"error": {"code": "content_filter", "message": "Content filtered"}},
        )
        mock_create.side_effect.code = "content_filter"

        with pytest.raises(OpenAIContentFilterException, match="service encountered a content error"):
            response_stream = client.get_response(stream=True, messages=[Message(role="user", contents=["Test"])])
            async for _ in response_stream:
                break


def test_response_content_creation_with_annotations() -> None:
    """Test _parse_response_from_openai with different annotation types."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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


def test_response_content_keeps_reasoning_and_function_calls_in_one_message() -> None:
    """Reasoning + function calls should parse into one assistant message."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    mock_reasoning_item.id = "rs_123"
    mock_reasoning_item.content = [mock_reasoning_content]
    mock_reasoning_item.summary = []

    mock_function_call_item_1 = MagicMock()
    mock_function_call_item_1.type = "function_call"
    mock_function_call_item_1.id = "fc_1"
    mock_function_call_item_1.call_id = "call_1"
    mock_function_call_item_1.name = "tool_1"
    mock_function_call_item_1.arguments = '{"x": 1}'

    mock_function_call_item_2 = MagicMock()
    mock_function_call_item_2.type = "function_call"
    mock_function_call_item_2.id = "fc_2"
    mock_function_call_item_2.call_id = "call_2"
    mock_function_call_item_2.name = "tool_2"
    mock_function_call_item_2.arguments = '{"y": 2}'

    mock_response.output = [
        mock_reasoning_item,
        mock_function_call_item_1,
        mock_function_call_item_2,
    ]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages) == 1
    assert response.messages[0].role == "assistant"
    assert [content.type for content in response.messages[0].contents] == [
        "text_reasoning",
        "function_call",
        "function_call",
    ]


def test_response_content_creation_with_code_interpreter() -> None:
    """Test _parse_response_from_openai with code interpreter outputs."""

    client = OpenAIChatClient(model="test-model", api_key="test-key")

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


def test_get_shell_tool_basic() -> None:
    """Test get_shell_tool returns hosted shell config with default auto environment."""
    tool = OpenAIChatClient.get_shell_tool()
    assert tool.type == "shell"
    assert tool.environment.type == "container_auto"


def test_get_shell_tool_rejects_local_without_func() -> None:
    """Local environment requires a local function executor."""
    with pytest.raises(ValueError, match="Local shell requires func"):
        OpenAIChatClient.get_shell_tool(environment={"type": "local"})


def test_get_shell_tool_rejects_environment_config_with_func() -> None:
    """Environment config is hosted-only and must not be passed with func."""

    def local_exec(command: str) -> str:
        return command

    with pytest.raises(ValueError, match="environment config is not supported"):
        OpenAIChatClient.get_shell_tool(
            func=local_exec,
            environment={"type": "container_auto"},
        )


def test_get_shell_tool_local_executor_maps_to_shell_tool() -> None:
    """Test local shell FunctionTool maps to OpenAI shell tool declaration."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    def local_exec(command: str) -> str:
        return command

    local_shell_tool = OpenAIChatClient.get_shell_tool(
        func=local_exec,
        approval_mode="never_require",
    )

    assert isinstance(local_shell_tool, FunctionTool)
    response_tools = client._prepare_tools_for_openai([local_shell_tool])
    assert len(response_tools) == 1
    assert response_tools[0].type == "shell"
    assert response_tools[0].environment.type == "local"


def test_get_shell_tool_reuses_function_tool_instance() -> None:
    """Passing a FunctionTool should update and return the same tool instance."""

    @tool(name="run_shell", approval_mode="never_require")
    def run_shell(command: str) -> str:
        return command

    shell_tool = OpenAIChatClient.get_shell_tool(
        func=run_shell,
        description="Run local shell command",
        approval_mode="always_require",
    )

    assert shell_tool is run_shell
    assert shell_tool.kind == "shell"
    assert shell_tool.description == "Run local shell command"
    assert shell_tool.approval_mode == "always_require"
    assert (shell_tool.additional_properties or {}).get("openai.responses.shell.environment") == {"type": "local"}


def test_response_content_creation_with_local_shell_call_maps_to_function_call() -> None:
    """Test local_shell_call is translated into function_call for invocation loop."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    def local_exec(command: str) -> str:
        return command

    local_shell_tool = OpenAIChatClient.get_shell_tool(func=local_exec)

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "completed"
    mock_response.incomplete = None

    mock_action = MagicMock()
    mock_action.command = ["python", "--version"]
    mock_action.timeout_ms = 30000

    mock_local_shell_call = MagicMock()
    mock_local_shell_call.type = "local_shell_call"
    mock_local_shell_call.id = "local-shell-item-1"
    mock_local_shell_call.call_id = "local-shell-call-1"
    mock_local_shell_call.action = mock_action
    mock_local_shell_call.status = "completed"

    mock_response.output = [mock_local_shell_call]

    response = client._parse_response_from_openai(mock_response, options={"tools": [local_shell_tool]})  # type: ignore[arg-type]
    assert len(response.messages[0].contents) == 1
    call_content = response.messages[0].contents[0]
    assert call_content.type == "function_call"
    assert call_content.call_id == "local-shell-call-1"
    assert call_content.name == local_shell_tool.name
    assert call_content.parse_arguments() == {"command": "python --version"}
    assert call_content.additional_properties[OPENAI_LOCAL_SHELL_CALL_ITEM_ID_KEY] == "local-shell-item-1"


@pytest.mark.asyncio
async def test_local_shell_tool_is_invoked_in_function_loop() -> None:
    """Test local shell call executes executor and sends local_shell_call_output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    executed_commands: list[str] = []

    def local_exec(command: str) -> str:
        executed_commands.append(command)
        return "Python 3.13.0"

    local_shell_tool = OpenAIChatClient.get_shell_tool(
        func=local_exec,
        approval_mode="never_require",
    )

    mock_response1 = MagicMock()
    mock_response1.output_parsed = None
    mock_response1.metadata = {}
    mock_response1.usage = None
    mock_response1.id = "resp-1"
    mock_response1.model = "test-model"
    mock_response1.created_at = 1000000000
    mock_response1.status = "completed"
    mock_response1.finish_reason = "tool_calls"
    mock_response1.incomplete = None

    mock_action = MagicMock()
    mock_action.command = ["python", "--version"]
    mock_action.timeout_ms = 30000

    mock_local_shell_call = MagicMock()
    mock_local_shell_call.type = "local_shell_call"
    mock_local_shell_call.id = "local-shell-item-1"
    mock_local_shell_call.call_id = "local-shell-call-1"
    mock_local_shell_call.action = mock_action
    mock_local_shell_call.status = "completed"
    mock_response1.output = [mock_local_shell_call]

    mock_response2 = MagicMock()
    mock_response2.output_parsed = None
    mock_response2.metadata = {}
    mock_response2.usage = None
    mock_response2.id = "resp-2"
    mock_response2.model = "test-model"
    mock_response2.created_at = 1000000001
    mock_response2.status = "completed"
    mock_response2.finish_reason = "stop"
    mock_response2.incomplete = None

    mock_text_item = MagicMock()
    mock_text_item.type = "message"
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "Python 3.13.0"
    mock_text_item.content = [mock_text_content]
    mock_response2.output = [mock_text_item]

    with patch.object(client.client.responses, "create", side_effect=[mock_response1, mock_response2]) as mock_create:
        await client.get_response(
            messages=[Message(role="user", contents=["What Python version is available?"])],
            options={"tools": [local_shell_tool]},
        )

        assert executed_commands == ["python --version"]
        assert mock_create.call_count == 2
        second_call_input = mock_create.call_args_list[1].kwargs["input"]
        local_shell_outputs = [item for item in second_call_input if item.get("type") == "local_shell_call_output"]
        assert len(local_shell_outputs) == 1
        output_payload = json.loads(local_shell_outputs[0]["output"])
        assert output_payload["stdout"] == "Python 3.13.0"


@pytest.mark.asyncio
async def test_shell_call_is_invoked_as_local_shell_function_loop() -> None:
    """Test shell_call maps to local function invocation and returns shell_call_output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    executed_commands: list[str] = []

    def local_exec(command: str) -> str:
        executed_commands.append(command)
        return "Python 3.13.0"

    local_shell_tool = OpenAIChatClient.get_shell_tool(
        func=local_exec,
        approval_mode="never_require",
    )

    mock_response1 = MagicMock()
    mock_response1.output_parsed = None
    mock_response1.metadata = {}
    mock_response1.usage = None
    mock_response1.id = "resp-1"
    mock_response1.model = "test-model"
    mock_response1.created_at = 1000000000
    mock_response1.status = "completed"
    mock_response1.finish_reason = "tool_calls"
    mock_response1.incomplete = None

    mock_action = MagicMock()
    mock_action.commands = ["python --version"]
    mock_action.timeout_ms = 30000
    mock_action.max_output_length = 4096

    mock_shell_call = MagicMock()
    mock_shell_call.type = "shell_call"
    mock_shell_call.id = "sh_test_shell_call_1"
    mock_shell_call.call_id = "shell-call-1"
    mock_shell_call.action = mock_action
    mock_shell_call.status = "completed"
    mock_response1.output = [mock_shell_call]

    mock_response2 = MagicMock()
    mock_response2.output_parsed = None
    mock_response2.metadata = {}
    mock_response2.usage = None
    mock_response2.id = "resp-2"
    mock_response2.model = "test-model"
    mock_response2.created_at = 1000000001
    mock_response2.status = "completed"
    mock_response2.finish_reason = "stop"
    mock_response2.incomplete = None

    mock_text_item = MagicMock()
    mock_text_item.type = "message"
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "Python 3.13.0"
    mock_text_item.content = [mock_text_content]
    mock_response2.output = [mock_text_item]

    with patch.object(client.client.responses, "create", side_effect=[mock_response1, mock_response2]) as mock_create:
        await client.get_response(
            messages=[Message(role="user", contents=["What Python version is available?"])],
            options={"tools": [local_shell_tool]},
        )

        assert executed_commands == ["python --version"]
        assert mock_create.call_count == 2
        second_call_input = mock_create.call_args_list[1].kwargs["input"]
        shell_outputs = [item for item in second_call_input if item.get("type") == "shell_call_output"]
        assert len(shell_outputs) == 1
        assert shell_outputs[0]["call_id"] == "shell-call-1"
        assert isinstance(shell_outputs[0]["output"], list)
        assert shell_outputs[0]["output"][0]["stdout"] == "Python 3.13.0"
        local_shell_outputs = [item for item in second_call_input if item.get("type") == "local_shell_call_output"]
        assert len(local_shell_outputs) == 0


async def test_tool_loop_store_false_omits_reasoning_items_from_second_request() -> None:
    """Stateless tool-loop replay must omit response-scoped reasoning items."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response1 = MagicMock()
    mock_response1.output_parsed = None
    mock_response1.metadata = {}
    mock_response1.usage = None
    mock_response1.id = "resp-1"
    mock_response1.model = "test-model"
    mock_response1.created_at = 1000000000
    mock_response1.status = "completed"
    mock_response1.finish_reason = "tool_calls"
    mock_response1.incomplete = None
    mock_response1.conversation = None

    mock_reasoning_item = MagicMock()
    mock_reasoning_item.type = "reasoning"
    mock_reasoning_item.id = "rs_local_only"
    mock_reasoning_item.content = []
    mock_reasoning_item.summary = []
    mock_reasoning_item.encrypted_content = None

    mock_function_call_item = MagicMock()
    mock_function_call_item.type = "function_call"
    mock_function_call_item.id = "fc_tool123"
    mock_function_call_item.call_id = "call_123"
    mock_function_call_item.name = "get_weather"
    mock_function_call_item.arguments = '{"location":"Amsterdam"}'
    mock_function_call_item.status = "completed"

    mock_response1.output = [mock_reasoning_item, mock_function_call_item]

    mock_response2 = MagicMock()
    mock_response2.output_parsed = None
    mock_response2.metadata = {}
    mock_response2.usage = None
    mock_response2.id = "resp-2"
    mock_response2.model = "test-model"
    mock_response2.created_at = 1000000001
    mock_response2.status = "completed"
    mock_response2.finish_reason = "stop"
    mock_response2.incomplete = None
    mock_response2.conversation = None

    mock_text_item = MagicMock()
    mock_text_item.type = "message"
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "The weather in Amsterdam is sunny."
    mock_text_item.content = [mock_text_content]
    mock_response2.output = [mock_text_item]

    with patch.object(client.client.responses, "create", side_effect=[mock_response1, mock_response2]) as mock_create:
        response = await client.get_response(
            messages=[Message(role="user", contents=["What's the weather in Amsterdam?"])],
            options={
                "store": False,
                "tools": [get_weather],
                "tool_choice": {"mode": "required", "required_function_name": "get_weather"},
            },
        )

    assert response.text == "The weather in Amsterdam is sunny."
    assert mock_create.call_count == 2

    second_call_input = mock_create.call_args_list[1].kwargs["input"]
    assert not any(item.get("type") == "reasoning" for item in second_call_input)

    function_calls = [item for item in second_call_input if item.get("type") == "function_call"]
    assert len(function_calls) == 1
    assert function_calls[0]["id"] == "fc_tool123"

    function_outputs = [item for item in second_call_input if item.get("type") == "function_call_output"]
    assert len(function_outputs) == 1
    assert function_outputs[0]["call_id"] == "call_123"


def test_response_content_creation_with_shell_call() -> None:
    """Test _parse_response_from_openai with shell_call output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "completed"
    mock_response.incomplete = None

    mock_action = MagicMock()
    mock_action.commands = ["ls -la", "pwd"]
    mock_action.timeout_ms = 60000
    mock_action.max_output_length = 4096

    mock_shell_call = MagicMock()
    mock_shell_call.type = "shell_call"
    mock_shell_call.call_id = "shell-call-1"
    mock_shell_call.action = mock_action
    mock_shell_call.status = "completed"

    mock_response.output = [mock_shell_call]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 1
    call_content = response.messages[0].contents[0]
    assert call_content.type == "shell_tool_call"
    assert call_content.call_id == "shell-call-1"
    assert call_content.commands == ["ls -la", "pwd"]
    assert call_content.timeout_ms == 60000
    assert call_content.max_output_length == 4096
    assert call_content.status == "completed"


def test_response_content_creation_with_shell_call_output() -> None:
    """Test _parse_response_from_openai with shell_call_output output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "completed"
    mock_response.incomplete = None

    mock_outcome = MagicMock()
    mock_outcome.type = "exit"
    mock_outcome.exit_code = 0

    mock_output_entry = MagicMock()
    mock_output_entry.stdout = "hello world\n"
    mock_output_entry.stderr = ""
    mock_output_entry.outcome = mock_outcome

    mock_shell_output = MagicMock()
    mock_shell_output.type = "shell_call_output"
    mock_shell_output.call_id = "shell-call-1"
    mock_shell_output.output = [mock_output_entry]
    mock_shell_output.max_output_length = 4096

    mock_response.output = [mock_shell_output]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 1
    result_content = response.messages[0].contents[0]
    assert result_content.type == "shell_tool_result"
    assert result_content.call_id == "shell-call-1"
    assert result_content.outputs is not None
    assert len(result_content.outputs) == 1
    assert result_content.outputs[0].type == "shell_command_output"
    assert result_content.outputs[0].stdout == "hello world\n"
    assert result_content.outputs[0].exit_code == 0
    assert result_content.outputs[0].timed_out is False
    assert result_content.max_output_length == 4096


def test_response_content_creation_with_shell_call_timeout() -> None:
    """Test _parse_response_from_openai with shell_call_output that timed out."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "completed"
    mock_response.incomplete = None

    mock_outcome = MagicMock()
    mock_outcome.type = "timeout"

    mock_output_entry = MagicMock()
    mock_output_entry.stdout = "partial output"
    mock_output_entry.stderr = None
    mock_output_entry.outcome = mock_outcome

    mock_shell_output = MagicMock()
    mock_shell_output.type = "shell_call_output"
    mock_shell_output.call_id = "shell-call-t"
    mock_shell_output.output = [mock_output_entry]
    mock_shell_output.max_output_length = None

    mock_response.output = [mock_shell_output]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    result_content = response.messages[0].contents[0]
    assert result_content.type == "shell_tool_result"
    assert result_content.outputs is not None
    assert result_content.outputs[0].type == "shell_command_output"
    assert result_content.outputs[0].timed_out is True
    assert result_content.outputs[0].exit_code is None


def test_response_content_creation_with_function_call() -> None:
    """Test _parse_response_from_openai with function call content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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


def test_parse_response_from_openai_with_web_search_call() -> None:
    """Test _parse_response_from_openai with web search output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp-web"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_search_item = MagicMock()
    mock_search_item.type = "web_search_call"
    mock_search_item.id = "ws_123"
    mock_search_item.status = "completed"
    mock_search_item.action = {
        "type": "search",
        "query": "current weather in Seattle",
        "queries": ["current weather in Seattle"],
        "sources": [{"title": "Weather", "url": "https://weather.example"}],
    }

    mock_response.output = [mock_search_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 2
    call_content, result_content = response.messages[0].contents
    assert call_content.type == "search_tool_call"
    assert call_content.call_id == "ws_123"
    assert call_content.tool_name == "web_search"
    assert call_content.status == "completed"
    assert call_content.arguments == mock_search_item.action
    assert result_content.type == "search_tool_result"
    assert result_content.call_id == "ws_123"
    assert result_content.tool_name == "web_search"
    assert result_content.status == "completed"
    assert result_content.result == {"action": mock_search_item.action}


def test_parse_response_from_openai_with_file_search_call() -> None:
    """Test _parse_response_from_openai with file search output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp-file"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000

    mock_search_item = MagicMock()
    mock_search_item.type = "file_search_call"
    mock_search_item.id = "fs_123"
    mock_search_item.status = "completed"
    mock_search_item.queries = ["weather history"]
    mock_search_item.results = [
        {
            "file_id": "file_1",
            "filename": "weather.txt",
            "score": 0.9,
            "text": "Seattle was cloudy.",
        }
    ]

    mock_response.output = [mock_search_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 2
    call_content, result_content = response.messages[0].contents
    assert call_content.type == "search_tool_call"
    assert call_content.call_id == "fs_123"
    assert call_content.tool_name == "file_search"
    assert call_content.status == "completed"
    assert call_content.arguments == {"queries": ["weather history"]}
    assert result_content.type == "search_tool_result"
    assert result_content.call_id == "fs_123"
    assert result_content.tool_name == "file_search"
    assert result_content.status == "completed"
    assert result_content.result == {"results": mock_search_item.results}


def test_prepare_content_for_opentool_approval_response() -> None:
    """Test _prepare_content_for_openai with function approval response content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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

    result = client._prepare_content_for_openai("assistant", approval_response)

    assert result["type"] == "mcp_approval_response"
    assert result["approval_request_id"] == "approval_001"
    assert result["approve"] is True


def test_prepare_content_for_openai_error_content() -> None:
    """Test _prepare_content_for_openai with error content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    error_content = Content.from_error(
        message="Operation failed",
        error_code="ERR_123",
        error_details="Invalid parameter",
    )

    result = client._prepare_content_for_openai("assistant", error_content)

    # ErrorContent should return empty dict (logged but not sent)
    assert result == {}


def test_prepare_content_for_openai_usage_content() -> None:
    """Test _prepare_content_for_openai with usage content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    usage_content = Content.from_usage(
        usage_details={
            "input_token_count": 100,
            "output_token_count": 50,
            "total_token_count": 150,
        }
    )

    result = client._prepare_content_for_openai("assistant", usage_content)

    # UsageContent should return empty dict (logged but not sent)
    assert result == {}


def test_prepare_content_for_openai_hosted_vector_store_content() -> None:
    """Test _prepare_content_for_openai with hosted vector store content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    vector_store_content = Content.from_hosted_vector_store(
        vector_store_id="vs_123",
    )

    result = client._prepare_content_for_openai("assistant", vector_store_content)

    # HostedVectorStoreContent should return empty dict (logged but not sent)
    assert result == {}


def test_prepare_content_for_openai_text_uses_role_specific_type() -> None:
    """Text content should use input_text for user and output_text for assistant."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    text_content = Content.from_text(text="hello")

    user_result = client._prepare_content_for_openai("user", text_content)
    assistant_result = client._prepare_content_for_openai("assistant", text_content)

    assert user_result["type"] == "input_text"
    assert assistant_result["type"] == "output_text"
    assert assistant_result["annotations"] == []
    assert user_result["text"] == "hello"
    assert assistant_result["text"] == "hello"


def test_prepare_messages_for_openai_assistant_history_uses_output_text_with_annotations() -> None:
    """Assistant history should be output_text and include required annotations."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    messages = [
        Message(role="user", contents=["What is async/await?"]),
        Message(role="assistant", contents=["Async/await enables non-blocking concurrency."]),
    ]

    prepared = client._prepare_messages_for_openai(messages)

    assert prepared[0]["role"] == "user"
    assert prepared[0]["content"][0]["type"] == "input_text"
    assert prepared[1]["role"] == "assistant"
    assert prepared[1]["content"][0]["type"] == "output_text"
    assert prepared[1]["content"][0]["annotations"] == []


def test_parse_response_from_openai_with_mcp_server_tool_result() -> None:
    """Test _parse_response_from_openai with MCP server tool result."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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


def test_parse_chunk_from_openai_with_web_search_call_added() -> None:
    """Test that response.output_item.added for web_search_call emits search tool call content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"
    mock_event.output_index = 0

    mock_item = MagicMock()
    mock_item.type = "web_search_call"
    mock_item.id = "ws_call_123"
    mock_item.status = "in_progress"
    mock_item.action = {"type": "search", "query": "weather in Seattle"}
    mock_event.item = mock_item

    update = client._parse_chunk_from_openai(mock_event, options=chat_options, function_call_ids=function_call_ids)

    assert len(update.contents) == 1
    content = update.contents[0]
    assert content.type == "search_tool_call"
    assert content.call_id == "ws_call_123"
    assert content.tool_name == "web_search"
    assert content.status == "in_progress"
    assert content.arguments == {"type": "search", "query": "weather in Seattle"}


def test_parse_chunk_from_openai_with_file_search_call_done() -> None:
    """Test that response.output_item.done for file_search_call emits search tool result content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_item.done"

    mock_item = MagicMock()
    mock_item.type = "file_search_call"
    mock_item.id = "fs_call_123"
    mock_item.status = "completed"
    mock_item.results = [{"file_id": "file_1", "text": "Seattle was cloudy."}]
    mock_event.item = mock_item

    update = client._parse_chunk_from_openai(mock_event, options=chat_options, function_call_ids=function_call_ids)

    assert len(update.contents) == 1
    content = update.contents[0]
    assert content.type == "search_tool_result"
    assert content.call_id == "fs_call_123"
    assert content.tool_name == "file_search"
    assert content.status == "completed"
    assert content.result == {"results": [{"file_id": "file_1", "text": "Seattle was cloudy."}]}


@pytest.mark.parametrize(
    "event_type",
    [
        "response.web_search_call.in_progress",
        "response.web_search_call.searching",
        "response.web_search_call.completed",
        "response.file_search_call.in_progress",
        "response.file_search_call.searching",
        "response.file_search_call.completed",
    ],
)
def test_parse_chunk_from_openai_ignores_search_progress_events(event_type: str) -> None:
    """Search progress events should be explicitly ignored instead of logged as unparsed."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = event_type

    update = client._parse_chunk_from_openai(mock_event, options=chat_options, function_call_ids=function_call_ids)

    assert update.contents == []


def test_parse_chunk_from_openai_with_mcp_call_added_defers_result() -> None:
    """Test that response.output_item.added for mcp_call emits only the call, not the result.

    The result is deferred to response.output_item.done.
    """
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_event = MagicMock()
    mock_event.type = "response.output_item.added"

    mock_item = MagicMock()
    mock_item.type = "mcp_call"
    mock_item.id = "mcp_call_456"
    mock_item.call_id = "call_456"
    mock_item.name = "fetch_resource"
    mock_item.server_label = "ResourceServer"
    mock_item.arguments = {"resource_id": "123"}
    mock_item.result = None
    mock_item.output = None
    mock_item.outputs = None

    mock_event.item = mock_item
    mock_event.output_index = 0

    function_call_ids: dict[int, tuple[str, str]] = {}

    update = client._parse_chunk_from_openai(mock_event, options={}, function_call_ids=function_call_ids)

    # Should have only the call content — result is deferred
    assert len(update.contents) == 1
    call_content = update.contents[0]

    assert call_content.type == "mcp_server_tool_call"
    assert call_content.call_id in ["mcp_call_456", "call_456"]
    assert call_content.tool_name == "fetch_resource"

    # No result should be emitted at this point
    result_contents = [c for c in update.contents if c.type == "mcp_server_tool_result"]
    assert len(result_contents) == 0


def test_parse_chunk_from_openai_with_mcp_output_item_done() -> None:
    """Test that response.output_item.done for mcp_call emits mcp_server_tool_result with output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_event = MagicMock()
    mock_event.type = "response.output_item.done"

    mock_item = MagicMock()
    mock_item.type = "mcp_call"
    mock_item.id = "mcp_call_456"
    mock_item.output = "The weather in Seattle is 72F and sunny."
    mock_event.item = mock_item

    function_call_ids: dict[int, tuple[str, str]] = {}

    update = client._parse_chunk_from_openai(mock_event, options={}, function_call_ids=function_call_ids)

    assert len(update.contents) == 1
    result_content = update.contents[0]

    assert result_content.type == "mcp_server_tool_result"
    assert result_content.call_id == "mcp_call_456"
    assert result_content.output is not None
    assert len(result_content.output) == 1
    assert result_content.output[0].text == "The weather in Seattle is 72F and sunny."
    assert result_content.raw_representation is mock_item


def test_parse_chunk_from_openai_with_mcp_output_item_done_no_output() -> None:
    """Test that response.output_item.done for mcp_call with no output emits result with None output."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_event = MagicMock()
    mock_event.type = "response.output_item.done"

    mock_item = MagicMock()
    mock_item.type = "mcp_call"
    mock_item.id = "mcp_call_789"
    mock_item.output = None
    mock_event.item = mock_item

    function_call_ids: dict[int, tuple[str, str]] = {}

    update = client._parse_chunk_from_openai(mock_event, options={}, function_call_ids=function_call_ids)

    assert len(update.contents) == 1
    result_content = update.contents[0]

    assert result_content.type == "mcp_server_tool_result"
    assert result_content.call_id == "mcp_call_789"
    assert result_content.output is None
    assert result_content.raw_representation is mock_item


def test_parse_chunk_from_openai_with_mcp_output_item_done_call_id_fallback() -> None:
    """Test that response.output_item.done for mcp_call falls back to call_id when id is missing."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_event = MagicMock()
    mock_event.type = "response.output_item.done"

    mock_item = MagicMock(spec=[])
    mock_item.type = "mcp_call"
    mock_item.call_id = "mcp_fallback_123"
    mock_item.output = "fallback result"
    mock_event.item = mock_item

    function_call_ids: dict[int, tuple[str, str]] = {}

    update = client._parse_chunk_from_openai(mock_event, options={}, function_call_ids=function_call_ids)

    assert len(update.contents) == 1
    result_content = update.contents[0]

    assert result_content.type == "mcp_server_tool_result"
    assert result_content.call_id == "mcp_fallback_123"
    assert result_content.output is not None
    assert result_content.output[0].text == "fallback result"
    assert result_content.raw_representation is mock_item


def test_parse_chunk_from_openai_with_mcp_output_item_done_no_id_fallback() -> None:
    """Test that response.output_item.done for mcp_call falls back to empty string when neither id nor call_id exist."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_event = MagicMock()
    mock_event.type = "response.output_item.done"

    mock_item = MagicMock(spec=[])
    mock_item.type = "mcp_call"
    mock_item.output = "some result"
    mock_event.item = mock_item

    function_call_ids: dict[int, tuple[str, str]] = {}

    update = client._parse_chunk_from_openai(mock_event, options={}, function_call_ids=function_call_ids)

    assert len(update.contents) == 1
    result_content = update.contents[0]

    assert result_content.type == "mcp_server_tool_result"
    assert result_content.call_id == ""
    assert result_content.output is not None
    assert result_content.output[0].text == "some result"
    assert result_content.raw_representation is mock_item


def test_prepare_message_for_openai_with_function_approval_response() -> None:
    """Test _prepare_message_for_openai with function approval response content in messages."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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

    message = Message(role="user", contents=[approval_response])

    result = client._prepare_message_for_openai(message)

    # FunctionApprovalResponseContent is added directly, not nested in args with role
    assert len(result) == 1
    prepared_message = result[0]
    assert prepared_message["type"] == "mcp_approval_response"
    assert prepared_message["approval_request_id"] == "approval_003"
    assert prepared_message["approve"] is True


def test_prepare_message_for_openai_includes_reasoning_with_function_call() -> None:
    """Test _prepare_message_for_openai includes reasoning items alongside function_calls.

    Reasoning models require reasoning items to be present in the input when
    function_call items are included. Stripping reasoning causes a 400 error:
    "function_call was provided without its required reasoning item".
    """
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    reasoning = Content.from_text_reasoning(
        id="rs_abc123",
        text="Let me analyze the request",
        additional_properties={"status": "completed"},
    )
    function_call = Content.from_function_call(
        call_id="call_123",
        name="search_hotels",
        arguments='{"city": "Paris"}',
    )

    message = Message(role="assistant", contents=[reasoning, function_call])

    result = client._prepare_message_for_openai(message)

    # Both reasoning and function_call should be present as top-level items
    types = [item["type"] for item in result]
    assert "reasoning" in types, "Reasoning items must be included for reasoning models"
    assert "function_call" in types

    reasoning_item = next(item for item in result if item["type"] == "reasoning")
    assert reasoning_item["summary"][0]["text"] == "Let me analyze the request"
    assert reasoning_item["id"] == "rs_abc123", "Reasoning id must be preserved for the API"


def test_prepare_messages_for_openai_full_conversation_with_reasoning() -> None:
    """Test _prepare_messages_for_openai correctly serializes a full conversation
    that includes reasoning + function_call + function_result + final text.

    This simulates the conversation history passed between agents in a workflow.
    The API requires reasoning items alongside function_calls.
    """
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    messages = [
        Message(role="user", contents=[Content.from_text(text="search for hotels")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text_reasoning(
                    id="rs_test123",
                    text="I need to search for hotels",
                    additional_properties={"status": "completed"},
                ),
                Content.from_function_call(
                    call_id="call_1",
                    name="search_hotels",
                    arguments='{"city": "Paris"}',
                    additional_properties={"fc_id": "fc_test456"},
                ),
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_1",
                    result="Found 3 hotels in Paris",
                ),
            ],
        ),
        Message(
            role="assistant",
            contents=[Content.from_text(text="I found hotels for you")],
        ),
    ]

    result = client._prepare_messages_for_openai(messages)

    types = [item.get("type") for item in result]
    assert "message" in types, "User/assistant messages should be present"
    assert "reasoning" in types, "Reasoning items must be present"
    assert "function_call" in types, "Function call items must be present"
    assert "function_call_output" in types, "Function call output must be present"

    # Verify reasoning has id
    reasoning_items = [item for item in result if item.get("type") == "reasoning"]
    assert reasoning_items[0]["id"] == "rs_test123"

    # Verify function_call has id
    fc_items = [item for item in result if item.get("type") == "function_call"]
    assert fc_items[0]["id"] == "fc_test456"

    # Verify correct ordering: reasoning before function_call
    reasoning_idx = types.index("reasoning")
    fc_idx = types.index("function_call")
    assert reasoning_idx < fc_idx, "Reasoning must come before function_call"


def test_prepare_message_for_openai_filters_error_content() -> None:
    """Test that error content in messages is handled properly."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    error_content = Content.from_error(
        message="Test error",
        error_code="TEST_ERR",
    )

    message = Message(role="assistant", contents=[error_content])

    result = client._prepare_message_for_openai(message)

    # Message should be empty since ErrorContent is filtered out
    assert len(result) == 0


def test_chat_message_with_usage_content() -> None:
    """Test that usage content in messages is handled properly."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    usage_content = Content.from_usage(
        usage_details={
            "input_token_count": 200,
            "output_token_count": 100,
            "total_token_count": 300,
        }
    )

    message = Message(role="assistant", contents=[usage_content])

    result = client._prepare_message_for_openai(message)

    # Message should be empty since UsageContent is filtered out
    assert len(result) == 0


def test_hosted_file_content_preparation() -> None:
    """Test _prepare_content_for_openai with hosted file content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    hosted_file = Content.from_hosted_file(
        file_id="file_abc123",
        media_type="application/pdf",
        name="document.pdf",
    )

    result = client._prepare_content_for_openai("user", hosted_file)
    assert result["type"] == "input_file"
    assert result["file_id"] == "file_abc123"


def test_function_approval_response_with_mcp_tool_call() -> None:
    """Test function approval response content with MCP server tool call content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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

    result = client._prepare_content_for_openai("assistant", approval_response)

    assert result["type"] == "mcp_approval_response"
    assert result["approval_request_id"] == "approval_mcp_001"
    assert result["approve"] is False


def test_response_format_with_conflicting_definitions() -> None:
    """Test that conflicting response_format definitions raise an error."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Mock response_format and text_config that conflict
    response_format = {
        "type": "json_schema",
        "format": {"type": "json_schema", "name": "Test", "schema": {}},
    }
    text_config = {"format": {"type": "json_object"}}

    with pytest.raises(
        ChatClientInvalidRequestException,
        match="Conflicting response_format definitions",
    ):
        client._prepare_response_and_text_format(response_format=response_format, text_config=text_config)


def test_response_format_json_object_type() -> None:
    """Test response_format with json_object type."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "json_object"}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "json_object"


def test_response_format_text_type() -> None:
    """Test response_format with text type."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "text"}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "text"


def test_response_format_with_format_key() -> None:
    """Test response_format that already has a format key."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {
        "format": {
            "type": "json_schema",
            "name": "MySchema",
            "schema": {"type": "object"},
        }
    }

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "json_schema"
    assert text_config["format"]["name"] == "MySchema"


def test_response_format_json_schema_no_name_uses_title() -> None:
    """Test json_schema response_format without name uses title from schema."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {
        "type": "json_schema",
        "json_schema": {"schema": {"title": "MyTitle", "type": "object", "properties": {}}},
    }

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["name"] == "MyTitle"


def test_response_format_json_schema_with_strict() -> None:
    """Test json_schema response_format with strict mode."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "StrictSchema",
            "schema": {"type": "object"},
            "strict": True,
        },
    }

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["strict"] is True


def test_response_format_json_schema_with_description() -> None:
    """Test json_schema response_format with description."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "json_schema", "json_schema": {"name": "NoSchema"}}

    with pytest.raises(
        ChatClientInvalidRequestException,
        match="json_schema response_format requires a schema",
    ):
        client._prepare_response_and_text_format(response_format=response_format, text_config=None)


def test_response_format_raw_json_schema_with_properties() -> None:
    """Test raw JSON schema with properties is wrapped in json_schema envelope."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "object", "properties": {"x": {"type": "string"}}, "title": "MyOutput"}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    fmt = text_config["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "MyOutput"
    assert fmt["strict"] is True
    assert fmt["schema"]["additionalProperties"] is False
    assert "title" not in fmt["schema"]


def test_response_format_raw_json_schema_no_title() -> None:
    """Test raw JSON schema without title defaults name to 'response'."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "object", "properties": {"x": {"type": "string"}}}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["name"] == "response"


def test_response_format_raw_json_schema_preserves_additional_properties() -> None:
    """Test raw JSON schema preserves existing additionalProperties."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "object", "properties": {"x": {"type": "string"}}, "additionalProperties": True}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["schema"]["additionalProperties"] is True


def test_response_format_raw_json_schema_non_object_type() -> None:
    """Test raw JSON schema with non-object type does not inject additionalProperties."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "array", "items": {"type": "string"}}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert "additionalProperties" not in text_config["format"]["schema"]


def test_response_format_raw_json_schema_with_anyof() -> None:
    """Test raw JSON schema with anyOf keyword is detected."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"anyOf": [{"type": "string"}, {"type": "number"}]}

    _, text_config = client._prepare_response_and_text_format(response_format=response_format, text_config=None)

    assert text_config is not None
    assert text_config["format"]["type"] == "json_schema"


def test_response_format_unsupported_type() -> None:
    """Test unsupported response_format type raises error."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = {"type": "unsupported_format"}

    with pytest.raises(ChatClientInvalidRequestException, match="Unsupported response_format"):
        client._prepare_response_and_text_format(response_format=response_format, text_config=None)


def test_response_format_invalid_type() -> None:
    """Test invalid response_format type raises error."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    response_format = "invalid"  # Not a Pydantic model or mapping

    with pytest.raises(
        ChatClientInvalidRequestException,
        match="response_format must be a Pydantic model or mapping",
    ):
        client._prepare_response_and_text_format(response_format=response_format, text_config=None)  # type: ignore


def test_parse_response_with_store_false() -> None:
    """Test _get_conversation_id returns None when store is False."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_123"
    mock_response.conversation = MagicMock()
    mock_response.conversation.id = "conv_456"

    conversation_id = client._get_conversation_id(mock_response, store=False)

    assert conversation_id is None


def test_parse_response_uses_response_id_when_no_conversation() -> None:
    """Test _get_conversation_id returns response ID when no conversation exists."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.id = "resp_789"
    mock_response.conversation = None

    conversation_id = client._get_conversation_id(mock_response, store=True)

    assert conversation_id == "resp_789"


def test_streaming_chunk_with_usage_only() -> None:
    """Test streaming chunk that only contains usage info."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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


def test_prepare_tools_for_openai_with_mcp() -> None:
    """Test that MCP tool dict is converted to the correct response tool dict."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Use static method to create MCP tool
    tool = OpenAIChatClient.get_mcp_tool(
        name="My_MCP",
        url="https://mcp.example",
        allowed_tools=["tool_a", "tool_b"],
        headers={"X-Test": "yes"},
        approval_mode={"always_require_approval": ["tool_a", "tool_b"]},
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
    assert mcp["headers"]["X-Test"] == "yes"
    assert set(mcp["allowed_tools"]) == {"tool_a", "tool_b"}
    # approval mapping created from approval_mode dict
    assert "require_approval" in mcp


def test_prepare_tools_for_openai_single_function_tool() -> None:
    """Test that a single FunctionTool (not wrapped in a list) is handled correctly."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    @tool
    def hello(name: str) -> str:
        """Say hello."""
        return name

    resp_tools = client._prepare_tools_for_openai(hello)
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 1
    tool_def = resp_tools[0]
    assert tool_def["type"] == "function"
    assert tool_def["name"] == "hello"
    assert tool_def["strict"] is False
    assert "parameters" in tool_def
    params = tool_def["parameters"]
    assert isinstance(params, dict)
    assert params.get("type") == "object"
    assert "properties" in params
    assert "name" in params["properties"]
    assert params["properties"]["name"]["type"] == "string"


def test_prepare_tools_for_openai_single_dict_tool() -> None:
    """Test that a single dict tool (not wrapped in a list) is handled correctly."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    web_tool = OpenAIChatClient.get_web_search_tool(search_context_size="low")
    resp_tools = client._prepare_tools_for_openai(web_tool)
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 1
    assert "type" in resp_tools[0]
    assert resp_tools[0]["search_context_size"] == "low"


def test_prepare_tools_for_openai_none() -> None:
    """Test that passing None returns an empty list."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    resp_tools = client._prepare_tools_for_openai(None)
    assert isinstance(resp_tools, list)
    assert len(resp_tools) == 0


def test_parse_response_from_openai_with_mcp_approval_request() -> None:
    """Test that a non-streaming mcp_approval_request is parsed into FunctionApprovalRequestContent."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient()

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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


def test_prepare_tools_for_openai_with_image_generation_options() -> None:
    """Test image generation tool conversion with options."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Use static method to create image generation tool
    tool = OpenAIChatClient.get_image_generation_tool(
        output_format="png",
        size="512x512",
        quality="high",
    )

    resp_tools = client._prepare_tools_for_openai([tool])
    assert len(resp_tools) == 1
    image_tool = resp_tools[0]
    assert image_tool["type"] == "image_generation"
    assert image_tool["output_format"] == "png"
    assert image_tool["size"] == "512x512"
    assert image_tool["quality"] == "high"


def test_prepare_tools_for_openai_with_custom_image_generation_model() -> None:
    """Test image generation tool conversion with a custom model string."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    tool = OpenAIChatClient.get_image_generation_tool(model="custom-image-model")

    resp_tools = client._prepare_tools_for_openai([tool])
    assert len(resp_tools) == 1
    image_tool = resp_tools[0]
    assert image_tool["type"] == "image_generation"
    assert image_tool["model"] == "custom-image-model"


def test_parse_chunk_from_openai_with_mcp_approval_request() -> None:
    """Test that a streaming mcp_approval_request event is parsed into FunctionApprovalRequestContent."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
        response = await client.get_response(messages=[Message(role="user", contents=["Trigger approval"])])
        assert response.messages[0].contents[0].type == "function_approval_request"
        req = response.messages[0].contents[0]
        assert req.id == "approval-1"

        # Build a user approval and send it (include required function_call)
        approval = Content.from_function_approval_response(approved=True, id=req.id, function_call=req.function_call)
        approval_message = Message(role="user", contents=[approval])
        _ = await client.get_response(messages=[approval_message])

        # After approval is processed, the model is called again to get the final response
        assert mock_create.call_count == 2


def test_usage_details_basic() -> None:
    """Test _parse_usage_from_openai without cached or reasoning tokens."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions(store=True)
    function_call_ids: dict[int, tuple[str, str]] = {}

    # Test with a basic mock event to ensure the method returns proper structure
    mock_event = MagicMock()

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)  # type: ignore

    # Should get a valid ChatResponseUpdate structure
    assert isinstance(response, ChatResponseUpdate)
    assert response.role == "assistant"
    assert response.model == "test-model"
    assert isinstance(response.contents, list)
    assert response.raw_representation is mock_event


def test_streaming_response_created_type() -> None:
    """Test streaming response with created type"""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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


def test_streaming_annotation_added_with_url_citation() -> None:
    """Test streaming annotation added event with url_citation type produces citation annotation."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 0
    mock_event.annotation = {
        "type": "url_citation",
        "url": "https://example.sharepoint.com/sites/my-site/doc.pdf",
        "title": "doc.pdf",
        "start_index": 100,
        "end_index": 112,
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 1
    content = response.contents[0]
    assert content.type == "text"
    assert content.annotations is not None
    assert len(content.annotations) == 1
    annotation = content.annotations[0]
    assert annotation["type"] == "citation"
    assert annotation["title"] == "doc.pdf"
    assert annotation["url"] == "https://example.sharepoint.com/sites/my-site/doc.pdf"
    assert annotation["additional_properties"]["annotation_index"] == 0
    assert annotation["raw_representation"] == mock_event.annotation
    assert annotation["annotated_regions"] is not None
    assert len(annotation["annotated_regions"]) == 1
    region = annotation["annotated_regions"][0]
    assert region["type"] == "text_span"
    assert region["start_index"] == 100
    assert region["end_index"] == 112


def test_streaming_annotation_added_with_url_citation_no_url() -> None:
    """Test streaming annotation added event with url_citation but missing url is ignored."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 0
    mock_event.annotation = {
        "type": "url_citation",
        "title": "doc.pdf",
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 0


def test_streaming_annotation_added_with_url_citation_no_indices() -> None:
    """Test streaming annotation with url_citation that has url but no start_index/end_index."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 0
    mock_event.annotation = {
        "type": "url_citation",
        "url": "https://example.com",
        "title": "Example",
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 1
    annotation = response.contents[0].annotations[0]
    assert annotation["type"] == "citation"
    assert annotation["title"] == "Example"
    assert annotation["url"] == "https://example.com"
    assert annotation["additional_properties"]["annotation_index"] == 0
    assert "annotated_regions" not in annotation


def test_streaming_annotation_added_with_unknown_type() -> None:
    """Test streaming annotation added event with unknown type is ignored."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.output_text.annotation.added"
    mock_event.annotation_index = 0
    mock_event.annotation = {
        "type": "some_future_annotation_type",
        "data": "test",
    }

    response = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert len(response.contents) == 0


async def test_service_response_exception_includes_original_error_details() -> None:
    """Test that ChatClientException messages include original error details in the new format."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [Message(role="user", contents=["test message"])]

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
        pytest.raises(ChatClientException) as exc_info,
    ):
        await client.get_response(messages=messages, options={"response_format": OutputStruct})

    exception_message = str(exc_info.value)
    assert "service failed to complete the prompt:" in exception_message
    assert original_error_message in exception_message


async def test_get_response_streaming_with_response_format() -> None:
    """Test get_response streaming with response_format."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [Message(role="user", contents=["Test streaming with format"])]

    # It will fail due to invalid API key, but exercises the code path
    with pytest.raises(ChatClientException):

        async def run_streaming():
            async for _ in client.get_response(
                stream=True,
                messages=messages,
                options={"response_format": OutputStruct},
            ):
                pass

        await run_streaming()


async def test_inner_get_response_streaming_with_response_format_tracks_reasoning_delta_ids() -> None:
    """The responses.stream path should suppress reasoning done events after deltas."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [Message(role="user", contents=["Test streaming with format"])]
    item_id = "reasoning_stream"
    events = [
        ResponseReasoningTextDeltaEvent(
            type="response.reasoning_text.delta",
            content_index=0,
            item_id=item_id,
            output_index=0,
            sequence_number=1,
            delta="Hello ",
        ),
        ResponseReasoningTextDoneEvent(
            type="response.reasoning_text.done",
            content_index=0,
            item_id=item_id,
            output_index=0,
            sequence_number=2,
            text="Hello ",
        ),
    ]

    with (
        patch.object(
            client,
            "_prepare_request",
            new=AsyncMock(return_value=(client.client, {"text_format": OutputStruct}, {})),
        ),
        patch.object(client.client.responses, "stream", return_value=_FakeAsyncEventStreamContext(events)),
        patch.object(client, "_get_metadata_from_response", return_value={}),
    ):
        stream = client._inner_get_response(messages=messages, options={}, stream=True)
        updates = [update async for update in stream]

    reasoning_chunks = [
        content.text for update in updates for content in update.contents if content.type == "text_reasoning"
    ]
    assert reasoning_chunks == ["Hello "]


def test_prepare_content_for_openai_image_content() -> None:
    """Test _prepare_content_for_openai with image content variations."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test image content with detail parameter and file_id
    image_content_with_detail = Content.from_uri(
        uri="https://example.com/image.jpg",
        media_type="image/jpeg",
        additional_properties={"detail": "high", "file_id": "file_123"},
    )
    result = client._prepare_content_for_openai("user", image_content_with_detail)
    assert result["type"] == "input_image"
    assert result["image_url"] == "https://example.com/image.jpg"
    assert result["detail"] == "high"
    assert result["file_id"] == "file_123"

    # Test image content without additional properties (defaults)
    image_content_basic = Content.from_uri(uri="https://example.com/basic.png", media_type="image/png")
    result = client._prepare_content_for_openai("user", image_content_basic)
    assert result["type"] == "input_image"
    assert result["detail"] == "auto"
    assert "file_id" not in result


def test_prepare_content_for_openai_audio_content() -> None:
    """Test _prepare_content_for_openai with audio content variations."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test WAV audio content
    wav_content = Content.from_uri(uri="data:audio/wav;base64,abc123", media_type="audio/wav")
    result = client._prepare_content_for_openai("user", wav_content)
    assert result["type"] == "input_audio"
    assert result["input_audio"]["data"] == "data:audio/wav;base64,abc123"
    assert result["input_audio"]["format"] == "wav"

    # Test MP3 audio content
    mp3_content = Content.from_uri(uri="data:audio/mp3;base64,def456", media_type="audio/mp3")
    result = client._prepare_content_for_openai("user", mp3_content)
    assert result["type"] == "input_audio"
    assert result["input_audio"]["format"] == "mp3"


def test_prepare_content_for_openai_unsupported_content() -> None:
    """Test _prepare_content_for_openai with unsupported content types."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test unsupported audio format
    unsupported_audio = Content.from_uri(uri="data:audio/ogg;base64,ghi789", media_type="audio/ogg")
    result = client._prepare_content_for_openai("user", unsupported_audio)
    assert result == {}

    # Test non-media content
    text_uri_content = Content.from_uri(uri="https://example.com/document.txt", media_type="text/plain")
    result = client._prepare_content_for_openai("user", text_uri_content)
    assert result == {}


def test_prepare_content_for_openai_function_result_with_rich_items() -> None:
    """Test _prepare_content_for_openai with function_result containing rich items."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    image_content = Content.from_data(data=b"image_bytes", media_type="image/png")
    content = Content.from_function_result(
        call_id="call_rich",
        result=[Content.from_text("Result text"), image_content],
    )

    result = client._prepare_content_for_openai("user", content)

    assert result["type"] == "function_call_output"
    assert result["call_id"] == "call_rich"
    # Output should be a list with text and image parts
    output = result["output"]
    assert isinstance(output, list)
    assert len(output) == 2
    assert output[0]["type"] == "input_text"
    assert output[0]["text"] == "Result text"
    assert output[1]["type"] == "input_image"


def test_prepare_content_for_openai_function_result_without_items() -> None:
    """Test _prepare_content_for_openai with plain string function_result."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    content = Content.from_function_result(
        call_id="call_plain",
        result="Simple result",
    )

    result = client._prepare_content_for_openai("user", content)

    assert result["type"] == "function_call_output"
    assert result["call_id"] == "call_plain"
    assert result["output"] == "Simple result"


def test_parse_chunk_from_openai_code_interpreter() -> None:
    """Test _parse_chunk_from_openai with code_interpreter_call."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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

    result = client._parse_chunk_from_openai(mock_event_image, chat_options, function_call_ids)
    assert len(result.contents) == 1
    assert result.contents[0].type == "code_interpreter_tool_result"
    assert result.contents[0].outputs
    assert any(out.type == "uri" and out.uri == "https://example.com/plot.png" for out in result.contents[0].outputs)


def test_parse_chunk_from_openai_code_interpreter_delta() -> None:
    """Test _parse_chunk_from_openai with code_interpreter_call_code delta events."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    # Test delta event
    mock_delta_event = MagicMock()
    mock_delta_event.type = "response.code_interpreter_call_code.delta"
    mock_delta_event.item_id = "ci_123"
    mock_delta_event.delta = "import pandas as pd\n"
    mock_delta_event.output_index = 0
    mock_delta_event.sequence_number = 1
    mock_delta_event.call_id = None  # Ensure fallback to item_id
    mock_delta_event.id = None

    result = client._parse_chunk_from_openai(mock_delta_event, chat_options, function_call_ids)
    assert len(result.contents) == 1
    assert result.contents[0].type == "code_interpreter_tool_call"
    assert result.contents[0].call_id == "ci_123"
    assert result.contents[0].inputs
    assert result.contents[0].inputs[0].type == "text"
    assert result.contents[0].inputs[0].text == "import pandas as pd\n"
    # Verify additional_properties for stream ordering
    assert result.contents[0].additional_properties["output_index"] == 0
    assert result.contents[0].additional_properties["sequence_number"] == 1
    assert result.contents[0].additional_properties["item_id"] == "ci_123"


def test_parse_chunk_from_openai_code_interpreter_done() -> None:
    """Test _parse_chunk_from_openai with code_interpreter_call_code done event."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}

    # Test done event
    mock_done_event = MagicMock()
    mock_done_event.type = "response.code_interpreter_call_code.done"
    mock_done_event.item_id = "ci_456"
    mock_done_event.code = "import pandas as pd\ndf = pd.DataFrame({'a': [1, 2, 3]})\nprint(df)"
    mock_done_event.output_index = 0
    mock_done_event.sequence_number = 5
    mock_done_event.call_id = None  # Ensure fallback to item_id
    mock_done_event.id = None

    result = client._parse_chunk_from_openai(mock_done_event, chat_options, function_call_ids)
    assert len(result.contents) == 1
    assert result.contents[0].type == "code_interpreter_tool_call"
    assert result.contents[0].call_id == "ci_456"
    assert result.contents[0].inputs
    assert result.contents[0].inputs[0].type == "text"
    assert "import pandas as pd" in result.contents[0].inputs[0].text
    # Verify additional_properties for stream ordering
    assert result.contents[0].additional_properties["output_index"] == 0
    assert result.contents[0].additional_properties["sequence_number"] == 5
    assert result.contents[0].additional_properties["item_id"] == "ci_456"


def test_parse_chunk_from_openai_reasoning() -> None:
    """Test _parse_chunk_from_openai with reasoning content."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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

    result = client._parse_chunk_from_openai(mock_event_reasoning, chat_options, function_call_ids)
    assert len(result.contents) == 1
    assert result.contents[0].type == "text_reasoning"
    assert result.contents[0].text == "Analyzing the problem step by step..."
    if result.contents[0].additional_properties:
        assert result.contents[0].additional_properties["summary"] == "Problem analysis summary"


def test_prepare_content_for_openai_text_reasoning_comprehensive() -> None:
    """Test _prepare_content_for_openai with TextReasoningContent all additional properties."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Test TextReasoningContent with all additional properties
    comprehensive_reasoning = Content.from_text_reasoning(
        id="rs_comprehensive",
        text="Comprehensive reasoning summary",
        additional_properties={
            "status": "in_progress",
            "reasoning_text": "Step-by-step analysis",
            "encrypted_content": "secure_data_456",
        },
    )
    result = client._prepare_content_for_openai("assistant", comprehensive_reasoning)
    assert result["type"] == "reasoning"
    assert result["id"] == "rs_comprehensive"
    assert result["summary"][0]["text"] == "Comprehensive reasoning summary"
    assert result["status"] == "in_progress"
    assert result["content"][0]["type"] == "reasoning_text"
    assert result["content"][0]["text"] == "Step-by-step analysis"
    assert result["encrypted_content"] == "secure_data_456"


def test_streaming_reasoning_text_delta_event() -> None:
    """Test reasoning text delta event creates TextReasoningContent."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
        assert response.contents[0].id == "reasoning_123"
        assert response.contents[0].text == "reasoning delta"
        assert response.contents[0].raw_representation == event
        mock_metadata.assert_called_once_with(event)


def test_streaming_reasoning_text_done_event_skipped_after_deltas() -> None:
    """Test reasoning text done event does not emit content when deltas were already received."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}
    seen_reasoning_delta_item_ids: set[str] = {"reasoning_456"}

    event = ResponseReasoningTextDoneEvent(
        type="response.reasoning_text.done",
        content_index=0,
        item_id="reasoning_456",
        output_index=0,
        sequence_number=2,
        text="complete reasoning",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"test": "data"}) as mock_metadata:
        response = client._parse_chunk_from_openai(
            event, chat_options, function_call_ids, seen_reasoning_delta_item_ids
        )  # type: ignore

        assert len(response.contents) == 0
        mock_metadata.assert_called_once_with(event)
        assert response.additional_properties == {"test": "data"}


def test_streaming_reasoning_text_done_event_fallback_without_deltas() -> None:
    """Test reasoning text done event emits content when no deltas were received for this item_id."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}
    seen_reasoning_delta_item_ids: set[str] = set()

    event = ResponseReasoningTextDoneEvent(
        type="response.reasoning_text.done",
        content_index=0,
        item_id="reasoning_456",
        output_index=0,
        sequence_number=2,
        text="complete reasoning",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"test": "data"}) as mock_metadata:
        response = client._parse_chunk_from_openai(
            event, chat_options, function_call_ids, seen_reasoning_delta_item_ids
        )  # type: ignore

        assert len(response.contents) == 1
        assert response.contents[0].type == "text_reasoning"
        assert response.contents[0].id == "reasoning_456"
        assert response.contents[0].text == "complete reasoning"
        mock_metadata.assert_called_once_with(event)
        assert response.additional_properties == {"test": "data"}


def test_streaming_reasoning_summary_text_delta_event() -> None:
    """Test reasoning summary text delta event creates TextReasoningContent."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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


def test_streaming_reasoning_summary_text_done_event_skipped_after_deltas() -> None:
    """Test reasoning summary text done event does not emit content when deltas were already received."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}
    seen_reasoning_delta_item_ids: set[str] = {"summary_012"}

    event = ResponseReasoningSummaryTextDoneEvent(
        type="response.reasoning_summary_text.done",
        item_id="summary_012",
        output_index=0,
        sequence_number=4,
        summary_index=0,
        text="complete summary",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"custom": "meta"}) as mock_metadata:
        response = client._parse_chunk_from_openai(
            event, chat_options, function_call_ids, seen_reasoning_delta_item_ids
        )  # type: ignore

        assert len(response.contents) == 0
        mock_metadata.assert_called_once_with(event)
        assert response.additional_properties == {"custom": "meta"}


def test_streaming_reasoning_summary_text_done_event_fallback_without_deltas() -> None:
    """Test reasoning summary text done event emits content when no deltas were received for this item_id."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}
    seen_reasoning_delta_item_ids: set[str] = set()

    event = ResponseReasoningSummaryTextDoneEvent(
        type="response.reasoning_summary_text.done",
        item_id="summary_012",
        output_index=0,
        sequence_number=4,
        summary_index=0,
        text="complete summary",
    )

    with patch.object(client, "_get_metadata_from_response", return_value={"custom": "meta"}) as mock_metadata:
        response = client._parse_chunk_from_openai(
            event, chat_options, function_call_ids, seen_reasoning_delta_item_ids
        )  # type: ignore

        assert len(response.contents) == 1
        assert response.contents[0].type == "text_reasoning"
        assert response.contents[0].id == "summary_012"
        assert response.contents[0].text == "complete summary"
        mock_metadata.assert_called_once_with(event)
        assert response.additional_properties == {"custom": "meta"}


def test_streaming_reasoning_deltas_then_done_no_duplication() -> None:
    """Sending delta events followed by a done event produces content only from deltas."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options = ChatOptions()
    function_call_ids: dict[int, tuple[str, str]] = {}
    seen_reasoning_delta_item_ids: set[str] = set()
    item_id = "reasoning_seq"

    delta1 = ResponseReasoningTextDeltaEvent(
        type="response.reasoning_text.delta",
        content_index=0,
        item_id=item_id,
        output_index=0,
        sequence_number=1,
        delta="Hello ",
    )
    delta2 = ResponseReasoningTextDeltaEvent(
        type="response.reasoning_text.delta",
        content_index=0,
        item_id=item_id,
        output_index=0,
        sequence_number=2,
        delta="world",
    )
    done = ResponseReasoningTextDoneEvent(
        type="response.reasoning_text.done",
        content_index=0,
        item_id=item_id,
        output_index=0,
        sequence_number=3,
        text="Hello world",
    )

    all_contents = []
    with patch.object(client, "_get_metadata_from_response", return_value={}):
        for event in [delta1, delta2, done]:
            response = client._parse_chunk_from_openai(
                event,
                chat_options,
                function_call_ids,
                seen_reasoning_delta_item_ids,  # type: ignore
            )
            all_contents.extend(response.contents)

    assert len(all_contents) == 2
    assert all_contents[0].text == "Hello "
    assert all_contents[1].text == "world"
    assert "".join(c.text for c in all_contents) == "Hello world"


async def test_inner_get_response_streaming_create_tracks_reasoning_delta_ids() -> None:
    """The responses.create(stream=True) path should suppress reasoning done events after deltas."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [Message(role="user", contents=["Test streaming"])]
    item_id = "reasoning_create"
    events = [
        ResponseReasoningTextDeltaEvent(
            type="response.reasoning_text.delta",
            content_index=0,
            item_id=item_id,
            output_index=0,
            sequence_number=1,
            delta="Hello ",
        ),
        ResponseReasoningTextDoneEvent(
            type="response.reasoning_text.done",
            content_index=0,
            item_id=item_id,
            output_index=0,
            sequence_number=2,
            text="Hello ",
        ),
    ]

    with (
        patch.object(client, "_prepare_request", new=AsyncMock(return_value=(client.client, {}, {}))),
        patch.object(client.client.responses, "create", new=AsyncMock(return_value=_FakeAsyncEventStream(events))),
        patch.object(client, "_get_metadata_from_response", return_value={}),
    ):
        stream = client._inner_get_response(messages=messages, options={}, stream=True)
        updates = [update async for update in stream]

    reasoning_chunks = [
        content.text for update in updates for content in update.contents if content.type == "text_reasoning"
    ]
    assert reasoning_chunks == ["Hello "]


def test_streaming_reasoning_events_preserve_metadata() -> None:
    """Test that reasoning events preserve metadata like regular text events."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")

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
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [Message(role="user", contents=["Test message"])]

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


async def test_prepare_options_store_false_omits_reasoning_items_for_stateless_replay() -> None:
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [
        Message(role="user", contents=[Content.from_text(text="search for hotels")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text_reasoning(
                    id="rs_test123",
                    text="I need to search for hotels",
                    additional_properties={"status": "completed"},
                ),
                Content.from_function_call(
                    call_id="call_1",
                    name="search_hotels",
                    arguments='{"city": "Paris"}',
                    additional_properties={"fc_id": "fc_test456"},
                ),
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_1",
                    result="Found 3 hotels in Paris",
                ),
            ],
        ),
    ]

    options = await client._prepare_options(messages, ChatOptions(store=False))  # type: ignore[arg-type]

    assert not any(item.get("type") == "reasoning" for item in options["input"])
    assert any(item.get("type") == "function_call" for item in options["input"])
    assert any(item.get("type") == "function_call_output" for item in options["input"])


async def test_prepare_options_with_conversation_id_keeps_reasoning_items() -> None:
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [
        Message(role="user", contents=[Content.from_text(text="search for hotels")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text_reasoning(
                    id="rs_test123",
                    text="I need to search for hotels",
                    additional_properties={"status": "completed"},
                ),
                Content.from_function_call(
                    call_id="call_1",
                    name="search_hotels",
                    arguments='{"city": "Paris"}',
                    additional_properties={"fc_id": "fc_test456"},
                ),
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_1",
                    result="Found 3 hotels in Paris",
                ),
            ],
        ),
    ]

    options = await client._prepare_options(
        messages,
        ChatOptions(store=False, conversation_id="resp_prev123"),  # type: ignore[arg-type]
    )

    reasoning_items = [item for item in options["input"] if item.get("type") == "reasoning"]
    assert len(reasoning_items) == 1
    assert reasoning_items[0]["id"] == "rs_test123"
    assert options["previous_response_id"] == "resp_prev123"


async def test_prepare_options_with_conversation_id_omits_reasoning_items_for_attributed_replay() -> None:
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    messages = [
        Message(role="user", contents=[Content.from_text(text="search for hotels")]),
        Message(
            role="assistant",
            contents=[
                Content.from_text_reasoning(
                    id="rs_history123",
                    text="I need to search history for hotels",
                    additional_properties={"status": "completed"},
                ),
                Content.from_function_call(
                    call_id="call_history",
                    name="search_hotels",
                    arguments='{"city": "Paris"}',
                    additional_properties={"fc_id": "fc_history456"},
                ),
            ],
            additional_properties={"_attribution": {"source_id": "history", "source_type": "InMemoryHistoryProvider"}},
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_history",
                    result="Found 3 hotels in Paris",
                ),
            ],
        ),
        Message(
            role="assistant",
            contents=[
                Content.from_text_reasoning(
                    id="rs_live123",
                    text="I should refine the search for a live follow-up",
                    additional_properties={"status": "completed"},
                ),
                Content.from_function_call(
                    call_id="call_live",
                    name="search_hotels",
                    arguments='{"city": "London"}',
                    additional_properties={"fc_id": "fc_live456"},
                ),
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_live",
                    result="Found 4 hotels in London",
                ),
            ],
        ),
    ]

    options = await client._prepare_options(
        messages,
        ChatOptions(store=False, conversation_id="resp_prev123"),  # type: ignore[arg-type]
    )

    reasoning_items = [item for item in options["input"] if item.get("type") == "reasoning"]
    assert [item["id"] for item in reasoning_items] == ["rs_live123"]
    assert any(
        item.get("type") == "function_call" and item.get("call_id") == "call_history" for item in options["input"]
    )
    assert any(item.get("type") == "function_call" and item.get("call_id") == "call_live" for item in options["input"])
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == "call_history"
        for item in options["input"]
    )
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == "call_live" for item in options["input"]
    )
    assert options["previous_response_id"] == "resp_prev123"


def _create_mock_responses_text_response(*, response_id: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.id = response_id
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.finish_reason = None

    mock_message_content = MagicMock()
    mock_message_content.type = "output_text"
    mock_message_content.text = "Hello! How can I help?"
    mock_message_content.annotations = []

    mock_message_item = MagicMock()
    mock_message_item.type = "message"
    mock_message_item.content = [mock_message_content]

    mock_response.output = [mock_message_item]
    return mock_response


async def test_instructions_sent_first_turn_then_skipped_for_continuation() -> None:
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    mock_response = _create_mock_responses_text_response(response_id="resp_123")

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        await client.get_response(
            messages=[Message(role="user", contents=["Hello"])],
            options={"instructions": "Reply in uppercase."},
        )

        first_input_messages = mock_create.call_args.kwargs["input"]
        assert len(first_input_messages) == 2
        assert first_input_messages[0]["role"] == "system"
        assert any("Reply in uppercase" in str(c) for c in first_input_messages[0]["content"])
        assert first_input_messages[1]["role"] == "user"

        await client.get_response(
            messages=[Message(role="user", contents=["Tell me a joke"])],
            options={
                "instructions": "Reply in uppercase.",
                "conversation_id": "resp_123",
            },
        )

        second_input_messages = mock_create.call_args.kwargs["input"]
        assert len(second_input_messages) == 1
        assert second_input_messages[0]["role"] == "user"
        assert not any(message["role"] == "system" for message in second_input_messages)


@pytest.mark.parametrize("conversation_id", ["resp_456", "conv_abc123"])
async def test_instructions_not_repeated_for_continuation_ids(
    conversation_id: str,
) -> None:
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    mock_response = _create_mock_responses_text_response(response_id="resp_456")

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        await client.get_response(
            messages=[Message(role="user", contents=["Continue conversation"])],
            options={"instructions": "Be helpful.", "conversation_id": conversation_id},
        )

        input_messages = mock_create.call_args.kwargs["input"]
        assert len(input_messages) == 1
        assert input_messages[0]["role"] == "user"
        assert not any(message["role"] == "system" for message in input_messages)


async def test_instructions_included_without_conversation_id() -> None:
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    mock_response = _create_mock_responses_text_response(response_id="resp_new")

    with patch.object(client.client.responses, "create", return_value=mock_response) as mock_create:
        await client.get_response(
            messages=[Message(role="user", contents=["Hello"])],
            options={"instructions": "You are a helpful assistant."},
        )

        input_messages = mock_create.call_args.kwargs["input"]
        assert len(input_messages) == 2
        assert input_messages[0]["role"] == "system"
        assert any("helpful assistant" in str(c) for c in input_messages[0]["content"])
        assert input_messages[1]["role"] == "user"


def test_with_callable_api_key() -> None:
    """Test OpenAIChatClient initialization with callable API key."""

    async def get_api_key() -> str:
        return "test-api-key-123"

    client = OpenAIChatClient(model="gpt-4o", api_key=get_api_key)

    # Verify client was created successfully
    assert client.model == "gpt-4o"
    # OpenAI SDK now manages callable API keys internally
    assert client.client is not None


# region Integration Tests


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
@pytest.mark.parametrize(
    "option_name,option_value,needs_validation",
    [
        # Simple ChatOptions - just verify they don't fail
        param("max_tokens", 500, False, id="max_tokens"),
        param("seed", 123, False, id="seed"),
        param("user", "test-user-id", False, id="user"),
        param("metadata", {"test_key": "test_value"}, False, id="metadata"),
        param("frequency_penalty", 0.5, False, id="frequency_penalty"),
        param("presence_penalty", 0.3, False, id="presence_penalty"),
        param("stop", ["END"], False, id="stop"),
        param("allow_multiple_tool_calls", True, False, id="allow_multiple_tool_calls"),
        param("tool_choice", "none", True, id="tool_choice_none"),
        # OpenAIChatOptions - just verify they don't fail
        param("safety_identifier", "user-hash-abc123", False, id="safety_identifier"),
        param("truncation", "auto", False, id="truncation"),
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
    """Parametrized test covering all ChatOptions and OpenAIChatOptions.

    Tests both streaming and non-streaming modes for each option to ensure
    they don't cause failures. Options marked with needs_validation also
    check that the feature actually works correctly.
    """
    client = OpenAIChatClient()
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
    response = await client.get_response(stream=True, messages=messages, options=options).get_final_response()

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
                assert response.value is not None
                assert isinstance(response.value, dict)
                assert "location" in response.value
                assert "seattle" in response.value["location"].lower()


@pytest.mark.timeout(300)
@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_integration_web_search() -> None:
    client = OpenAIChatClient(model="gpt-5")

    # Test that the client will use the web search tool with location
    web_search_tool_with_location = OpenAIChatClient.get_web_search_tool(
        user_location={"country": "US", "city": "Seattle"},
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
    response = await client.get_response(stream=True, **content).get_final_response()
    assert response.text is not None


@pytest.mark.skip(
    reason="Unreliable due to OpenAI vector store indexing potential "
    "race condition. See https://github.com/microsoft/agent-framework/issues/1669"
)
@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_integration_file_search() -> None:
    openai_responses_client = OpenAIChatClient()

    assert isinstance(openai_responses_client, SupportsChatGetResponse)

    file_id, vector_store = await create_vector_store(openai_responses_client)
    # Use static method for file search tool
    file_search_tool = OpenAIChatClient.get_file_search_tool(vector_store_ids=[vector_store.vector_store_id])
    # Test that the client will use the file search tool
    response = await openai_responses_client.get_response(
        messages=[
            Message(
                role="user",
                contents=["What is the weather today? Do a file search to find the answer."],
            )
        ],
        options={
            "tool_choice": "auto",
            "tools": [file_search_tool],
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
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_integration_streaming_file_search() -> None:
    openai_responses_client = OpenAIChatClient()

    assert isinstance(openai_responses_client, SupportsChatGetResponse)

    file_id, vector_store = await create_vector_store(openai_responses_client)
    # Use static method for file search tool
    file_search_tool = OpenAIChatClient.get_file_search_tool(vector_store_ids=[vector_store.vector_store_id])
    # Test that the client will use the web search tool
    response = openai_responses_client.get_streaming_response(
        messages=[
            Message(
                role="user",
                contents=["What is the weather today? Do a file search to find the answer."],
            )
        ],
        options={
            "tool_choice": "auto",
            "tools": [file_search_tool],
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


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_integration_tool_rich_content_image() -> None:
    """Integration test: a tool returns an image and the model describes it."""
    image_path = Path(__file__).parent.parent / "assets" / "sample_image.jpg"
    image_bytes = image_path.read_bytes()

    @tool(approval_mode="never_require")
    def get_test_image() -> Content:
        """Return a test image for analysis."""
        return Content.from_data(data=image_bytes, media_type="image/jpeg")

    client = OpenAIChatClient()
    client.function_invocation_configuration["max_iterations"] = 2

    messages = [
        Message(
            role="user",
            contents=["Call the get_test_image tool and describe what you see."],
        )
    ]
    options: dict[str, Any] = {"tools": [get_test_image], "tool_choice": "auto"}

    response = await client.get_response(messages=messages, stream=True, options=options).get_final_response()

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert response.text is not None
    assert len(response.text) > 0
    # sample_image.jpg contains a photo of a house; the model should mention it.
    assert "house" in response.text.lower(), f"Model did not describe the house image. Response: {response.text}"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_openai_integration_tests_disabled
async def test_integration_agent_replays_local_tool_history_without_stale_fc_id() -> None:
    """Integration test: persisted local Responses tool history can be replayed on a later turn."""
    hotel_code = "HOTEL-PERSIST-4672"

    @tool(name="search_hotels", approval_mode="never_require")
    async def search_hotels(city: Annotated[str, "The city to search for hotels in"]) -> str:
        return f"The only hotel option in {city} is {hotel_code}."

    # override with model that does not do reasoning by default
    client = OpenAIChatClient(model="gpt-5.4")
    client.function_invocation_configuration["max_iterations"] = 2

    agent = Agent(client=client, tools=[search_hotels], default_options={"store": False})
    session = agent.create_session()

    first_response = await agent.run(
        "Call the search_hotels tool for Paris and answer with the hotel code you found.",
        session=session,
        options={"tool_choice": {"mode": "required", "required_function_name": "search_hotels"}},
    )
    assert first_response.text is not None
    assert hotel_code in first_response.text

    shared_messages = session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID]["messages"]
    shared_function_call = next(
        content for message in shared_messages for content in message.contents if content.type == "function_call"
    )
    assert shared_function_call.additional_properties is not None
    assert isinstance(shared_function_call.additional_properties.get("fc_id"), str)
    assert shared_function_call.additional_properties["fc_id"]

    second_response = await agent.run(
        "What hotel code did you already find for Paris? Answer with the exact code only.",
        session=session,
        options={"tool_choice": "none"},
    )
    assert second_response.text is not None
    assert hotel_code in second_response.text


def test_continuation_token_json_serializable() -> None:
    """Test that OpenAIContinuationToken is a plain dict and JSON-serializable."""
    from agent_framework_openai import OpenAIContinuationToken

    token = OpenAIContinuationToken(response_id="resp_abc123")
    assert token["response_id"] == "resp_abc123"

    # JSON round-trip
    serialized = json.dumps(token)
    restored = json.loads(serialized)
    assert restored["response_id"] == "resp_abc123"


def test_chat_response_with_continuation_token() -> None:
    """Test that ChatResponse accepts and stores continuation_token."""
    from agent_framework_openai import OpenAIContinuationToken

    token = OpenAIContinuationToken(response_id="resp_123")
    response = ChatResponse(
        messages=Message(role="assistant", contents=[Content.from_text(text="Hello")]),
        response_id="resp_123",
        continuation_token=token,
    )
    assert response.continuation_token is not None
    assert response.continuation_token["response_id"] == "resp_123"


def test_chat_response_without_continuation_token() -> None:
    """Test that ChatResponse defaults continuation_token to None."""
    response = ChatResponse(
        messages=Message(role="assistant", contents=[Content.from_text(text="Hello")]),
    )
    assert response.continuation_token is None


def test_chat_response_update_with_continuation_token() -> None:
    """Test that ChatResponseUpdate accepts and stores continuation_token."""
    from agent_framework_openai import OpenAIContinuationToken

    token = OpenAIContinuationToken(response_id="resp_456")
    update = ChatResponseUpdate(
        contents=[Content.from_text(text="chunk")],
        role="assistant",
        continuation_token=token,
    )
    assert update.continuation_token is not None
    assert update.continuation_token["response_id"] == "resp_456"


def test_agent_response_with_continuation_token() -> None:
    """Test that AgentResponse accepts and stores continuation_token."""
    from agent_framework import AgentResponse

    from agent_framework_openai import OpenAIContinuationToken

    token = OpenAIContinuationToken(response_id="resp_789")
    response = AgentResponse(
        messages=Message(role="assistant", contents=[Content.from_text(text="done")]),
        continuation_token=token,
    )
    assert response.continuation_token is not None
    assert response.continuation_token["response_id"] == "resp_789"


def test_agent_response_update_with_continuation_token() -> None:
    """Test that AgentResponseUpdate accepts and stores continuation_token."""
    from agent_framework import AgentResponseUpdate

    from agent_framework_openai import OpenAIContinuationToken

    token = OpenAIContinuationToken(response_id="resp_012")
    update = AgentResponseUpdate(
        contents=[Content.from_text(text="streaming")],
        role="assistant",
        continuation_token=token,
    )
    assert update.continuation_token is not None
    assert update.continuation_token["response_id"] == "resp_012"


def test_parse_response_from_openai_with_background_in_progress() -> None:
    """Test that _parse_response_from_openai sets continuation_token when status is in_progress."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp_bg_123"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "in_progress"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.content = []
    mock_response.output = [mock_message]

    options: dict[str, Any] = {"store": False}
    result = client._parse_response_from_openai(mock_response, options=options)

    assert result.continuation_token is not None
    assert result.continuation_token["response_id"] == "resp_bg_123"


def test_parse_response_from_openai_with_background_queued() -> None:
    """Test that _parse_response_from_openai sets continuation_token when status is queued."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp_bg_456"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "queued"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.content = []
    mock_response.output = [mock_message]

    options: dict[str, Any] = {"store": False}
    result = client._parse_response_from_openai(mock_response, options=options)

    assert result.continuation_token is not None
    assert result.continuation_token["response_id"] == "resp_bg_456"


def test_parse_response_from_openai_with_background_completed() -> None:
    """Test that _parse_response_from_openai does NOT set continuation_token when status is completed."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "resp_bg_789"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.status = "completed"

    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "Final answer"
    mock_text_content.annotations = []
    mock_text_content.logprobs = None

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.content = [mock_text_content]
    mock_response.output = [mock_message]

    options: dict[str, Any] = {"store": False}
    result = client._parse_response_from_openai(mock_response, options=options)

    assert result.continuation_token is None


def test_streaming_response_in_progress_sets_continuation_token() -> None:
    """Test that _parse_chunk_from_openai sets continuation_token for in_progress events."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options: dict[str, Any] = {}
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.in_progress"
    mock_event.response = MagicMock()
    mock_event.response.id = "resp_stream_123"
    mock_event.response.conversation = MagicMock()
    mock_event.response.conversation.id = "conv_456"
    mock_event.response.status = "in_progress"

    update = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert update.continuation_token is not None
    assert update.continuation_token["response_id"] == "resp_stream_123"


def test_streaming_response_created_with_in_progress_status_sets_continuation_token() -> None:
    """Test that response.created with in_progress status sets continuation_token."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options: dict[str, Any] = {}
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.created"
    mock_event.response = MagicMock()
    mock_event.response.id = "resp_created_123"
    mock_event.response.conversation = MagicMock()
    mock_event.response.conversation.id = "conv_789"
    mock_event.response.status = "in_progress"

    update = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert update.continuation_token is not None
    assert update.continuation_token["response_id"] == "resp_created_123"


def test_streaming_response_completed_no_continuation_token() -> None:
    """Test that response.completed does NOT set continuation_token."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    chat_options: dict[str, Any] = {}
    function_call_ids: dict[int, tuple[str, str]] = {}

    mock_event = MagicMock()
    mock_event.type = "response.completed"
    mock_event.response = MagicMock()
    mock_event.response.id = "resp_done_123"
    mock_event.response.conversation = MagicMock()
    mock_event.response.conversation.id = "conv_done"
    mock_event.response.model = "test-model"
    mock_event.response.usage = None

    update = client._parse_chunk_from_openai(mock_event, chat_options, function_call_ids)

    assert update.continuation_token is None


def test_map_chat_to_agent_update_preserves_continuation_token() -> None:
    """Test that map_chat_to_agent_update propagates continuation_token."""
    from agent_framework._types import map_chat_to_agent_update

    token = {"response_id": "resp_map_123"}
    chat_update = ChatResponseUpdate(
        contents=[Content.from_text(text="chunk")],
        role="assistant",
        response_id="resp_map_123",
        continuation_token=token,
    )

    agent_update = map_chat_to_agent_update(chat_update, agent_name="test-agent")

    assert agent_update.continuation_token is not None
    assert agent_update.continuation_token["response_id"] == "resp_map_123"


async def test_prepare_options_excludes_continuation_token() -> None:
    """Test that _prepare_options does not pass continuation_token to OpenAI API."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    messages = [Message(role="user", contents=[Content.from_text(text="Hello")])]
    options: dict[str, Any] = {
        "model": "test-model",
        "continuation_token": {"response_id": "resp_123"},
        "background": True,
    }

    run_options = await client._prepare_options(messages, options)

    assert "continuation_token" not in run_options
    assert "background" in run_options
    assert run_options["background"] is True


# endregion


# region Function Call Fidelity Tests


def test_parse_response_from_openai_function_call_includes_status() -> None:
    """Test _parse_response_from_openai includes status in function call additional_properties."""
    from openai.types.responses import ResponseFunctionToolCall

    client = OpenAIChatClient(model="test-model", api_key="test-key")

    # Create a real ResponseFunctionToolCall object
    mock_function_call_item = ResponseFunctionToolCall(
        type="function_call",
        call_id="call_123",
        name="get_weather",
        arguments='{"location": "Seattle"}',
        id="fc_456",
        status="completed",
    )

    mock_response = MagicMock()
    mock_response.output_parsed = None
    mock_response.metadata = {}
    mock_response.usage = None
    mock_response.id = "test-id"
    mock_response.model = "test-model"
    mock_response.created_at = 1000000000
    mock_response.output = [mock_function_call_item]

    response = client._parse_response_from_openai(mock_response, options={})  # type: ignore

    assert len(response.messages[0].contents) == 1
    function_call = response.messages[0].contents[0]
    assert function_call.type == "function_call"
    assert function_call.call_id == "call_123"
    assert function_call.name == "get_weather"
    assert function_call.arguments == '{"location": "Seattle"}'
    # Verify status is included in additional_properties
    assert function_call.additional_properties is not None
    assert function_call.additional_properties.get("status") == "completed"
    assert function_call.additional_properties.get("fc_id") == "fc_456"
    # Verify raw_representation is preserved
    assert function_call.raw_representation is mock_function_call_item


async def test_prepare_messages_for_openai_does_not_replay_fc_id_when_loaded_from_history() -> None:
    """Loaded history must not replay provider-ephemeral Responses function call IDs."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")
    provider = InMemoryHistoryProvider()

    session = AgentSession(session_id="thread-1")
    session.state[provider.source_id] = {
        "messages": [
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_1",
                        name="search_hotels",
                        arguments='{"city": "Paris"}',
                        additional_properties={"fc_id": "fc_provider123", "status": "completed"},
                    ),
                ],
            ),
            Message(
                role="tool",
                contents=[
                    Content.from_function_result(
                        call_id="call_1",
                        result="Found 3 hotels in Paris",
                    ),
                ],
            ),
        ]
    }

    next_turn_input = Message(role="user", contents=[Content.from_text(text="Book the cheapest one")])

    live_result = client._prepare_messages_for_openai([*session.state[provider.source_id]["messages"], next_turn_input])
    live_function_call = next(item for item in live_result if item.get("type") == "function_call")
    assert live_function_call["id"] == "fc_provider123"

    context = SessionContext(session_id=session.session_id, input_messages=[next_turn_input])
    await provider.before_run(
        agent=None,
        session=session,
        context=context,
        state=session.state.setdefault(provider.source_id, {}),
    )  # type: ignore[arg-type]

    loaded_result = client._prepare_messages_for_openai(
        context.get_messages(sources={provider.source_id}, include_input=True)
    )
    loaded_function_call = next(item for item in loaded_result if item.get("type") == "function_call")
    assert loaded_function_call["id"] == "fc_call_1"

    stored_function_call = session.state[provider.source_id]["messages"][0].contents[0]
    assert stored_function_call.additional_properties is not None
    assert stored_function_call.additional_properties.get("fc_id") == "fc_provider123"

    restored = AgentSession.from_dict(json.loads(json.dumps(session.to_dict())))
    restored_context = SessionContext(session_id=restored.session_id, input_messages=[next_turn_input])
    await provider.before_run(
        agent=None,
        session=restored,
        context=restored_context,
        state=restored.state.setdefault(provider.source_id, {}),
    )  # type: ignore[arg-type]

    restored_result = client._prepare_messages_for_openai(
        restored_context.get_messages(sources={provider.source_id}, include_input=True)
    )
    restored_function_call = next(item for item in restored_result if item.get("type") == "function_call")
    assert restored_function_call["id"] == "fc_call_1"


def test_prepare_messages_for_openai_keeps_live_fc_id_separate_from_replayed_history() -> None:
    """Replayed history must not borrow a live Responses function call ID with the same call_id."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    history_message = Message(
        role="assistant",
        contents=[
            Content.from_function_call(
                call_id="call_1",
                name="search_hotels",
                arguments='{"city": "Paris"}',
                additional_properties={"fc_id": "fc_history123"},
            )
        ],
        additional_properties={"_attribution": {"source_id": "history", "source_type": "InMemoryHistoryProvider"}},
    )
    live_message = Message(
        role="assistant",
        contents=[
            Content.from_function_call(
                call_id="call_1",
                name="search_hotels",
                arguments='{"city": "London"}',
                additional_properties={"fc_id": "fc_live123"},
            )
        ],
    )

    result = client._prepare_messages_for_openai([history_message, live_message])

    function_calls = [item for item in result if item.get("type") == "function_call"]
    assert [item["id"] for item in function_calls] == ["fc_call_1", "fc_live123"]


def test_prepare_messages_for_openai_filters_empty_fc_id() -> None:
    """Test _prepare_messages_for_openai correctly filters empty fc_id values from call_id_to_id mapping."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    messages = [
        Message(role="user", contents=[Content.from_text(text="check hotels")]),
        Message(
            role="assistant",
            contents=[
                # Function call with empty fc_id - should NOT be added to call_id_to_id
                Content.from_function_call(
                    call_id="call_empty",
                    name="search_hotels",
                    arguments='{"city": "Paris"}',
                    additional_properties={"fc_id": ""},  # Empty string
                ),
            ],
        ),
        Message(
            role="assistant",
            contents=[
                # Function call with valid fc_id - SHOULD be added to call_id_to_id
                Content.from_function_call(
                    call_id="call_valid",
                    name="search_flights",
                    arguments='{"from": "NYC"}',
                    additional_properties={"fc_id": "fc_valid123"},
                ),
            ],
        ),
    ]

    result = client._prepare_messages_for_openai(messages)

    # Find the function_call items in the result
    fc_items = [item for item in result if item.get("type") == "function_call"]
    assert len(fc_items) == 2

    # The empty fc_id should result in an auto-generated id (starts with fc_)
    empty_fc_item = next(item for item in fc_items if item.get("call_id") == "call_empty")
    assert empty_fc_item["id"].startswith("fc_")
    assert empty_fc_item["id"] != ""

    # The valid fc_id should be preserved
    valid_fc_item = next(item for item in fc_items if item.get("call_id") == "call_valid")
    assert valid_fc_item["id"] == "fc_valid123"


def test_prepare_messages_for_openai_filters_none_fc_id() -> None:
    """Test _prepare_messages_for_openai correctly filters None fc_id values."""
    client = OpenAIChatClient(model="test-model", api_key="test-key")

    messages = [
        Message(
            role="assistant",
            contents=[
                # Function call with None fc_id value
                Content.from_function_call(
                    call_id="call_none",
                    name="get_info",
                    arguments="{}",
                    additional_properties={"fc_id": None},  # None value
                ),
            ],
        ),
    ]

    result = client._prepare_messages_for_openai(messages)

    # Find the function_call item
    fc_items = [item for item in result if item.get("type") == "function_call"]
    assert len(fc_items) == 1

    # The None fc_id should result in an auto-generated id
    fc_item = fc_items[0]
    assert fc_item["id"].startswith("fc_")


# endregion
