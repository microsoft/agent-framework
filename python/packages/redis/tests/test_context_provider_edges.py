# Copyright (c) Microsoft. All rights reserved.

"""Additional edge-case coverage for ``RedisContextProvider``."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework.exceptions import IntegrationInvalidRequestException
from redisvl.utils.vectorize import BaseVectorizer

from agent_framework_redis._context_provider import RedisContextProvider


@pytest.fixture
def mock_index() -> AsyncMock:
    index = AsyncMock()
    index.create = AsyncMock()
    index.exists = AsyncMock(return_value=False)
    index.load = AsyncMock()
    index.query = AsyncMock(return_value=[])
    return index


@pytest.fixture
def patch_index(mock_index: AsyncMock) -> Generator[MagicMock]:
    with patch("agent_framework_redis._context_provider.AsyncSearchIndex") as mock_cls:
        mock_cls.from_dict = MagicMock(return_value=mock_index)
        mock_cls.from_existing = AsyncMock()
        yield mock_cls


def test_build_filter_from_dict_combines_multiple_tags(
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")
    combined = provider._build_filter_from_dict({
        "application_id": "app-1",
        "agent_id": None,
        "user_id": "user-1",
    })

    assert combined is not None
    assert str(combined) == "(@application_id:{app\\-1} @user_id:{user\\-1})"


def test_schema_dict_includes_vector_configuration(
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    vectorizer = MagicMock(spec=BaseVectorizer)
    vectorizer.dims = 3
    vectorizer.dtype = "float16"

    provider = RedisContextProvider(
        source_id="ctx",
        user_id="user-1",
        redis_vectorizer=vectorizer,
        vector_field_name="embedding",
        vector_algorithm="flat",
        vector_distance_metric="l2",
    )

    vector_field = next(field for field in provider.schema_dict["fields"] if field["name"] == "embedding")

    assert vector_field["type"] == "vector"
    assert vector_field["attrs"] == {
        "algorithm": "flat",
        "dims": 3,
        "distance_metric": "l2",
        "datatype": "float16",
    }


async def test_ensure_index_short_circuits_after_first_initialization(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")
    provider._index_initialized = True

    await provider._ensure_index()

    mock_index.exists.assert_not_called()
    mock_index.create.assert_not_called()


async def test_ensure_index_validates_existing_schema_before_create(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    mock_index.exists.return_value = True
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")

    with patch.object(provider, "_validate_schema_compatibility", AsyncMock()) as validate_schema:
        await provider._ensure_index()

    validate_schema.assert_awaited_once()
    mock_index.create.assert_awaited_once_with(overwrite=False, drop=False)
    assert provider._index_initialized is True


async def test_validate_schema_compatibility_raises_for_significant_mismatch(
    patch_index: MagicMock,
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")
    existing_index = AsyncMock()
    existing_index.schema.to_dict = MagicMock(
        return_value={
            "index": {"name": "context", "prefix": "other", "key_separator": ":", "storage_type": "hash"},
            "fields": [{"name": "content", "type": "text"}],
        }
    )
    patch_index.from_existing = AsyncMock(return_value=existing_index)

    with pytest.raises(ValueError, match="overwrite_index=True"):
        await provider._validate_schema_compatibility()


async def test_add_requires_content_field(
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")

    with (
        patch.object(provider, "_ensure_index", AsyncMock()),
        pytest.raises(IntegrationInvalidRequestException, match="requires a 'content' field"),
    ):
        await provider._add(data={"role": "user"}, session_id="session-1")


async def test_add_vectorizes_documents_and_applies_defaults(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    vectorizer = MagicMock(spec=BaseVectorizer)
    vectorizer.dims = 2
    vectorizer.dtype = "float32"
    vectorizer.aembed_many = AsyncMock(return_value=[[1.0, 2.0], [3.0, 4.0]])

    provider = RedisContextProvider(
        source_id="ctx",
        application_id="app-1",
        agent_id="agent-1",
        user_id="user-1",
        redis_vectorizer=vectorizer,
        vector_field_name="embedding",
    )

    with patch.object(provider, "_ensure_index", AsyncMock()):
        await provider._add(
            data=[
                {"content": "first"},
                {"content": "second", "conversation_id": "custom-conversation"},
            ],
            session_id="session-1",
        )

    loaded_docs = mock_index.load.await_args.args[0]
    assert [doc["content"] for doc in loaded_docs] == ["first", "second"]
    assert loaded_docs[0]["application_id"] == "app-1"
    assert loaded_docs[0]["agent_id"] == "agent-1"
    assert loaded_docs[0]["user_id"] == "user-1"
    assert loaded_docs[0]["thread_id"] == "session-1"
    assert loaded_docs[0]["conversation_id"] == "session-1"
    assert isinstance(loaded_docs[0]["embedding"], bytes)
    assert isinstance(loaded_docs[1]["embedding"], bytes)
    vectorizer.aembed_many.assert_awaited_once_with(["first", "second"], batch_size=2)


async def test_redis_search_requires_non_empty_text(
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")

    with (
        patch.object(provider, "_ensure_index", AsyncMock()),
        pytest.raises(IntegrationInvalidRequestException, match="non-empty text"),
    ):
        await provider._redis_search(text="   ")


async def test_redis_search_combines_explicit_filter_expression(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1", application_id="app-1")
    base_filter = MagicMock()
    merged_filter = object()
    base_filter.__and__.return_value = merged_filter
    explicit_filter = object()

    with (
        patch.object(provider, "_ensure_index", AsyncMock()),
        patch.object(provider, "_build_filter_from_dict", return_value=base_filter),
        patch("agent_framework_redis._context_provider.TextQuery") as text_query,
    ):
        text_query.return_value = MagicMock()
        await provider._redis_search(
            text="hello redis",
            session_id="session-1",
            filter_expression=explicit_filter,
            return_fields=["content"],
            num_results=3,
        )

    base_filter.__and__.assert_called_once_with(explicit_filter)
    assert text_query.call_args.kwargs["filter_expression"] is merged_filter
    assert text_query.call_args.kwargs["return_fields"] == ["content"]
    assert text_query.call_args.kwargs["num_results"] == 3
    mock_index.query.assert_awaited_once()


async def test_search_all_collects_paginated_batches(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")

    async def paginate(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, str]]]:  # noqa: ARG001
        yield [{"content": "first"}]
        yield [{"content": "second"}, {"content": "third"}]

    mock_index.paginate = MagicMock(return_value=paginate())

    results = await provider.search_all(page_size=2)

    assert results == [
        {"content": "first"},
        {"content": "second"},
        {"content": "third"},
    ]
