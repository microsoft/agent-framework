# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from functools import partial
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from agent_framework import SecretString, VectorStoreCollectionDefinition, VectorStoreField, load_settings
from redis.asyncio import Redis

from agent_framework_redis import RedisCollection, RedisSettings, RedisStore


@pytest.fixture(params=["collection", "store"])
def factory(request, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    if request.param == "store":
        return RedisStore
    return partial(
        RedisCollection,
        dict,
        definition=VectorStoreCollectionDefinition(fields=[VectorStoreField("key", name="id", type_="str")]),
        collection_name="settings",
    )


async def test_default_connection_settings(factory):
    async with factory() as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 6379
        assert kwargs["decode_responses"] is False
        assert kwargs["protocol"] == 2
        assert kwargs.get("db", 0) == 0
        assert kwargs.get("encoding", "utf-8") == "utf-8"
        assert kwargs.get("encoding_errors", "strict") == "strict"


async def test_connection_settings_from_environment(factory, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6380/0")
    async with factory() as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "environment"
        assert kwargs["port"] == 6380
        assert kwargs["db"] == 0


@pytest.mark.parametrize("override", ["redis://explicit:6381/0", SecretString("redis://explicit:6381/0")])
async def test_explicit_url_overrides_environment_and_file(factory, monkeypatch, tmp_path, override):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6380/0")
    env_file = tmp_path / "redis.env"
    env_file.write_text("REDIS_URL=redis://file:6382/0\n", encoding="utf-8")
    async with factory(redis_url=override, env_file_path=str(env_file)) as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "explicit"
        assert kwargs["port"] == 6381
        assert kwargs["db"] == 0


async def test_explicit_env_file_overrides_environment(factory, monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6380/0")
    env_file = tmp_path / "redis.env"
    env_file.write_text("REDIS_URL=redis://file:6382/0\n", encoding="utf-16")
    async with factory(redis_url=None, env_file_path=str(env_file), env_file_encoding="utf-16") as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "file"
        assert kwargs["port"] == 6382
        assert kwargs["db"] == 0


def test_explicit_missing_env_file_fails(factory, tmp_path):
    with pytest.raises(FileNotFoundError):
        factory(env_file_path=str(tmp_path / "missing.env"))


@pytest.mark.parametrize("url", ["", "not-a-redis-url"])
def test_invalid_url_does_not_fall_back_to_localhost(factory, monkeypatch, url):
    monkeypatch.setenv("REDIS_URL", url)
    with pytest.raises(ValueError):
        factory()


def test_invalid_url_override_type(factory):
    with pytest.raises(ValueError, match="url"):
        factory(redis_url=123)


@pytest.mark.parametrize("source", ["url", "borrowed"])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"encoding": "ascii", "encoding_errors": "ignore"},
        {"encoding": "latin-1"},
        {"encoding": "utf-8-sig"},
        {"encoding": "not-an-encoding"},
        {"encoding_errors": "ignore"},
        {"encoding_errors": "replace"},
        {"encoding_errors": "surrogatepass"},
    ],
)
async def test_incompatible_client_encoding_rejected_before_io(factory, source, kwargs):
    borrowed = Redis(**kwargs) if source == "borrowed" else None
    try:
        with (
            patch.object(Redis, "execute_command", new_callable=AsyncMock) as execute,
            patch.object(Redis, "aclose", new_callable=AsyncMock) as close,
        ):
            with pytest.raises(ValueError, match="strict UTF-8"):
                if borrowed is not None:
                    factory(redis_client=borrowed)
                else:
                    factory(redis_url=f"redis://localhost:6379?{urlencode(kwargs)}")
            execute.assert_not_awaited()
            close.assert_not_awaited()
    finally:
        if borrowed is not None:
            await borrowed.aclose()


@pytest.mark.parametrize("encoding", ["utf-8", "utf8", "UTF_8"])
async def test_strict_utf8_aliases_accepted(factory, encoding):
    async with factory(redis_url=f"redis://localhost:6379/0?encoding={encoding}&encoding_errors=strict") as owner:
        assert owner.redis_client.get_encoder().encode("a\u00e9b\u00e9c") == "a\u00e9b\u00e9c".encode()
    async with Redis(encoding=encoding) as borrowed, factory(redis_client=borrowed) as owner:
        assert owner.redis_client is borrowed
        assert borrowed.get_encoder().encode("a\u00e9b\u00e9c") != borrowed.get_encoder().encode("abc")


@pytest.mark.parametrize("source", ["path", "query", "borrowed"])
@pytest.mark.parametrize("db", [-1, 1, 2, 3, 4])
async def test_nonzero_database_rejected_before_io(factory, source, db):
    borrowed = Redis(db=db) if source == "borrowed" else None
    try:
        with (
            patch.object(Redis, "execute_command", new_callable=AsyncMock) as execute,
            patch.object(Redis, "aclose", new_callable=AsyncMock) as close,
        ):
            with pytest.raises(ValueError, match="require database 0"):
                if borrowed is not None:
                    factory(redis_client=borrowed)
                elif source == "path":
                    factory(redis_url=f"redis://localhost:6379/{db}")
                else:
                    factory(redis_url=f"redis://localhost:6379/0?db={db}")
            execute.assert_not_awaited()
            close.assert_not_awaited()
    finally:
        if borrowed is not None:
            await borrowed.aclose()


@pytest.mark.parametrize("url", ["redis://localhost:6379/0", "redis://localhost:6379/2?db=0"])
async def test_resolved_database_zero_accepted(factory, url):
    async with factory(redis_url=url) as owner:
        assert owner.redis_client.connection_pool.connection_kwargs["db"] == 0


async def test_borrowed_client_bypasses_settings_and_is_not_closed(factory, monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "invalid")
    borrowed = Redis(host="borrowed")
    with patch.object(borrowed, "aclose") as close:
        async with factory(redis_client=borrowed, env_file_path=str(tmp_path / "missing.env")) as owner:
            assert owner.redis_client is borrowed
        close.assert_not_awaited()
    await borrowed.aclose()


async def test_store_created_collection_reuses_resolved_client(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://initial:6380/0")
    async with RedisStore() as store:
        monkeypatch.setenv("REDIS_URL", "invalid")
        collection = store.get_collection(
            dict,
            definition=VectorStoreCollectionDefinition(fields=[VectorStoreField("key", name="id", type_="str")]),
            collection_name="settings",
        )
        assert collection.redis_client is store.redis_client
        assert collection.redis_client.connection_pool.connection_kwargs["host"] == "initial"


def test_settings_mask_credentials_and_export_namespace(monkeypatch):
    from agent_framework.redis import RedisSettings as NamespaceSettings

    from agent_framework_redis._vector_store import RedisSettings as ConnectorSettings

    monkeypatch.setenv("REDIS_URL", "redis://user:dummy-password@localhost:6379")
    settings = load_settings(RedisSettings, env_prefix="REDIS_")
    assert isinstance(settings["url"], SecretString)
    assert "dummy-password" not in repr(settings)
    assert settings["url"].get_secret_value() == "redis://user:dummy-password@localhost:6379"
    assert NamespaceSettings is RedisSettings
    assert ConnectorSettings is RedisSettings
