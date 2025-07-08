# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Sequence
from typing import Any

from pytest import fixture

from agent_framework import (
    ChatClient,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    EmbeddingGenerator,
    GeneratedEmbeddings,
    TextContent,
)


class ImplementedChatClient:
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


class ImplementedEmbeddingGenerator:
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
def chat_client() -> ImplementedChatClient:
    return ImplementedChatClient()


@fixture
def embedding_generator() -> ImplementedEmbeddingGenerator:
    gen: EmbeddingGenerator[str, list[float]] = ImplementedEmbeddingGenerator()
    return gen


def test_chat_client_type(chat_client: ImplementedChatClient):
    assert isinstance(chat_client, ChatClient)


async def test_chat_client_get_response(chat_client: ImplementedChatClient):
    response = await chat_client.get_response(ChatMessage(role="user", text="Hello"))
    assert response.text == "test response"
    assert response.messages[0].role == ChatRole.ASSISTANT


async def test_chat_client_get_streaming_response(chat_client: ImplementedChatClient):
    async for update in chat_client.get_streaming_response(ChatMessage(role="user", text="Hello")):
        assert update.text == "test streaming response" or update.text == "another update"
        assert update.role == ChatRole.ASSISTANT


def test_embedding_generator_type(embedding_generator: ImplementedEmbeddingGenerator):
    assert isinstance(embedding_generator, EmbeddingGenerator)


async def test_embedding_generator_generate(embedding_generator: ImplementedEmbeddingGenerator):
    input_data = ["Hello", "world"]
    embeddings = await embedding_generator.generate(input_data)
    assert len(embeddings) == len(input_data)
    for emb in embeddings:
        assert len(emb) == 5
