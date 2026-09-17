# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from functools import partial
from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import SecretString, load_settings
from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from agent_framework_mongodb import MongoDBCollection, MongoDBSettings, MongoDBStore


@pytest.fixture(params=["collection", "store"])
def connector_factory(request, definition):
    if request.param == "collection":
        return partial(MongoDBCollection, dict, definition=definition, collection_name="test")
    return MongoDBStore


def _client_mock():
    client = AsyncMock(spec=AsyncMongoClient)
    database = AsyncMock(spec=AsyncDatabase)
    database.get_collection.return_value = AsyncMock(spec=AsyncCollection)
    client.get_database.return_value = database
    return client


def test_settings_mask_uri(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://user:password@example.test")
    monkeypatch.setenv("MONGODB_DATABASE_NAME", "vectors")
    settings = load_settings(MongoDBSettings, env_prefix="MONGODB_")
    uri = settings["uri"]
    assert isinstance(uri, SecretString)
    assert uri.get_secret_value() == "mongodb://user:password@example.test"
    assert "password" not in repr(settings)


async def test_environment_settings_and_owned_close(connector_factory, monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://environment.test")
    monkeypatch.setenv("MONGODB_DATABASE_NAME", "environment_db")
    monkeypatch.setenv("MONGODB_APP_NAME", "environment-app")
    client = _client_mock()
    with patch("agent_framework_mongodb._vector_store.AsyncMongoClient", return_value=client) as factory:
        async with connector_factory():
            pass
    factory.assert_called_once_with("mongodb://environment.test", appname="environment-app")
    client.get_database.assert_called_once_with("environment_db")
    client.close.assert_awaited_once()


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
async def test_env_file_overrides_environment(connector_factory, monkeypatch, tmp_path, encoding):
    monkeypatch.setenv("MONGODB_URI", "mongodb://environment.test")
    monkeypatch.setenv("MONGODB_DATABASE_NAME", "environment_db")
    env_file = tmp_path / "mongodb.env"
    env_file.write_text(
        "MONGODB_URI=mongodb://file.test\nMONGODB_DATABASE_NAME=file_db\nMONGODB_APP_NAME=file-app\n",
        encoding=encoding,
    )
    client = _client_mock()
    with patch("agent_framework_mongodb._vector_store.AsyncMongoClient", return_value=client) as factory:
        async with connector_factory(env_file_path=str(env_file), env_file_encoding=encoding):
            pass
    factory.assert_called_once_with("mongodb://file.test", appname="file-app")
    client.get_database.assert_called_once_with("file_db")


async def test_explicit_settings_override_file_and_environment(connector_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("MONGODB_URI", "mongodb://environment.test")
    monkeypatch.setenv("MONGODB_DATABASE_NAME", "environment_db")
    env_file = tmp_path / "mongodb.env"
    env_file.write_text("MONGODB_URI=mongodb://file.test\nMONGODB_DATABASE_NAME=file_db\n")
    client = _client_mock()
    with patch("agent_framework_mongodb._vector_store.AsyncMongoClient", return_value=client) as factory:
        async with connector_factory(
            uri=SecretString("mongodb://explicit.test"),
            database_name="explicit_db",
            app_name="explicit-app",
            env_file_path=str(env_file),
        ):
            pass
    factory.assert_called_once_with("mongodb://explicit.test", appname="explicit-app")
    client.get_database.assert_called_once_with("explicit_db")


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"uri": "mongodb://localhost"},
        {"database_name": "vectors"},
        {"uri": "", "database_name": "vectors"},
        {"uri": "mongodb://localhost", "database_name": ""},
    ],
)
def test_required_settings_fail_before_sdk_creation(connector_factory, settings):
    with (
        patch("agent_framework_mongodb._vector_store.AsyncMongoClient") as factory,
        pytest.raises(ValueError),
    ):
        connector_factory(**settings)
    factory.assert_not_called()


async def test_injected_client_bypasses_settings_and_remains_borrowed(connector_factory, monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://unrelated.test")
    monkeypatch.setenv("MONGODB_DATABASE_NAME", "unrelated")
    client = _client_mock()
    with patch("agent_framework_mongodb._vector_store.load_settings") as loader:
        async with connector_factory(async_client=client, database_name="vectors") as connector:
            assert connector.async_client is client
    loader.assert_not_called()
    client.close.assert_not_awaited()


@pytest.mark.parametrize(
    "settings",
    [
        {"uri": "mongodb://unused"},
        {"app_name": "unused"},
        {"env_file_path": "unused.env"},
        {"env_file_encoding": "utf-16"},
    ],
)
def test_injected_client_rejects_connection_settings(connector_factory, settings):
    client = _client_mock()
    with (
        patch("agent_framework_mongodb._vector_store.load_settings") as loader,
        pytest.raises(ValueError, match="async_client cannot be combined"),
    ):
        connector_factory(async_client=client, database_name="vectors", **settings)
    loader.assert_not_called()


def test_store_collections_reuse_resolved_client_without_settings(definition):
    client = _client_mock()
    store = MongoDBStore(async_client=client, database_name="vectors")
    with patch("agent_framework_mongodb._vector_store.load_settings") as loader:
        collection = store.get_collection(dict, definition=definition, collection_name="test")
    loader.assert_not_called()
    assert collection.async_client is client
    assert not collection.managed_client
