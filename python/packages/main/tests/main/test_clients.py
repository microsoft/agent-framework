# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from collections.abc import AsyncIterable, MutableSequence, Sequence
from typing import Any

from pydantic import Field
from pytest import fixture

from agent_framework import (
    BaseChatClient,
    ChatClientProtocol,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    EmbeddingGenerator,
    FunctionCallContent,
    FunctionResultContent,
    GeneratedEmbeddings,
    Role,
    TextContent,
    ai_function,
    use_tool_calling,
)

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore
else:
    from typing_extensions import override  # type: ignore[import]


class MockChatClient:
    """Simple implementation of a chat client."""

    async def get_response(
        self,
        messages: ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        # Implement the method

        return ChatResponse(messages=ChatMessage(role="assistant", text="test response"))

    async def get_streaming_response(
        self,
        messages: ChatMessage | Sequence[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # Implement the method
        yield ChatResponseUpdate(text=TextContent(text="test streaming response"), role="assistant")
        yield ChatResponseUpdate(contents=[TextContent(text="another update")], role="assistant")


@use_tool_calling
class MockBaseChatClient(BaseChatClient):
    """Mock implementation of the BaseChatClient."""

    run_responses: list[ChatResponse] = Field(default_factory=list)
    streaming_responses: list[list[ChatResponseUpdate]] = Field(default_factory=list)

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat request to the AI service.

        Args:
            messages: The chat messages to send.
            chat_options: The options for the request.
            kwargs: Any additional keyword arguments.

        Returns:
            The chat response contents representing the response(s).
        """
        if not self.run_responses or chat_options.tool_choice == "none":
            return ChatResponse(messages=ChatMessage(role="assistant", text=f"test response - {messages[0].text}"))
        return self.run_responses.pop(0)

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        if not self.streaming_responses or chat_options.tool_choice == "none":
            yield ChatResponseUpdate(text=f"update - {messages[0].text}", role="assistant")
            return
        response = self.streaming_responses.pop(0)
        for update in response:
            yield update
        await asyncio.sleep(0)


class MockEmbeddingGenerator:
    """Simple implementation of an embedding generator."""

    async def generate(
        self,
        input_data: Sequence[str],
        **kwargs: Any,
    ) -> GeneratedEmbeddings[list[float]]:
        # Implement the method
        embeddings = GeneratedEmbeddings[list[float]]()
        for i, _ in enumerate(input_data):
            embeddings.append([0.0 * 1, 0.1 * 1, 0.2 * 1, 0.3 * i, 0.4 * i])
        return embeddings


@fixture
def chat_client() -> MockChatClient:
    return MockChatClient()


@fixture
def chat_client_base() -> MockBaseChatClient:
    return MockBaseChatClient()


@fixture
def embedding_generator() -> MockEmbeddingGenerator:
    gen: EmbeddingGenerator[str, list[float]] = MockEmbeddingGenerator()
    return gen


def test_chat_client_type(chat_client: MockChatClient):
    assert isinstance(chat_client, ChatClientProtocol)


async def test_chat_client_get_response(chat_client: MockChatClient):
    response = await chat_client.get_response(ChatMessage(role="user", text="Hello"))
    assert response.text == "test response"
    assert response.messages[0].role == Role.ASSISTANT


async def test_chat_client_get_streaming_response(chat_client: MockChatClient):
    async for update in chat_client.get_streaming_response(ChatMessage(role="user", text="Hello")):
        assert update.text == "test streaming response" or update.text == "another update"
        assert update.role == Role.ASSISTANT


def test_embedding_generator_type(embedding_generator: MockEmbeddingGenerator):
    assert isinstance(embedding_generator, EmbeddingGenerator)


async def test_embedding_generator_generate(embedding_generator: MockEmbeddingGenerator):
    input_data = ["Hello", "world"]
    embeddings = await embedding_generator.generate(input_data)
    assert len(embeddings) == len(input_data)
    for emb in embeddings:
        assert len(emb) == 5


def test_base_client(chat_client_base: MockBaseChatClient):
    assert isinstance(chat_client_base, BaseChatClient)
    assert isinstance(chat_client_base, ChatClientProtocol)


async def test_base_client_get_response(chat_client_base: MockBaseChatClient):
    response = await chat_client_base.get_response(ChatMessage(role="user", text="Hello"))
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "test response - Hello"


async def test_base_client_get_streaming_response(chat_client_base: MockBaseChatClient):
    async for update in chat_client_base.get_streaming_response(ChatMessage(role="user", text="Hello")):
        assert update.text == "update - Hello" or update.text == "another update"


async def test_base_client_with_function_calling(chat_client_base: MockBaseChatClient):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])
    assert exec_counter == 1
    assert len(response.messages) == 3
    assert response.messages[0].role == Role.ASSISTANT
    assert isinstance(response.messages[0].contents[0], FunctionCallContent)
    assert response.messages[0].contents[0].name == "test_function"
    assert response.messages[0].contents[0].arguments == '{"arg1": "value1"}'
    assert response.messages[0].contents[0].call_id == "1"
    assert response.messages[1].role == Role.TOOL
    assert isinstance(response.messages[1].contents[0], FunctionResultContent)
    assert response.messages[1].contents[0].call_id == "1"
    assert response.messages[1].contents[0].result == "Processed value1"
    assert response.messages[2].role == Role.ASSISTANT
    assert response.messages[2].text == "done"


async def test_base_client_with_function_calling_disabled(chat_client_base: MockBaseChatClient):
    chat_client_base.__maximum_iterations_per_request = 0
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1": "value1"}')],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]
    response = await chat_client_base.get_response("hello", tool_choice="auto", tools=[ai_func])
    assert exec_counter == 0
    assert len(response.messages) == 1
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "test response - hello"


async def test_base_client_with_streaming_function_calling(chat_client_base: MockBaseChatClient):
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1":')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='"value1"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[TextContent(text="Processed value1")],
                role="assistant",
            )
        ],
    ]
    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[ai_func]):
        updates.append(update)
    assert len(updates) == 4  # two updates with the function call, the function result and the final text
    assert updates[0].contents[0].call_id == "1"
    assert updates[1].contents[0].call_id == "1"
    assert updates[2].contents[0].call_id == "1"
    assert updates[3].text == "Processed value1"
    assert exec_counter == 1


async def test_base_client_with_streaming_function_calling_disabled(chat_client_base: MockBaseChatClient):
    chat_client_base.__maximum_iterations_per_request = 0
    exec_counter = 0

    @ai_function(name="test_function")
    def ai_func(arg1: str) -> str:
        nonlocal exec_counter
        exec_counter += 1
        return f"Processed {arg1}"

    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='{"arg1":')],
                role="assistant",
            ),
            ChatResponseUpdate(
                contents=[FunctionCallContent(call_id="1", name="test_function", arguments='"value1"}')],
                role="assistant",
            ),
        ],
        [
            ChatResponseUpdate(
                contents=[TextContent(text="Processed value1")],
                role="assistant",
            )
        ],
    ]
    updates = []
    async for update in chat_client_base.get_streaming_response("hello", tool_choice="auto", tools=[ai_func]):
        updates.append(update)
    assert len(updates) == 1
    assert exec_counter == 0
