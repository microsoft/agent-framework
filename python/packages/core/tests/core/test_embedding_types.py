# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from datetime import datetime

from agent_framework import Embedding, EmbeddingGenerationOptions, GeneratedEmbeddings

# --- Embedding tests ---


def test_embedding_basic_construction() -> None:
    embedding = Embedding(vector=[0.1, 0.2, 0.3])
    assert embedding.vector == [0.1, 0.2, 0.3]
    assert embedding.model_id is None
    assert embedding.created_at is None
    assert embedding.additional_properties == {}


def test_embedding_construction_with_metadata() -> None:
    now = datetime.now()
    embedding = Embedding(
        vector=[0.1, 0.2],
        model_id="text-embedding-3-small",
        created_at=now,
        additional_properties={"key": "value"},
    )
    assert embedding.model_id == "text-embedding-3-small"
    assert embedding.created_at == now
    assert embedding.additional_properties == {"key": "value"}


def test_embedding_dimensions_computed_from_list() -> None:
    embedding = Embedding(vector=[0.1, 0.2, 0.3])
    assert embedding.dimensions == 3


def test_embedding_dimensions_computed_from_tuple() -> None:
    embedding = Embedding(vector=(0.1, 0.2, 0.3, 0.4))
    assert embedding.dimensions == 4


def test_embedding_dimensions_computed_from_bytes() -> None:
    embedding = Embedding(vector=b"\x00\x01\x02")
    assert embedding.dimensions == 3


def test_embedding_dimensions_explicit_overrides_computed() -> None:
    embedding = Embedding(vector=[0.1, 0.2, 0.3], dimensions=1536)
    assert embedding.dimensions == 1536


def test_embedding_dimensions_none_for_unknown_type() -> None:
    embedding = Embedding(vector="not a list")  # type: ignore[arg-type]
    assert embedding.dimensions is None


def test_embedding_dimensions_explicit_with_unknown_type() -> None:
    embedding = Embedding(vector="not a list", dimensions=100)  # type: ignore[arg-type]
    assert embedding.dimensions == 100


def test_embedding_empty_vector() -> None:
    embedding = Embedding(vector=[])
    assert embedding.dimensions == 0


def test_embedding_int_vector() -> None:
    embedding = Embedding(vector=[1, 2, 3])
    assert embedding.vector == [1, 2, 3]
    assert embedding.dimensions == 3


# --- GeneratedEmbeddings tests ---


def test_generated_basic_construction() -> None:
    embeddings = GeneratedEmbeddings()
    assert len(embeddings) == 0
    assert embeddings.options is None
    assert embeddings.usage is None
    assert embeddings.additional_properties == {}


def test_generated_construction_with_embeddings() -> None:
    items = [Embedding(vector=[0.1, 0.2]), Embedding(vector=[0.3, 0.4])]
    embeddings = GeneratedEmbeddings(items)
    assert len(embeddings) == 2
    assert embeddings[0].vector == [0.1, 0.2]
    assert embeddings[1].vector == [0.3, 0.4]


def test_generated_construction_with_usage() -> None:
    usage = {"prompt_tokens": 10, "total_tokens": 10}
    embeddings = GeneratedEmbeddings(
        [
            Embedding(
                vector=[0.1],
                model_id="test-model",
            )
        ],
        usage=usage,
    )
    assert embeddings.usage == usage
    assert embeddings.usage["prompt_tokens"] == 10


def test_generated_construction_with_additional_properties() -> None:
    embeddings = GeneratedEmbeddings(
        additional_properties={"model": "test"},
    )
    assert embeddings.additional_properties == {"model": "test"}


def test_generated_construction_with_options() -> None:
    opts: EmbeddingGenerationOptions = {"model_id": "text-embedding-3-small", "dimensions": 256}
    embeddings = GeneratedEmbeddings(
        [Embedding(vector=[0.1])],
        options=opts,
    )
    assert embeddings.options is not None
    assert embeddings.options["model_id"] == "text-embedding-3-small"
    assert embeddings.options["dimensions"] == 256


def test_generated_list_behavior_iteration() -> None:
    items = [Embedding(vector=[float(i)]) for i in range(5)]
    embeddings = GeneratedEmbeddings(items)
    vectors = [e.vector for e in embeddings]
    assert vectors == [[0.0], [1.0], [2.0], [3.0], [4.0]]


def test_generated_list_behavior_indexing() -> None:
    items = [Embedding(vector=[0.1]), Embedding(vector=[0.2])]
    embeddings = GeneratedEmbeddings(items)
    assert embeddings[0].vector == [0.1]
    assert embeddings[-1].vector == [0.2]


def test_generated_list_behavior_slicing() -> None:
    items = [Embedding(vector=[float(i)]) for i in range(5)]
    embeddings = GeneratedEmbeddings(items)
    sliced = embeddings[1:3]
    assert len(sliced) == 2


def test_generated_list_behavior_append() -> None:
    embeddings = GeneratedEmbeddings()
    embeddings.append(Embedding(vector=[0.1]))
    assert len(embeddings) == 1


def test_generated_none_embeddings_creates_empty_list() -> None:
    embeddings = GeneratedEmbeddings(None)
    assert len(embeddings) == 0


# --- EmbeddingGenerationOptions tests ---


def test_options_empty() -> None:
    options: EmbeddingGenerationOptions = {}
    assert "model_id" not in options


def test_options_with_model_id() -> None:
    options: EmbeddingGenerationOptions = {"model_id": "text-embedding-3-small"}
    assert options["model_id"] == "text-embedding-3-small"


def test_options_with_dimensions() -> None:
    options: EmbeddingGenerationOptions = {"dimensions": 1536}
    assert options["dimensions"] == 1536


def test_options_with_all_fields() -> None:
    options: EmbeddingGenerationOptions = {
        "model_id": "text-embedding-3-small",
        "dimensions": 1536,
    }
    assert options["model_id"] == "text-embedding-3-small"
    assert options["dimensions"] == 1536
