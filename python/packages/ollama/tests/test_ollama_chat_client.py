# Copyright (c) Microsoft. All rights reserved.

import os
import uuid
from collections.abc import AsyncIterable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import (
    Agent,
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
from pydantic import BaseModel
from pytest import fixture

from agent_framework_ollama import OllamaChatClient

# region Service Setup

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("OLLAMA_MODEL", "") in ("", "test-model"),
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

    env_vars = {"OLLAMA_HOST": "http://localhost:12345", "OLLAMA_MODEL": "test"}

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


def test_agent_accepts_ollama_chat_client(ollama_unit_test_env: dict[str, str]) -> None:
    client = OllamaChatClient()
    agent = Agent(client=client, instructions="test agent")
    assert agent.client is client


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
            tool_calls=cast(Any, [{"function": {"name": "hello_world", "arguments": {"arg1": "value1"}}}]),
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
            tool_calls=cast(Any, [{"function": {"name": "hello_world", "arguments": {"arg1": "value1"}}}]),
        ),
        model="test",
        created_at="2024-01-01T00:00:00Z",
    )


@tool(approval_mode="never_require")
def hello_world(arg1: str) -> str:
    return "Hello World"


@tool(approval_mode="never_require")
def greet() -> str:
    """Say hello to the world. No-arg tool for integration tests to avoid argument parsing flakiness."""
    return "Hello World"


def test_init(ollama_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ollama_chat_client = OllamaChatClient()

    assert ollama_chat_client.client is not None
    assert isinstance(ollama_chat_client.client, AsyncClient)
    assert ollama_chat_client.model == ollama_unit_test_env["OLLAMA_MODEL"]
    assert isinstance(ollama_chat_client, BaseChatClient)


def test_init_client(ollama_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization with provided client
    test_client = MagicMock(spec=AsyncClient)
    # Mock underlying HTTP client's base_url
    test_client._client = MagicMock()
    test_client._client.base_url = ollama_unit_test_env["OLLAMA_MODEL"]
    ollama_chat_client = OllamaChatClient(client=test_client)

    assert ollama_chat_client.client is test_client
    assert ollama_chat_client.model == ollama_unit_test_env["OLLAMA_MODEL"]
    assert isinstance(ollama_chat_client, BaseChatClient)


@pytest.mark.parametrize("exclude_list", [["OLLAMA_MODEL"]], indirect=True)
def test_with_invalid_settings(ollama_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(SettingNotFoundError, match="Required setting 'model'"):
        OllamaChatClient(
            host="http://localhost:12345",
            model=None,
        )


def test_serialize(ollama_unit_test_env: dict[str, str]) -> None:
    settings = {
        "host": ollama_unit_test_env["OLLAMA_HOST"],
        "model": ollama_unit_test_env["OLLAMA_MODEL"],
    }

    ollama_chat_client = OllamaChatClient.from_dict(settings)
    serialized = ollama_chat_client.to_dict()

    assert isinstance(serialized, dict)
    assert serialized["host"] == ollama_unit_test_env["OLLAMA_HOST"]
    assert serialized["model"] == ollama_unit_test_env["OLLAMA_MODEL"]


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
        model="test-model",
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
    chat_history.append(Message(contents=["hello world"], role="system"))
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert result.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_maps_done_reason_to_finish_reason(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    mock_chat.return_value = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        eval_count=2,
        prompt_eval_count=3,
        done_reason="length",
    )
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert result.finish_reason == "length"
    assert result.usage_details == {
        "input_token_count": 3,
        "output_token_count": 2,
        "total_token_count": 5,
    }


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_leaves_unknown_done_reason_unset(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    mock_chat.return_value = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        done_reason="load",
    )
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert result.finish_reason is None


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_omits_usage_when_token_counts_are_missing(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    mock_chat.return_value = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        done_reason="stop",
    )
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert result.finish_reason == "stop"
    assert not result.usage_details


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_response_format_dict(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    mock_chat.return_value = OllamaChatResponse(
        message=OllamaMessage(content='{"answer": "test"}', role="assistant"),
        model="test",
        eval_count=1,
        prompt_eval_count=1,
        created_at="2024-01-01T00:00:00Z",
    )
    chat_history.append(Message(contents=["hello world"], role="system"))
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(
        messages=chat_history,
        options={"response_format": {"type": "object", "properties": {"answer": {"type": "string"}}}},
    )

    assert result.value is not None
    assert isinstance(result.value, dict)
    assert result.value["answer"] == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_response_format_pydantic_model(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    """A Pydantic model class is converted to a JSON schema dict for Ollama's ``format``.

    Ollama only accepts ``''``, ``'json'``, or a JSON-schema dict for ``format``; a model
    class would fail request construction. The class is still kept for typed parsing of
    the response, matching OpenAI/Foundry behavior.
    """

    class Answer(BaseModel):
        answer: str

    mock_chat.return_value = OllamaChatResponse(
        message=OllamaMessage(content='{"answer": "test"}', role="assistant"),
        model="test",
        eval_count=1,
        prompt_eval_count=1,
        created_at="2024-01-01T00:00:00Z",
    )
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history, options={"response_format": Answer})

    # Outgoing ``format`` must be the JSON schema dict, not the model class.
    assert mock_chat.await_args is not None
    assert mock_chat.await_args.kwargs["format"] == Answer.model_json_schema()

    # Typed parsing still works because the original model class is preserved.
    assert isinstance(result.value, Answer)
    assert result.value.answer == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_reasoning(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_chat_completion_response_reasoning: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_chat_completion_response_reasoning
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    reasoning = "".join(cast("str", c.text) for c in result.messages.pop().contents if c.type == "text_reasoning")
    assert reasoning == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_chat_failure(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    # Simulate a failure in the Ollama client
    mock_chat.side_effect = Exception("Connection error")
    chat_history.append(Message(contents=["hello world"], role="user"))

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
    chat_history.append(Message(contents=["hello world"], role="system"))
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True)

    async for chunk in result:
        assert chunk.text == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_maps_done_reason_and_usage(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    response = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        done=True,
        done_reason="stop",
        eval_count=4,
        prompt_eval_count=6,
        created_at="2024-01-01T00:00:00Z",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [response]
    mock_chat.return_value = stream
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True)
    async for _ in result:
        pass
    final_response = await result.get_final_response()

    assert final_response.text == "test"
    assert final_response.finish_reason == "stop"
    assert final_response.usage_details == {
        "input_token_count": 6,
        "output_token_count": 4,
        "total_token_count": 10,
    }


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_ignores_done_reason_and_usage_before_final_chunk(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    response = OllamaChatResponse(
        message=OllamaMessage(content="test", role="assistant"),
        model="test",
        done=False,
        done_reason="stop",
        eval_count=4,
        prompt_eval_count=6,
        created_at="2024-01-01T00:00:00Z",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [response]
    mock_chat.return_value = stream
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True)
    async for _ in result:
        pass
    final_response = await result.get_final_response()

    assert final_response.text == "test"
    assert final_response.finish_reason is None
    assert final_response.usage_details is None


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_reasoning(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
    mock_streaming_chat_completion_response_reasoning: AsyncStream[OllamaChatResponse],
) -> None:
    mock_chat.return_value = mock_streaming_chat_completion_response_reasoning
    chat_history.append(Message(contents=["hello world"], role="user"))

    ollama_client = OllamaChatClient()
    result = ollama_client.get_response(messages=chat_history, stream=True)

    async for chunk in result:
        reasoning = "".join(cast("str", c.text) for c in chunk.contents if c.type == "text_reasoning")
        assert reasoning == "test"


@patch.object(AsyncClient, "chat", new_callable=AsyncMock)
async def test_cmc_streaming_chat_failure(
    mock_chat: AsyncMock,
    ollama_unit_test_env: dict[str, str],
    chat_history: list[Message],
) -> None:
    # Simulate a failure in the Ollama client for streaming
    mock_chat.side_effect = Exception("Streaming connection error")
    chat_history.append(Message(contents=["hello world"], role="user"))

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

    chat_history.append(Message(contents=["hello world"], role="user"))

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
    chat_history.append(Message(contents=["hello world"], role="user"))

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
        ollama_client.client.chat = AsyncMock(return_value=mock_streaming_chat_completion_response)  # type: ignore[method-assign]

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
    chat_history.append(Message(contents=["Call the greet function and repeat what it says"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history, options={"tools": [greet]})

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
    chat_history.append(Message(contents=["Say Hello World"], role="user"))

    ollama_client = OllamaChatClient()
    result = await ollama_client.get_response(messages=chat_history)

    assert "hello" in result.text.lower()


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_cmc_streaming_integration_with_tool_call(
    chat_history: list[Message],
) -> None:
    chat_history.append(Message(contents=["Call the greet function and repeat what it says"], role="user"))

    ollama_client = OllamaChatClient()
    result: AsyncIterable[ChatResponseUpdate] = ollama_client.get_response(
        messages=chat_history, stream=True, options={"tools": [greet]}
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
                assert tool_call.name == "greet"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_integration_tests_disabled
async def test_cmc_streaming_integration_with_chat_completion(
    chat_history: list[Message],
) -> None:
    chat_history.append(Message(contents=["Say Hello World"], role="user"))

    ollama_client = OllamaChatClient()
    result: AsyncIterable[ChatResponseUpdate] = ollama_client.get_response(messages=chat_history, stream=True)

    full_text = ""
    async for chunk in result:
        full_text += chunk.text

    assert "hello" in full_text.lower() and "world" in full_text.lower()


class TestParallelToolCallUniqueness:
    """Verify that repeated tool calls in one turn get unique call_ids."""

    def test_parse_duplicate_tool_names_get_unique_call_ids(self) -> None:
        """Two calls to the same tool should have different call_ids."""
        mock_func_1 = MagicMock()
        mock_func_1.name = "search"
        mock_func_1.arguments = {"query": "Azure"}

        mock_func_2 = MagicMock()
        mock_func_2.name = "search"
        mock_func_2.arguments = {"query": "AWS"}

        mock_tool_1 = MagicMock()
        mock_tool_1.function = mock_func_1

        mock_tool_2 = MagicMock()
        mock_tool_2.function = mock_func_2

        client = OllamaChatClient(host="http://localhost:12345", model="test-model")
        results = client._parse_tool_calls_from_ollama([mock_tool_1, mock_tool_2])

        assert len(results) == 2
        id1 = results[0].call_id
        id2 = results[1].call_id

        assert id1 != id2, f"Parallel tool calls collided on call_id: {id1}"

        assert id1 is not None
        assert id2 is not None
        try:
            uuid.UUID(str(id1))
            uuid.UUID(str(id2))
        except ValueError:
            pytest.fail(f"call_id is not a valid UUID: {id1=}, {id2=}")

    def test_format_tool_message_strips_unique_suffix(self) -> None:
        """_format_tool_message must send only the bare tool name to Ollama."""
        client = OllamaChatClient(host="http://localhost:12345", model="test-model")

        # Fake a function_result content item
        mock_item = MagicMock()
        mock_item.type = "function_result"
        mock_item.name = "search:advanced"
        mock_item.call_id = str(uuid.uuid4())
        mock_item.result = "found it"
        mock_item.items = None

        mock_message = MagicMock()
        mock_message.contents = [mock_item]

        formatted = client._format_tool_message(mock_message)

        assert len(formatted) == 1
        assert formatted[0].tool_name == "search:advanced", (
            f"Expected bare name 'search:advanced', got '{formatted[0].tool_name}'"
        )
