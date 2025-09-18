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


class TestRedisProviderAdd:
    @pytest.mark.asyncio
    async def test_add_requires_content(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework.exceptions import ServiceInvalidRequestError

        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        with pytest.raises(ServiceInvalidRequestError):
            await provider.add(data={"role": "user"})

    @pytest.mark.asyncio
    async def test_add_sets_defaults_and_vectors(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        class DummyVectorizer:
            dims = 3

            async def aembed_many(self, texts, batch_size=None):  # noqa: ANN001, ARG002
                return [[0.1, 0.2, 0.3] for _ in texts]

        provider = RedisProvider(
            application_id="app",
            agent_id="agent",
            user_id="user",
            thread_id="t-main",
            vectorizer=DummyVectorizer(),
            vector_field_name="vec",
        )

        await provider.add(data={"content": "hello"})
        assert mock_index.load.await_count == 1
        loaded_docs = mock_index.load.await_args.args[0]
        assert loaded_docs and loaded_docs[0]["application_id"] == "app"
        assert loaded_docs[0]["agent_id"] == "agent"
        assert loaded_docs[0]["user_id"] == "user"
        assert loaded_docs[0]["thread_id"] == "t-main"
        assert isinstance(loaded_docs[0]["vec"], (bytes, bytearray))

    @pytest.mark.asyncio
    async def test_messages_adding_filters_and_calls_add(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")

        added: list[dict[str, str]] = []

        async def fake_add(*, data, metadata=None):  # noqa: ANN001, ARG001
            docs = data if isinstance(data, list) else [data]
            added.extend(docs)

        provider.add = AsyncMock(side_effect=fake_add)

        msgs = [
            ChatMessage(role=Role.USER, text="u1"),
            ChatMessage(role=Role.ASSISTANT, text="a1"),
            ChatMessage(role=Role.SYSTEM, text="s1"),
            ChatMessage(role=Role.TOOL, text="tool should be ignored"),
            ChatMessage(role=Role.USER, text="   "),
        ]

        await provider.messages_adding("thread-1", msgs)
        assert provider.add.await_count == 1
        # Only three valid messages should be persisted
        assert added == [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "s1"},
        ]

    @pytest.mark.asyncio
    async def test_messages_adding_scoped_thread_conflict(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", scope_to_per_operation_thread_id=True)
        provider.add = AsyncMock()  # avoid writing
        await provider.messages_adding("t1", ChatMessage(role=Role.USER, text="hi"))
        with pytest.raises(ValueError):
            await provider.messages_adding("t2", ChatMessage(role=Role.USER, text="hi2"))


class TestRedisSearch:
    @pytest.mark.asyncio
    async def test_text_search_builds_TextQuery(self, mock_index: AsyncMock, patch_index_from_dict, patch_queries):
        from agent_framework_redis._provider import RedisProvider

        mock_index.query = AsyncMock(return_value=[])
        provider = RedisProvider(user_id="u1")

        # Avoid dependency on Tag/FilterExpression in unit test
        provider._build_filter_from_dict = lambda _f: None  # type: ignore[assignment]

        await provider.redis_search("hello", num_results=0)
        # Verify TextQuery was constructed with sanitized num_results and default return fields
        calls = patch_queries["calls"]["TextQuery"]
        assert calls, "TextQuery was not created"
        kwargs = calls[-1]
        assert kwargs["text"] == "hello"
        assert kwargs["num_results"] == 1
        assert kwargs["return_score"] is True
        assert kwargs["return_fields"] == [
            "content",
            "role",
            "application_id",
            "agent_id",
            "user_id",
            "thread_id",
        ]

    @pytest.mark.asyncio
    async def test_text_search_with_external_filter_expression(
        self, mock_index: AsyncMock, patch_index_from_dict, patch_queries
    ):
        from agent_framework_redis._provider import RedisProvider

        mock_index.query = AsyncMock(return_value=[])
        provider = RedisProvider(user_id="u1")
        provider._build_filter_from_dict = lambda _f: None  # type: ignore[assignment]

        await provider.redis_search("hello", filter_expression="FE_SENTINEL")
        kwargs = patch_queries["calls"]["TextQuery"][-1]
        assert kwargs["filter_expression"] == "FE_SENTINEL"

    @pytest.mark.asyncio
    async def test_hybrid_search_builds_HybridQuery(self, mock_index: AsyncMock, patch_index_from_dict, patch_queries):
        from agent_framework_redis._provider import RedisProvider

        class DummyVectorizer:
            dims = 3

            async def aembed_many(self, texts, batch_size=None):  # noqa: ANN001, ARG002
                return [[0.1, 0.2, 0.3] for _ in texts]

        mock_index.query = AsyncMock(return_value=[{"content": "x"}])
        provider = RedisProvider(user_id="u1", vectorizer=DummyVectorizer(), vector_field_name="vec")
        provider._build_filter_from_dict = lambda _f: None  # type: ignore[assignment]

        res = await provider.redis_search("hello")
        assert res == [{"content": "x"}]
        calls = patch_queries["calls"]["HybridQuery"]
        assert calls, "HybridQuery was not created"
        kwargs = calls[-1]
        assert kwargs["text"] == "hello"
        assert kwargs["vector_field_name"] == "vec"
        assert kwargs["dtype"] == "float32"
        assert "alpha" in kwargs

    @pytest.mark.asyncio
    async def test_redis_search_empty_text_raises(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework.exceptions import ServiceInvalidRequestError

        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        with pytest.raises(ServiceInvalidRequestError):
            await provider.redis_search("")


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


class TestModelInvokingContext:
    @pytest.mark.asyncio
    async def test_model_invoking_assembles_context(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")

        async def fake_search(text: str, **_):  # noqa: ANN001, ARG001
            return [{"content": "mem1"}, {"content": "mem2"}]

        provider.redis_search = AsyncMock(side_effect=fake_search)

        ctx = await provider.model_invoking([
            ChatMessage(role=Role.USER, text="ask"),
            ChatMessage(role=Role.ASSISTANT, text="reply"),
        ])
        assert ctx.contents is not None and len(ctx.contents) == 1
        text = ctx.contents[0].text  # type: ignore[assignment]
        assert "Memories" in text
        assert "mem1" in text and "mem2" in text

    @pytest.mark.asyncio
    async def test_model_invoking_with_no_memories_returns_empty(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        provider.redis_search = AsyncMock(return_value=[])
        ctx = await provider.model_invoking(ChatMessage(role=Role.USER, text="ask"))
        assert ctx.contents is None
