# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import os
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from agent_framework import Embedding, GeneratedEmbeddings
from boto3.session import Session as Boto3Session

from agent_framework_bedrock import BedrockEmbeddingClient, BedrockEmbeddingOptions


class _StubBedrockEmbeddingRuntime:
    """Stub for the Bedrock runtime client that handles invoke_model for embeddings."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.meta = MagicMock(endpoint_url="https://bedrock-runtime.us-west-2.amazonaws.com")

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        body = json.loads(kwargs.get("body", "{}"))
        # Simulate Titan embedding response
        dimensions = body.get("dimensions", 3)
        return {
            "body": MagicMock(
                read=lambda: json.dumps({
                    "embedding": [0.1 * (i + 1) for i in range(dimensions)],
                    "inputTextTokenCount": 5,
                }).encode()
            ),
        }


async def test_bedrock_embedding_construction() -> None:
    """Test construction with explicit parameters."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )
    assert client.model == "amazon.titan-embed-text-v2:0"
    assert client.region == "us-west-2"


async def test_bedrock_embedding_construction_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing model raises an error."""
    monkeypatch.delenv("BEDROCK_EMBEDDING_MODEL", raising=False)
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        BedrockEmbeddingClient(region="us-west-2")


async def test_bedrock_embedding_get_embeddings() -> None:
    """Test generating embeddings via the Bedrock invoke_model API."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )

    result = await client.get_embeddings(["hello", "world"])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 2
    assert len(result[0].vector) == 3
    assert len(result[1].vector) == 3
    assert result[0].model == "amazon.titan-embed-text-v2:0"
    assert result.usage == {"input_token_count": 10}

    # Two calls since Titan processes one input at a time
    assert len(stub.calls) == 2
    call_texts = {json.loads(call["body"])["inputText"] for call in stub.calls}
    assert call_texts == {"hello", "world"}


async def test_bedrock_embedding_get_embeddings_empty_input() -> None:
    """Test generating embeddings with empty input."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )

    result = await client.get_embeddings([])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 0
    assert len(stub.calls) == 0


async def test_bedrock_embedding_get_embeddings_with_options() -> None:
    """Test generating embeddings with custom options."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )

    options: BedrockEmbeddingOptions = {
        "dimensions": 5,
        "normalize": True,
    }
    result = await client.get_embeddings(["hello"], options=options)  # ty: ignore[invalid-argument-type]

    assert len(result) == 1
    assert len(result[0].vector) == 5

    body = json.loads(stub.calls[0]["body"])
    assert body["dimensions"] == 5
    assert body["normalize"] is True


async def test_bedrock_embedding_get_embeddings_no_model_raises() -> None:
    """Test that missing model at call time raises ValueError."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )
    client.model = None  # type: ignore[assignment] # ty: ignore[invalid-assignment]

    with pytest.raises(ValueError, match="model is required"):
        await client.get_embeddings(["hello"])


async def test_bedrock_embedding_default_region() -> None:
    """Test that default region is us-east-1."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        client=stub,  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
    )
    assert client.region == "us-east-1"


class _FakeSession:
    def __init__(self, region_name: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.region_name = region_name

    def client(self, service_name: str, *, region_name: str, config: Any) -> _StubBedrockEmbeddingRuntime:
        self.calls.append({"service_name": service_name, "region_name": region_name})
        return _StubBedrockEmbeddingRuntime()


@pytest.mark.parametrize(
    ("region", "env_region", "session_region", "expected_region"),
    [
        (None, None, "eu-west-1", "eu-west-1"),
        ("us-west-2", None, "eu-west-1", "us-west-2"),
        (None, "ap-south-1", "eu-west-1", "ap-south-1"),
        (None, None, None, "us-east-1"),
    ],
    ids=["session-region", "region-argument-wins", "env-region-wins", "default-region"],
)
async def test_bedrock_embedding_resolves_region_with_boto3_session(
    monkeypatch: pytest.MonkeyPatch,
    region: str | None,
    env_region: str | None,
    session_region: str | None,
    expected_region: str,
) -> None:
    """A configured region wins, then the provided session's region, then the default region."""
    if env_region:
        monkeypatch.setenv("BEDROCK_REGION", env_region)
    else:
        monkeypatch.delenv("BEDROCK_REGION", raising=False)
    session = _FakeSession(region_name=session_region)

    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0", region=region, boto3_session=cast(Boto3Session, session)
    )

    assert session.calls == [{"service_name": "bedrock-runtime", "region_name": expected_region}]
    assert client.region == expected_region


async def test_bedrock_embedding_reports_boto3_default_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a region or session, the region boto3 resolves is used and reported."""
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")

    client = BedrockEmbeddingClient(model="amazon.titan-embed-text-v2:0")

    assert client.service_url() == "https://bedrock-runtime.eu-central-1.amazonaws.com"
    assert client.region == "eu-central-1"


async def test_bedrock_embedding_ignores_boto3_session_when_runtime_client_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preconfigured runtime client wins, so the unused session should not change the reported region."""
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    session = _FakeSession(region_name="eu-west-1")

    client = BedrockEmbeddingClient(
        model="amazon.titan-embed-text-v2:0",
        client=_StubBedrockEmbeddingRuntime(),  # pyrefly: ignore[bad-argument-type] # ty: ignore[invalid-argument-type] # pyright: ignore[reportArgumentType]
        boto3_session=cast(Boto3Session, session),
    )

    assert session.calls == []
    assert client.region == "us-east-1"


# region: Integration Tests

skip_if_bedrock_embedding_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("BEDROCK_EMBEDDING_MODEL", "") in ("", "test-model")
    or not (os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("BEDROCK_ACCESS_KEY")),
    reason="No real Bedrock embedding model or AWS credentials provided; skipping integration tests.",
)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_bedrock_embedding_integration_tests_disabled
async def test_bedrock_embedding_integration() -> None:
    """Integration test for Bedrock embedding client."""
    client = BedrockEmbeddingClient()
    result = await client.get_embeddings(["Hello, world!", "How are you?"])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 2
    for embedding in result:
        assert isinstance(embedding, Embedding)
        assert isinstance(embedding.vector, list)
        assert len(embedding.vector) > 0
        assert all(isinstance(v, float) for v in embedding.vector)
