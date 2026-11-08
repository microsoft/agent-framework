# Copyright (c) Microsoft. All rights reserved.

"""Exercise context writes through RedisVL and the Redis command encoder."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as redis
from agent_framework import AgentSession, Message, SessionContext
from redis.asyncio.connection import Connection
from redisvl.index import AsyncSearchIndex
from redisvl.index.storage import HashStorage
from redisvl.redis.utils import array_to_buffer
from redisvl.utils.vectorize import BaseVectorizer

from agent_framework_redis import RedisContextProvider
from agent_framework_redis._context_provider import _scope_token, _scope_token_field


class _TransportConnection(Connection):
    """Keep Redis command encoding real while replacing network transport."""

    packets: ClassVar[list[bytes]] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def can_read_destructive(self) -> bool:
        return False

    async def send_packed_command(self, command: bytes | str | Iterable[bytes], check_health: bool = True) -> None:
        if isinstance(command, str):
            packet = command.encode()
        elif isinstance(command, bytes):
            packet = command
        else:
            packet = b"".join(command)
        self.packets.append(packet)

    async def read_response(self, *args: Any, **kwargs: Any) -> int:
        return 1


@pytest.fixture
async def redis_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[redis.Redis]:
    _TransportConnection.packets = []
    client = redis.Redis(
        connection_pool=redis.ConnectionPool(connection_class=_TransportConnection, decode_responses=False)
    )
    monkeypatch.setattr(
        "redisvl.index.index.RedisConnectionFactory._get_aredis_connection", AsyncMock(return_value=client)
    )
    yield client
    await client.aclose()


def _provider(
    client: redis.Redis,
    *,
    borrowed: bool,
    **kwargs: Any,
) -> RedisContextProvider:
    provider = RedisContextProvider(**kwargs)
    if borrowed:
        index = AsyncSearchIndex.from_dict(provider.schema_dict, redis_client=client)
        provider = RedisContextProvider(redis_index=index, **kwargs)
    else:
        provider.redis_index._redis_client = client  # pyright: ignore[reportPrivateUsage]
    provider.redis_index.exists = AsyncMock(return_value=False)
    provider.redis_index.create = AsyncMock()
    object.__setattr__(provider, "_validate_schema_compatibility", AsyncMock())
    object.__setattr__(provider, "_existing_keys", AsyncMock(return_value=set()))
    return provider


def _capture_hash_writes(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    write = AsyncMock(wraps=HashStorage._aset)
    monkeypatch.setattr(HashStorage, "_aset", write)
    return write


@pytest.mark.asyncio
async def test_context_manager_closes_owned_index_only(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exiting the context manager closes the connection an owned index created and
    leaves a borrowed index under the caller's control."""
    closes = AsyncMock(wraps=redis_client.aclose)
    monkeypatch.setattr(redis_client, "aclose", closes)

    for borrowed, expected_waits in ((False, 1), (True, 0)):
        closes.reset_mock()
        provider = _provider(redis_client, borrowed=borrowed)
        async with provider:
            pass
        assert closes.await_count == expected_waits


@pytest.mark.parametrize("borrowed", [False, True], ids=["owned-index", "borrowed-index"])
@pytest.mark.parametrize("all_scopes", [False, True], ids=["user-scope", "all-scopes"])
async def test_after_run_encodes_messages_with_optional_fields_omitted(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch, borrowed: bool, all_scopes: bool
) -> None:
    scopes = {"user_id": "user-1"}
    if all_scopes:
        scopes.update(application_id="app-1", agent_id="agent-1")
    provider = _provider(redis_client, borrowed=borrowed, **scopes)
    write = _capture_hash_writes(monkeypatch)
    message = Message(role="user", contents=["Remember tea"])
    before = message.to_dict()
    session = AgentSession(session_id="session-1")
    context = SessionContext(session_id=session.session_id, input_messages=[message])

    await provider.after_run(agent=MagicMock(), session=session, context=context, state={})

    provider.redis_index.exists.assert_awaited_once()
    provider.redis_index.create.assert_awaited_once()
    write.assert_awaited_once()
    record = write.call_args.args[2]
    assert record["content"] == "Remember tea"
    assert record["user_id"] == "user-1"
    assert record["conversation_id"] == "session-1"
    assert record["thread_id"] == "session-1"
    assert record[_scope_token_field("user_id")] == _scope_token("user_id", "user-1")
    assert record[_scope_token_field("conversation_id")] == _scope_token("conversation_id", "session-1")
    assert record[_scope_token_field("thread_id")] == _scope_token("thread_id", "session-1")
    assert "message_id" not in record
    assert "author_name" not in record
    for key, value in scopes.items():
        assert record[key] == value
        assert record[_scope_token_field(key)] == _scope_token(key, value)
    if not all_scopes:
        assert "application_id" not in record
        assert "agent_id" not in record
    assert len(_TransportConnection.packets) == 1
    assert all(b"HSET" in packet for packet in _TransportConnection.packets)
    assert message.to_dict() == before


async def test_borrowed_index_omits_null_values_without_changing_nonnull_values_or_input(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _provider(
        redis_client,
        borrowed=True,
        application_id="configured-app",
        agent_id="configured-agent",
        user_id="user-1",
        vector_field_name="embedding",
    )
    write = _capture_hash_writes(monkeypatch)
    document = {
        "role": "user",
        "content": "Remember tea",
        "application_id": None,
        "agent_id": "0",
        "conversation_id": "0",
        "message_id": "0",
        "author_name": "",
        "mime_type": 0,
        "embedding": b"\x00\x00\x80?",
        "optional_metadata": None,
    }
    before = dict(document)

    await provider._add(data=document)

    record = write.call_args.args[2]
    assert record["application_id"] == "configured-app"
    assert record["agent_id"] == "configured-agent"
    assert record[_scope_token_field("application_id")] == _scope_token("application_id", "configured-app")
    assert record[_scope_token_field("agent_id")] == _scope_token("agent_id", "configured-agent")
    assert "thread_id" not in record
    assert "optional_metadata" not in record
    assert "conversation_id" not in record
    assert record["message_id"] == "0"
    assert record["author_name"] == ""
    assert record["mime_type"] == 0
    assert record["embedding"] == b"\x00\x00\x80?"
    assert len(_TransportConnection.packets) == 1
    assert document == before


async def test_borrowed_index_omits_unfilled_vector_placeholder(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _provider(redis_client, borrowed=True, user_id="user-1", vector_field_name="embedding")
    write = _capture_hash_writes(monkeypatch)
    document = {"role": "user", "content": "Remember tea"}

    await provider._add(data=document)

    record = write.call_args.args[2]
    assert "embedding" not in record
    assert "conversation_id" not in record
    assert "thread_id" not in record
    assert len(_TransportConnection.packets) == 1
    assert document == {"role": "user", "content": "Remember tea"}


async def test_borrowed_index_retains_generated_vector_buffer(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    vectorizer = MagicMock(spec=BaseVectorizer)
    vectorizer.dims = 2
    vectorizer.dtype = "float32"
    vectorizer.aembed_many = AsyncMock(return_value=[[1.0, 0.0]])
    provider = _provider(
        redis_client, borrowed=True, user_id="user-1", vector_field_name="embedding", redis_vectorizer=vectorizer
    )
    write = _capture_hash_writes(monkeypatch)
    document = {"role": "user", "content": "Remember tea", "embedding": None}
    before = dict(document)

    await provider._add(data=document)

    vectorizer.aembed_many.assert_awaited_once_with(["Remember tea"], batch_size=1)
    assert write.call_args.args[2]["embedding"] == array_to_buffer([1.0, 0.0], dtype="float32")
    assert len(_TransportConnection.packets) == 1
    assert document == before


async def test_after_run_does_not_store_replayed_input_messages(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replayed input messages are not stored again."""
    provider = _provider(redis_client, borrowed=True, user_id="user-1")
    write = _capture_hash_writes(monkeypatch)
    session = AgentSession(session_id="session-1")

    first_message = Message(role="user", contents=["First fact"])
    await provider.after_run(
        agent=MagicMock(),
        session=session,
        context=SessionContext(session_id=session.session_id, input_messages=[first_message]),
        state={},
    )
    assert write.await_count == 1

    first_key = provider._document_redis_key(role="user", content="First fact", session_id=session.session_id)
    object.__setattr__(provider, "_existing_keys", AsyncMock(return_value={first_key}))
    second_message = Message(role="user", contents=["Second fact"])
    await provider.after_run(
        agent=MagicMock(),
        session=session,
        context=SessionContext(
            session_id=session.session_id,
            input_messages=[first_message, second_message],
        ),
        state={},
    )

    assert write.await_count == 2
    written_contents = [call.args[2]["content"] for call in write.call_args_list]
    assert written_contents.count("First fact") == 1
    assert written_contents.count("Second fact") == 1


async def test_add_skips_embedding_for_already_stored_documents(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already-stored documents are skipped before the embedding call."""
    vectorizer = MagicMock(spec=BaseVectorizer)
    vectorizer.dims = 2
    vectorizer.dtype = "float32"
    vectorizer.aembed_many = AsyncMock(return_value=[[1.0, 0.0]])
    provider = _provider(
        redis_client,
        borrowed=True,
        user_id="user-1",
        vector_field_name="embedding",
        redis_vectorizer=vectorizer,
    )
    write = _capture_hash_writes(monkeypatch)

    document = {"role": "user", "content": "Remember tea"}
    key = provider._document_redis_key(role="user", content="Remember tea", session_id="session-1")
    object.__setattr__(provider, "_existing_keys", AsyncMock(return_value={key}))

    await provider._add(data=document, session_id="session-1")

    vectorizer.aembed_many.assert_not_awaited()
    write.assert_not_awaited()


async def test_add_deduplicates_within_a_single_batch(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same (scope, role, content) appearing twice in one batch is stored once."""
    provider = _provider(redis_client, borrowed=True, user_id="user-1")
    write = _capture_hash_writes(monkeypatch)

    documents = [
        {"role": "user", "content": "Duplicate fact"},
        {"role": "user", "content": "Duplicate fact"},
    ]
    await provider._add(data=documents, session_id="session-1")

    write.assert_awaited_once()


async def test_add_calls_existing_keys_with_candidate_keys(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_add checks Redis for existing keys before loading."""
    provider = _provider(redis_client, borrowed=True, user_id="user-1")
    existing_keys_mock = AsyncMock(return_value=set())
    object.__setattr__(provider, "_existing_keys", existing_keys_mock)
    _capture_hash_writes(monkeypatch)

    document = {"role": "user", "content": "Remember tea"}
    await provider._add(data=document, session_id="session-1")

    existing_keys_mock.assert_awaited_once()
    candidate_keys = existing_keys_mock.call_args.args[0]
    assert len(candidate_keys) == 1
    expected_key = provider._document_redis_key(role="user", content="Remember tea", session_id="session-1")
    assert candidate_keys[0] == expected_key


async def test_add_collapses_messages_with_same_content_but_different_message_ids(
    redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Messages with different message_ids but same scope/role/content share a key.

    The assistant reply comes back with a different id than the one stored
    , so the key must not depend on message_id.
    """
    provider = _provider(redis_client, borrowed=True, user_id="user-1")
    write = _capture_hash_writes(monkeypatch)

    documents = [
        {"role": "assistant", "content": "We deploy to westus3.", "message_id": "chatcmpl-abc"},
        {"role": "assistant", "content": "We deploy to westus3.", "message_id": "agui-stream-xyz"},
    ]
    await provider._add(data=documents, session_id="session-1")

    write.assert_awaited_once()


async def test_document_key_differs_across_scopes_roles_or_content(
    redis_client: redis.Redis,
) -> None:
    """The document key changes when scope, role, or content changes."""
    provider = _provider(redis_client, borrowed=True, user_id="user-1", application_id="app-1")
    base = provider._document_redis_key(role="user", content="We deploy to westus3.", session_id="session-1")
    different_session = provider._document_redis_key(
        role="user", content="We deploy to westus3.", session_id="session-2"
    )
    different_role = provider._document_redis_key(
        role="assistant", content="We deploy to westus3.", session_id="session-1"
    )
    different_content = provider._document_redis_key(
        role="user", content="We deploy to eastus2.", session_id="session-1"
    )
    assert len({base, different_session, different_role, different_content}) == 4


async def test_add_skips_whitespace_only_content(redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only content is skipped before hashing.

    Tool-call messages often have content == "" — without skipping, all of
    them with the same role would collapse to one key.
    """
    provider = _provider(redis_client, borrowed=True, user_id="user-1")
    write = _capture_hash_writes(monkeypatch)

    documents = [
        {"role": "user", "content": "   "},
        {"role": "assistant", "content": ""},
    ]
    await provider._add(data=documents, session_id="session-1")

    write.assert_not_awaited()


async def test_add_strips_content_before_keying(redis_client: redis.Redis, monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace differences do not produce a second copy.

    The replayed assistant text from AG-UI may differ slightly in
    whitespace from the stored model text — .strip() prevents a second copy.
    """
    provider = _provider(redis_client, borrowed=True, user_id="user-1")
    write = _capture_hash_writes(monkeypatch)

    documents = [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": "hi "},
    ]
    await provider._add(data=documents, session_id="session-1")

    write.assert_awaited_once()
