# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import SecretString, VectorStoreCollectionDefinition, load_settings, register_vectorstoremodel
from agent_framework.exceptions import SettingNotFoundError
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
    "target",
    ["store-account", "store-database", "collection-account", "collection-database", "collection-collection"],
)
async def test_injected_objects_ignore_connection_settings(
    target, definition_factory, pymongo_objects, monkeypatch, tmp_path
):
    client, database, collection = pymongo_objects
    monkeypatch.setenv("AZURE_DOCUMENTDB_CONNECTION_STRING", "")
    monkeypatch.setenv("AZURE_DOCUMENTDB_DATABASE_NAME", "x" * 64)
    monkeypatch.setenv("AZURE_DOCUMENTDB_COLLECTION_NAME", "x" * 256)
    kwargs: dict[str, Any] = {
        "connection_string": "mongodb://ignored",
        "client_options": {"tls": False},
        "env_file_path": str(tmp_path / "missing.env"),
        "env_file_encoding": "invalid-encoding",
    }
    kind = target.split("-")[1]
    if kind == "account":
        kwargs.update(client=client, database_name="explicit_db")
    elif kind == "database":
        kwargs.update(database=database, database_name="test_database")
    else:
        kwargs.update(collection=collection, database_name="ignored", collection_name="documents")
    if target.startswith("collection") and kind != "collection":
        kwargs["collection_name"] = "explicit_collection"

    with patch.object(module, "load_settings", side_effect=AssertionError("settings must be bypassed")):
        resource: Any
        if target.startswith("store"):
            resource = AzureDocumentDBStore(**kwargs)
        else:
            resource = AzureDocumentDBCollection(dict, definition=definition_factory(), **kwargs)
        await resource.aclose()

    assert not resource.managed_client
    client.close.assert_not_awaited()


@pytest.mark.parametrize("target", ["store", "collection"])
@pytest.mark.parametrize("explicit", [False, True])
def test_injected_account_resolves_database_independently(
    target, explicit, definition_factory, pymongo_objects, monkeypatch
):
    client, database, _ = pymongo_objects
    monkeypatch.setenv("AZURE_DOCUMENTDB_DATABASE_NAME", "environment_db")
    kwargs: dict[str, Any] = {"client": client}
    if explicit:
        kwargs["database_name"] = "explicit_db"
    resource: Any
    if target == "store":
        resource = AzureDocumentDBStore(**kwargs)
    else:
        resource = AzureDocumentDBCollection(dict, definition=definition_factory(), **kwargs)

    expected = "explicit_db" if explicit else "environment_db"
    client.__getitem__.assert_called_once_with(expected)
    assert resource._client.database is database


@pytest.mark.parametrize("kind", ["account", "database"])
@pytest.mark.parametrize("explicit", [False, True])
def test_injected_collection_resolves_collection_independently(
    kind, explicit, definition_factory, pymongo_objects, monkeypatch
):
    client, database, _ = pymongo_objects
    monkeypatch.setenv("AZURE_DOCUMENTDB_COLLECTION_NAME", "environment_collection")
    definition = VectorStoreCollectionDefinition(definition_factory().fields)
    kwargs: dict[str, Any] = {"client": client, "database_name": "db"} if kind == "account" else {"database": database}
    resource = AzureDocumentDBCollection(
        dict,
        definition=definition,
        collection_name="explicit_collection" if explicit else None,
        **kwargs,
    )

    assert resource.collection_name == ("explicit_collection" if explicit else "environment_collection")


@pytest.mark.parametrize("env_name", [None, "environment_collection"])
def test_injected_collection_uses_registered_definition_before_environment(
    env_name, definition_factory, pymongo_objects, monkeypatch
):
    if env_name is None:
        monkeypatch.delenv("AZURE_DOCUMENTDB_COLLECTION_NAME", raising=False)
    else:
        monkeypatch.setenv("AZURE_DOCUMENTDB_COLLECTION_NAME", env_name)
    definition = VectorStoreCollectionDefinition(definition_factory().fields, collection_name="registered_collection")
    resource = AzureDocumentDBCollection(
        dict,
        definition=definition,
        client=pymongo_objects[0],
        database_name="db",
    )

    assert resource.collection_name == "registered_collection"
    assert resource.definition is definition


@pytest.mark.parametrize("kind", ["account", "database"])
def test_registered_model_definition_precedes_environment_without_explicit_definition(
    kind, definition_factory, pymongo_objects, monkeypatch
):
    class RegisteredRecord:
        pass

    definition = VectorStoreCollectionDefinition(definition_factory().fields, collection_name="registered_collection")
    register_vectorstoremodel(RegisteredRecord, definition=definition, decoder=lambda data: RegisteredRecord())
    monkeypatch.setenv("AZURE_DOCUMENTDB_COLLECTION_NAME", "environment_collection")
    client, database, _ = pymongo_objects
    kwargs: dict[str, Any] = {"client": client, "database_name": "db"} if kind == "account" else {"database": database}

    resource = AzureDocumentDBCollection(RegisteredRecord, **kwargs)

    assert resource.collection_name == "registered_collection"
    assert resource.definition is definition


@pytest.mark.parametrize("target", ["store-account", "collection-account", "collection-database"])
def test_injected_objects_report_missing_selector(target, definition_factory, pymongo_objects, monkeypatch):
    monkeypatch.delenv("AZURE_DOCUMENTDB_DATABASE_NAME", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENTDB_COLLECTION_NAME", raising=False)
    client, database, _ = pymongo_objects
    kwargs = {"database": database} if target.endswith("database") else {"client": client}
    selector = "AZURE_DOCUMENTDB_DATABASE_NAME" if target == "store-account" else "AZURE_DOCUMENTDB_COLLECTION_NAME"
    with pytest.raises(SettingNotFoundError, match=selector) as exc:
        if target.startswith("store"):
            AzureDocumentDBStore(**kwargs)
        else:
            AzureDocumentDBCollection(
                dict,
                definition=VectorStoreCollectionDefinition(definition_factory().fields),
                **kwargs,
            )
    parameter = "database_name" if target == "store-account" else "collection_name"
    assert parameter in str(exc.value)


@pytest.mark.parametrize("target", ["store-database", "collection-database", "collection-collection"])
def test_injected_proxy_rejects_mismatched_name(target, definition_factory, pymongo_objects):
    _, database, collection = pymongo_objects
    kwargs: dict[str, Any] = {"collection": collection, "collection_name": "other"}
    message = "collection_name must match the injected collection."
    if target.endswith("database"):
        kwargs = {"database": database, "database_name": "other"}
        message = "database_name must match the injected database."
    with pytest.raises(ValueError) as exc:
        if target.startswith("store"):
            AzureDocumentDBStore(**kwargs)
        else:
            AzureDocumentDBCollection(dict, definition=definition_factory(), **kwargs)
    assert str(exc.value) == message


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
