# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import AsyncIterable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    BaseChatClient,
    ChatMessage,
    ChatResponseUpdate,
    DataContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedWebSearchTool,
    TextContent,
    UriContent,
)
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError
from ollama import AsyncClient
from ollama._types import ChatResponse as OllamaChatResponse
from ollama._types import Message as OllamaMessage
from openai import AsyncStream

from agent_framework_ollama import OllamaChatClient

# region Service Setup

os.environ["RUN_INTEGRATION_TESTS"] = "false"

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OLLAMA_CHAT_MODEL_ID", "") in ("", "test-model"),
    reason="No real Ollama chat model provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


@pytest.fixture
def mock_streaming_chat_completion_response() -> AsyncStream[OllamaChatResponse]:
    response = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [response]
    return stream


@pytest.fixture
def mock_chat_completion_response() -> OllamaChatResponse:
    return OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        eval_count=1,
        prompt_eval_count=1,
        created_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def mock_streaming_chat_completion_tool_call() -> AsyncStream[OllamaChatResponse]:
    ollama_tool_call = OllamaChatResponse(
        message=OllamaMessage(
            content="",
            role="assistant",
            tool_calls=[{"function": {"name": "hello_world", "arguments": {"arg1": "value1"}}}],
        ),
        model="test",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [ollama_tool_call]
    return stream


@pytest.fixture
def mock_chat_completion_tool_call() -> OllamaChatResponse:
    return OllamaChatResponse(
        message=OllamaMessage(
            content="",
            role="assistant",
            tool_calls=[{"function": {"name": "hello_world", "arguments": {"arg1": "value1"}}}],
        ),
        model="test",
        created_at="2024-01-01T00:00:00Z",
    )


def hello_world(arg1: str) -> str:
    return "Hello World"


def test_init(ollama_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ollama_chat_client = OllamaChatClient()

    assert ollama_chat_client.client is not None
    assert isinstance(ollama_chat_client.client, AsyncClient)
    assert ollama_chat_client.chat_model_id == ollama_unit_test_env["OLLAMA_CHAT_MODEL_ID"]
    assert isinstance(ollama_chat_client, BaseChatClient)


def test_init_client(ollama_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization with provided client
    test_client = MagicMock(spec=AsyncClient)
    # Mock underlying HTTP client's base_url
    test_client._client = MagicMock()
    test_client._client.base_url = ollama_unit_test_env["OLLAMA_CHAT_MODEL_ID"]
    ollama_chat_client = OllamaChatClient(client=test_client)

    assert ollama_chat_client.client is test_client
    assert ollama_chat_client.chat_model_id == ollama_unit_test_env["OLLAMA_CHAT_MODEL_ID"]
    assert isinstance(ollama_chat_client, BaseChatClient)


@pytest.mark.parametrize("exclude_list", [["OLLAMA_CHAT_MODEL_ID"]], indirect=True)
def test_with_invalid_settings(ollama_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OllamaChatClient(
            host="http://localhost:12345",
            chat_model_id=None,
            env_file_path="test.env",
        )


def test_serialize(ollama_unit_test_env: dict[str, str]) -> None:
    settings = {
        "host": ollama_unit_test_env["OLLAMA_HOST"],
        "chat_model_id": ollama_unit_test_env["OLLAMA_CHAT_MODEL_ID"],
    }

    ollama_chat_client = OllamaChatClient.from_dict(settings)
    serialized = ollama_chat_client.to_dict()

    assert isinstance(serialized, dict)
    assert serialized["host"] == ollama_unit_test_env["OLLAMA_HOST"]
    assert serialized["chat_model_id"] == ollama_unit_test_env["OLLAMA_CHAT_MODEL_ID"]


# region CMC


async def test_empty_messages() -> None:
    ollama_chat_client = OllamaChatClient(
        host="http://localhost:12345",
        chat_model_id="test-model",
    )
    with pytest.raises(ServiceInvalidRequestError):
        await ollama_chat_client.get_response(messages=[])


async def test_function_choice_required_argument() -> None:
    ollama_chat_client = OllamaChatClient(
        host="http://localhost:12345",
        chat_model_id="test-model",
    )
    with pytest.raises(ServiceInvalidRequestError):
        await ollama_chat_client.get_response(
            messages=[ChatMessage(text="hello world", role="user")],
            tool_choice="required",
            tools=[hello_world],
        )


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_streaming_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_streaming_chat_completion_response
    chat_history.append(ChatMessage(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_streaming_response(messages=chat_history)

    async for chunk in result:
        assert chunk.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_with_tool_call(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_streaming_chat_completion_response: AsyncStream[OllamaChatResponse],
    mock_streaming_chat_completion_tool_call: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.side_effect = [mock_streaming_chat_completion_tool_call, mock_streaming_chat_completion_response]

    chat_history.append(ChatMessage(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_streaming_response(messages=chat_history, tools=[hello_world])

    chunks: list[ChatResponseUpdate] = []
    async for chunk in result:
        chunks.append(chunk)

    # Check parsed Toolcalls
    assert isinstance(chunks[0].contents[0], FunctionCallContent)
    tool_call = chunks[0].contents[0]
    assert tool_call.name == "hello_world"
    assert tool_call.arguments == {"arg1": "value1"}
    assert isinstance(chunks[1].contents[0], FunctionResultContent)
    tool_result = chunks[1].contents[0]
    assert tool_result.result == "Hello World"
    assert isinstance(chunks[2].contents[0], TextContent)
    text_result = chunks[2].contents[0]
    assert text_result.text == "test"


async def test_cmc_with_hosted_tool_call(
    ollama_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
) -> None:
    with pytest.raises(ServiceInvalidRequestError):
        additional_properties = {
            "user_location": {
                "country": "US",
                "city": "Seattle",
            }
        }

        chat_history.append(ChatMessage(text="hello world", role="user"))

        ollama_client = OllamaChatClient()
        await ollama_client.get_response(
            messages=chat_history, tools=[HostedWebSearchTool(additional_properties=additional_properties)]
        )


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_data_content_type(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: OllamaChatResponse,
) -> None:
    mock_chat.return_value = mock_chat_completion_response
    chat_history.append(
        ChatMessage(contents=[DataContent(uri="data:image/png;base64,xyz", media_type="image/png")], role="user")
    )

    ollama_client = OllamaChatClient()

    result = await ollama_client.get_response(messages=chat_history)
    assert result.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_invalid_data_content_media_type(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_streaming_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    with pytest.raises(ServiceInvalidRequestError):
        mock_chat.return_value = mock_streaming_chat_completion_response
        # Remote Uris are not supported by Ollama client
        chat_history.append(
            ChatMessage(contents=[DataContent(uri="data:audio/mp3;base64,xyz", media_type="audio/mp3")], role="user")
        )

        ollama_client = OllamaChatClient()
        ollama_client.client.chat = AsyncMock(return_value=mock_streaming_chat_completion_response)

        await ollama_client.get_response(messages=chat_history)


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_invalid_content_type(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[ChatMessage],
    mock_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    with pytest.raises(ServiceInvalidRequestError):
        mock_chat.return_value = mock_chat_completion_response
        # Remote Uris are not supported by Ollama client
        chat_history.append(
            ChatMessage(contents=[UriContent(uri="http://example.com/image.png", media_type="image/png")], role="user")
        )

        ollama_client = OllamaChatClient()

        await ollama_client.get_response(messages=chat_history)


@skip_if_azure_integration_tests_disabled
async def test_cmc_integration_with_tool_call(
    chat_history: list[ChatMessage],
) -> None:
    chat_history.append(ChatMessage(text="Call the hello world function and repeat what it says", role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history, tools=[hello_world])

    assert "hello" in result.text.lower() and "world" in result.text.lower()
    assert isinstance(result.messages[-2].contents[0], FunctionResultContent)
    tool_result = result.messages[-2].contents[0]
    assert tool_result.result == "Hello World"


@skip_if_azure_integration_tests_disabled
async def test_cmc_integration_with_chat_completion(
    chat_history: list[ChatMessage],
) -> None:
    chat_history.append(ChatMessage(text="Say Hello World", role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert "hello" in result.text.lower() and "world" in result.text.lower()


@skip_if_azure_integration_tests_disabled
async def test_cmc_streaming_integration_with_tool_call(
    chat_history: list[ChatMessage],
) -> None:
    chat_history.append(ChatMessage(text="Call the hello world function and repeat what it says", role="user"))

    ollama_client = OllamaChatClient()
    result: AsyncIterable[ChatResponseUpdate] = ollama_client.get_streaming_response(
        messages=chat_history, tools=[hello_world]
    )

    chunks: list[ChatResponseUpdate] = []
    async for chunk in result:
        chunks.append(chunk)

    for c in chunks:
        if len(c.contents) > 0:
            if isinstance(c.contents[0], FunctionResultContent):
                tool_result = c.contents[0]
                assert tool_result.result == "Hello World"
            if isinstance(c.contents[0], FunctionCallContent):
                tool_call = c.contents[0]
                assert tool_call.name == "hello_world"


@skip_if_azure_integration_tests_disabled
async def test_cmc_streaming_integration_with_chat_completion(
    chat_history: list[ChatMessage],
) -> None:
    chat_history.append(ChatMessage(text="Say Hello World", role="user"))

    ollama_client = OllamaChatClient()
    result: AsyncIterable[ChatResponseUpdate] = ollama_client.get_streaming_response(messages=chat_history)

    full_text = ""
    async for chunk in result:
        full_text += chunk.text

    assert "hello" in full_text.lower() and "world" in full_text.lower()
