# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import AsyncIterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    BaseChatClient,
    ChatResponseUpdate,
    Content,
    Message,
    chat_middleware,
    tool,
)
from agent_framework.exceptions import ChatClientException, ChatClientInvalidRequestException, SettingNotFoundError
from ollama import AsyncClient
from ollama._types import ChatResponse as OllamaChatResponse
from ollama._types import Message as OllamaMessage
from openai import AsyncStream
from pytest import fixture

from agent_framework_ollama import OllamaChatClient

# region Service Setup

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OLLAMA_MODEL_ID", "") in ("", "test-model"),
    reason="No real Ollama chat model provided; skipping integration tests.",
)


# region: Connector Settings fixtures
@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


# These two fixtures are used for multiple things, also non-connector tests
@fixture()
def ollama_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for OllamaSettings."""

    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {"OLLAMA_HOST": "http://localhost:12345", "OLLAMA_MODEL_ID": "test"}

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@fixture
def chat_history() -> list[Message]:
    return []


@fixture
def mock_streaming_chat_completion_response() -> AsyncStream[OllamaChatResponse]:
    response = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [response]
    return stream


@fixture
def mock_streaming_chat_completion_response_reasoning() -> AsyncStream[OllamaChatResponse]:
    response = OllamaChatResponse(
        message=OllamaMessage(thinking="test", role="assistant"),
        model="test",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [response]
    return stream


@fixture
def mock_chat_completion_response() -> OllamaChatResponse:
    return OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        eval_count=1,
        prompt_eval_count=1,
        created_at="2024-01-01T00:00:00Z",
    )


@fixture
def mock_chat_completion_response_reasoning() -> OllamaChatResponse:
    return OllamaChatResponse(
        message=OllamaMessage(thinking="test", role="assistant"),
        model="test",
        eval_count=1,
        prompt_eval_count=1,
        created_at="2024-01-01T00:00:00Z",
    )


@fixture
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


@fixture
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


@tool(approval_mode="never_require")
def hello_world(arg1: str) -> str:
    return "Hello World"


def test_init(ollama_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ollama_chat_client = OllamaChatClient()

    assert ollama_chat_client.client is not None
    assert isinstance(ollama_chat_client.client, AsyncClient)
    assert ollama_chat_client.model_id == ollama_unit_test_env["OLLAMA_MODEL_ID"]
    assert isinstance(ollama_chat_client, BaseChatClient)


def test_init_client(ollama_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization with provided client
    test_client = MagicMock(spec=AsyncClient)
    # Mock underlying HTTP client's base_url
    test_client._client = MagicMock()
    test_client._client.base_url = ollama_unit_test_env["OLLAMA_MODEL_ID"]
    ollama_chat_client = OllamaChatClient(client=test_client)

    assert ollama_chat_client.client is test_client
    assert ollama_chat_client.model_id == ollama_unit_test_env["OLLAMA_MODEL_ID"]
    assert isinstance(ollama_chat_client, BaseChatClient)


@pytest.mark.parametrize("exclude_list", [["OLLAMA_MODEL_ID"]], indirect=True)
def test_with_invalid_settings(ollama_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(SettingNotFoundError, match="Required setting 'model_id'"):
        OllamaChatClient(
            host="http://localhost:12345",
            model_id=None,
        )


def test_serialize(ollama_unit_test_env: dict[str, str]) -> None:
    settings = {
        "host": ollama_unit_test_env["OLLAMA_HOST"],
        "model_id": ollama_unit_test_env["OLLAMA_MODEL_ID"],
    }

    ollama_chat_client = OllamaChatClient.from_dict(settings)
    serialized = ollama_chat_client.to_dict()

    assert isinstance(serialized, dict)
    assert serialized["host"] == ollama_unit_test_env["OLLAMA_HOST"]
    assert serialized["model_id"] == ollama_unit_test_env["OLLAMA_MODEL_ID"]


def test_chat_middleware(ollama_unit_test_env: dict[str, str]) -> None:
    @chat_middleware
    async def sample_middleware(context, call_next):
        await call_next()

    ollama_chat_client = OllamaChatClient(middleware=[sample_middleware])
    assert len(ollama_chat_client.middleware) == 1
    assert ollama_chat_client.middleware[0] == sample_middleware


def test_additional_properties(ollama_unit_test_env: dict[str, str]) -> None:
    additional_properties = {
        "user_location": {
            "country": "US",
            "city": "Seattle",
        }
    }
    ollama_chat_client = OllamaChatClient(
        additional_properties=additional_properties,
    )
    assert ollama_chat_client.additional_properties == additional_properties


# region CMC


async def test_empty_messages() -> None:
    ollama_chat_client = OllamaChatClient(
        host="http://localhost:12345",
        model_id="test-model",
    )
    with pytest.raises(ChatClientInvalidRequestException):
        await ollama_chat_client.get_response(messages=[])


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_chat_completion_response
    chat_history.append(Message(text="hello world", role="system"))
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert result.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_reasoning(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_chat_completion_response_reasoning: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_chat_completion_response_reasoning
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    reasoning = "".join(c.text for c in result.messages.pop().contents if c.type == "text_reasoning")
    assert reasoning == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_chat_failure(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    # Simulate a failure in the Ollama client
    mock_chat.side_effect = Exception("Connection error")
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()

    with pytest.raises(ChatClientException) as exc_info:
        await ollama_client.get_response(messages=chat_history)

    assert "Ollama chat request failed" in str(exc_info.value)
    assert "Connection error" in str(exc_info.value)


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_streaming_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_streaming_chat_completion_response
    chat_history.append(Message(text="hello world", role="system"))
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True)

    async for chunk in result:
        assert chunk.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_reasoning(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_streaming_chat_completion_response_reasoning: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_streaming_chat_completion_response_reasoning
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True)

    async for chunk in result:
        reasoning = "".join(c.text for c in chunk.contents if c.type == "text_reasoning")
        assert reasoning == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_chat_failure(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    # Simulate a failure in the Ollama client for streaming
    mock_chat.side_effect = Exception("Streaming connection error")
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()

    with pytest.raises(ChatClientException) as exc_info:
        async for _ in ollama_client.get_response(messages=chat_history, stream=True):
            pass

    assert "Ollama streaming chat request failed" in str(exc_info.value)
    assert "Streaming connection error" in str(exc_info.value)


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_with_tool_call(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_streaming_chat_completion_response: AsyncStream[OllamaChatResponse],
    mock_streaming_chat_completion_tool_call: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.side_effect = [
        mock_streaming_chat_completion_tool_call,
        mock_streaming_chat_completion_response,
    ]

    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True, options={"tools": [hello_world]})

    chunks: list[ChatResponseUpdate] = []
    async for chunk in result:
        chunks.append(chunk)

    # Check parsed Toolcalls
    assert chunks[0].contents[0].type == "function_call"
    tool_call = chunks[0].contents[0]
    assert tool_call.name == "hello_world"
    assert tool_call.arguments == {"arg1": "value1"}
    assert chunks[1].contents[0].type == "function_result"
    tool_result = chunks[1].contents[0]
    assert tool_result.result == "Hello World"
    assert chunks[2].contents[0].type == "text"
    text_result = chunks[2].contents[0]
    assert text_result.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_dict_tool_passthrough(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_chat_completion_response: OllamaChatResponse,
) -> None:
    """Test that dict-based tools are passed through to Ollama."""
    mock_chat.return_value = mock_chat_completion_response
    chat_history.append(Message(text="hello world", role="user"))

    ollama_client = OllamaChatClient()
    await ollama_client.get_response(
        messages=chat_history,
        options={
            "tools": [{"type": "function", "function": {"name": "custom_tool", "parameters": {}}}],
        },
    )

    # Verify the tool was passed through to the Ollama client
    mock_chat.assert_called_once()
    call_kwargs = mock_chat.call_args.kwargs
    assert "tools" in call_kwargs
    assert call_kwargs["tools"] == [{"type": "function", "function": {"name": "custom_tool", "parameters": {}}}]


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_data_content_type(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_chat_completion_response: OllamaChatResponse,
) -> None:
    mock_chat.return_value = mock_chat_completion_response
    chat_history.append(
        Message(
            contents=[Content.from_uri(uri="data:image/png;base64,xyz", media_type="image/png")],
            role="user",
        )
    )

    ollama_client = OllamaChatClient()

    result = await ollama_client.get_response(messages=chat_history)
    assert result.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_invalid_data_content_media_type(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_streaming_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    with pytest.raises(ChatClientInvalidRequestException):
        mock_chat.return_value = mock_streaming_chat_completion_response
        # Remote Uris are not supported by Ollama client
        chat_history.append(
            Message(
                contents=[Content.from_uri(uri="data:audio/mp3;base64,xyz", media_type="audio/mp3")],
                role="user",
            )
        )

        ollama_client = OllamaChatClient()
        ollama_client.client.chat = AsyncMock(return_value=mock_streaming_chat_completion_response)

        await ollama_client.get_response(messages=chat_history)


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_with_invalid_content_type(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_chat_completion_response: AsyncStream[OllamaChatResponse],
) -> None:
    with pytest.raises(ChatClientInvalidRequestException):
        mock_chat.return_value = mock_chat_completion_response
        # Remote Uris are not supported by Ollama client
        chat_history.append(
            Message(
                contents=[Content.from_uri(uri="http://example.com/image.png", media_type="image/png")],
                role="user",
            )
        )

        ollama_client = OllamaChatClient()

        await ollama_client.get_response(messages=chat_history)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_cmc_integration_with_tool_call(
    chat_history: list[Message],
) -> None:
    chat_history.append(Message(text="Call the hello world function and repeat what it says", role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history, options={"tools": [hello_world]})

    assert "hello" in result.text.lower() and "world" in result.text.lower()
    assert result.messages[-2].contents[0].type == "function_result"
    tool_result = result.messages[-2].contents[0]
    assert tool_result.result == "Hello World"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_cmc_integration_with_chat_completion(
    chat_history: list[Message],
) -> None:
    chat_history.append(Message(text="Say Hello World", role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert "hello" in result.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_cmc_streaming_integration_with_tool_call(
    chat_history: list[Message],
) -> None:
    chat_history.append(Message(text="Call the hello world function and repeat what it says", role="user"))

    ollama_client = OllamaChatClient()
    result: AsyncIterable[ChatResponseUpdate] = ollama_client.get_response(
        messages=chat_history, stream=True, options={"tools": [hello_world]}
    )

    chunks: list[ChatResponseUpdate] = []
    async for chunk in result:
        chunks.append(chunk)

    for c in chunks:
        if len(c.contents) > 0:
            if c.contents[0].type == "function_result":
                tool_result = c.contents[0]
                assert tool_result.result == "Hello World"
            if c.contents[0].type == "function_call":
                tool_call = c.contents[0]
                assert tool_call.name == "hello_world"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_cmc_streaming_integration_with_chat_completion(
    chat_history: list[Message],
) -> None:
    chat_history.append(Message(text="Say Hello World", role="user"))

    ollama_client = OllamaChatClient()
    result: AsyncIterable[ChatResponseUpdate] = ollama_client.get_response(messages=chat_history, stream=True)

    full_text = ""
    async for chunk in result:
        full_text += chunk.text

    assert "hello" in full_text.lower() and "world" in full_text.lower()
