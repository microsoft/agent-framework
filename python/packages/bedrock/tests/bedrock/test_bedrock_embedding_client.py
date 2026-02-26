# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agent_framework import Embedding, GeneratedEmbeddings

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
        model_id="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,
    )
    assert client.model_id == "amazon.titan-embed-text-v2:0"
    assert client.region == "us-west-2"


async def test_bedrock_embedding_construction_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing model_id raises an error."""
    monkeypatch.delenv("BEDROCK_EMBEDDING_MODEL_ID", raising=False)
    from agent_framework.exceptions import SettingNotFoundError

    with pytest.raises(SettingNotFoundError):
        BedrockEmbeddingClient(region="us-west-2")


async def test_bedrock_embedding_get_embeddings() -> None:
    """Test generating embeddings via the Bedrock invoke_model API."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model_id="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,
    )

    result = await client.get_embeddings(["hello", "world"])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 2
    assert len(result[0].vector) == 3
    assert len(result[1].vector) == 3
    assert result[0].model_id == "amazon.titan-embed-text-v2:0"
    assert result.usage == {"input_token_count": 10}

    # Two calls since Titan processes one input at a time
    assert len(stub.calls) == 2
    call_texts = {json.loads(call["body"])["inputText"] for call in stub.calls}
    assert call_texts == {"hello", "world"}


async def test_bedrock_embedding_get_embeddings_empty_input() -> None:
    """Test generating embeddings with empty input."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model_id="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,
    )

    result = await client.get_embeddings([])

    assert isinstance(result, GeneratedEmbeddings)
    assert len(result) == 0
    assert len(stub.calls) == 0


async def test_bedrock_embedding_get_embeddings_with_options() -> None:
    """Test generating embeddings with custom options."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model_id="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,
    )

    options: BedrockEmbeddingOptions = {
        "dimensions": 5,
        "normalize": True,
    }
    result = await client.get_embeddings(["hello"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 5

    body = json.loads(stub.calls[0]["body"])
    assert body["dimensions"] == 5
    assert body["normalize"] is True


async def test_bedrock_embedding_get_embeddings_no_model_raises() -> None:
    """Test that missing model_id at call time raises ValueError."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model_id="amazon.titan-embed-text-v2:0",
        region="us-west-2",
        client=stub,
    )
    client.model_id = None  # type: ignore[assignment]

    with pytest.raises(ValueError, match="model_id is required"):
        await client.get_embeddings(["hello"])


async def test_bedrock_embedding_default_region() -> None:
    """Test that default region is us-east-1."""
    stub = _StubBedrockEmbeddingRuntime()
    client = BedrockEmbeddingClient(
        model_id="amazon.titan-embed-text-v2:0",
        client=stub,
    )
    assert client.region == "us-east-1"


# region: Integration Tests

skip_if_bedrock_embedding_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("BEDROCK_EMBEDDING_MODEL_ID", "") in ("", "test-model")
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
