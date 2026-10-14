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


def _provider(client: redis.Redis, *, borrowed: bool, **kwargs: Any) -> RedisContextProvider:
    provider = RedisContextProvider(**kwargs)
    if borrowed:
        # Borrowed indexes use RedisVL's default validate_on_load=False.
        index = AsyncSearchIndex.from_dict(provider.schema_dict, redis_client=client)
        provider = RedisContextProvider(redis_index=index, **kwargs)
    provider.redis_index.exists = AsyncMock(return_value=False)
    provider.redis_index.create = AsyncMock()
    return provider


def _capture_hash_writes(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    write = AsyncMock(wraps=HashStorage._aset)
    monkeypatch.setattr(HashStorage, "_aset", write)
    return write


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
    assert "message_id" not in record
    assert "author_name" not in record
    for key, value in scopes.items():
        assert record[key] == value
    if not all_scopes:
        assert "application_id" not in record
        assert "agent_id" not in record
    assert len(_TransportConnection.packets) == 1
    assert b"HSET" in _TransportConnection.packets[0]
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
    assert "application_id" not in record
    assert "thread_id" not in record
    assert "optional_metadata" not in record
    assert record["agent_id"] == "0"
    assert record["conversation_id"] == "0"
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
