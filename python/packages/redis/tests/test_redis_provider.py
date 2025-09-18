# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatMessage, Role
from agent_framework.exceptions import ServiceInitializationError


@pytest.fixture
def mock_index() -> AsyncMock:
    idx = AsyncMock()
    idx.create = AsyncMock()
    idx.load = AsyncMock()
    idx.query = AsyncMock()

    async def _paginate_generator(*_args: Any, **_kwargs: Any):
        # Default empty generator; override per-test as needed
        if False:  # pragma: no cover
            yield []
        return

    idx.paginate = _paginate_generator
    return idx


@pytest.fixture
def patch_index_from_dict(mock_index: AsyncMock):
    with patch("agent_framework_redis._provider.AsyncSearchIndex") as mock_cls:
        mock_cls.from_dict = MagicMock(return_value=mock_index)
        yield mock_cls


@pytest.fixture
def patch_queries():
    calls: dict[str, Any] = {"TextQuery": [], "HybridQuery": [], "FilterExpression": []}

    def _mk_query(kind: str):
        class _Q:  # simple marker object with captured kwargs
            def __init__(self, **kwargs):
                self.kind = kind
                self.kwargs = kwargs

        return _Q

    with (
        patch(
            "agent_framework_redis._provider.TextQuery",
            side_effect=lambda **k: calls["TextQuery"].append(k) or _mk_query("text")(**k),
        ) as text_q,
        patch(
            "agent_framework_redis._provider.HybridQuery",
            side_effect=lambda **k: calls["HybridQuery"].append(k) or _mk_query("hybrid")(**k),
        ) as hybrid_q,
        patch(
            "agent_framework_redis._provider.FilterExpression",
            side_effect=lambda s: calls["FilterExpression"].append(s) or ("FE", s),
        ) as filt,
    ):
        yield {"calls": calls, "TextQuery": text_q, "HybridQuery": hybrid_q, "FilterExpression": filt}


class TestRedisProviderInitialization:
    def test_import(self):
        from agent_framework_redis._provider import RedisProvider

        assert RedisProvider is not None

    def test_init_without_filters_ok(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider()
        assert provider.user_id is None
        assert provider.agent_id is None
        assert provider.application_id is None
        assert provider.thread_id is None

    def test_schema_without_vector_field(self, patch_index_from_dict):
        from agent_framework_redis._provider import RedisProvider

        RedisProvider(user_id="u1")
        # Inspect schema passed to from_dict
        args, kwargs = patch_index_from_dict.from_dict.call_args
        schema = args[0]
        assert isinstance(schema, dict)
        names = [f["name"] for f in schema["fields"]]
        types = [f["type"] for f in schema["fields"]]
        assert "content" in names
        assert "text" in types
        assert "vector" not in types


class TestRedisProviderMessages:
    @pytest.fixture
    def sample_messages(self) -> list[ChatMessage]:
        return [
            ChatMessage(role=Role.USER, text="Hello, how are you?"),
            ChatMessage(role=Role.ASSISTANT, text="I'm doing well, thank you!"),
            ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
        ]

    @pytest.mark.asyncio
    async def test_messages_adding_requires_filters(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider()
        with pytest.raises(ServiceInitializationError):
            await provider.messages_adding("thread123", ChatMessage(role=Role.USER, text="Hello"))

    @pytest.mark.asyncio
    async def test_thread_created_sets_per_operation_id(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        await provider.thread_created("t1")
        assert provider._per_operation_thread_id == "t1"

    @pytest.mark.asyncio
    async def test_thread_created_conflict_when_scoped(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", scope_to_per_operation_thread_id=True)
        provider._per_operation_thread_id = "t1"
        with pytest.raises(ValueError) as exc:
            await provider.thread_created("t2")
        assert "only be used with one thread" in str(exc.value)

    @pytest.mark.asyncio
    async def test_search_all_paginates(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        async def gen(_q, page_size: int = 200):  # noqa: ARG001, ANN001
            yield [{"id": 1}]
            yield [{"id": 2}, {"id": 3}]

        mock_index.paginate = gen
        provider = RedisProvider(user_id="u1")
        res = await provider.search_all(page_size=2)
        assert res == [{"id": 1}, {"id": 2}, {"id": 3}]


class TestRedisProviderModelInvoking:
    @pytest.mark.asyncio
    async def test_model_invoking_requires_filters(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider()
        with pytest.raises(ServiceInitializationError):
            await provider.model_invoking(ChatMessage(role=Role.USER, text="Hi"))


class TestRedisProviderContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager_returns_self(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        async with provider as ctx:
            assert ctx is provider

    @pytest.mark.asyncio
    async def test_aexit_noop(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        assert await provider.__aexit__(None, None, None) is None


class TestRedisProviderSchemaVectors:
    def test_schema_with_vector_field_and_dims_inferred(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        class DummyVectorizer:
            dims = 3

        RedisProvider(user_id="u1", vectorizer=DummyVectorizer(), vector_field_name="vec")
        args, _ = patch_index_from_dict.from_dict.call_args
        schema = args[0]
        names = [f["name"] for f in schema["fields"]]
        types = {f["name"]: f["type"] for f in schema["fields"]}
        assert "vec" in names
        assert types["vec"] == "vector"

    def test_init_vectorizer_missing_dims_raises(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework.exceptions import ServiceInvalidRequestError

        from agent_framework_redis._provider import RedisProvider

        class DummyVectorizer:
            pass

        with pytest.raises(ServiceInvalidRequestError):
            RedisProvider(user_id="u1", vectorizer=DummyVectorizer(), vector_field_name="vec")

    def test_init_vector_dims_override(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        class DummyVectorizer:
            dims = 3

        RedisProvider(
            user_id="u1",
            vectorizer=DummyVectorizer(),
            vector_field_name="vec",
            vector_dims=5,
            vector_algorithm="hnsw",
            vector_datatype="float32",
            vector_distance_metric="cosine",
        )
        args, _ = patch_index_from_dict.from_dict.call_args
        schema = args[0]
        vec = next(f for f in schema["fields"] if f["name"] == "vec")
        assert vec["attrs"]["dims"] == 5


class TestEnsureIndex:
    @pytest.mark.asyncio
    async def test_ensure_index_drop_true_creates_once(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", drop_redis_index=True)
        assert provider.fresh_initialization is False
        await provider._ensure_index()
        assert mock_index.create.await_count == 1
        assert provider.fresh_initialization is True
        await provider._ensure_index()
        # Should not create again
        assert mock_index.create.await_count == 1

    @pytest.mark.asyncio
    async def test_ensure_index_when_drop_false_and_not_exists(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        mock_index.exists = AsyncMock(return_value=False)
        provider = RedisProvider(user_id="u1", drop_redis_index=False)
        await provider._ensure_index()
        assert mock_index.create.await_count == 1
