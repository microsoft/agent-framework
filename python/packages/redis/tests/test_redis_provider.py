# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from agent_framework import ChatMessage, Context, Role, TextContent
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError


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


class TestRedisProviderAdd:
    @pytest.mark.asyncio
    async def test_add_single_document_sets_defaults(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", application_id="app1", agent_id="a1")
        await provider.add(data={"content": "Hello"})
        mock_index.load.assert_awaited_once()
        loaded = mock_index.load.call_args.args[0]
        assert isinstance(loaded, list) and len(loaded) == 1
        doc = loaded[0]
        assert doc["content"] == "Hello"
        assert doc["user_id"] == "u1"
        assert doc["application_id"] == "app1"
        assert doc["agent_id"] == "a1"
        assert "thread_id" in doc  # may be None

    @pytest.mark.asyncio
    async def test_add_requires_content(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        with pytest.raises(ServiceInvalidRequestError):
            await provider.add(data={"role": "user"})

    @pytest.mark.asyncio
    async def test_add_with_vectorizer_embeds_and_serializes(
        self, mock_index: AsyncMock, patch_index_from_dict, patch_vectorizers
    ):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", vectorizer_choice="openai", vector_field_name="vector")
        await provider.add(data=[{"content": "one"}, {"content": "two"}])
        loaded = mock_index.load.call_args.args[0]
        assert len(loaded) == 2
        for d in loaded:
            vec = d.get("vector")
            assert isinstance(vec, (bytes, bytearray))
            # Dummy openai dims=3 -> 12 bytes when float32
            assert len(vec) == 3 * np.dtype(np.float32).itemsize


class TestRedisProviderMessages:
    @pytest.fixture
    def sample_messages(self) -> list[ChatMessage]:
        return [
            ChatMessage(role=Role.USER, text="Hello, how are you?"),
            ChatMessage(role=Role.ASSISTANT, text="I'm doing well, thank you!"),
            ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
        ]

    @pytest.mark.asyncio
    async def test_messages_adding_sets_thread_and_calls_add(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        provider.add = AsyncMock()  # isolate from redis
        await provider.messages_adding(
            "thread123",
            [
                ChatMessage(role=Role.USER, text=""),
                ChatMessage(role=Role.USER, text="Hi"),
                ChatMessage(role=Role.USER, text="   "),
            ],
        )
        assert provider._per_operation_thread_id == "thread123"
        provider.add.assert_awaited_once()
        msgs = provider.add.call_args.kwargs["data"]
        assert msgs == [{"role": "user", "content": "Hi"}]

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


class TestRedisProviderSearch:
    @pytest.mark.asyncio
    async def test_redis_search_requires_filters(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider()
        with pytest.raises(ServiceInitializationError):
            await provider.redis_search("hello")

    @pytest.mark.asyncio
    async def test_redis_search_requires_nonempty_text(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        with pytest.raises(ServiceInvalidRequestError) as exc:
            await provider.redis_search("   ")
        assert "requires non-empty text" in str(exc.value)

    @pytest.mark.asyncio
    async def test_text_only_search_builds_textquery(self, mock_index: AsyncMock, patch_index_from_dict, patch_queries):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        mock_index.query.return_value = [{"content": "doc"}]
        res = await provider.redis_search(
            "hello world",
            filter_expression="@role:{user}",
            return_fields=["content"],
            stopwords=["and", "or"],
            num_results=5,
            in_order=True,
        )
        assert res == [{"content": "doc"}]
        # Ensure TextQuery was used
        assert len(patch_queries["calls"]["TextQuery"]) == 1
        kwargs = patch_queries["calls"]["TextQuery"][0]
        assert kwargs["text"] == "hello world"
        assert isinstance(kwargs["stopwords"], set)
        # Combined filter applied
        fe_arg = patch_queries["calls"]["FilterExpression"][0]
        assert "@user_id:{u1}" in fe_arg or "@user_id:{u1}" in str(fe_arg)
        assert "@role:{user}" in fe_arg or "@role:{user}" in str(fe_arg)

    @pytest.mark.asyncio
    async def test_hybrid_search_when_vectorizer_present(
        self, mock_index: AsyncMock, patch_index_from_dict, patch_vectorizers, patch_queries
    ):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1", vectorizer_choice="hf", vector_field_name="vec")
        mock_index.query.return_value = [{"content": "vdoc"}]
        res = await provider.redis_search("needle")
        assert res == [{"content": "vdoc"}]
        # Ensure HybridQuery was used
        assert len(patch_queries["calls"]["HybridQuery"]) == 1
        assert len(patch_queries["calls"]["TextQuery"]) == 0
        h_kwargs = patch_queries["calls"]["HybridQuery"][0]
        assert h_kwargs["vector_field_name"] == "vec"
        assert isinstance(h_kwargs["vector"], list)
        assert h_kwargs["dtype"] == "float32"

    @pytest.mark.asyncio
    async def test_redis_search_wraps_exceptions(self, mock_index: AsyncMock, patch_index_from_dict, patch_queries):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")

        # Make query raise
        async def boom(_q):  # noqa: ANN001
            raise RuntimeError("fail")

        mock_index.query.side_effect = boom
        with pytest.raises(ServiceInvalidRequestError) as exc:
            await provider.redis_search("hello")
        assert "Redis text search failed" in str(exc.value)

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

    @pytest.mark.asyncio
    async def test_model_invoking_single_message_builds_context(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        provider.redis_search = AsyncMock(return_value=[{"content": "A"}, {"content": "B"}])
        ctx = await provider.model_invoking(ChatMessage(role=Role.USER, text="What's up?"))
        provider.redis_search.assert_awaited_once()
        called_with = provider.redis_search.call_args.kwargs.get("text") or provider.redis_search.call_args.args[0]
        assert called_with == "What's up?"
        assert isinstance(ctx, Context)
        assert ctx.contents and isinstance(ctx.contents[0], TextContent)
        text = ctx.contents[0].text
        assert "## Memories" in text
        assert "A" in text and "B" in text

    @pytest.mark.asyncio
    async def test_model_invoking_multiple_messages_joins_input(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        provider.redis_search = AsyncMock(return_value=[])
        msgs = [
            ChatMessage(role=Role.USER, text="Hello"),
            ChatMessage(role=Role.ASSISTANT, text="There"),
            ChatMessage(role=Role.SYSTEM, text="General Kenobi"),
        ]
        await provider.model_invoking(msgs)
        # The joined text should be used as the search query
        called_with = provider.redis_search.call_args.kwargs.get("text") or provider.redis_search.call_args.args[0]
        assert called_with == "Hello\nThere\nGeneral Kenobi"

    @pytest.mark.asyncio
    async def test_model_invoking_no_memories_returns_empty_context(self, patch_index_from_dict):  # noqa: ARG002
        from agent_framework_redis._provider import RedisProvider

        provider = RedisProvider(user_id="u1")
        provider.redis_search = AsyncMock(return_value=[])
        ctx = await provider.model_invoking(ChatMessage(role=Role.USER, text="Hi"))
        assert isinstance(ctx, Context)
        assert not ctx.contents


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
