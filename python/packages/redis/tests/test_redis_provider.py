# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from agent_framework import ChatMessage, Role
from agent_framework.exceptions import ServiceInitializationError
from pydantic import ValidationError
from redisvl.utils.vectorize import CustomTextVectorizer

from agent_framework_redis import RedisProvider

CUSTOM_VECTORIZER = CustomTextVectorizer(embed=lambda x: [1.0, 2.0, 3.0], dtype="float32")


@pytest.fixture
def mock_index() -> AsyncMock:
    idx = AsyncMock()
    idx.create = AsyncMock()
    idx.load = AsyncMock()
    idx.query = AsyncMock()
    idx.exists = AsyncMock(return_value=False)

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

        # Mock from_existing to return a mock with matching schema by default
        # This prevents schema validation errors in tests that don't specifically test schema validation
        async def mock_from_existing(index_name, redis_url):
            mock_existing = AsyncMock()
            # Return a schema that will match whatever the provider generates
            # This is a bit of a hack, but allows existing tests to continue working
            mock_existing.schema.to_dict = MagicMock(
                side_effect=lambda: mock_cls.from_dict.call_args[0][0] if mock_cls.from_dict.call_args else {}
            )
            return mock_existing

        mock_cls.from_existing = AsyncMock(side_effect=mock_from_existing)

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
    # Verifies the provider can be imported from the package
    def test_import(self):
        from agent_framework_redis._provider import RedisProvider

        assert RedisProvider is not None

    # Constructing without filters should not raise; filters are enforced at call-time
    def test_init_without_filters_ok(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider()
        assert provider.user_id is None
        assert provider.agent_id is None
        assert provider.application_id is None
        assert provider.thread_id is None

    # Schema should omit vector field when no vector configuration is provided
    def test_schema_without_vector_field(self, patch_index_from_dict):
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
    # Writes require at least one scoping filter to avoid unbounded operations
    async def test_messages_adding_requires_filters(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider()
        with pytest.raises(ServiceInitializationError):
            await provider.messages_adding("thread123", ChatMessage(role=Role.USER, text="Hello"))

    @pytest.mark.asyncio
    # Captures the per-operation thread id when provided
    async def test_thread_created_sets_per_operation_id(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider(user_id="u1")
        await provider.thread_created("t1")
        assert provider._per_operation_thread_id == "t1"

    @pytest.mark.asyncio
    # Enforces single-thread usage when scope_to_per_operation_thread_id is True
    async def test_thread_created_conflict_when_scoped(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider(user_id="u1", scope_to_per_operation_thread_id=True)
        provider._per_operation_thread_id = "t1"
        with pytest.raises(ValueError) as exc:
            await provider.thread_created("t2")
        assert "only be used with one thread" in str(exc.value)

    @pytest.mark.asyncio
    # Aggregates all results from the async paginator into a flat list
    async def test_search_all_paginates(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        async def gen(_q, page_size: int = 200):  # noqa: ARG001, ANN001
            yield [{"id": 1}]
            yield [{"id": 2}, {"id": 3}]

        mock_index.paginate = gen
        provider = RedisProvider(user_id="u1")
        res = await provider.search_all(page_size=2)
        assert res == [{"id": 1}, {"id": 2}, {"id": 3}]


class TestRedisProviderModelInvoking:
    @pytest.mark.asyncio
    # Reads require at least one scoping filter to avoid unbounded operations
    async def test_model_invoking_requires_filters(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider()
        with pytest.raises(ServiceInitializationError):
            await provider.model_invoking(ChatMessage(role=Role.USER, text="Hi"))

    @pytest.mark.asyncio
    # Ensures text-only search path is used and context is composed from hits
    async def test_textquery_path_and_context_contents(
        self, mock_index: AsyncMock, patch_index_from_dict, patch_queries
    ):  # noqa: ARG002
        # Arrange: text-only search
        mock_index.query = AsyncMock(return_value=[{"content": "A"}, {"content": "B"}])
        provider = RedisProvider(user_id="u1")

        # Act
        ctx = await provider.model_invoking([ChatMessage(role=Role.USER, text="q1")])

        # Assert: TextQuery used (not HybridQuery), filter_expression included
        assert patch_queries["TextQuery"].call_count == 1
        assert patch_queries["HybridQuery"].call_count == 0
        kwargs = patch_queries["calls"]["TextQuery"][0]
        assert kwargs["text"] == "q1"
        assert kwargs["text_field_name"] == "content"
        assert kwargs["num_results"] == 10
        assert "filter_expression" in kwargs

        # Context contains memories joined after the default prompt
        assert ctx.contents is not None and len(ctx.contents) == 1
        text = ctx.contents[0].text
        assert text.endswith("A\nB")

    @pytest.mark.asyncio
    # When no results are returned, Context should have no contents
    async def test_model_invoking_empty_results_returns_empty_context(
        self, mock_index: AsyncMock, patch_index_from_dict, patch_queries
    ):  # noqa: ARG002
        mock_index.query = AsyncMock(return_value=[])
        provider = RedisProvider(user_id="u1")
        ctx = await provider.model_invoking([ChatMessage(role=Role.USER, text="any")])
        assert ctx.contents is None

    @pytest.mark.asyncio
    # Ensures hybrid vector-text search is used when a vectorizer and vector field are configured
    async def test_hybridquery_path_with_vectorizer(self, mock_index: AsyncMock, patch_index_from_dict, patch_queries):  # noqa: ARG002
        mock_index.query = AsyncMock(return_value=[{"content": "Hit"}])
        provider = RedisProvider(user_id="u1", redis_vectorizer=CUSTOM_VECTORIZER, vector_field_name="vec")

        ctx = await provider.model_invoking([ChatMessage(role=Role.USER, text="hello")])

        # Assert: HybridQuery used with vector and vector field
        assert patch_queries["HybridQuery"].call_count == 1
        k = patch_queries["calls"]["HybridQuery"][0]
        assert k["text"] == "hello"
        assert k["vector_field_name"] == "vec"
        assert k["vector"] == [1.0, 2.0, 3.0]
        assert k["dtype"] == "float32"
        assert k["num_results"] == 10
        assert "filter_expression" in k

        # Context assembled from returned memories
        assert ctx.contents and "Hit" in ctx.contents[0].text


class TestRedisProviderContextManager:
    @pytest.mark.asyncio
    # Verifies async context manager returns self for chaining
    async def test_async_context_manager_returns_self(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider(user_id="u1")
        async with provider as ctx:
            assert ctx is provider

    @pytest.mark.asyncio
    # Exit should be a no-op and not raise
    async def test_aexit_noop(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider(user_id="u1")
        assert await provider.__aexit__(None, None, None) is None


class TestMessagesAddingBehavior:
    @pytest.mark.asyncio
    # Adds messages while injecting partition defaults and preserving allowed roles
    async def test_messages_adding_adds_partition_defaults_and_roles(
        self, mock_index: AsyncMock, patch_index_from_dict
    ):  # noqa: ARG002
        provider = RedisProvider(
            application_id="app",
            agent_id="agent",
            user_id="u1",
            scope_to_per_operation_thread_id=True,
        )

        msgs = [
            ChatMessage(role=Role.USER, text="u"),
            ChatMessage(role=Role.ASSISTANT, text="a"),
            ChatMessage(role=Role.SYSTEM, text="s"),
        ]

        await provider.messages_adding("t1", msgs)

        # Ensure load invoked with shaped docs containing defaults
        assert mock_index.load.await_count == 1
        (loaded_args, _kwargs) = mock_index.load.call_args
        docs = loaded_args[0]
        assert isinstance(docs, list) and len(docs) == 3
        for d in docs:
            assert d["role"] in {"user", "assistant", "system"}
            assert d["content"] in {"u", "a", "s"}
            assert d["application_id"] == "app"
            assert d["agent_id"] == "agent"
            assert d["user_id"] == "u1"
            assert d["thread_id"] == "t1"  # scoped via per-operation thread id

    @pytest.mark.asyncio
    # Skips blank text and disallowed roles (e.g., TOOL) when adding messages
    async def test_messages_adding_ignores_blank_and_disallowed_roles(
        self, mock_index: AsyncMock, patch_index_from_dict
    ):  # noqa: ARG002
        provider = RedisProvider(user_id="u1", scope_to_per_operation_thread_id=True)
        msgs = [
            ChatMessage(role=Role.USER, text="   "),
            ChatMessage(role=Role.TOOL, text="tool output"),
        ]
        await provider.messages_adding("tid", msgs)
        # No valid messages -> no load
        assert mock_index.load.await_count == 0


class TestIndexCreationPublicCalls:
    @pytest.mark.asyncio
    # Ensures index is created only once when drop=True on first public write call
    async def test_messages_adding_triggers_index_create_once_when_drop_true(
        self, mock_index: AsyncMock, patch_index_from_dict
    ):  # noqa: ARG002
        provider = RedisProvider(user_id="u1", drop_redis_index=True)
        await provider.messages_adding("t1", ChatMessage(role=Role.USER, text="m1"))
        await provider.messages_adding("t1", ChatMessage(role=Role.USER, text="m2"))
        # create only on first call
        assert mock_index.create.await_count == 1

    @pytest.mark.asyncio
    # Ensures index is created when drop=False and the index does not exist on first read
    async def test_model_invoking_triggers_create_when_drop_false_and_not_exists(
        self, mock_index: AsyncMock, patch_index_from_dict
    ):  # noqa: ARG002
        mock_index.exists = AsyncMock(return_value=False)
        provider = RedisProvider(user_id="u1", drop_redis_index=False)
        mock_index.query = AsyncMock(return_value=[{"content": "C"}])
        await provider.model_invoking([ChatMessage(role=Role.USER, text="q")])
        assert mock_index.create.await_count == 1


class TestThreadCreatedAdditional:
    @pytest.mark.asyncio
    # Allows None or same thread id repeatedly; different id raises when scoped
    async def test_thread_created_allows_none_and_same_id(self, patch_index_from_dict):  # noqa: ARG002
        provider = RedisProvider(user_id="u1", scope_to_per_operation_thread_id=True)
        # None is allowed
        await provider.thread_created(None)
        # Same id is allowed repeatedly
        await provider.thread_created("t1")
        await provider.thread_created("t1")
        # Different id should raise
        with pytest.raises(ValueError):
            await provider.thread_created("t2")


class TestVectorPopulation:
    @pytest.mark.asyncio
    # When vectorizer configured, messages_adding should embed content and populate the vector field
    async def test_messages_adding_populates_vector_field_when_vectorizer_present(
        self, mock_index: AsyncMock, patch_index_from_dict
    ):  # noqa: ARG002
        provider = RedisProvider(
            user_id="u1",
            scope_to_per_operation_thread_id=True,
            redis_vectorizer=CUSTOM_VECTORIZER,
            vector_field_name="vec",
        )

        await provider.messages_adding("t1", ChatMessage(role=Role.USER, text="hello"))
        assert mock_index.load.await_count == 1
        (loaded_args, _kwargs) = mock_index.load.call_args
        docs = loaded_args[0]
        assert isinstance(docs, list) and len(docs) == 1
        vec = docs[0].get("vec")
        assert isinstance(vec, (bytes, bytearray))
        assert len(vec) == 3 * np.dtype(np.float32).itemsize


class TestRedisProviderSchemaVectors:
    # Adds a vector field when vectorizer supplies dims implicitly
    def test_schema_with_vector_field_and_dims_inferred(self, patch_index_from_dict):  # noqa: ARG002
        RedisProvider(user_id="u1", redis_vectorizer=CUSTOM_VECTORIZER, vector_field_name="vec")
        args, _ = patch_index_from_dict.from_dict.call_args
        schema = args[0]
        names = [f["name"] for f in schema["fields"]]
        types = {f["name"]: f["type"] for f in schema["fields"]}
        assert "vec" in names
        assert types["vec"] == "vector"

    # Raises when redis_vectorizer is not the correct type
    def test_init_invalid_vectorizer(self, patch_index_from_dict):  # noqa: ARG002
        class DummyVectorizer:
            pass

        with pytest.raises(ValidationError):
            RedisProvider(user_id="u1", redis_vectorizer=DummyVectorizer(), vector_field_name="vec")


class TestEnsureIndex:
    @pytest.mark.asyncio
    # Creates index once and marks _index_initialized to prevent duplicate calls
    async def test_ensure_index_creates_once(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        # Mock index doesn't exist, so it will be created
        mock_index.exists = AsyncMock(return_value=False)
        provider = RedisProvider(user_id="u1", overwrite_index=False)

        assert provider._index_initialized is False
        await provider._ensure_index()
        assert mock_index.create.await_count == 1
        assert provider._index_initialized is True

        # Second call should not create again due to _index_initialized flag
        await provider._ensure_index()
        assert mock_index.create.await_count == 1

    @pytest.mark.asyncio
    # Creates index with overwrite=True when overwrite_index=True
    async def test_ensure_index_with_overwrite_true(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        mock_index.exists = AsyncMock(return_value=True)
        provider = RedisProvider(user_id="u1", overwrite_index=True)

        await provider._ensure_index()

        # Should call create with overwrite=True, drop=False
        mock_index.create.assert_called_once_with(overwrite=True, drop=False)

    @pytest.mark.asyncio
    # Creates index with overwrite=False when index doesn't exist
    async def test_ensure_index_create_if_missing(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        mock_index.exists = AsyncMock(return_value=False)
        provider = RedisProvider(user_id="u1", overwrite_index=False)

        await provider._ensure_index()

        # Should call create with overwrite=False, drop=False
        mock_index.create.assert_called_once_with(overwrite=False, drop=False)

    @pytest.mark.asyncio
    # Validates schema compatibility when index exists and overwrite=False
    async def test_ensure_index_schema_validation_success(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        mock_index.exists = AsyncMock(return_value=True)
        provider = RedisProvider(user_id="u1", overwrite_index=False)

        # Mock existing index with matching schema
        expected_schema = provider.schema_dict
        patch_index_from_dict.from_existing.return_value.schema.to_dict.return_value = expected_schema

        await provider._ensure_index()

        # Should validate schema and proceed to create
        patch_index_from_dict.from_existing.assert_called_once_with("context", redis_url="redis://localhost:6379")
        mock_index.create.assert_called_once_with(overwrite=False, drop=False)

    @pytest.mark.asyncio
    # Raises ServiceInitializationError when schemas don't match
    async def test_ensure_index_schema_validation_failure(self, mock_index: AsyncMock, patch_index_from_dict):  # noqa: ARG002
        mock_index.exists = AsyncMock(return_value=True)
        provider = RedisProvider(user_id="u1", overwrite_index=False)

        # Override the mock to return a different schema after provider is created
        async def mock_from_existing_different(index_name, redis_url):
            mock_existing = AsyncMock()
            mock_existing.schema.to_dict = MagicMock(return_value={"different": "schema"})
            return mock_existing

        patch_index_from_dict.from_existing = AsyncMock(side_effect=mock_from_existing_different)

        with pytest.raises(ServiceInitializationError) as exc:
            await provider._ensure_index()

        assert "incompatible with the current configuration" in str(exc.value)
        assert "overwrite_index=True" in str(exc.value)

        # Should not call create when schema validation fails
        mock_index.create.assert_not_called()
