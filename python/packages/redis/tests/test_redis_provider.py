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


@pytest.fixture
def patch_vectorizers():
    class DummyVectorizer:
        def __init__(self, dims: int):
            self.dims = dims

        async def aembed_many(self, texts, batch_size: int = 1):  # noqa: ARG002
            # deterministic embeddings of correct length
            return [[float(i + 1) for i in range(self.dims)] for _ in texts]

    with (
        patch("agent_framework_redis._provider.EmbeddingsCache") as _cache,
        patch(
            "agent_framework_redis._provider.OpenAITextVectorizer",
            side_effect=lambda **_k: DummyVectorizer(3),
        ) as openai_vec,
        patch(
            "agent_framework_redis._provider.HFTextVectorizer",
            side_effect=lambda **_k: DummyVectorizer(4),
        ) as hf_vec,
    ):
        yield {"openai": openai_vec, "hf": hf_vec}


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

    def test_schema_with_vectorizer_hf(self, patch_index_from_dict, patch_vectorizers):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        RedisProvider(user_id="u1", vectorizer_choice="hf", vector_field_name="vector")
        args, _ = patch_index_from_dict.from_dict.call_args
        schema = args[0]
        vec_fields = [f for f in schema["fields"] if f["type"] == "vector"]
        assert len(vec_fields) == 1
        attrs = vec_fields[0]["attrs"]
        # Our dummy HF vectorizer dims=4
        assert attrs["dims"] == 4
        assert attrs["distance_metric"] in {"cosine", "ip", "l2"}

    @pytest.mark.asyncio
    async def test_create_index_calls_flags(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", overwrite_redis_index=True, drop_redis_index=False)
        await provider.create_redis_index()
        mock_index.create.assert_awaited_once_with(overwrite=True, drop=False)


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
