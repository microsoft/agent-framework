# Copyright (c) Microsoft. All rights reserved.

"""Tests for RedisContextProvider and RedisHistoryProvider."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentResponse, ChatOptions, Content, Message
from agent_framework._compaction import annotate_message_groups
from agent_framework._sessions import AgentSession, SessionContext
from redis.asyncio import Redis

from agent_framework_redis._context_provider import _SCOPE_FIELDS, RedisContextProvider, _scope_token_field
from agent_framework_redis._feature_usage import FeatureIndex
from agent_framework_redis._history_provider import RedisHistoryProvider, _redis_result, _trim_start_index

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


async def test_empty_history_save_marks_redis_used(mock_redis_client: MagicMock) -> None:
    with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
        provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

    with patch("agent_framework_redis._history_provider.mark_feature_used") as mark_feature_used:
        await provider.save_messages("session", [])

    mark_feature_used.assert_called_once_with(FeatureIndex.REDIS)


@pytest.fixture
def mock_index() -> AsyncMock:
    idx = AsyncMock()
    client = MagicMock()
    client.aclose = AsyncMock()
    idx.client = client
    idx.create = AsyncMock()
    idx.load = AsyncMock()
    idx.query = AsyncMock(return_value=[])
    idx.exists = AsyncMock(return_value=False)
    return idx


@pytest.fixture
def patch_index_from_dict(mock_index: AsyncMock):
    with patch("agent_framework_redis._context_provider.AsyncSearchIndex") as mock_cls:
        mock_cls.from_dict = MagicMock(return_value=mock_index)

        async def mock_from_existing(*args: Any, **kwargs: Any):  # noqa: ARG001
            mock_existing = AsyncMock()
            mock_existing.schema.to_dict = MagicMock(
                side_effect=lambda: mock_cls.from_dict.call_args[0][0] if mock_cls.from_dict.call_args else {}
            )
            return mock_existing

        mock_cls.from_existing = AsyncMock(side_effect=mock_from_existing)
        yield mock_cls


@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    client.lrange = AsyncMock(return_value=[])
    client.llen = AsyncMock(return_value=0)
    client.ltrim = AsyncMock()
    client.delete = AsyncMock()
    client.aclose = AsyncMock()

    mock_pipeline = AsyncMock()
    mock_pipeline.rpush = AsyncMock()
    mock_pipeline.execute = AsyncMock()
    client.pipeline.return_value.__aenter__.return_value = mock_pipeline

    return client


# ===========================================================================
# RedisContextProvider tests
# ===========================================================================


class TestRedisContextProviderInit:
    def test_basic_construction(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        assert provider.source_id == "ctx"
        assert provider.user_id == "u1"
        assert provider.redis_url == "redis://localhost:6379"
        assert provider.index_name == "context"
        assert provider.prefix == "context"

    def test_custom_params(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(
            source_id="ctx",
            redis_url="redis://custom:6380",
            index_name="my_idx",
            prefix="my_prefix",
            application_id="app1",
            agent_id="agent1",
            user_id="user1",
            context_prompt="Custom prompt",
        )
        assert provider.redis_url == "redis://custom:6380"
        assert provider.index_name == "my_idx"
        assert provider.prefix == "my_prefix"
        assert provider.application_id == "app1"
        assert provider.agent_id == "agent1"
        assert provider.context_prompt == "Custom prompt"

    def test_default_context_prompt(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        assert "Memories" in provider.context_prompt

    def test_invalid_vectorizer_raises(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        from agent_framework.exceptions import AgentException

        with pytest.raises(AgentException, match="not a valid type"):
            RedisContextProvider(source_id="ctx", user_id="u1", redis_vectorizer="bad")  # type: ignore[arg-type] # ty: ignore[invalid-argument-type]


class TestRedisContextProviderValidateFilters:
    def test_no_filters_raises(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx")
        with pytest.raises(ValueError, match="(?i)at least one"):
            provider._validate_filters()

    def test_any_single_filter_ok(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        for kwargs in [{"user_id": "u"}, {"agent_id": "a"}, {"application_id": "app"}]:
            provider = RedisContextProvider(source_id="ctx", **cast(Any, kwargs))
            provider._validate_filters()  # should not raise


class TestRedisContextProviderSchema:
    def test_schema_has_expected_fields(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        schema = provider.schema_dict
        field_names = [f["name"] for f in schema["fields"]]
        for expected in ("role", "content", "message_id"):
            assert expected in field_names
        for scope_field in _SCOPE_FIELDS:
            assert scope_field not in field_names
            assert _scope_token_field(scope_field) in field_names
        assert schema["index"]["name"] == "context"
        assert schema["index"]["prefix"] == "context"

    def test_schema_no_vector_without_vectorizer(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        field_types = [f["type"] for f in provider.schema_dict["fields"]]
        assert "vector" not in field_types


class TestRedisContextProviderBeforeRun:
    async def test_search_results_added_to_context(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        mock_index.query = AsyncMock(return_value=[{"content": "Memory A"}, {"content": "Memory B"}])
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test query"])], session_id="s1")

        await provider.before_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        assert "ctx" in ctx.context_messages
        msgs = ctx.context_messages["ctx"]
        assert len(msgs) == 1
        assert "Memory A" in msgs[0].text
        assert "Memory B" in msgs[0].text

    async def test_empty_input_no_search(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["   "])], session_id="s1")

        await provider.before_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        mock_index.query.assert_not_called()
        assert "ctx" not in ctx.context_messages

    async def test_before_run_searches_without_session_id(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        """Verify that before_run performs cross-session retrieval (no session_id filter)."""
        mock_index.query = AsyncMock(return_value=[{"content": "Memory"}])
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["test query"])], session_id="s1")

        with patch.object(provider, "_redis_search", wraps=provider._redis_search) as spy:
            await provider.before_run(
                agent=cast(Any, None),
                session=session,
                context=ctx,
                state=session.state.setdefault(provider.source_id, {}),
            )  # type: ignore[arg-type]

            spy.assert_called_once()
            # session_id should not be passed to _redis_search (cross-session retrieval)
            assert "session_id" not in spy.call_args.kwargs

    async def test_empty_results_no_messages(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        mock_index.query = AsyncMock(return_value=[])
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.before_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        assert "ctx" not in ctx.context_messages


class TestRedisContextProviderAfterRun:
    async def test_stores_messages(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        session = AgentSession(session_id="test-session")
        response = AgentResponse(messages=[Message(role="assistant", contents=["response text"])])
        ctx = SessionContext(input_messages=[Message(role="user", contents=["user input"])], session_id="s1")
        ctx._response = response

        await provider.after_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        mock_index.load.assert_called_once()
        loaded = mock_index.load.call_args[0][0]
        assert len(loaded) == 2
        roles = {d["role"] for d in loaded}
        assert roles == {"user", "assistant"}

    async def test_skips_empty_conversations(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["   "])], session_id="s1")

        await provider.after_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        mock_index.load.assert_not_called()

    async def test_stores_partition_fields(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002
    ):
        provider = RedisContextProvider(source_id="ctx", application_id="app", agent_id="ag", user_id="u1")
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        loaded = mock_index.load.call_args[0][0]
        doc = loaded[0]
        assert doc["application_id"] == "app"
        assert doc["agent_id"] == "ag"
        assert doc["user_id"] == "u1"
        assert doc["conversation_id"] == "s1"


class TestRedisContextProviderContextManager:
    async def test_aenter_returns_self(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        async with provider as p:
            assert p is provider


class TestRedisContextProviderHybridQuery:
    """Test for AggregateHybridQuery parameter compatibility with redisvl 0.14.0."""

    async def test_aggregate_hybrid_query_uses_alpha(
        self,
        mock_index: AsyncMock,
        patch_index_from_dict: MagicMock,  # noqa: ARG002 - fixture modifies behavior via side effects
    ):
        """Ensure AggregateHybridQuery is called with alpha parameter."""
        from redisvl.utils.vectorize import BaseVectorizer

        # Create a mock vectorizer that inherits from BaseVectorizer
        mock_vectorizer = MagicMock(spec=BaseVectorizer)
        mock_vectorizer.dims = 128
        mock_vectorizer.dtype = "float32"
        mock_vectorizer.aembed = AsyncMock(return_value=[0.1] * 128)

        mock_index.query = AsyncMock(return_value=[{"content": "test result"}])

        provider = RedisContextProvider(
            source_id="ctx",
            user_id="u1",
            redis_vectorizer=mock_vectorizer,
            vector_field_name="embedding",
        )

        # Call _redis_search with custom alpha
        with patch("agent_framework_redis._context_provider.AggregateHybridQuery") as mock_hybrid_query:
            mock_hybrid_query.return_value = MagicMock()
            await provider._redis_search(text="test query", alpha=0.5)

            # Verify AggregateHybridQuery was called with alpha parameter
            mock_hybrid_query.assert_called_once()
            call_kwargs = mock_hybrid_query.call_args.kwargs
            assert "alpha" in call_kwargs
            assert call_kwargs["alpha"] == 0.5


# ===========================================================================
# RedisHistoryProvider tests
# ===========================================================================


class TestRedisHistoryProviderInit:
    def test_basic_construction(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("memory", redis_url="redis://localhost:6379", application_id="test-app")

        assert provider.source_id == "memory"
        assert provider.key_prefix == "chat_messages"
        assert provider.max_messages is None
        assert provider.load_messages is True
        assert provider.store_outputs is True
        assert provider.store_inputs is True

    def test_custom_params(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="test-app",
                key_prefix="custom",
                max_messages=50,
                load_messages=False,
                store_outputs=False,
                store_inputs=False,
            )

        assert provider.key_prefix == "custom"
        assert provider.application_id == "test-app"
        assert provider.key_format == "scoped"
        assert provider.max_messages == 50
        assert provider.load_messages is False
        assert provider.store_outputs is False
        assert provider.store_inputs is False

    def test_no_redis_url_or_credential_raises(self):
        with pytest.raises(ValueError, match="Either redis_client, redis_url, or credential_provider"):
            RedisHistoryProvider("mem")

    def test_both_url_and_credential_raises(self):
        mock_cred = MagicMock()
        with pytest.raises(ValueError, match="mutually exclusive"):
            RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                credential_provider=mock_cred,
                host="myhost",
            )

    def test_borrowed_client_is_used_directly(self):
        borrowed = Redis(decode_responses=True)

        provider = RedisHistoryProvider("mem", redis_client=borrowed, application_id="test-app")

        assert provider._redis_client is borrowed
        assert provider._owns_client is False

    @pytest.mark.parametrize(
        "connection_kwargs",
        [
            {"redis_url": "redis://ignored:6379"},
            {"credential_provider": MagicMock()},
            {
                "credential_provider": MagicMock(),
                "host": "ignored",
                "port": 1234,
                "ssl": False,
                "username": "ignored",
            },
            {
                "redis_url": "redis://ignored:6379",
                "credential_provider": MagicMock(),
            },
        ],
    )
    def test_borrowed_client_takes_precedence_over_other_connection_sources(self, connection_kwargs: dict[str, Any]):
        # A caller-owned client is the connection. URL, credential provider and the
        # individual connection settings describe how to build one, so supplying
        # them alongside it is redundant rather than conflicting, and none of them
        # is validated. This matches what the Redis vector stores already do.
        borrowed = Redis(decode_responses=True)
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            provider = RedisHistoryProvider(
                "mem",
                redis_client=borrowed,
                application_id="test-app",
                **connection_kwargs,
            )

        assert provider._redis_client is borrowed
        assert provider._owns_client is False
        assert provider.redis_url is None
        mock_from_url.assert_not_called()

    def test_borrowed_client_still_passes_compatibility_checks_with_redundant_settings(self):
        # The settings are ignored; the client itself is not.
        with pytest.raises(ValueError, match="decode_responses=True"):
            RedisHistoryProvider(
                "mem",
                redis_client=Redis(decode_responses=False),
                redis_url="redis://ignored:6379",
                application_id="test-app",
            )

    def test_borrowed_client_keeps_provider_scoping_and_retention(self):
        # Connection precedence does not reach provider-level storage settings.
        borrowed = Redis(decode_responses=True)
        provider = RedisHistoryProvider(
            "mem",
            redis_client=borrowed,
            redis_url="redis://ignored:6379",
            application_id="app",
            tenant_id="tenant",
            agent_id="agent",
            max_messages=7,
            key_prefix="hist",
        )

        assert provider.max_messages == 7
        assert provider.key_prefix == "hist"
        key = provider._redis_key("session")
        assert "|v2|" in key
        assert "tenant" in key and "agent" in key

    def test_borrowed_client_must_be_async_redis(self):
        with pytest.raises(TypeError, match=r"redis\.asyncio\.Redis"):
            RedisHistoryProvider(
                "mem",
                redis_client=cast(Any, MagicMock()),
                application_id="test-app",
            )

    def test_borrowed_client_requires_decoded_responses(self):
        borrowed = Redis(decode_responses=False)

        with pytest.raises(ValueError, match="decode_responses=True"):
            RedisHistoryProvider("mem", redis_client=borrowed, application_id="test-app")

    def test_credential_provider_without_host_raises(self):
        mock_cred = MagicMock()
        with pytest.raises(ValueError, match="host is required"):
            RedisHistoryProvider("mem", credential_provider=mock_cred)

    def test_negative_max_messages_raises(self):
        with pytest.raises(ValueError, match="max_messages"):
            RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app", max_messages=-5)

    def test_credential_provider_with_host(self):
        mock_cred = MagicMock()
        with patch("agent_framework_redis._history_provider.redis.Redis") as mock_redis_cls:
            mock_redis_cls.return_value = MagicMock()
            provider = RedisHistoryProvider(
                "mem", credential_provider=mock_cred, host="myhost", application_id="test-app"
            )

        mock_redis_cls.assert_called_once_with(
            host="myhost",
            port=6380,
            ssl=True,
            username=None,
            credential_provider=mock_cred,
            decode_responses=True,
        )
        assert provider.redis_url is None


class TestRedisHistoryProviderClose:
    async def test_owned_client_is_closed(self, mock_redis_client: MagicMock):
        with patch(
            "agent_framework_redis._history_provider.redis.from_url",
            return_value=mock_redis_client,
        ):
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.aclose()

        mock_redis_client.aclose.assert_awaited_once()

    async def test_borrowed_client_is_not_closed(self):
        borrowed = Redis(decode_responses=True)
        with patch.object(borrowed, "aclose", new_callable=AsyncMock) as close:
            provider = RedisHistoryProvider("mem", redis_client=borrowed, application_id="test-app")

            await provider.aclose()

            close.assert_not_awaited()
        await borrowed.aclose()


def _seed_history(mock_redis_client: MagicMock, rows: list[str]) -> None:
    """Seed stored history on the parent client and on the pipeline connection.

    ``save_messages`` reads the watched history through the pipeline's reserved
    connection (the parent client would need a second one), while ``get_messages``
    reads through the parent. Tests about deduplication and trimming care about the
    history they seed, not about which connection reads it, so both are seeded.
    The single-connection behaviour itself has its own regression.
    """
    mock_redis_client.lrange = AsyncMock(return_value=rows)
    mock_redis_client.pipeline.return_value.__aenter__.return_value.lrange = AsyncMock(return_value=rows)


def _reasoning_tool_group_history() -> list[Message]:
    messages = [
        Message(
            role="assistant",
            contents=[
                Content.from_text_reasoning(
                    id="rs_1",
                    text="thinking",
                    protected_data="encrypted-reasoning",
                    additional_properties={"status": "completed"},
                )
            ],
        ),
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="c1",
                    name="f",
                    arguments="{}",
                    additional_properties={"fc_id": "fc_1"},
                )
            ],
        ),
        Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="ok")]),
        Message(role="assistant", contents=["done"]),
    ]
    annotate_message_groups(messages)
    return messages


class TestRedisHistoryProviderRedisKey:
    def test_scoped_key_is_deterministic_and_encodes_opaque_components(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "source:one",
                redis_url="redis://localhost:6379",
                key_prefix="messages:one",
                tenant_id="tenant/one",
                application_id="Application One",
                agent_id="agent:one",
            )

        key = provider._redis_key("session/one")

        assert key == provider._redis_key("session/one")
        assert key.split("|")[1] == "v2"
        assert ":" not in key
        raw_components = ("messages:one", "tenant/one", "Application One", "agent:one", "source:one", "session/one")
        assert all(raw_component not in key for raw_component in raw_components)

    def test_scoped_key_isolates_each_boundary(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            providers = [
                RedisHistoryProvider(
                    source_id,
                    redis_url="redis://localhost:6379",
                    tenant_id=tenant_id,
                    application_id=application_id,
                    agent_id=agent_id,
                )
                for source_id, tenant_id, application_id, agent_id in (
                    ("source-a", "tenant-a", "app-a", "agent-a"),
                    ("source-b", "tenant-a", "app-a", "agent-a"),
                    ("source-a", "tenant-b", "app-a", "agent-a"),
                    ("source-a", "tenant-a", "app-b", "agent-a"),
                    ("source-a", "tenant-a", "app-a", "agent-b"),
                )
            ]

        keys = {provider._redis_key("shared-session") for provider in providers}

        assert len(keys) == len(providers)

    @pytest.mark.parametrize("application_id", [None, ""])
    def test_scoped_format_requires_application_id(
        self, mock_redis_client: MagicMock, application_id: str | None
    ) -> None:
        with (
            patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client),
            pytest.raises(ValueError, match="application_id"),
        ):
            RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id=application_id)

    @pytest.mark.parametrize(("tenant_id", "agent_id", "field"), [("", None, "tenant_id"), (None, "", "agent_id")])
    def test_scoped_format_rejects_empty_optional_scope(
        self, mock_redis_client: MagicMock, tenant_id: str | None, agent_id: str | None, field: str
    ) -> None:
        with (
            patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client),
            pytest.raises(ValueError, match=field),
        ):
            RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                tenant_id=tenant_id,
                agent_id=agent_id,
            )

    @pytest.mark.parametrize("session_id", [None, ""])
    def test_scoped_format_requires_session_id(self, mock_redis_client: MagicMock, session_id: str | None) -> None:
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
            )

        with pytest.raises(ValueError, match="session_id"):
            provider._redis_key(session_id)

    @pytest.mark.parametrize("max_messages", [None, 0])
    async def test_scoped_save_validates_session_before_noop(
        self, mock_redis_client: MagicMock, max_messages: int | None
    ) -> None:
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=max_messages,
            )

        messages = [] if max_messages is None else [Message(role="user", contents=["hello"])]
        with pytest.raises(ValueError, match="session_id"):
            await provider.save_messages(None, messages)

    async def test_scoped_operations_use_only_the_scoped_key(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                tenant_id="tenant",
                application_id="app",
                agent_id="agent",
            )

        expected_key = provider._redis_key("session")
        message = Message(role="user", contents=["hello"])

        await provider.get_messages("session")
        await provider.save_messages("session", [message])
        await provider.clear("session")

        expected_range_call = ((expected_key, 0, -1),)
        # `get_messages` reads through the parent client; `save_messages` reads the
        # watched history through the pipeline's reserved connection. Either way the
        # scoped key is the one used.
        assert mock_redis_client.lrange.call_args_list == [expected_range_call]
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.lrange.call_args_list == [expected_range_call]
        pipeline.rpush.assert_awaited_once_with(expected_key, provider._serialize_json(message))
        mock_redis_client.delete.assert_awaited_once_with(expected_key)
        assert expected_key != "chat_messages:session"

    async def test_trim_does_not_orphan_tool_result(self, mock_redis_client: MagicMock) -> None:
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        call = Message(role="assistant", contents=[Content.from_function_call(call_id="c1", name="f", arguments="{}")])
        result = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="ok")])
        user = Message(role="user", contents=["hi"])
        mock_redis_client.llen = AsyncMock(return_value=3)
        await provider.save_messages("s", [call, result, user])
        # Post-append history is [call, result, user] (3 > 2). Keeping the last two would leave
        # [result, user] with a function_result whose call was trimmed, which the model rejects on
        # every later turn. The trim must advance past the orphaned result and keep [user].
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 2, -1)

    async def test_trim_keeps_a_retained_approval_request_and_response_pair(self, mock_redis_client: MagicMock) -> None:
        # Approval wrappers carry no `call_id`; they pair through `Content.id` and the
        # embedded function call. Treating them as unpairable made a valid recent
        # approval sequence look orphaned and let the trim discard it.
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        function_call = Content.from_function_call(id="c1", call_id="c1", name="f", arguments="{}")
        request = Content.from_function_approval_request(id="c1", function_call=function_call)
        response = Content.from_function_approval_response(approved=True, id="c1", function_call=function_call)
        request_message = Message(role="assistant", contents=[function_call, request])
        response_message = Message(role="user", contents=[response])
        mock_redis_client.llen = AsyncMock(return_value=2)
        await provider.save_messages("s", [request_message, response_message])
        # The pair is exactly max_messages, so nothing is trimmed away.
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_not_awaited()

    async def test_trim_drops_approval_response_when_its_request_is_cut(self, mock_redis_client: MagicMock) -> None:
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        function_call = Content.from_function_call(id="c1", call_id="c1", name="f", arguments="{}")
        request = Content.from_function_approval_request(id="c1", function_call=function_call)
        response = Content.from_function_approval_response(approved=True, id="c1", function_call=function_call)
        history = [
            Message(role="assistant", contents=[function_call, request]),
            Message(role="user", contents=[response]),
            Message(role="assistant", contents=["done"]),
        ]
        _seed_history(mock_redis_client, [])
        await provider.save_messages("s", history)
        # The raw last-two window starts with the approval response and omits its
        # request. The whole approval group must move outside the window.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 2, -1)

    def test_pending_approval_group_survives_when_it_precedes_the_raw_window(self) -> None:
        first_call = Content.from_function_call(id="c1", call_id="c1", name="f", arguments="{}")
        second_call = Content.from_function_call(id="c2", call_id="c2", name="f", arguments="{}")
        batch = Message(
            role="assistant",
            contents=[
                first_call,
                second_call,
                Content.from_function_approval_request(id="c1", function_call=first_call),
                Content.from_function_approval_request(id="c2", function_call=second_call),
            ],
        )
        response = Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id="c1", function_call=first_call)],
        )
        result = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="one")])
        history = [
            batch,
            response,
            result,
            Message(role="assistant", contents=["later one"]),
            Message(role="assistant", contents=["later two"]),
        ]

        assert _trim_start_index(history, max_messages=2) == 0

    async def test_multi_save_approval_batch_never_replays_orphaned_results(self, mock_redis_client: MagicMock) -> None:
        openai = pytest.importorskip("agent_framework_openai")
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        first_call = Content.from_function_call(id="c1", call_id="c1", name="f", arguments="{}")
        second_call = Content.from_function_call(id="c2", call_id="c2", name="f", arguments="{}")
        batch = Message(
            role="assistant",
            contents=[
                first_call,
                second_call,
                Content.from_function_approval_request(id="c1", function_call=first_call),
                Content.from_function_approval_request(id="c2", function_call=second_call),
            ],
        )
        first_response = Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id="c1", function_call=first_call)],
        )
        second_response = Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id="c2", function_call=second_call)],
        )
        first_result = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="one")])
        second_result = Message(role="tool", contents=[Content.from_function_result(call_id="c2", result="two")])
        done = Message(role="assistant", contents=["done"])
        stored_rows: list[str] = []
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.multi = MagicMock()
        pipeline.lrange = AsyncMock(side_effect=lambda *args: list(stored_rows))

        async def execute() -> list[Any]:
            stored_rows.extend(call.args[1] for call in pipeline.rpush.await_args_list)
            for call in pipeline.ltrim.await_args_list:
                start, stop = call.args[1:3]
                stored_rows[:] = stored_rows[start : None if stop == -1 else stop + 1]
            pipeline.rpush.reset_mock()
            pipeline.ltrim.reset_mock()
            return []

        pipeline.execute = AsyncMock(side_effect=execute)
        mock_redis_client.lrange = AsyncMock(side_effect=lambda *args: list(stored_rows))
        await provider.save_messages("s", [Message(role="user", contents=["old"]), batch])
        await provider.save_messages("s", [first_response, first_result])
        await provider.save_messages("s", [second_response, second_result, done])

        retained = await provider.get_messages("s")
        client = openai.OpenAIChatClient(model="test-model", api_key="test-key")
        replay = await client._prepare_options(
            [*retained, Message(role="user", contents=["follow up"])],
            ChatOptions(store=False),
        )
        assert replay["store"] is False
        assert [message.text for message in retained] == ["done"]

    async def test_trim_pairs_call_and_result_by_occurrence_when_an_id_is_reused(
        self, mock_redis_client: MagicMock
    ) -> None:
        # A provider that reuses a call_id must not let the second call legitimize the
        # first result after the first call has been trimmed: pairing is by occurrence.
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        first_call = Message(
            role="assistant", contents=[Content.from_function_call(call_id="c1", name="f", arguments="{}")]
        )
        first_result = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="one")])
        second_call = Message(
            role="assistant", contents=[Content.from_function_call(call_id="c1", name="f", arguments="{}")]
        )
        mock_redis_client.llen = AsyncMock(return_value=3)
        await provider.save_messages("s", [first_call, first_result, second_call])
        # Keeping the last two would leave [first_result, second_call]: the result is
        # paired by occurrence with first_call, which is outside the window. The trim
        # must advance past that result and keep [second_call] alone.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 2, -1)

    async def test_trim_does_not_split_a_group_separated_by_a_plain_message(self, mock_redis_client: MagicMock) -> None:
        # Non-adjacent pairs count. A plain assistant message between a call and its
        # result does not end the dependency, so a cut may not land between them just
        # because the message in between carries no tool content at all.
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=3,
            )
        call = Message(role="assistant", contents=[Content.from_function_call(call_id="c1", name="f", arguments="{}")])
        note = Message(role="assistant", contents=["approval completed"])
        result = Message(role="tool", contents=[Content.from_function_result(call_id="c1", result="ok")])
        done = Message(role="assistant", contents=["done"])
        mock_redis_client.llen = AsyncMock(return_value=4)
        await provider.save_messages("s", [call, note, result, done])
        # Keeping the last three would leave [note, result, done] and split the pair.
        # The boundary must keep advancing past the orphaned result, so the retained
        # window is [done] alone: the limit is a bound on what to keep, and dropping a
        # dangling result is cheaper than handing the model a history it will reject.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 3, -1)

    async def test_trim_follows_overlapping_linked_groups_to_a_stable_boundary(
        self, mock_redis_client: MagicMock
    ) -> None:
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=7,
            )
        call_a = Message(role="assistant", contents=[Content.from_function_call(call_id="a", name="f", arguments="{}")])
        call_c = Message(role="assistant", contents=[Content.from_function_call(call_id="c", name="f", arguments="{}")])
        history = [
            call_a,
            Message(role="assistant", contents=["between calls"]),
            call_c,
            Message(role="assistant", contents=["before a"]),
            Message(role="tool", contents=[Content.from_function_result(call_id="a", result="a")]),
            Message(role="assistant", contents=["before c"]),
            Message(role="tool", contents=[Content.from_function_result(call_id="c", result="c")]),
            Message(role="assistant", contents=["done"]),
        ]
        _seed_history(mock_redis_client, [])
        await provider.save_messages("s", history)
        # Moving past group A's result lands inside group C. The cut must advance
        # again rather than retaining C's result without its declaration.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 7, -1)

    async def test_trim_discards_whole_reasoning_tool_group(self, mock_redis_client: MagicMock) -> None:
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=3,
            )
        _seed_history(mock_redis_client, [])
        await provider.save_messages("s", _reasoning_tool_group_history())
        # Keeping the last three messages would drop the reasoning prefix but retain its
        # function call and result. The complete core compaction group must be dropped instead.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 3, -1)

    async def test_trimmed_reasoning_group_allows_later_stateless_replay(self, mock_redis_client: MagicMock) -> None:
        openai = pytest.importorskip("agent_framework_openai")
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=3,
            )
        history = _reasoning_tool_group_history()
        client = openai.OpenAIChatClient(model="test-model", api_key="test-key")
        control = await client._prepare_options(history, ChatOptions(store=False))
        assert control["store"] is False

        stored_rows: list[str] = []
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.lrange = AsyncMock(return_value=[])

        async def execute() -> list[Any]:
            stored_rows.extend(call.args[1] for call in pipeline.rpush.await_args_list)
            for call in pipeline.ltrim.await_args_list:
                start, stop = call.args[1:3]
                stored_rows[:] = stored_rows[start : None if stop == -1 else stop + 1]
            return []

        pipeline.execute = AsyncMock(side_effect=execute)
        mock_redis_client.lrange = AsyncMock(side_effect=lambda *args: list(stored_rows))
        await provider.save_messages("s", history)

        # A later store=False request replays the retained history through the real OpenAI
        # request validator. The old raw window retained the call/result annotations that
        # pointed back to the trimmed reasoning item, so this preparation raised a 400-class
        # ChatClientInvalidRequestException before any network call.
        retained = await provider.get_messages("s")
        replay = await client._prepare_options(
            [*retained, Message(role="user", contents=["follow up"])],
            ChatOptions(store=False),
        )
        assert replay["store"] is False

    async def test_trim_keeps_sources_that_have_no_output_of_their_own(self, mock_redis_client: MagicMock) -> None:
        # Only outputs depend on a source, so a run of calls that were never answered
        # costs nothing to keep. Deciding the cut from the number of outputs alone
        # under-counted the transcript and walked the boundary past them anyway.
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=5,
            )
        pending = [
            Message(role="assistant", contents=[Content.from_function_call(call_id=f"c{i}", name="f", arguments="{}")])
            for i in range(1, 5)
        ]
        call = Message(role="assistant", contents=[Content.from_function_call(call_id="c5", name="f", arguments="{}")])
        result = Message(role="tool", contents=[Content.from_function_result(call_id="c5", result="ok")])
        await provider.save_messages("s", [*pending, call, result])
        # Every message after the first belongs to a self-contained window, so the
        # boundary is the first index and the four unanswered calls are kept.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 1, -1)

    async def test_trim_does_not_empty_history_over_an_output_with_no_source(
        self, mock_redis_client: MagicMock
    ) -> None:
        # A result whose call was never stored cannot be un-orphaned by trimming:
        # there is no source to keep. Treating that as a broken dependency walked the
        # boundary to the end of the list and LTRIM wiped the whole session.
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=3,
            )
        user = Message(role="user", contents=["hi"])
        first = Message(role="assistant", contents=["one"])
        second = Message(role="assistant", contents=["two"])
        stray = Message(role="tool", contents=[Content.from_function_result(call_id="gone", result="ok")])
        await provider.save_messages("s", [user, first, second, stray])
        # The three newest messages are kept. The stray result stays because the trim
        # is responsible for not creating orphans, not for repairing history damage it
        # cannot see a cause for.
        key = provider._redis_key("s")
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_awaited_once_with(key, 1, -1)

    async def test_save_reads_the_watched_history_through_the_pipeline_connection(
        self, mock_redis_client: MagicMock
    ) -> None:
        # WATCH has reserved the pipeline connection. Going back out through the parent
        # client needs a second one, so a borrowed client with max_connections=1 would
        # fail every non-empty save.
        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.lrange = AsyncMock(return_value=[])
        message = Message(role="user", contents=["hi"])
        await provider.save_messages("s", [message])
        pipeline.lrange.assert_awaited_once_with(provider._redis_key("s"), 0, -1)
        mock_redis_client.lrange.assert_not_awaited()

    async def test_save_raises_after_the_watch_retries_are_exhausted(self, mock_redis_client: MagicMock) -> None:
        # Falling off the retry loop reported success while every transaction had been
        # aborted and nothing was persisted.
        from redis.exceptions import WatchError

        with patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                max_messages=2,
            )
        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.lrange = AsyncMock(return_value=[])
        pipeline.execute = AsyncMock(side_effect=WatchError("aborted"))
        message = Message(role="user", contents=["hi"])
        with pytest.raises(WatchError, match="aborted"):
            await provider.save_messages("s", [message])
        assert pipeline.execute.await_count == 8

    def test_legacy_format_warns_and_preserves_historical_keys(self, mock_redis_client: MagicMock):
        with (
            patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client),
            pytest.warns(DeprecationWarning, match="key_format='legacy'.*deprecated"),
        ):
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                key_prefix="msgs",
                key_format="legacy",
            )

        assert provider._redis_key("session-123") == "msgs:session-123"
        assert provider._redis_key(None) == "msgs:default"

    def test_legacy_format_rejects_scoped_configuration(self, mock_redis_client: MagicMock):
        with (
            patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client),
            pytest.raises(ValueError, match="legacy"),
        ):
            RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="app",
                key_format="legacy",
            )

    def test_rejects_unsupported_key_format(self, mock_redis_client: MagicMock):
        with (
            patch("agent_framework_redis._history_provider.redis.from_url", return_value=mock_redis_client),
            pytest.raises(ValueError, match="key_format"),
        ):
            RedisHistoryProvider("mem", redis_url="redis://localhost:6379", key_format=cast(Any, "unsupported"))


class TestRedisHistoryProviderGetMessages:
    async def test_returns_deserialized_messages(self, mock_redis_client: MagicMock):
        msg1 = Message(role="user", contents=["Hello"])
        msg2 = Message(role="assistant", contents=["Hi!"])
        _seed_history(mock_redis_client, [json.dumps(msg1.to_dict()), json.dumps(msg2.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        messages = await provider.get_messages("s1")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].text == "Hi!"

    async def test_empty_returns_empty(self, mock_redis_client: MagicMock):
        _seed_history(mock_redis_client, [])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        messages = await provider.get_messages("s1")
        assert messages == []

    async def test_returns_messages_when_lrange_is_synchronous(self, mock_redis_client: MagicMock):
        """redis-py types several commands as returning a value or an awaitable; handle both."""
        msg = Message(role="user", contents=["Hello"])
        mock_redis_client.lrange = MagicMock(return_value=[json.dumps(msg.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        messages = await provider.get_messages("s1")
        assert len(messages) == 1
        assert messages[0].text == "Hello"


class TestRedisResultHelper:
    async def test_awaits_an_awaitable_result(self):
        async def _coro() -> int:
            return 7

        # Annotated as the union redis-py actually declares (``int | Awaitable[int]``),
        # which is the shape ``_redis_result`` exists to normalise. Handing it a bare
        # coroutine is outside that contract: the single union parameter solves ``_T``
        # from the non-awaitable arm alone, so mypy rejects the awaitable, exactly as
        # the helper's own docstring says it only covers ``Awaitable[T] | T``.
        pending: int | Awaitable[int] = _coro()
        assert await _redis_result(pending) == 7

    async def test_passes_through_a_plain_result(self):
        assert await _redis_result(7) == 7


class TestRedisHistoryProviderSaveMessages:
    async def test_saves_serialized_messages(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        msgs = [Message(role="user", contents=["Hello"]), Message(role="assistant", contents=["Hi"])]
        await provider.save_messages("s1", msgs)

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 2
        pipeline.execute.assert_called_once()

    async def test_empty_messages_noop(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.save_messages("s1", [])
        mock_redis_client.pipeline.assert_not_called()

    async def test_max_messages_trimming(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem", redis_url="redis://localhost:6379", application_id="test-app", max_messages=2
            )

        # Three plain messages over a limit of two. With no tool call/result pair to protect, the
        # retained window is simply the last two, starting at index 1.
        messages = [
            Message(role="user", contents=["a"]),
            Message(role="user", contents=["b"]),
            Message(role="user", contents=["c"]),
        ]
        await provider.save_messages("s1", messages)

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.ltrim.assert_called_once_with(provider._redis_key("s1"), 1, -1)
        assert all(message.message_id is None for message in messages)

    async def test_no_trim_when_under_limit(self, mock_redis_client: MagicMock):
        mock_redis_client.llen = AsyncMock(return_value=3)

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem", redis_url="redis://localhost:6379", application_id="test-app", max_messages=10
            )

        await provider.save_messages("s1", [Message(role="user", contents=["msg"])])

        mock_redis_client.ltrim.assert_not_called()

    async def test_max_messages_zero_retains_nothing(self, mock_redis_client: MagicMock):
        """Only None means unlimited, so a retention count of 0 must retain nothing.

        ``LTRIM key 0 -1`` is Redis's "keep the whole list", so trimming to
        ``-max_messages`` cannot express a limit of zero.
        """
        mock_redis_client.llen = AsyncMock(return_value=15)

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem", redis_url="redis://localhost:6379", application_id="test-app", max_messages=0
            )

        await provider.save_messages("s1", [Message(role="user", contents=["msg"])])

        # No payload reaches Redis at all, so nothing is exposed to readers, AOF or replicas.
        mock_redis_client.pipeline.assert_not_called()
        mock_redis_client.ltrim.assert_not_called()

    async def test_max_messages_zero_leaves_stored_history_alone(self, mock_redis_client: MagicMock):
        """Disabling retention must leave previously stored history unchanged."""
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem", redis_url="redis://localhost:6379", application_id="test-app", max_messages=0
            )

        await provider.save_messages("s1", [Message(role="user", contents=["msg"])])

        mock_redis_client.delete.assert_not_called()


class TestRedisHistoryProviderClear:
    async def test_clear_calls_delete(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.clear("session-1")
        mock_redis_client.delete.assert_called_once_with(provider._redis_key("session-1"))


class TestRedisHistoryProviderBeforeAfterRun:
    """Test before_run/after_run integration via HistoryProvider defaults."""

    async def test_before_run_loads_history(self, mock_redis_client: MagicMock):
        msg = Message(role="user", contents=["old msg"])
        _seed_history(mock_redis_client, [json.dumps(msg.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["new msg"])], session_id="s1")

        await provider.before_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        assert "mem" in ctx.context_messages
        assert len(ctx.context_messages["mem"]) == 1
        assert ctx.context_messages["mem"][0].text == "old msg"

    async def test_after_run_stores_input_and_response(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hello"])])

        await provider.after_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 2
        pipeline.execute.assert_called_once()

    async def test_after_run_skips_when_no_messages(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem",
                redis_url="redis://localhost:6379",
                application_id="test-app",
                store_inputs=False,
                store_outputs=False,
            )

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")

        await provider.after_run(
            agent=cast(Any, None),
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )  # type: ignore[arg-type]

        mock_redis_client.pipeline.assert_not_called()


class TestRedisHistoryProviderDeduplication:
    """Tests for Redis save_messages deduplication and trimming behavior."""

    async def test_deduplicates_identical_messages(self, mock_redis_client: MagicMock):
        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])

        _seed_history(mock_redis_client, [json.dumps(msg1.to_dict()), json.dumps(msg2.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.save_messages("s1", [msg1, msg2])

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        pipeline.rpush.assert_not_called()
        pipeline.execute.assert_not_called()

    async def test_only_appends_new_messages(self, mock_redis_client: MagicMock):
        msg1 = Message(role="user", contents=["hello"])
        msg2 = Message(role="assistant", contents=["hi there"])
        msg3 = Message(role="user", contents=["how are you?"])

        _seed_history(mock_redis_client, [json.dumps(msg1.to_dict()), json.dumps(msg2.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.save_messages("s1", [msg1, msg2, msg3])

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 1

        call_args = pipeline.rpush.call_args[0]
        pushed_msg_dict = json.loads(call_args[1])
        assert pushed_msg_dict["contents"][0]["text"] == "how are you?"

    async def test_different_roles_same_text_not_deduplicated(self, mock_redis_client: MagicMock):
        msg1 = Message(role="user", contents=["ping"], message_id="original-ping")

        _seed_history(mock_redis_client, [json.dumps(msg1.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        msg2 = Message(role="assistant", contents=["ping"])
        await provider.save_messages("s1", [msg1, msg2])

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 1
        pushed_msg_dict = json.loads(pipeline.rpush.call_args.args[1])
        assert pushed_msg_dict["role"] == "assistant"

    async def test_repeated_user_turn_is_not_deduplicated(self, mock_redis_client: MagicMock):
        previous = [Message(role="user", contents=["yes"]), Message(role="assistant", contents=["first reply"])]
        _seed_history(mock_redis_client, [json.dumps(msg.to_dict()) for msg in previous])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.save_messages(
            "s1", [Message(role="user", contents=["yes"]), Message(role="assistant", contents=["second reply"])]
        )

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert [json.loads(call.args[1])["contents"][0]["text"] for call in pipeline.rpush.await_args_list] == [
            "yes",
            "second reply",
        ]

    async def test_trimmed_messages_not_reappended(self, mock_redis_client: MagicMock):
        """Messages trimmed by max_messages should not be re-appended
        when the caller resends the full transcript. Sequence matching
        handles this without needing a :seen set."""
        msg_old = Message(role="user", contents=["old"])
        msg_new = Message(role="assistant", contents=["new"])

        _seed_history(mock_redis_client, [json.dumps(msg_new.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.save_messages("s1", [msg_old, msg_new])

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value

        pipeline.rpush.assert_not_called()

    async def test_preserves_duplicate_content(self, mock_redis_client: MagicMock):
        """Two separate user 'yes' replies must both be persisted."""
        yes_1 = Message(role="user", contents=["yes"])
        yes_2 = Message(role="user", contents=["yes"])

        _seed_history(mock_redis_client, [])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", application_id="test-app")

        await provider.save_messages("s1", [yes_1, yes_2])

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 2
