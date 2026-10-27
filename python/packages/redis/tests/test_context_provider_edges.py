# Copyright (c) Microsoft. All rights reserved.

"""Additional edge-case coverage for ``RedisContextProvider``."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentResponse, AgentSession, Message, SessionContext
from agent_framework.exceptions import IntegrationInvalidRequestException
from redisvl.redis.utils import buffer_to_array
from redisvl.utils.vectorize import BaseVectorizer

from agent_framework_redis._context_provider import (
    _SCOPE_FIELDS,
    _SCOPE_TAG_SEPARATOR,
    RedisContextProvider,
    _scope_token,
    _scope_token_field,
)


@pytest.fixture
def mock_index() -> AsyncMock:
    index = AsyncMock()
    client = MagicMock()
    index.client = client
    index.create = AsyncMock()
    index.exists = AsyncMock(return_value=False)
    index.load = AsyncMock()
    index.query = AsyncMock(return_value=[])
    return index


@pytest.fixture
def patch_index(mock_index: AsyncMock) -> Generator[MagicMock]:
    with patch("agent_framework_redis._context_provider.AsyncSearchIndex") as mock_cls:
        mock_cls.from_dict = MagicMock(return_value=mock_index)

        async def mock_from_existing(*args: Any, **kwargs: Any) -> AsyncMock:  # noqa: ARG001
            existing = AsyncMock()
            existing.schema.to_dict = MagicMock(
                side_effect=lambda: mock_cls.from_dict.call_args.args[0] if mock_cls.from_dict.call_args else {}
            )
            return existing

        mock_cls.from_existing = AsyncMock(side_effect=mock_from_existing)
        yield mock_cls


def test_build_filter_from_dict_combines_multiple_tags(
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user|1")
    combined = provider._build_filter_from_dict({
        "application_id": "App,1",
        "agent_id": None,
        "user_id": "user|1",
    })

    assert combined is not None
    assert str(combined) == (
        f"(@{_scope_token_field('application_id')}:{{{_scope_token('application_id', 'App,1')}}} "
        f"@{_scope_token_field('user_id')}:{{{_scope_token('user_id', 'user|1')}}})"
    )
    assert "App,1" not in str(combined)
    assert "user|1" not in str(combined)


def test_scope_tokens_preserve_identity_and_field_domain() -> None:
    assert _scope_token("user_id", "Alice") != _scope_token("user_id", "alice")
    assert _scope_token("user_id", "same") != _scope_token("agent_id", "same")
    assert set(_scope_token("user_id", r"a,b|c\ d{}*")) <= set("0123456789abcdef")


def test_scope_token_field_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="Unsupported Redis context scope field"):
        _scope_token_field("content")


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


def test_schema_uses_versioned_identity_preserving_scope_tags(
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    provider = RedisContextProvider(source_id="ctx", user_id="user-1")
    fields = {field["name"]: field for field in provider.schema_dict["fields"]}

    for name in _SCOPE_FIELDS:
        assert name not in fields
        assert fields[_scope_token_field(name)] == {
            "name": _scope_token_field(name),
            "type": "tag",
            "attrs": {"case_sensitive": True, "separator": _SCOPE_TAG_SEPARATOR},
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

    assert validate_schema.await_count == 2
    mock_index.create.assert_awaited_once_with(overwrite=False, drop=False)
    assert provider._index_initialized is True


async def test_ensure_index_validates_before_overwriting_compatible_index(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    mock_index.exists.return_value = True
    provider = RedisContextProvider(source_id="ctx", user_id="user-1", overwrite_index=True)

    with patch.object(provider, "_validate_schema_compatibility", AsyncMock()) as validate_schema:
        await provider._ensure_index()

    assert validate_schema.await_count == 2
    mock_index.create.assert_awaited_once_with(overwrite=True, drop=False)
    assert provider._index_initialized is True


async def test_ensure_index_validates_schema_created_by_concurrent_initializer(
    mock_index: AsyncMock,
    patch_index: MagicMock,  # noqa: ARG001
) -> None:
    mock_index.exists.return_value = False
    provider = RedisContextProvider(source_id="ctx", user_id="user-1", overwrite_index=True)

    with (
        patch.object(
            provider,
            "_validate_schema_compatibility",
            AsyncMock(side_effect=ValueError("incompatible concurrent schema")),
        ) as validate_schema,
        pytest.raises(ValueError, match="incompatible concurrent schema"),
    ):
        await provider._ensure_index()

    mock_index.create.assert_awaited_once_with(overwrite=False, drop=False)
    validate_schema.assert_awaited_once()
    assert provider._index_initialized is False


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

    with pytest.raises(ValueError, match="Delete the existing index and its context hashes"):
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
                {
                    "content": "first",
                    "application_id": "caller-app",
                    "agent_id": "caller-agent",
                    "user_id": "caller-user",
                    "thread_id": "caller-thread",
                    "conversation_id": "caller-conversation",
                    _scope_token_field("user_id"): "caller-token",
                },
                {"content": "second"},
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
    for name, value in {
        "application_id": "app-1",
        "agent_id": "agent-1",
        "user_id": "user-1",
        "thread_id": "session-1",
        "conversation_id": "session-1",
    }.items():
        assert loaded_docs[0][_scope_token_field(name)] == _scope_token(name, value)
    assert isinstance(loaded_docs[0]["embedding"], bytes)
    assert isinstance(loaded_docs[1]["embedding"], bytes)
    vectorizer.aembed_many.assert_awaited_once_with(["first", "second"], batch_size=2)


@pytest.mark.parametrize("dtype, expected_size", [("float16", 4), ("float32", 8), ("float64", 16), ("bfloat16", 4)])
async def test_after_run_stores_vectors_in_configured_dtype(
    dtype: str,
    expected_size: int,
    mock_index: AsyncMock,
) -> None:
    vectorizer = MagicMock(spec=BaseVectorizer)
    vectorizer.dims = 2
    vectorizer.dtype = dtype
    embeddings = [[1.5, -2.25], [3.125, 4.5]]
    vectorizer.aembed_many = AsyncMock(return_value=embeddings)
    provider = RedisContextProvider(
        user_id="user-1",
        redis_vectorizer=vectorizer,
        vector_field_name="embedding",
        redis_index=mock_index,
    )
    object.__setattr__(provider, "_validate_schema_compatibility", AsyncMock())
    session = AgentSession(session_id="session-1")
    context = SessionContext(
        session_id=session.session_id,
        input_messages=[Message(role="user", contents=["I prefer tea"])],
    )
    context._response = AgentResponse(messages=[Message(role="assistant", contents=["I'll remember that"])])

    await provider.after_run(agent=MagicMock(), session=session, context=context, state={})

    vector_field = next(field for field in provider.schema_dict["fields"] if field["name"] == "embedding")
    assert vector_field["attrs"]["datatype"] == dtype
    mock_index.load.assert_awaited_once()
    loaded_docs = mock_index.load.await_args.args[0]
    assert [doc["content"] for doc in loaded_docs] == ["I prefer tea", "I'll remember that"]
    for doc, expected_embedding in zip(loaded_docs, embeddings, strict=True):
        assert len(doc["embedding"]) == expected_size
        assert buffer_to_array(doc["embedding"], dtype) == expected_embedding
    vectorizer.aembed_many.assert_awaited_once_with(["I prefer tea", "I'll remember that"], batch_size=2)


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
    captured_query: list[Any] = []

    def paginate(*args: Any, **kwargs: Any) -> AsyncIterator[list[dict[str, str]]]:  # noqa: ARG001
        captured_query.append(args[0])

        async def batches() -> AsyncIterator[list[dict[str, str]]]:
            yield [{"content": "first"}]
            yield [{"content": "second"}, {"content": "third"}]

        return batches()

    mock_index.paginate = MagicMock(side_effect=paginate)

    results = await provider.search_all(page_size=2)

    assert results == [
        {"content": "first"},
        {"content": "second"},
        {"content": "third"},
    ]
    assert _scope_token_field("user_id") in str(captured_query[0]._filter_expression)
    assert "user-1" not in str(captured_query[0]._filter_expression)
