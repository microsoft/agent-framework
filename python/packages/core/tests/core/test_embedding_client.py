# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence

from agent_framework import (
    BaseEmbeddingClient,
    Embedding,
    EmbeddingGenerationOptions,
    GeneratedEmbeddings,
    SupportsGetEmbeddings,
)


class MockEmbeddingClient(BaseEmbeddingClient):
    """A simple mock embedding client for testing."""

    async def get_embeddings(
        self,
        values: Sequence[str],
        *,
        options: EmbeddingGenerationOptions | None = None,
    ) -> GeneratedEmbeddings[list[float]]:
        return GeneratedEmbeddings(
            [Embedding(vector=[0.1, 0.2, 0.3], model_id="mock-model") for _ in values],
            usage={"prompt_tokens": len(values), "total_tokens": len(values)},
        )


# --- BaseEmbeddingClient tests ---


async def test_base_get_embeddings() -> None:
    client = MockEmbeddingClient()
    result = await client.get_embeddings(["hello", "world"])
    assert len(result) == 2
    assert result[0].vector == [0.1, 0.2, 0.3]
    assert result[0].model_id == "mock-model"


async def test_base_get_embeddings_with_options() -> None:
    client = MockEmbeddingClient()
    options: EmbeddingGenerationOptions = {"model_id": "test", "dimensions": 3}
    result = await client.get_embeddings(["hello"], options=options)
    assert len(result) == 1


async def test_base_get_embeddings_usage() -> None:
    client = MockEmbeddingClient()
    result = await client.get_embeddings(["a", "b", "c"])
    assert result.usage is not None
    assert result.usage["prompt_tokens"] == 3


def test_base_additional_properties_default() -> None:
    client = MockEmbeddingClient()
    assert client.additional_properties == {}


def test_base_additional_properties_custom() -> None:
    client = MockEmbeddingClient(additional_properties={"key": "value"})
    assert client.additional_properties == {"key": "value"}


# --- SupportsGetEmbeddings protocol tests ---


def test_mock_client_satisfies_protocol() -> None:
    client = MockEmbeddingClient()
    assert isinstance(client, SupportsGetEmbeddings)


def test_plain_class_satisfies_protocol() -> None:
    """A plain class with the right signature should satisfy the protocol."""

    class PlainEmbeddingClient:
        additional_properties: dict = {}

        async def get_embeddings(self, values, *, options=None):
            return GeneratedEmbeddings()

    client = PlainEmbeddingClient()
    assert isinstance(client, SupportsGetEmbeddings)


def test_wrong_class_does_not_satisfy_protocol() -> None:
    """A class without get_embeddings should not satisfy the protocol."""

    class NotAnEmbeddingClient:
        additional_properties: dict = {}

        async def generate(self, values):
            pass

    client = NotAnEmbeddingClient()
    assert not isinstance(client, SupportsGetEmbeddings)
