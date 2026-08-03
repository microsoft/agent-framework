# Copyright (c) Microsoft. All rights reserved.

import json
import os
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from agent_framework import Embedding, GeneratedEmbeddings
from agent_framework.exceptions import (
    IntegrationException,
    IntegrationInvalidAuthException,
    IntegrationInvalidRequestException,
    IntegrationInvalidResponseException,
)

from agent_framework_mistral import MistralEmbeddingClient, MistralEmbeddingOptions

# region: Unit Tests


def make_embeddings_payload(
    vectors: Sequence[Sequence[float]],
    model: str = "mistral-embed",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "object": "list",
        "model": model,
        "data": [{"object": "embedding", "index": i, "embedding": list(vector)} for i, vector in enumerate(vectors)],
        "usage": usage if usage is not None else {"prompt_tokens": 10, "total_tokens": 10},
    }


class MockMistral:
    def __init__(self, responses: Sequence[httpx.Response]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        return self._responses.pop(0)

    @property
    def last_request(self) -> dict[str, Any]:
        return self.requests[-1]


def make_client(*responses: httpx.Response) -> tuple[MistralEmbeddingClient, MockMistral]:
    server = MockMistral(responses)
    http_client = httpx.AsyncClient(
        base_url="https://api.mistral.ai",
        transport=httpx.MockTransport(server.handler),
    )
    client = MistralEmbeddingClient(model="mistral-embed", http_client=http_client)
    return client, server


def test_mistral_embedding_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test construction with environment variables."""
    monkeypatch.setenv("MISTRAL_EMBEDDING_MODEL", "mistral-embed")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    client = MistralEmbeddingClient()
    assert client.model == "mistral-embed"


def test_mistral_embedding_construction_with_params() -> None:
    """Test construction with explicit parameters."""
    client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
    assert client.model == "mistral-embed"
    assert client.client.headers["Authorization"] == "Bearer test-key"


def test_mistral_embedding_construction_with_server_url() -> None:
    """Test construction with custom server URL."""
    client = MistralEmbeddingClient(
        model="mistral-embed",
        api_key="test-key",
        server_url="https://custom.mistral.ai",
    )
    assert client.model == "mistral-embed"
    assert client.server_url == "https://custom.mistral.ai"
    assert str(client.client.base_url) == "https://custom.mistral.ai"


def test_mistral_embedding_construction_with_http_client() -> None:
    """Test construction with a pre-configured client."""
    http_client = httpx.AsyncClient(base_url="https://api.mistral.ai")
    client = MistralEmbeddingClient(model="mistral-embed", http_client=http_client)
    assert client.client is http_client


def test_mistral_embedding_deprecated_client_param_accepts_httpx() -> None:
    http_client = httpx.AsyncClient(base_url="https://api.mistral.ai")
    with pytest.deprecated_call():
        client = MistralEmbeddingClient(model="mistral-embed", client=http_client)
    assert client.client is http_client


class FakeMistralSDK:
    """Duck-typed stand-in for a mistralai.Mistral client."""

    def __init__(self, vectors: Sequence[Sequence[float]] = ((0.1, 0.2),)) -> None:
        self.requests: list[dict[str, Any]] = []
        self._vectors = vectors
        self.embeddings = SimpleNamespace(create_async=self._create_async)

    async def _create_async(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return SimpleNamespace(
            model="mistral-embed",
            data=[SimpleNamespace(index=i, embedding=list(v)) for i, v in enumerate(self._vectors)],
            usage=SimpleNamespace(prompt_tokens=3, total_tokens=3),
        )


async def test_mistral_embedding_deprecated_client_param_accepts_sdk_client() -> None:
    """An injected mistralai.Mistral keeps working through the legacy SDK path."""
    sdk = FakeMistralSDK()
    with pytest.deprecated_call():
        client = MistralEmbeddingClient(model="mistral-embed", client=sdk)

    result = await client.get_embeddings(["hello"], options=MistralEmbeddingOptions(dimensions=2))

    assert [e.vector for e in result] == [[0.1, 0.2]]
    assert result.usage == {"input_token_count": 3, "total_token_count": 3}
    assert sdk.requests == [{"model": "mistral-embed", "inputs": ["hello"], "output_dimension": 2}]


def test_mistral_embedding_deprecated_client_param_rejects_unknown_client() -> None:
    class NotAClient:
        pass

    with pytest.deprecated_call(), pytest.raises(TypeError, match="httpx.AsyncClient"):
        MistralEmbeddingClient(model="mistral-embed", client=NotAClient())


def test_mistral_embedding_client_and_http_client_conflict() -> None:
    http_client = httpx.AsyncClient(base_url="https://api.mistral.ai")
    with pytest.deprecated_call(), pytest.raises(ValueError, match="not both"):
        MistralEmbeddingClient(model="mistral-embed", http_client=http_client, client=http_client)


def test_mistral_embedding_construction_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing model raises an error."""
    monkeypatch.delenv("MISTRAL_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        MistralEmbeddingClient()


def test_mistral_embedding_construction_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing API key raises an error."""
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setenv("MISTRAL_EMBEDDING_MODEL", "mistral-embed")
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        MistralEmbeddingClient()


def test_mistral_embedding_service_url() -> None:
    """Test service_url returns the correct URL."""
    client = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
    assert client.service_url() == "https://api.mistral.ai"


def test_mistral_embedding_service_url_custom() -> None:
    """Test service_url returns custom URL when set."""
    client = MistralEmbeddingClient(
        model="mistral-embed",
        api_key="test-key",
        server_url="https://custom.mistral.ai",
    )
    assert client.service_url() == "https://custom.mistral.ai"


async def test_mistral_embedding_close_only_closes_owned_client() -> None:
    owned = MistralEmbeddingClient(model="mistral-embed", api_key="test-key")
    await owned.close()
    assert owned.client.is_closed

    http_client = httpx.AsyncClient(base_url="https://custom.mistral.ai")
    injected = MistralEmbeddingClient(model="mistral-embed", http_client=http_client)
    assert injected.service_url() == "https://custom.mistral.ai"

    await injected.close()

    assert not http_client.is_closed
    await http_client.aclose()


async def test_mistral_embedding_marks_feature_used(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    import agent_framework_mistral._embedding_client as embedding_client_module
    from agent_framework_mistral._feature_usage import FeatureIndex

    mark = MagicMock()
    monkeypatch.setattr(embedding_client_module, "mark_feature_used", mark)
    client, _ = make_client(httpx.Response(200, json=make_embeddings_payload([[0.1, 0.2]])))

    await client.get_embeddings(["hello"])

    mark.assert_called_once_with(FeatureIndex.MISTRAL)


async def test_mistral_embedding_get_embeddings() -> None:
    """Test generating embeddings via the Mistral API."""
    client, server = make_client(httpx.Response(200, json=make_embeddings_payload([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])))

    result = await client.get_embeddings(["hello", "world"])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 2
    assert result[0].vector == [0.1, 0.2, 0.3]
    assert result[1].vector == [0.4, 0.5, 0.6]
    assert result[0].model == "mistral-embed"
    assert result.usage == {"input_token_count": 10, "total_token_count": 10}
    assert server.last_request == {"model": "mistral-embed", "input": ["hello", "world"]}


async def test_mistral_embedding_get_embeddings_empty_input() -> None:
    """Test generating embeddings with empty input."""
    client, server = make_client()

    result = await client.get_embeddings([])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 0
    assert server.requests == []


async def test_mistral_embedding_get_embeddings_with_dimensions() -> None:
    """Test generating embeddings with custom dimensions option."""
    client, server = make_client(
        httpx.Response(200, json=make_embeddings_payload([[0.1, 0.2]], usage={"prompt_tokens": 5, "total_tokens": 5}))
    )

    options: MistralEmbeddingOptions = {"dimensions": 512}
    result = await client.get_embeddings(["hello"], options=options)

    assert len(result) == 1
    assert server.last_request == {"model": "mistral-embed", "input": ["hello"], "output_dimension": 512}


async def test_mistral_embedding_get_embeddings_no_model_raises() -> None:
    """Test that missing model at call time raises ValueError."""
    client, _ = make_client()
    client.model = None  # type: ignore[assignment] # ty: ignore[invalid-assignment]

    with pytest.raises(ValueError, match="model is required"):
        await client.get_embeddings(["hello"])


async def test_mistral_embedding_get_embeddings_model_override() -> None:
    """Test that model can be overridden via options."""
    client, server = make_client(
        httpx.Response(
            200,
            json=make_embeddings_payload(
                [[0.1, 0.2, 0.3]], model="custom-embed", usage={"prompt_tokens": 5, "total_tokens": 5}
            ),
        )
    )

    options: MistralEmbeddingOptions = {"model": "custom-embed"}
    result = await client.get_embeddings(["hello"], options=options)

    assert len(result) == 1
    assert result[0].model == "custom-embed"
    assert server.last_request == {"model": "custom-embed", "input": ["hello"]}


async def test_mistral_embedding_get_embeddings_no_usage() -> None:
    """Test handling response without usage information."""
    client, _ = make_client(httpx.Response(200, json=make_embeddings_payload([[0.1, 0.2, 0.3]], usage={})))

    result = await client.get_embeddings(["hello"])

    assert len(result) == 1
    assert result.usage is None


@pytest.mark.parametrize(
    ("status_code", "expected_exception"),
    [
        (401, IntegrationInvalidAuthException),
        (400, IntegrationInvalidRequestException),
        (500, IntegrationException),
    ],
)
async def test_mistral_embedding_http_error_wrapped(
    status_code: int,
    expected_exception: type[IntegrationException],
) -> None:
    """Test that HTTP errors surface with the appropriate integration exception."""
    client, _ = make_client(httpx.Response(status_code, json={"message": "request failed"}))

    with pytest.raises(expected_exception, match=f"status {status_code}"):
        await client.get_embeddings(["hello"])


async def test_mistral_embedding_network_error_wrapped() -> None:
    def raise_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    http_client = httpx.AsyncClient(
        base_url="https://api.mistral.ai",
        transport=httpx.MockTransport(raise_connect_error),
    )
    client = MistralEmbeddingClient(model="mistral-embed", http_client=http_client)

    with pytest.raises(IntegrationException, match="Mistral embeddings request failed"):
        await client.get_embeddings(["hello"])


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, content=b"{"), "response was invalid"),
        (httpx.Response(200, json=[]), "must be a JSON object"),
        (httpx.Response(200, json={"data": ["not-an-object"]}), "response was invalid"),
    ],
)
async def test_mistral_embedding_invalid_payload_wrapped(response: httpx.Response, message: str) -> None:
    client, _ = make_client(response)

    with pytest.raises(IntegrationInvalidResponseException, match=message):
        await client.get_embeddings(["hello"])


# region: Integration Tests

skip_if_mistral_embedding_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("MISTRAL_EMBEDDING_MODEL", "") in ("", "test-model") or os.getenv("MISTRAL_API_KEY", "") == "",
    reason="No real Mistral embedding model or API key provided; skipping integration tests.",
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_mistral_embedding_integration_tests_disabled
async def test_mistral_embedding_integration() -> None:
    """Integration test for Mistral AI embedding client."""
    client = MistralEmbeddingClient()
    try:
        result = await client.get_embeddings(["Hello, world!", "How are you?"])

        assert isinstance(result, GeneratedEmbeddings)
        assert len(result) == 2
        for embedding in result:
            assert isinstance(embedding, Embedding)
            assert isinstance(embedding.vector, list)
            assert len(embedding.vector) > 0
            assert all(isinstance(v, float) for v in embedding.vector)
        assert result.usage is not None
        assert result.usage["input_token_count"] is not None
        assert result.usage["input_token_count"] > 0
    finally:
        await client.close()
