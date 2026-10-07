# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import SecretString, load_settings
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from agent_framework_azure_documentdb import (
    AzureDocumentDBCollection,
    AzureDocumentDBSettings,
    AzureDocumentDBStore,
)
from agent_framework_azure_documentdb import _vector_store as module


def test_public_settings_use_af_secret_string(monkeypatch):
    monkeypatch.setenv("AZURE_DOCUMENTDB_CONNECTION_STRING", "mongodb://user:secret@example")
    monkeypatch.setenv("AZURE_DOCUMENTDB_DATABASE_NAME", "environment_db")
    assert get_type_hints(AzureDocumentDBSettings) == {
        "connection_string": SecretString | None,
        "database_name": str | None,
    }
    settings = load_settings(AzureDocumentDBSettings, env_prefix="AZURE_DOCUMENTDB_")
    secret = settings["connection_string"]
    assert isinstance(secret, SecretString)
    assert secret.get_secret_value() == "mongodb://user:secret@example"
    assert "secret" not in str(secret)
    assert settings["database_name"] == "environment_db"


def test_explicit_settings_precede_file_and_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_DOCUMENTDB_CONNECTION_STRING", "mongodb://environment")
    monkeypatch.setenv("AZURE_DOCUMENTDB_DATABASE_NAME", "environment_db")
    env_file = tmp_path / "selected.env"
    env_file.write_text(
        "AZURE_DOCUMENTDB_CONNECTION_STRING=mongodb://file\nAZURE_DOCUMENTDB_DATABASE_NAME=file_db\n",
        encoding="utf-8",
    )
    created = MagicMock(spec=AsyncMongoClient)
    created.close = AsyncMock()
    with patch.object(module, "AsyncMongoClient", return_value=created) as client_type:
        store = AzureDocumentDBStore(
            connection_string=SecretString("mongodb://explicit"),
            database_name="explicit_db",
            env_file_path=str(env_file),
        )
    assert store._client.client is created
    assert client_type.call_args.args == ("mongodb://explicit",)
    assert client_type.call_args.kwargs == {
        "appname": "agent-framework-azure-documentdb",
        "retryWrites": False,
        "tls": True,
    }
    created.__getitem__.assert_called_once_with("explicit_db")


def test_selected_file_precedes_environment_and_uses_encoding(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_DOCUMENTDB_CONNECTION_STRING", "mongodb://environment")
    monkeypatch.setenv("AZURE_DOCUMENTDB_DATABASE_NAME", "environment_db")
    env_file = tmp_path / "selected.env"
    env_file.write_text(
        "AZURE_DOCUMENTDB_CONNECTION_STRING=mongodb://file\nAZURE_DOCUMENTDB_DATABASE_NAME=file_db\n",
        encoding="utf-16",
    )
    with patch.object(module, "AsyncMongoClient") as client_type:
        AzureDocumentDBStore(env_file_path=str(env_file), env_file_encoding="utf-16")
    assert client_type.call_args.args == ("mongodb://file",)
    client_type.return_value.__getitem__.assert_called_once_with("file_db")


def test_missing_or_empty_settings_rejected_before_client(monkeypatch):
    monkeypatch.delenv("AZURE_DOCUMENTDB_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENTDB_DATABASE_NAME", raising=False)
    with patch.object(module, "AsyncMongoClient") as client_type:
        with pytest.raises(ValueError, match="connection_string"):
            AzureDocumentDBStore()
        with pytest.raises(ValueError, match="connection_string"):
            AzureDocumentDBStore(connection_string="", database_name="db")
    client_type.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        {"tls": False},
        {"retryWrites": True},
        {"appname": ""},
        {"appname": "x\0y"},
        {"password": "must-not-be-forwarded"},
    ],
)
def test_client_options_rejected(options):
    with patch.object(module, "AsyncMongoClient") as client_type, pytest.raises((ValueError, NotImplementedError)):
        AzureDocumentDBStore(
            connection_string="mongodb://explicit",
            database_name="db",
            client_options=options,
        )
    client_type.assert_not_called()


async def test_injected_client_bypasses_settings_and_remains_caller_owned(monkeypatch):
    monkeypatch.setenv("AZURE_DOCUMENTDB_CONNECTION_STRING", "must-not-be-read")
    client = MagicMock(spec=AsyncMongoClient)
    client.close = AsyncMock()
    database = MagicMock(spec=AsyncDatabase)
    client.__getitem__.return_value = database
    with patch.object(module, "load_settings", side_effect=AssertionError("settings must be bypassed")):
        store = AzureDocumentDBStore(client=client, database_name="borrowed")
        await store.aclose()
    assert store._client.database is database
    assert not store.managed_client
    client.close.assert_not_awaited()


async def test_injected_database_and_collection_bypass_settings(definition_factory, pymongo_objects):
    client, database, collection = pymongo_objects
    with patch.object(module, "load_settings", side_effect=AssertionError("settings must be bypassed")):
        store = AzureDocumentDBStore(database=database)
        direct = AzureDocumentDBCollection(dict, definition=definition_factory(), collection=collection)
        await store.aclose()
        await direct.aclose()
    client.close.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connection_string": "mongodb://explicit"},
        {"client_options": {"tls": True}},
        {"env_file_path": "selected.env"},
        {"env_file_encoding": "utf-16"},
    ],
)
def test_injected_client_rejects_connection_settings(kwargs, pymongo_objects):
    with (
        patch.object(module, "load_settings", side_effect=AssertionError("settings must be bypassed")),
        pytest.raises(ValueError, match="cannot be combined"),
    ):
        AzureDocumentDBStore(client=pymongo_objects[0], database_name="db", **kwargs)


async def test_store_children_reuse_resolved_client(definition_factory, pymongo_objects):
    store = AzureDocumentDBStore(database=pymongo_objects[1])
    with patch.object(module, "load_settings", side_effect=AssertionError("children must reuse the database")):
        child = store.get_collection(dict, definition=definition_factory())
    assert child._client is store._client
    await child.aclose()
    pymongo_objects[0].close.assert_not_awaited()


async def test_created_client_closes_once(monkeypatch):
    monkeypatch.setenv("AZURE_DOCUMENTDB_CONNECTION_STRING", "mongodb://environment")
    monkeypatch.setenv("AZURE_DOCUMENTDB_DATABASE_NAME", "environment_db")
    created = MagicMock(spec=AsyncMongoClient)
    created.close = AsyncMock()
    with patch.object(module, "AsyncMongoClient", return_value=created):
        store = AzureDocumentDBStore()
        await store.aclose()
        await store.aclose()
    created.close.assert_awaited_once()
