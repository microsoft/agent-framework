# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from functools import partial
from unittest.mock import patch

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


async def test_connection_settings_from_environment(factory, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6380/2")
    async with factory() as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "environment"
        assert kwargs["port"] == 6380
        assert kwargs["db"] == 2


@pytest.mark.parametrize("override", ["redis://explicit:6381/3", SecretString("redis://explicit:6381/3")])
async def test_explicit_url_overrides_environment_and_file(factory, monkeypatch, tmp_path, override):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6380/2")
    env_file = tmp_path / "redis.env"
    env_file.write_text("REDIS_URL=redis://file:6382/4\n", encoding="utf-8")
    async with factory(redis_url=override, env_file_path=str(env_file)) as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "explicit"
        assert kwargs["port"] == 6381
        assert kwargs["db"] == 3


async def test_explicit_env_file_overrides_environment(factory, monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "redis://environment:6380/2")
    env_file = tmp_path / "redis.env"
    env_file.write_text("REDIS_URL=redis://file:6382/4\n", encoding="utf-16")
    async with factory(redis_url=None, env_file_path=str(env_file), env_file_encoding="utf-16") as owner:
        kwargs = owner.redis_client.connection_pool.connection_kwargs
        assert kwargs["host"] == "file"
        assert kwargs["port"] == 6382
        assert kwargs["db"] == 4


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


async def test_borrowed_client_bypasses_settings_and_is_not_closed(factory, monkeypatch, tmp_path):
    monkeypatch.setenv("REDIS_URL", "invalid")
    borrowed = Redis(host="borrowed")
    with patch.object(borrowed, "aclose") as close:
        async with factory(redis_client=borrowed, env_file_path=str(tmp_path / "missing.env")) as owner:
            assert owner.redis_client is borrowed
        close.assert_not_awaited()
    await borrowed.aclose()


async def test_store_created_collection_reuses_resolved_client(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://initial:6380/2")
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
