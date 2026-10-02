# Copyright (c) Microsoft. All rights reserved.

import json
import math
import os
from dataclasses import dataclass
from typing import Annotated, Any, cast

import httpx2
import pytest
from agent_framework import InMemoryCollection, VectorStoreField, create_vector_search_tool, vectorstoremodel
from agent_framework._settings import SecretString
from openai import AsyncOpenAI

from agent_framework_nvidia import NvidiaEmbeddingClient, RawNvidiaEmbeddingClient
from agent_framework_nvidia._embedding_client import (  # pyright: ignore[reportPrivateUsage]
    DEFAULT_BASE_URL,
    MAX_BATCH_BYTES,
    MAX_BATCH_SIZE,
    _batches,  # pyright: ignore[reportPrivateUsage]
)
from agent_framework_nvidia._feature_usage import FeatureIndex  # pyright: ignore[reportPrivateUsage]

# region: helpers


@pytest.fixture(autouse=True)
def _clear_nvidia_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's real NVIDIA settings out of the unit tests.

    Without this a populated environment can make a construction test pass for the wrong
    reason, and can make the missing-setting tests fail only on other people's machines.
    Integration tests keep the environment, since it holds their credentials.
    """
    if request.node.get_closest_marker("integration"):
        return
    for name in ("NVIDIA_API_KEY", "NVIDIA_EMBEDDING_MODEL", "NVIDIA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def make_embeddings_payload(vectors: list[list[float]], model: str = "test-model") -> dict[str, Any]:
    return {
        "object": "list",
        "model": model,
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }


class MockNvidia:
    """Captures the requests the client actually puts on the wire."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.requests: list[httpx2.Request] = []
        self.bodies: list[dict[str, Any]] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        self.bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=self._payload)


def make_mock_client(model: str = "test-model") -> tuple[NvidiaEmbeddingClient, MockNvidia]:
    server = MockNvidia(make_embeddings_payload([[0.1, 0.2, 0.3]], model=model))
    async_client = AsyncOpenAI(
        api_key="test-key",
        base_url=DEFAULT_BASE_URL,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server.handler)),
    )
    return NvidiaEmbeddingClient(model=model, async_client=async_client), server


# region: construction and settings


def test_construction_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    client = NvidiaEmbeddingClient()

    assert client.model == "nvidia/nemotron-3-embed-1b"


def test_defaults_to_the_nvidia_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of the package: an NVIDIA key must not be sent to OpenAI.

    The client is built on the OpenAI client, whose own default base URL is OpenAI's, so
    this asserts the override rather than trusting it.
    """
    monkeypatch.setenv("NVIDIA_EMBEDDING_MODEL", "test-model")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    client = NvidiaEmbeddingClient()

    assert "integrate.api.nvidia.com" in str(client.client.base_url)
    assert "api.openai.com" not in str(client.client.base_url)


def test_base_url_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Self-hosted NIM containers are reached by pointing base_url at them."""
    monkeypatch.setenv("NVIDIA_EMBEDDING_MODEL", "test-model")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "http://localhost:8000/v1")

    client = NvidiaEmbeddingClient()

    assert "localhost:8000" in str(client.client.base_url)


def test_explicit_arguments_win_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_EMBEDDING_MODEL", "from-env")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "http://from-env/v1")

    client = NvidiaEmbeddingClient(model="from-arg", base_url="http://from-arg/v1")

    assert client.model == "from-arg"
    assert "from-arg" in str(client.client.base_url)


@pytest.mark.parametrize("api_key", ["test-key", SecretString("test-key")], ids=["str", "secret"])
def test_api_key_accepts_str_or_secretstring(api_key: str | SecretString) -> None:
    client = NvidiaEmbeddingClient(model="test-model", api_key=api_key)

    assert client.model == "test-model"


def test_missing_model_raises() -> None:
    with pytest.raises(Exception, match="model"):
        NvidiaEmbeddingClient(api_key="test-key")


def test_missing_api_key_raises_and_names_the_setting() -> None:
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        NvidiaEmbeddingClient(model="test-model")


def test_injected_client_does_not_require_an_api_key() -> None:
    """A caller supplying their own client has already handled auth."""
    async_client = AsyncOpenAI(api_key="test-key", base_url="http://injected/v1")

    client = NvidiaEmbeddingClient(model="test-model", async_client=async_client)

    assert "injected" in str(client.client.base_url)


async def test_close_closes_a_client_it_created() -> None:
    client = NvidiaEmbeddingClient(model="test-model", api_key="test-key")

    await client.close()

    assert client.client.is_closed()


async def test_close_leaves_an_injected_client_open() -> None:
    async_client = AsyncOpenAI(api_key="test-key", base_url="http://injected/v1")
    client = NvidiaEmbeddingClient(model="test-model", async_client=async_client)

    await client.close()

    assert not async_client.is_closed()
    await async_client.close()


# region: wiring


def test_provider_identity() -> None:
    client = NvidiaEmbeddingClient(model="test-model", api_key="test-key")

    assert client.OTEL_PROVIDER_NAME == "nvidia"
    assert NvidiaEmbeddingClient._FEATURE_USAGE_INDEX == FeatureIndex.NVIDIA  # pyright: ignore[reportPrivateUsage]


def test_telemetry_layer_wraps_the_raw_client() -> None:
    """The layer order decides whether calls are traced, so pin it."""
    names = [c.__name__ for c in NvidiaEmbeddingClient.__mro__]

    assert names.index("EmbeddingTelemetryLayer") < names.index("RawNvidiaEmbeddingClient")
    assert names.index("RawNvidiaEmbeddingClient") < names.index("RawOpenAIEmbeddingClient")


async def test_raw_client_sends_nvidia_options_without_telemetry() -> None:
    server = MockNvidia(make_embeddings_payload([[0.1, 0.2, 0.3]]))
    async_client = AsyncOpenAI(
        api_key="test-key",
        base_url=DEFAULT_BASE_URL,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server.handler)),
    )
    client = RawNvidiaEmbeddingClient(model="test-model", async_client=async_client)

    await client.get_embeddings(["hello"], options={"input_type": "query"})

    assert "EmbeddingTelemetryLayer" not in [c.__name__ for c in type(client).__mro__]
    assert server.bodies[-1]["input_type"] == "query"


# region: requests


async def test_get_embeddings_returns_vectors() -> None:
    client, server = make_mock_client()

    result = await client.get_embeddings(["hello"])

    assert len(result) == 1
    assert result[0].vector == [0.1, 0.2, 0.3]
    assert server.bodies[-1]["input"] == ["hello"]


async def test_requests_go_to_the_nvidia_host() -> None:
    client, server = make_mock_client()

    await client.get_embeddings(["hello"])

    assert server.requests[-1].url.host == "integrate.api.nvidia.com"


# region: NVIDIA options


async def test_input_type_and_truncate_reach_the_wire() -> None:
    client, server = make_mock_client()

    await client.get_embeddings(["hello"], options={"input_type": "passage", "truncate": "END"})

    assert server.bodies[-1]["input_type"] == "passage"
    assert server.bodies[-1]["truncate"] == "END"


async def test_omitted_options_send_no_nvidia_fields() -> None:
    client, server = make_mock_client()

    await client.get_embeddings(["hello"])

    assert "input_type" not in server.bodies[-1]
    assert "truncate" not in server.bodies[-1]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"input_type": "document"}, "input_type"),
        ({"truncate": "end"}, "truncate"),
    ],
    ids=["input_type", "truncate"],
)
async def test_invalid_options_fail_before_the_request(options: dict[str, Any], message: str) -> None:
    client, server = make_mock_client()

    with pytest.raises(ValueError, match=message):
        await client.get_embeddings(["hello"], options=cast(Any, options))

    assert server.requests == []


@pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning")
async def test_vector_search_tool_routes_passage_and_query_to_nvidia() -> None:
    @vectorstoremodel(collection_name="nvidia-input-type-test")
    @dataclass
    class Note:
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[str | list[float] | None, VectorStoreField("vector", dimensions=3)] = None

    client, server = make_mock_client()
    collection: InMemoryCollection[str, Note] = InMemoryCollection(Note, embedding_generator=client)
    await collection.ensure_collection_exists()

    await collection.upsert([Note("one", "NIM hosts models")], embeddings_options={"input_type": "passage"})
    search_tool = create_vector_search_tool(collection, embeddings_options={"input_type": "query"}, top=1)
    await search_tool(query="What hosts models?")

    upsert_body, search_body = server.bodies
    assert (upsert_body["input_type"], upsert_body["dimensions"]) == ("passage", 3)
    assert (search_body["input_type"], search_body["dimensions"]) == ("query", 3)


# region: batching


class BatchingNvidia:
    """Returns one vector per input, numbered across requests, and can fail a chosen request."""

    def __init__(self, fail_request: int | None = None) -> None:
        self.batch_sizes: list[int] = []
        self.bodies: list[dict[str, Any]] = []
        self._fail_request = fail_request
        self._next = 0

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        self.batch_sizes.append(len(body["input"]))
        if len(self.batch_sizes) == self._fail_request:
            return httpx2.Response(
                400, json={"object": "error", "message": "rejected", "type": "invalid_request_error"}
            )
        vectors = [[float(self._next + i), 0.0, 0.0] for i in range(len(body["input"]))]
        self._next += len(vectors)
        payload = make_embeddings_payload(vectors)
        payload["usage"] = {"prompt_tokens": len(vectors), "total_tokens": len(vectors)}
        return httpx2.Response(200, json=payload)


def make_batching_client(server: BatchingNvidia) -> NvidiaEmbeddingClient:
    async_client = AsyncOpenAI(
        api_key="test-key",
        base_url=DEFAULT_BASE_URL,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server.handler)),
    )
    return NvidiaEmbeddingClient(model="test-model", async_client=async_client)


@pytest.mark.parametrize(
    ("count", "batch_sizes"),
    [(MAX_BATCH_SIZE, [MAX_BATCH_SIZE]), (MAX_BATCH_SIZE + 1, [MAX_BATCH_SIZE, 1])],
    ids=["at-limit", "over-limit"],
)
async def test_requests_stay_within_the_batch_limit(count: int, batch_sizes: list[int]) -> None:
    server = BatchingNvidia()
    client = make_batching_client(server)

    await client.get_embeddings([f"text {i}" for i in range(count)])

    assert server.batch_sizes == batch_sizes


async def test_batched_results_keep_order_usage_and_options() -> None:
    server = BatchingNvidia()
    client = make_batching_client(server)

    result = await client.get_embeddings([f"text {i}" for i in range(600)], options={"input_type": "passage"})

    assert server.batch_sizes == [256, 256, 88]
    assert [embedding.vector[0] for embedding in result] == [float(i) for i in range(600)]
    assert result.usage == {"input_token_count": 600, "total_token_count": 600}
    assert all(body["input_type"] == "passage" for body in server.bodies)


async def test_empty_input_sends_no_request() -> None:
    server = BatchingNvidia()
    client = make_batching_client(server)

    result = await client.get_embeddings([])

    assert list(result) == []
    assert server.batch_sizes == []


async def test_invalid_options_fail_before_any_batch_is_sent() -> None:
    server = BatchingNvidia()
    client = make_batching_client(server)

    with pytest.raises(ValueError, match="input_type"):
        await client.get_embeddings([f"text {i}" for i in range(600)], options=cast(Any, {"input_type": "document"}))

    assert server.batch_sizes == []


async def test_a_failed_batch_fails_the_whole_call() -> None:
    server = BatchingNvidia(fail_request=2)
    client = make_batching_client(server)

    with pytest.raises(Exception, match="rejected"):
        await client.get_embeddings([f"text {i}" for i in range(600)])

    assert server.batch_sizes == [256, 256]


@pytest.mark.parametrize(
    ("values", "batch_sizes"),
    [
        (["a" * 600_000] * 5, [3, 2]),
        (["a" * (MAX_BATCH_BYTES + 1), "b"], [1, 1]),
        (["é" * 400_000, "b"], [1, 1]),
        (["short"] * (MAX_BATCH_SIZE * 2), [MAX_BATCH_SIZE, MAX_BATCH_SIZE]),
    ],
    ids=["by-bytes", "oversized-alone", "non-ascii-costed-as-escaped", "by-count"],
)
def test_batches_respect_count_and_byte_limits(values: list[str], batch_sizes: list[int]) -> None:
    batches = list(_batches(values))

    assert [len(batch) for batch in batches] == batch_sizes
    assert [value for batch in batches for value in batch] == values


async def test_large_documents_are_split_by_request_size() -> None:
    server = BatchingNvidia()
    client = make_batching_client(server)

    result = await client.get_embeddings(["a" * 600_000] * 5)

    assert server.batch_sizes == [3, 2]
    assert len(result) == 5


@pytest.mark.filterwarnings("ignore::agent_framework._feature_stage.ExperimentalWarning")
async def test_upsert_larger_than_the_batch_limit() -> None:
    @vectorstoremodel(collection_name="nvidia-batch-test")
    @dataclass
    class Note:
        id: Annotated[str, VectorStoreField("key")]
        vector: Annotated[str | list[float] | None, VectorStoreField("vector", dimensions=3)] = None

    server = BatchingNvidia()
    client = make_batching_client(server)
    collection: InMemoryCollection[str, Note] = InMemoryCollection(Note, embedding_generator=client)
    await collection.ensure_collection_exists()

    await collection.upsert(
        [Note(str(i), f"note {i}") for i in range(300)], embeddings_options={"input_type": "passage"}
    )

    assert server.batch_sizes == [256, 44]
    stored = await collection.get(["0", "299"], include_vectors=True)
    assert [note.vector for note in stored] == [[0.0, 0.0, 0.0], [299.0, 0.0, 0.0]]


# region: integration


@pytest.mark.flaky
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("NVIDIA_API_KEY"), reason="Set NVIDIA_API_KEY to run.")
async def test_nvidia_embedding_integration() -> None:
    """The service embeds a passage and a query differently, which a mock cannot show.

    Repeated identical requests are not bit-for-bit equal, so compare cosine similarity:
    the same text measures about 1.0 under one input type and about 0.66 across the two.
    """
    client = NvidiaEmbeddingClient(model=os.getenv("NVIDIA_EMBEDDING_MODEL") or "nvidia/nemotron-3-embed-1b")
    try:
        passage = await client.get_embeddings(["What does NIM serve?"], options={"input_type": "passage"})
        query = await client.get_embeddings(["What does NIM serve?"], options={"input_type": "query"})
    finally:
        await client.close()

    a, b = passage[0].vector, query[0].vector
    similarity = sum(x * y for x, y in zip(a, b, strict=True)) / (math.hypot(*a) * math.hypot(*b))
    assert similarity < 0.99
