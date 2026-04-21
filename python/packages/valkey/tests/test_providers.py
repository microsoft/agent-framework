# Copyright (c) Microsoft. All rights reserved.

"""Tests for ValkeyContextProvider and ValkeyChatMessageStore."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from agent_framework import AgentResponse, Message
from agent_framework._sessions import AgentSession, SessionContext
from agent_framework.exceptions import IntegrationInvalidRequestException

np = pytest.importorskip("numpy")

from agent_framework_valkey._chat_message_store import ValkeyChatMessageStore
from agent_framework_valkey._context_provider import ValkeyContextProvider

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_glide_client() -> AsyncMock:
    """Create a mock GlideClient for testing."""
    client = AsyncMock()
    client.lrange = AsyncMock(return_value=[])
    client.llen = AsyncMock(return_value=0)
    client.ltrim = AsyncMock()
    client.rpush = AsyncMock()
    client.delete = AsyncMock()
    client.hset = AsyncMock()
    client.custom_command = AsyncMock(return_value=[0])
    client.close = AsyncMock()
    return client


# ===========================================================================
# ValkeyChatMessageStore tests
# ===========================================================================


class TestValkeyChatMessageStoreInit:
    def test_basic_construction(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(source_id="mem", client=mock_glide_client)
        assert store.source_id == "mem"
        assert store.key_prefix == "chat_messages"
        assert store.max_messages is None
        assert store.load_messages is True
        assert store.store_outputs is True
        assert store.store_inputs is True

    def test_custom_params(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(
            source_id="mem",
            client=mock_glide_client,
            key_prefix="custom",
            max_messages=50,
            load_messages=False,
            store_outputs=False,
            store_inputs=False,
        )
        assert store.key_prefix == "custom"
        assert store.max_messages == 50
        assert store.load_messages is False
        assert store.store_outputs is False
        assert store.store_inputs is False

    def test_default_source_id(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)
        assert store.source_id == "valkey_memory"

    def test_mutually_exclusive_url_and_host_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ValkeyChatMessageStore(valkey_url="valkey://other:6380", host="myhost", port=6380)

    def test_mutually_exclusive_url_and_default_host_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ValkeyChatMessageStore(valkey_url="valkey://other:6380", host="localhost", port=6379)


class TestValkeyChatMessageStoreKey:
    def test_key_format(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client, key_prefix="msgs")
        assert store._valkey_key("session-123") == "msgs:session-123"
        assert store._valkey_key(None) == "msgs:default"


class TestValkeyChatMessageStoreParseUrl:
    def test_parse_valkey_url(self) -> None:
        host, port = ValkeyChatMessageStore._parse_url("valkey://myhost:6380")
        assert host == "myhost"
        assert port == 6380

    def test_parse_redis_url(self) -> None:
        host, port = ValkeyChatMessageStore._parse_url("redis://localhost:6379")
        assert host == "localhost"
        assert port == 6379

    def test_parse_url_defaults(self) -> None:
        host, port = ValkeyChatMessageStore._parse_url("valkey://")
        assert host == "localhost"
        assert port == 6379


class TestValkeyChatMessageStoreGetMessages:
    async def test_returns_deserialized_messages(self, mock_glide_client: AsyncMock) -> None:
        msg1 = Message(role="user", contents=["Hello"])
        msg2 = Message(role="assistant", contents=["Hi!"])
        mock_glide_client.lrange = AsyncMock(return_value=[json.dumps(msg1.to_dict()), json.dumps(msg2.to_dict())])
        store = ValkeyChatMessageStore(client=mock_glide_client)

        messages = await store.get_messages("s1")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].text == "Hi!"

    async def test_handles_bytes_response(self, mock_glide_client: AsyncMock) -> None:
        msg = Message(role="user", contents=["Hello"])
        mock_glide_client.lrange = AsyncMock(return_value=[json.dumps(msg.to_dict()).encode("utf-8")])
        store = ValkeyChatMessageStore(client=mock_glide_client)

        messages = await store.get_messages("s1")
        assert len(messages) == 1
        assert messages[0].text == "Hello"

    async def test_empty_returns_empty(self, mock_glide_client: AsyncMock) -> None:
        mock_glide_client.lrange = AsyncMock(return_value=[])
        store = ValkeyChatMessageStore(client=mock_glide_client)

        messages = await store.get_messages("s1")
        assert messages == []


class TestValkeyChatMessageStoreSaveMessages:
    async def test_saves_batched_messages(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)
        msgs = [Message(role="user", contents=["Hello"]), Message(role="assistant", contents=["Hi"])]

        await store.save_messages("s1", msgs)

        # Single batched rpush call
        mock_glide_client.rpush.assert_called_once()
        call_args = mock_glide_client.rpush.call_args[0]
        assert call_args[0] == "chat_messages:s1"
        assert len(call_args[1]) == 2

    async def test_empty_messages_noop(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)

        await store.save_messages("s1", [])
        mock_glide_client.rpush.assert_not_called()

    async def test_max_messages_trimming(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client, max_messages=10)

        await store.save_messages("s1", [Message(role="user", contents=["msg"])])

        # LTRIM is always called unconditionally when max_messages is set
        mock_glide_client.ltrim.assert_called_once_with("chat_messages:s1", -10, -1)
        # No LLEN roundtrip needed
        mock_glide_client.llen.assert_not_called()

    async def test_no_trim_when_no_max(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)

        await store.save_messages("s1", [Message(role="user", contents=["msg"])])

        mock_glide_client.ltrim.assert_not_called()


class TestValkeyChatMessageStoreClear:
    async def test_clear_calls_delete(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)

        await store.clear("session-1")
        mock_glide_client.delete.assert_called_once_with(["chat_messages:session-1"])

    async def test_clear_none_session_uses_default(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)

        await store.clear(None)
        mock_glide_client.delete.assert_called_once_with(["chat_messages:default"])


class TestValkeyChatMessageStoreContextManager:
    async def test_aenter_returns_self(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)
        async with store as s:
            assert s is store


class TestValkeyChatMessageStoreBeforeAfterRun:
    """Test before_run/after_run integration via HistoryProvider defaults."""

    async def test_before_run_loads_history(self, mock_glide_client: AsyncMock) -> None:
        msg = Message(role="user", contents=["old msg"])
        mock_glide_client.lrange = AsyncMock(return_value=[json.dumps(msg.to_dict())])
        store = ValkeyChatMessageStore(client=mock_glide_client)

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["new msg"])], session_id="s1")

        await store.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(store.source_id, {})
        )  # type: ignore[arg-type]

        assert store.source_id in ctx.context_messages
        assert len(ctx.context_messages[store.source_id]) == 1
        assert ctx.context_messages[store.source_id][0].text == "old msg"

    async def test_after_run_stores_input_and_response(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client)

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")
        ctx._response = AgentResponse(messages=[Message(role="assistant", contents=["hello"])])

        await store.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(store.source_id, {})
        )  # type: ignore[arg-type]

        # Batched into single rpush call
        mock_glide_client.rpush.assert_called_once()

    async def test_after_run_skips_when_no_messages(self, mock_glide_client: AsyncMock) -> None:
        store = ValkeyChatMessageStore(client=mock_glide_client, store_inputs=False, store_outputs=False)

        session = AgentSession(session_id="test")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hi"])], session_id="s1")

        await store.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(store.source_id, {})
        )  # type: ignore[arg-type]

        mock_glide_client.rpush.assert_not_called()


# ===========================================================================
# ValkeyContextProvider tests
# ===========================================================================


class TestValkeyContextProviderInit:
    def test_basic_construction(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        assert provider.source_id == "ctx"
        assert provider.user_id == "u1"
        assert provider.host == "localhost"
        assert provider.port == 6379
        assert provider.index_name == "context_idx"
        assert provider.prefix == "context:"

    def test_custom_params(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(
            source_id="ctx",
            host="custom-host",
            port=6380,
            index_name="my_idx",
            prefix="my_prefix:",
            application_id="app1",
            agent_id="agent1",
            user_id="user1",
            context_prompt="Custom prompt",
            client=mock_glide_client,
        )
        assert provider.host == "custom-host"
        assert provider.port == 6380
        assert provider.index_name == "my_idx"
        assert provider.prefix == "my_prefix:"
        assert provider.application_id == "app1"
        assert provider.agent_id == "agent1"
        assert provider.context_prompt == "Custom prompt"

    def test_default_context_prompt(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        assert "Memories" in provider.context_prompt

    def test_valkey_url_support(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(
            source_id="ctx", user_id="u1", valkey_url="valkey://myhost:6380", client=mock_glide_client
        )
        assert provider.valkey_url == "valkey://myhost:6380"

    def test_mutually_exclusive_url_and_host_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ValkeyContextProvider(
                source_id="ctx", user_id="u1", valkey_url="valkey://other:6380", host="myhost", port=6380
            )

    def test_mutually_exclusive_url_and_default_host_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            ValkeyContextProvider(
                source_id="ctx", user_id="u1", valkey_url="valkey://other:6380", host="localhost", port=6379
            )

    def test_embed_fn_requires_vector_config(self, mock_glide_client: AsyncMock) -> None:
        mock_embed = AsyncMock(return_value=[0.1] * 128)
        with pytest.raises(ValueError, match="vector_field_name and vector_dims are required"):
            ValkeyContextProvider(
                source_id="ctx", user_id="u1", client=mock_glide_client, embed_fn=mock_embed
            )

    def test_embed_fn_requires_positive_dims(self, mock_glide_client: AsyncMock) -> None:
        mock_embed = AsyncMock(return_value=[0.1] * 128)
        with pytest.raises(ValueError, match="vector_dims must be a positive integer"):
            ValkeyContextProvider(
                source_id="ctx",
                user_id="u1",
                client=mock_glide_client,
                embed_fn=mock_embed,
                vector_field_name="embedding",
                vector_dims=0,
            )


class TestValkeyContextProviderValidateFilters:
    def test_no_filters_raises(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", client=mock_glide_client)
        with pytest.raises(ValueError, match="(?i)at least one"):
            provider._validate_filters()

    def test_any_single_filter_ok(self, mock_glide_client: AsyncMock) -> None:
        for kwargs in [{"user_id": "u"}, {"agent_id": "a"}, {"application_id": "app"}]:
            provider = ValkeyContextProvider(source_id="ctx", client=mock_glide_client, **kwargs)
            provider._validate_filters()  # should not raise


class TestValkeyContextProviderBeforeRun:
    async def test_search_results_added_to_context(self, mock_glide_client: AsyncMock) -> None:
        mock_glide_client.custom_command = AsyncMock(
            return_value=[2, b"doc:1", [b"content", b"Memory A"], b"doc:2", [b"content", b"Memory B"]]
        )
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
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

    async def test_empty_input_no_search(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["   "])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_glide_client.custom_command.assert_not_called()
        assert "ctx" not in ctx.context_messages

    async def test_empty_results_no_messages(self, mock_glide_client: AsyncMock) -> None:
        mock_glide_client.custom_command = AsyncMock(return_value=[0])
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.before_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert "ctx" not in ctx.context_messages


class TestValkeyContextProviderAfterRun:
    async def test_stores_messages(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        session = AgentSession(session_id="test-session")
        response = AgentResponse(messages=[Message(role="assistant", contents=["response text"])])
        ctx = SessionContext(input_messages=[Message(role="user", contents=["user input"])], session_id="s1")
        ctx._response = response

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert mock_glide_client.hset.call_count == 2

    async def test_skips_empty_conversations(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["   "])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        mock_glide_client.hset.assert_not_called()

    async def test_stores_partition_fields(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(
            source_id="ctx", application_id="app", agent_id="ag", user_id="u1", client=mock_glide_client
        )
        session = AgentSession(session_id="test-session")
        ctx = SessionContext(input_messages=[Message(role="user", contents=["hello"])], session_id="s1")

        await provider.after_run(
            agent=None, session=session, context=ctx, state=session.state.setdefault(provider.source_id, {})
        )  # type: ignore[arg-type]

        assert mock_glide_client.hset.call_count == 1
        field_dict = mock_glide_client.hset.call_args[0][1]
        assert field_dict["application_id"] == "app"
        assert field_dict["agent_id"] == "ag"
        assert field_dict["user_id"] == "u1"


class TestValkeyContextProviderContextManager:
    async def test_aenter_returns_self(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        async with provider as p:
            assert p is provider

    async def test_aclose_closes_owned_client(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        # Simulate owned client
        provider._owns_client = True
        await provider.aclose()
        mock_glide_client.close.assert_called_once()
        assert provider._client is None


class TestValkeyContextProviderEnsureIndex:
    async def test_creates_index_on_first_call(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        await provider._ensure_index()

        mock_glide_client.custom_command.assert_called_once()
        cmd_args = mock_glide_client.custom_command.call_args[0][0]
        assert cmd_args[0] == "FT.CREATE"
        assert provider._index_created is True

    async def test_skips_on_subsequent_calls(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        await provider._ensure_index()
        await provider._ensure_index()

        assert mock_glide_client.custom_command.call_count == 1

    async def test_handles_index_already_exists(self, mock_glide_client: AsyncMock) -> None:
        mock_glide_client.custom_command = AsyncMock(side_effect=Exception("Index already exists"))
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)

        await provider._ensure_index()  # should not raise
        assert provider._index_created is True

    async def test_includes_vector_field_in_schema(self, mock_glide_client: AsyncMock) -> None:
        mock_embed = AsyncMock(return_value=[0.1] * 128)
        provider = ValkeyContextProvider(
            source_id="ctx",
            user_id="u1",
            client=mock_glide_client,
            embed_fn=mock_embed,
            vector_field_name="embedding",
            vector_dims=128,
        )
        await provider._ensure_index()

        cmd_args = mock_glide_client.custom_command.call_args[0][0]
        assert "embedding" in cmd_args
        assert "VECTOR" in cmd_args
        assert "128" in cmd_args


class TestValkeyContextProviderHybridSearch:
    """Tests for the vector/hybrid search path (embed_fn provided)."""

    async def test_add_stores_raw_bytes_embedding(self, mock_glide_client: AsyncMock) -> None:
        mock_embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        provider = ValkeyContextProvider(
            source_id="ctx",
            user_id="u1",
            client=mock_glide_client,
            embed_fn=mock_embed,
            vector_field_name="embedding",
            vector_dims=3,
        )

        await provider._add(data=[{"content": "test", "role": "user"}])

        mock_embed.assert_called_once_with("test")
        # Verify the embedding is stored as raw bytes, not hex string
        hset_call = mock_glide_client.hset.call_args[0]
        field_map = hset_call[1]
        stored_embedding = field_map["embedding"]
        assert isinstance(stored_embedding, bytes)
        expected = np.asarray([0.1, 0.2, 0.3], dtype=np.float32).tobytes()
        assert stored_embedding == expected

    async def test_search_passes_raw_bytes_vector(self, mock_glide_client: AsyncMock) -> None:
        mock_embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
        mock_glide_client.custom_command = AsyncMock(return_value=[0])
        provider = ValkeyContextProvider(
            source_id="ctx",
            user_id="u1",
            client=mock_glide_client,
            embed_fn=mock_embed,
            vector_field_name="embedding",
            vector_dims=3,
        )
        provider._index_created = True

        await provider._search(text="test query")

        # Verify FT.SEARCH was called with raw bytes in PARAMS
        search_call = mock_glide_client.custom_command.call_args[0][0]
        assert search_call[0] == "FT.SEARCH"
        # Find the "vec" param value (follows "vec" in the args)
        vec_idx = search_call.index("vec") + 1
        vec_value = search_call[vec_idx]
        assert isinstance(vec_value, bytes)

    async def test_hybrid_search_constructs_knn_query(self, mock_glide_client: AsyncMock) -> None:
        mock_embed = AsyncMock(return_value=[0.1] * 128)
        mock_glide_client.custom_command = AsyncMock(return_value=[1, b"doc:1", [b"content", b"result"]])
        provider = ValkeyContextProvider(
            source_id="ctx",
            user_id="u1",
            client=mock_glide_client,
            embed_fn=mock_embed,
            vector_field_name="embedding",
            vector_dims=128,
        )
        provider._index_created = True

        results = await provider._search(text="test")

        search_call = mock_glide_client.custom_command.call_args[0][0]
        query_str = search_call[2]
        assert "KNN" in query_str
        assert "@embedding" in query_str
        assert len(results) == 1
        assert results[0]["content"] == "result"


class TestValkeyContextProviderSearchErrors:
    async def test_empty_text_raises_directly(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        provider._index_created = True

        with pytest.raises(IntegrationInvalidRequestException, match="non-empty text"):
            await provider._search(text="")

    async def test_connection_error_wrapped(self, mock_glide_client: AsyncMock) -> None:
        # First call succeeds (FT.CREATE), second fails (FT.SEARCH)
        mock_glide_client.custom_command = AsyncMock(side_effect=[None, ConnectionError("connection lost")])
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)

        with pytest.raises(IntegrationInvalidRequestException, match="Valkey search failed"):
            await provider._search(text="test")

    async def test_direct_integration_exception_not_double_wrapped(self, mock_glide_client: AsyncMock) -> None:
        provider = ValkeyContextProvider(source_id="ctx", user_id="u1", client=mock_glide_client)
        provider._index_created = True

        # Empty text should raise IntegrationInvalidRequestException directly, not wrapped
        with pytest.raises(IntegrationInvalidRequestException, match="non-empty text"):
            await provider._search(text="   ")


class TestValkeyContextProviderParseResults:
    def test_parse_empty_results(self) -> None:
        assert ValkeyContextProvider._parse_search_results([0]) == []
        assert ValkeyContextProvider._parse_search_results(None) == []
        assert ValkeyContextProvider._parse_search_results([]) == []

    def test_parse_results_with_docs(self) -> None:
        result = [2, b"doc:1", [b"content", b"Hello"], b"doc:2", [b"content", b"World"]]
        docs = ValkeyContextProvider._parse_search_results(result)
        assert len(docs) == 2
        assert docs[0]["content"] == "Hello"
        assert docs[1]["content"] == "World"

    def test_parse_results_with_string_fields(self) -> None:
        result = [1, "doc:1", ["content", "Hello", "role", "user"]]
        docs = ValkeyContextProvider._parse_search_results(result)
        assert len(docs) == 1
        assert docs[0]["content"] == "Hello"
        assert docs[0]["role"] == "user"


class TestValkeyContextProviderEscaping:
    def test_escape_tag(self) -> None:
        assert ValkeyContextProvider._escape_tag("simple") == "simple"
        assert "\\" in ValkeyContextProvider._escape_tag("has space")
        assert "\\" in ValkeyContextProvider._escape_tag("has@special")

    def test_escape_query(self) -> None:
        assert ValkeyContextProvider._escape_query("simple text") == "simple text"
        assert "\\" in ValkeyContextProvider._escape_query("@mention")
