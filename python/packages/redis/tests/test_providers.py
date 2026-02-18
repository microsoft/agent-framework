# Copyright (c) Microsoft. All rights reserved.

"""Tests for RedisContextProvider and RedisHistoryProvider."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import ServiceInitializationError

from agent_framework_redis._context_provider import RedisContextProvider
from agent_framework_redis._history_provider import RedisHistoryProvider

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_index() -> AsyncMock:
    idx = AsyncMock()
    idx.create = AsyncMock()
    idx.load = AsyncMock()
    idx.query = AsyncMock(return_value=[])
    idx.exists = AsyncMock(return_value=False)
    return idx


@pytest.fixture
def patch_index_from_dict(mock_index: AsyncMock):
    with patch("agent_framework_redis._context_provider.AsyncSearchIndex") as mock_cls:
        mock_cls.from_dict = MagicMock(return_value=mock_index)

        async def mock_from_existing(index_name: str, redis_url: str):  # noqa: ARG001
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
            RedisContextProvider(source_id="ctx", user_id="u1", redis_vectorizer="bad")  # type: ignore[arg-type]


class TestRedisContextProviderValidateFilters:
    def test_no_filters_raises(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx")
        with pytest.raises(ServiceInitializationError, match="(?i)at least one"):
            provider._validate_filters()

    def test_any_single_filter_ok(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        for kwargs in [{"user_id": "u"}, {"agent_id": "a"}, {"application_id": "app"}]:
            provider = RedisContextProvider(source_id="ctx", **kwargs)
            provider._validate_filters()  # should not raise


class TestRedisContextProviderSchema:
    def test_schema_has_expected_fields(self, patch_index_from_dict: MagicMock):  # noqa: ARG002
        provider = RedisContextProvider(source_id="ctx", user_id="u1")
        schema = provider.schema_dict
        field_names = [f["name"] for f in schema["fields"]]
        for expected in ("role", "content", "conversation_id", "message_id", "application_id", "agent_id", "user_id"):
            assert expected in field_names
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
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
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
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_index.query.assert_not_called()
        assert "ctx" not in ctx.context_messages

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
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
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
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
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
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
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
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
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


# ===========================================================================
# RedisHistoryProvider tests
# ===========================================================================


class TestRedisHistoryProviderInit:
    def test_basic_construction(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("memory", redis_url="redis://localhost:6379")

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
                key_prefix="custom",
                max_messages=50,
                load_messages=False,
                store_outputs=False,
                store_inputs=False,
            )

        assert provider.key_prefix == "custom"
        assert provider.max_messages == 50
        assert provider.load_messages is False
        assert provider.store_outputs is False
        assert provider.store_inputs is False

    def test_no_redis_url_or_credential_raises(self):
        with pytest.raises(ValueError, match="Either redis_url or credential_provider must be provided"):
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

    def test_credential_provider_without_host_raises(self):
        mock_cred = MagicMock()
        with pytest.raises(ValueError, match="host is required"):
            RedisHistoryProvider("mem", credential_provider=mock_cred)

    def test_credential_provider_with_host(self):
        mock_cred = MagicMock()
        with patch("agent_framework_redis._history_provider.redis.Redis") as mock_redis_cls:
            mock_redis_cls.return_value = MagicMock()
            provider = RedisHistoryProvider("mem", credential_provider=mock_cred, host="myhost")

        mock_redis_cls.assert_called_once_with(
            host="myhost",
            port=6380,
            ssl=True,
            username=None,
            credential_provider=mock_cred,
            decode_responses=True,
        )
        assert provider.redis_url is None


class TestRedisHistoryProviderRedisKey:
    def test_key_format(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", key_prefix="msgs")

        assert provider._redis_key("session-123") == "msgs:session-123"
        assert provider._redis_key(None) == "msgs:default"


class TestRedisHistoryProviderGetMessages:
    async def test_returns_deserialized_messages(self, mock_redis_client: MagicMock):
        msg1 = Message(role="user", contents=["Hello"])
        msg2 = Message(role="assistant", contents=["Hi!"])
        mock_redis_client.lrange = AsyncMock(return_value=[json.dumps(msg1.to_dict()), json.dumps(msg2.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        messages = await provider.get_messages("s1")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].text == "Hi!"

    async def test_empty_returns_empty(self, mock_redis_client: MagicMock):
        mock_redis_client.lrange = AsyncMock(return_value=[])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        messages = await provider.get_messages("s1")
        assert messages == []


class TestRedisHistoryProviderSaveMessages:
    async def test_saves_serialized_messages(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        msgs = [Message(role="user", contents=["Hello"]), Message(role="assistant", contents=["Hi"])]
        await provider.save_messages("s1", msgs)

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 2
        pipeline.execute.assert_called_once()

    async def test_empty_messages_noop(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        await provider.save_messages("s1", [])
        mock_redis_client.pipeline.assert_not_called()

    async def test_max_messages_trimming(self, mock_redis_client: MagicMock):
        mock_redis_client.llen = AsyncMock(return_value=15)

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", max_messages=10)

        await provider.save_messages("s1", [Message(role="user", contents=["msg"])])

        mock_redis_client.ltrim.assert_called_once_with("chat_messages:s1", -10, -1)

    async def test_no_trim_when_under_limit(self, mock_redis_client: MagicMock):
        mock_redis_client.llen = AsyncMock(return_value=3)

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379", max_messages=10)

        await provider.save_messages("s1", [Message(role="user", contents=["msg"])])

        mock_redis_client.ltrim.assert_not_called()


class TestRedisHistoryProviderClear:
    async def test_clear_calls_delete(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        await provider.clear("session-1")
        mock_redis_client.delete.assert_called_once_with("chat_messages:session-1")


class TestRedisHistoryProviderBeforeAfterRun:
    """Test before_run/after_run integration via BaseHistoryProvider defaults."""

    async def test_before_run_loads_history(self, mock_redis_client: MagicMock):
        msg = Message(role="user", contents=["old msg"])
        mock_redis_client.lrange = AsyncMock(return_value=[json.dumps(msg.to_dict())])

        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["new msg"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert "mem" in ctx.context_messages
        assert len(ctx.context_messages["mem"]) == 1
        assert ctx.context_messages["mem"][0].text == "old msg"

    async def test_after_run_stores_input_and_response(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider("mem", redis_url="redis://localhost:6379")

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hello"])])

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        pipeline = mock_redis_client.pipeline.return_value.__aenter__.return_value
        assert pipeline.rpush.call_count == 2
        pipeline.execute.assert_called_once()

    async def test_after_run_skips_when_no_messages(self, mock_redis_client: MagicMock):
        with patch("agent_framework_redis._history_provider.redis.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            provider = RedisHistoryProvider(
                "mem", redis_url="redis://localhost:6379", store_inputs=False, store_outputs=False
            )

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_redis_client.pipeline.assert_not_called()
