# Copyright (c) Microsoft. All rights reserved.

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import AsyncStream
from openai.resources.chat.completions import AsyncCompletions as AsyncChatCompletions
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta as ChunkChoiceDelta
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from pydantic import BaseModel

from agent_framework import ChatMessage, ChatResponseUpdate
from agent_framework.exceptions import (
    ServiceResponseException,
)
from agent_framework.openai import OpenAIChatClient


async def mock_async_process_chat_stream_response(_):
    mock_content = MagicMock(spec=ChatResponseUpdate)
    yield mock_content, None


@pytest.fixture(scope="function")
def chat_history() -> list[ChatMessage]:
    return []


@pytest.fixture
def mock_chat_completion_response() -> ChatCompletion:
    return ChatCompletion(
        id="test_id",
        choices=[
            Choice(index=0, message=ChatCompletionMessage(content="test", role="assistant"), finish_reason="stop")
        ],
        created=0,
        model="test",
        object="chat.completion",
    )


@pytest.fixture
def mock_streaming_chat_completion_response() -> AsyncStream[ChatCompletionChunk]:
    content = ChatCompletionChunk(
        id="test_id",
        choices=[ChunkChoice(index=0, delta=ChunkChoiceDelta(content="test", role="assistant"), finish_reason="stop")],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [content]
    return stream


# region Chat Message Content


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    openai_chat_completion = OpenAIChatClient()
    await openai_chat_completion.get_response(messages=chat_history)
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=False,
        messages=openai_chat_completion._prepare_chat_history_for_request(chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc_chat_options(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    openai_chat_completion = OpenAIChatClient()
    await openai_chat_completion.get_response(
        messages=chat_history,
    )
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=False,
        messages=openai_chat_completion._prepare_chat_history_for_request(chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc_no_fcc_in_response(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))
    orig_chat_history = deepcopy(chat_history)

    openai_chat_completion = OpenAIChatClient()
    await openai_chat_completion.get_response(
        messages=chat_history,
        arguments={},
    )
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=False,
        messages=openai_chat_completion._prepare_chat_history_for_request(orig_chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc_structured_output_no_fcc(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    # Define a mock response format
    class Test(BaseModel):
        name: str

    openai_chat_completion = OpenAIChatClient()
    await openai_chat_completion.get_response(
        messages=chat_history,
        response_format=Test,
    )
    mock_create.assert_awaited_once()


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_scmc_chat_options(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_streaming_chat_completion_response: AsyncStream[ChatCompletionChunk],
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_streaming_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    openai_chat_completion = OpenAIChatClient()
    async for msg in openai_chat_completion.get_streaming_response(
        messages=chat_history,
    ):
        assert isinstance(msg, ChatResponseUpdate)
        assert msg.message_id is not None
        assert msg.response_id is not None
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=True,
        stream_options={"include_usage": True},
        messages=openai_chat_completion._prepare_chat_history_for_request(chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock, side_effect=Exception)
async def test_cmc_general_exception(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    openai_chat_completion = OpenAIChatClient()
    with pytest.raises(ServiceResponseException):
        await openai_chat_completion.get_response(
            messages=chat_history,
        )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_cmc_additional_properties(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    openai_chat_completion = OpenAIChatClient()
    await openai_chat_completion.get_response(messages=chat_history, additional_properties={"reasoning_effort": "low"})
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=False,
        messages=openai_chat_completion._prepare_chat_history_for_request(chat_history),  # type: ignore
        reasoning_effort="low",
    )


# region Streaming


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_get_streaming(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    openai_unit_test_env: dict[str, str],
):
    content1 = ChatCompletionChunk(
        id="test_id",
        choices=[],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    content2 = ChatCompletionChunk(
        id="test_id",
        choices=[ChunkChoice(index=0, delta=ChunkChoiceDelta(content="test", role="assistant"), finish_reason="stop")],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [content1, content2]
    mock_create.return_value = stream
    chat_history.append(ChatMessage(role="user", text="hello world"))
    orig_chat_history = deepcopy(chat_history)

    openai_chat_completion = OpenAIChatClient()
    async for msg in openai_chat_completion.get_streaming_response(
        messages=chat_history,
    ):
        assert isinstance(msg, ChatResponseUpdate)
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=True,
        stream_options={"include_usage": True},
        messages=openai_chat_completion._prepare_chat_history_for_request(orig_chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_get_streaming_singular(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    openai_unit_test_env: dict[str, str],
):
    content1 = ChatCompletionChunk(
        id="test_id",
        choices=[],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    content2 = ChatCompletionChunk(
        id="test_id",
        choices=[ChunkChoice(index=0, delta=ChunkChoiceDelta(content="test", role="assistant"), finish_reason="stop")],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [content1, content2]
    mock_create.return_value = stream
    chat_history.append(ChatMessage(role="user", text="hello world"))
    orig_chat_history = deepcopy(chat_history)

    openai_chat_completion = OpenAIChatClient()
    async for msg in openai_chat_completion.get_streaming_response(
        messages=chat_history,
    ):
        assert isinstance(msg, ChatResponseUpdate)
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=True,
        stream_options={"include_usage": True},
        messages=openai_chat_completion._prepare_chat_history_for_request(orig_chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_get_streaming_structured_output_no_fcc(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    openai_unit_test_env: dict[str, str],
):
    content1 = ChatCompletionChunk(
        id="test_id",
        choices=[],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    content2 = ChatCompletionChunk(
        id="test_id",
        choices=[ChunkChoice(index=0, delta=ChunkChoiceDelta(content="test", role="assistant"), finish_reason="stop")],
        created=0,
        model="test",
        object="chat.completion.chunk",
    )
    stream = MagicMock(spec=AsyncStream)
    stream.__aiter__.return_value = [content1, content2]
    mock_create.return_value = stream
    chat_history.append(ChatMessage(role="user", text="hello world"))

    # Define a mock response format
    class Test(BaseModel):
        name: str

    openai_chat_completion = OpenAIChatClient()
    async for msg in openai_chat_completion.get_streaming_response(
        messages=chat_history,
        response_format=Test,
    ):
        assert isinstance(msg, ChatResponseUpdate)
    mock_create.assert_awaited_once()


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_get_streaming_no_fcc_in_response(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    mock_streaming_chat_completion_response: ChatCompletion,
    openai_unit_test_env: dict[str, str],
):
    mock_create.return_value = mock_streaming_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))
    orig_chat_history = deepcopy(chat_history)

    openai_chat_completion = OpenAIChatClient()
    [
        msg
        async for msg in openai_chat_completion.get_streaming_response(
            messages=chat_history,
        )
    ]
    mock_create.assert_awaited_once_with(
        model=openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        stream=True,
        stream_options={"include_usage": True},
        messages=openai_chat_completion._prepare_chat_history_for_request(orig_chat_history),  # type: ignore
    )


@patch.object(AsyncChatCompletions, "create", new_callable=AsyncMock)
async def test_get_streaming_no_stream(
    mock_create: AsyncMock,
    chat_history: list[ChatMessage],
    openai_unit_test_env: dict[str, str],
    mock_chat_completion_response: ChatCompletion,  # AsyncStream[ChatCompletionChunk]?
):
    mock_create.return_value = mock_chat_completion_response
    chat_history.append(ChatMessage(role="user", text="hello world"))

    openai_chat_completion = OpenAIChatClient()
    with pytest.raises(ServiceResponseException):
        [
            msg
            async for msg in openai_chat_completion.get_streaming_response(
                messages=chat_history,
            )
        ]


# region UTC Timestamp Tests


def test_chat_response_created_at_uses_utc(openai_unit_test_env: dict[str, str]):
    """Test that ChatResponse.created_at uses UTC timestamp, not local time.

    This is a regression test for the issue where created_at was using local time
    but labeling it as UTC (with 'Z' suffix).
    """
    from agent_framework import ChatOptions

    # Use a specific Unix timestamp: 1733011890 = 2024-12-01T00:31:30Z (UTC)
    # This ensures we test that the timestamp is actually converted to UTC
    utc_timestamp = 1733011890

    mock_response = ChatCompletion(
        id="test_id",
        choices=[
            Choice(index=0, message=ChatCompletionMessage(content="test", role="assistant"), finish_reason="stop")
        ],
        created=utc_timestamp,
        model="test",
        object="chat.completion",
    )

    client = OpenAIChatClient()
    response = client._create_chat_response(mock_response, ChatOptions())

    # Verify that created_at is correctly formatted as UTC
    assert response.created_at is not None
    assert response.created_at.endswith("Z"), "Timestamp should end with 'Z' for UTC"

    # Parse the timestamp and verify it matches UTC time
    expected_utc_time = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    expected_formatted = expected_utc_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert response.created_at == expected_formatted, (
        f"Expected UTC timestamp {expected_formatted}, got {response.created_at}"
    )


def test_chat_response_update_created_at_uses_utc(openai_unit_test_env: dict[str, str]):
    """Test that ChatResponseUpdate.created_at uses UTC timestamp, not local time.

    This is a regression test for the issue where created_at was using local time
    but labeling it as UTC (with 'Z' suffix).
    """
    # Use a specific Unix timestamp: 1733011890 = 2024-12-01T00:31:30Z (UTC)
    utc_timestamp = 1733011890

    mock_chunk = ChatCompletionChunk(
        id="test_id",
        choices=[ChunkChoice(index=0, delta=ChunkChoiceDelta(content="test", role="assistant"), finish_reason="stop")],
        created=utc_timestamp,
        model="test",
        object="chat.completion.chunk",
    )

    client = OpenAIChatClient()
    response_update = client._create_chat_response_update(mock_chunk)

    # Verify that created_at is correctly formatted as UTC
    assert response_update.created_at is not None
    assert response_update.created_at.endswith("Z"), "Timestamp should end with 'Z' for UTC"

    # Parse the timestamp and verify it matches UTC time
    expected_utc_time = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    expected_formatted = expected_utc_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    assert response_update.created_at == expected_formatted, (
        f"Expected UTC timestamp {expected_formatted}, got {response_update.created_at}"
    )
