# Copyright (c) Microsoft. All rights reserved.

"""Live Redis isolation coverage for ``RedisContextProvider``."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redisvl.index import AsyncSearchIndex
from redisvl.utils.vectorize import BaseVectorizer

from agent_framework_redis import RedisContextProvider
from agent_framework_redis._context_provider import _scope_token_field


@pytest.fixture
async def live_redis() -> AsyncIterator[tuple[str, Redis, str, str]]:
    url = os.getenv("REDIS_VECTOR_TEST_URL")
    if not url:
        pytest.skip("Set REDIS_VECTOR_TEST_URL to a disposable Redis Search server.")
    suffix = uuid4().hex
    index_name = f"af-context-test-{suffix}"
    prefix = f"af-context-test-[*]-{suffix}:"
    client = Redis.from_url(url)
    try:
        yield url, client, index_name, prefix
    finally:
        indexes = cast(list[bytes], await client.execute_command("FT._LIST"))
        encoded_name = index_name.encode()
        if encoded_name in indexes or index_name in indexes:
            await client.execute_command("FT.DROPINDEX", index_name)
        encoded_prefix = prefix.encode()
        keys = [
            key
            async for key in client.scan_iter(_type="hash")
            if (key if isinstance(key, bytes) else str(key).encode()).startswith(encoded_prefix)
        ]
        if keys:
            await client.delete(*keys)
        await client.aclose()


def _provider(
    url: str,
    index_name: str,
    prefix: str,
    *,
    application_id: str = "app",
    agent_id: str = "agent",
    user_id: str = "user",
    **kwargs: Any,
) -> RedisContextProvider:
    return RedisContextProvider(
        redis_url=url,
        index_name=index_name,
        prefix=prefix,
        application_id=application_id,
        agent_id=agent_id,
        user_id=user_id,
        **kwargs,
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("victim_id", "other_id"),
    [
        ("Alice", "alice"),
        ("a,b", "a"),
        ("victim", "x|victim"),
        (r"a,b|c\ d{}*", r"a,b|c\ d{}?"),
    ],
)
async def test_live_user_scope_preserves_exact_identity(
    live_redis: tuple[str, Redis, str, str], victim_id: str, other_id: str
) -> None:
    url, _, index_name, prefix = live_redis
    victim = _provider(url, index_name, prefix, user_id=victim_id)
    other = _provider(url, index_name, prefix, user_id=other_id)

    await victim._add(data={"content": "shared marker victim memory"}, session_id="victim-session")

    assert [item["content"] for item in await victim._redis_search("shared marker")] == ["shared marker victim memory"]
    assert await other._redis_search("shared marker") == []
    assert len(await victim.search_all()) == 1
    assert await other.search_all() == []


@pytest.mark.integration
@pytest.mark.parametrize("scope_name", ["application_id", "agent_id", "user_id"])
async def test_live_each_provider_scope_is_independent(
    live_redis: tuple[str, Redis, str, str], scope_name: str
) -> None:
    url, _, index_name, prefix = live_redis
    victim_scopes = {"application_id": "app", "agent_id": "agent", "user_id": "user"}
    other_scopes = dict(victim_scopes)
    other_scopes[scope_name] = victim_scopes[scope_name] + ",other|scope"
    victim = _provider(url, index_name, prefix, **victim_scopes)
    other = _provider(url, index_name, prefix, **other_scopes)

    await victim._add(data={"content": f"scope marker {scope_name}"}, session_id="session")

    assert len(await victim._redis_search(f"scope marker {scope_name}")) == 1
    assert await other._redis_search(f"scope marker {scope_name}") == []


@pytest.mark.integration
async def test_live_session_scopes_and_document_overrides_are_provider_owned(
    live_redis: tuple[str, Redis, str, str],
) -> None:
    url, client, index_name, prefix = live_redis
    provider = _provider(url, index_name, prefix, user_id="authoritative-user")
    await provider._add(
        data={
            "content": "session marker",
            "application_id": "caller-app",
            "agent_id": "caller-agent",
            "user_id": "caller-user",
            "thread_id": "caller-thread",
            "conversation_id": "caller-conversation",
            _scope_token_field("user_id"): "caller-token",
        },
        session_id="authoritative-session",
    )

    assert len(await provider._redis_search("session marker", session_id="authoritative-session")) == 1
    assert await provider._redis_search("session marker", session_id="other-session") == []
    caller = _provider(
        url, index_name, prefix, application_id="caller-app", agent_id="caller-agent", user_id="caller-user"
    )
    assert await caller._redis_search("session marker") == []

    encoded_prefix = prefix.encode()
    keys = [
        key
        async for key in client.scan_iter(_type="hash")
        if (key if isinstance(key, bytes) else str(key).encode()).startswith(encoded_prefix)
    ]
    assert len(keys) == 1
    key = keys[0].decode() if isinstance(keys[0], bytes) else str(keys[0])
    record = await cast(Awaitable[dict[bytes, bytes]], client.hgetall(key))
    assert record[b"application_id"] == b"app"
    assert record[b"agent_id"] == b"agent"
    assert record[b"user_id"] == b"authoritative-user"
    assert record[b"thread_id"] == b"authoritative-session"
    assert record[b"conversation_id"] == b"authoritative-session"
    assert record[_scope_token_field("user_id").encode()] != b"caller-token"


@pytest.mark.integration
async def test_live_hybrid_search_preserves_scope_isolation(
    live_redis: tuple[str, Redis, str, str],
) -> None:
    url, _, index_name, prefix = live_redis
    vectorizer = MagicMock(spec=BaseVectorizer)
    vectorizer.dims = 2
    vectorizer.dtype = "float32"
    vectorizer.aembed_many = AsyncMock(return_value=[[1.0, 0.0]])
    vectorizer.aembed = AsyncMock(return_value=[1.0, 0.0])
    victim = _provider(
        url,
        index_name,
        prefix,
        user_id="victim",
        redis_vectorizer=vectorizer,
        vector_field_name="embedding",
    )
    other = _provider(
        url,
        index_name,
        prefix,
        user_id="x|victim",
        redis_vectorizer=vectorizer,
        vector_field_name="embedding",
    )

    await victim._add(data={"content": "hybrid marker"}, session_id="session")

    assert len(await victim._redis_search("hybrid marker")) == 1
    assert await other._redis_search("hybrid marker") == []


@pytest.mark.integration
async def test_live_legacy_index_fails_closed_until_recreated(
    live_redis: tuple[str, Redis, str, str],
) -> None:
    url, client, index_name, prefix = live_redis
    legacy_schema = {
        "index": {"name": index_name, "prefix": prefix, "key_separator": ":", "storage_type": "hash"},
        "fields": [
            {"name": "content", "type": "text"},
            {"name": "application_id", "type": "tag"},
            {"name": "agent_id", "type": "tag"},
            {"name": "user_id", "type": "tag"},
            {"name": "thread_id", "type": "tag"},
            {"name": "conversation_id", "type": "tag"},
        ],
    }
    legacy_index = AsyncSearchIndex.from_dict(legacy_schema, redis_client=client)
    await legacy_index.create()
    await legacy_index.load([
        {
            "content": "migration marker",
            "application_id": "app",
            "agent_id": "agent",
            "user_id": "Alice",
            "thread_id": "session",
            "conversation_id": "session",
        }
    ])
    adjacent_key = f"{prefix.rstrip(':')}-other:foreign"
    await cast(
        Awaitable[int],
        client.hset(adjacent_key, mapping={"content": "foreign", "user_id": "Alice"}),
    )

    for overwrite_index in (False, True):
        incompatible = _provider(
            url,
            index_name,
            prefix,
            user_id="Alice",
            overwrite_index=overwrite_index,
        )
        with pytest.raises(ValueError, match="Delete the existing index and its context hashes"):
            await incompatible._redis_search("migration marker")

    await legacy_index.delete(drop=True)
    recreated = _provider(url, index_name, prefix, user_id="Alice")
    await recreated._add(data={"content": "re-ingested marker"}, session_id="session")

    assert len(await recreated._redis_search("re-ingested marker")) == 1
    assert await _provider(url, index_name, prefix, user_id="alice")._redis_search("re-ingested marker") == []
    adjacent_record = await cast(Awaitable[dict[bytes, bytes]], client.hgetall(adjacent_key))
    assert adjacent_record[b"content"] == b"foreign"
