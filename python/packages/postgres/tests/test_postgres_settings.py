# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from functools import partial
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import SecretString, load_settings
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from agent_framework_postgres import PostgresCollection, PostgresSettings, PostgresStore
from agent_framework_postgres import _vector_store as module


@pytest.fixture(params=["collection", "store"])
def constructor(request, definition_factory, monkeypatch):
    monkeypatch.delenv("POSTGRES_CONNECTION_STRING", raising=False)
    if request.param == "collection":
        return partial(PostgresCollection, dict, definition=definition_factory())
    return PostgresStore


def test_public_settings_use_af_secret_string(monkeypatch):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=environment password=private-test-value")
    assert get_type_hints(PostgresSettings) == {"connection_string": SecretString | None}
    settings = load_settings(PostgresSettings, env_prefix="POSTGRES_")
    value = settings["connection_string"]
    assert isinstance(value, SecretString)
    assert value.get_secret_value() == "host=environment password=private-test-value"
    assert str(value) == "**********"
    assert "private-test-value" not in repr(settings)
    assert "private-test-value" not in f"{value}"


@pytest.mark.parametrize("wrapped", [False, True])
def test_explicit_connection_precedes_file_and_environment(constructor, monkeypatch, tmp_path, wrapped):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=environment password=environment-secret")
    env_file = tmp_path / "selected.env"
    env_file.write_text("POSTGRES_CONNECTION_STRING='host=file password=file-secret'\n", encoding="utf-8")
    conninfo = "host=explicit password=explicit-secret"
    value = SecretString(conninfo) if wrapped else conninfo
    with patch.object(module, "_Client", wraps=module._Client) as create:
        instance = constructor(connection_string=value, env_file_path=str(env_file))
    resolved = create.call_args.args[0]
    assert isinstance(resolved, SecretString)
    assert resolved.get_secret_value() == conninfo
    if wrapped:
        assert resolved is value
    assert "explicit-secret" not in repr(resolved)
    assert instance._client.client.conninfo == conninfo
    assert instance._client.client.closed
    assert instance.managed_client


def test_selected_file_precedes_environment_and_uses_encoding(constructor, monkeypatch, tmp_path):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=environment")
    env_file = tmp_path / "selected.env"
    env_file.write_text("POSTGRES_CONNECTION_STRING='host=file password=file-secret'\n", encoding="utf-16")
    instance = constructor(env_file_path=str(env_file), env_file_encoding="utf-16")
    assert instance._client.client.conninfo == "host=file password=file-secret"
    assert instance.schema == "public"


def test_environment_fallback_without_schema_override(constructor, monkeypatch, tmp_path):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=environment")
    monkeypatch.setenv("POSTGRES_SCHEMA", "must_not_be_used")
    env_file = tmp_path / "selected.env"
    env_file.write_text("POSTGRES_SCHEMA=also_ignored\n", encoding="utf-8")
    instance = constructor(env_file_path=str(env_file))
    assert instance._client.client.conninfo == "host=environment"
    assert instance.schema == "public"
    assert constructor(schema="explicit_schema").schema == "explicit_schema"


def test_no_implicit_dotenv_discovery_or_default_database(constructor, monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("POSTGRES_CONNECTION_STRING=host=implicit\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with (
        patch("agent_framework._settings.dotenv_values", side_effect=AssertionError("Unexpected .env read")),
        patch.object(module, "AsyncConnectionPool") as pool,
        pytest.raises(ValueError, match="exactly one"),
    ):
        constructor()
    pool.assert_not_called()


@pytest.mark.parametrize("value", ["", " \t\n", SecretString(""), SecretString("   ")])
def test_empty_explicit_connection_does_not_fall_back(constructor, monkeypatch, value):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=environment")
    with patch.object(module, "AsyncConnectionPool") as pool, pytest.raises(ValueError, match="must not be empty"):
        constructor(connection_string=value)
    pool.assert_not_called()


@pytest.mark.parametrize("source", ["environment", "file"])
def test_empty_resolved_connection_does_not_fall_back(constructor, monkeypatch, tmp_path, source):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "" if source == "environment" else "host=environment")
    kwargs = {}
    if source == "file":
        env_file = tmp_path / "selected.env"
        env_file.write_text("POSTGRES_CONNECTION_STRING=''\n", encoding="utf-8")
        kwargs["env_file_path"] = str(env_file)
    with patch.object(module, "AsyncConnectionPool") as pool, pytest.raises(ValueError, match="must not be empty"):
        constructor(**kwargs)
    pool.assert_not_called()


def test_selected_missing_file_is_not_ignored_with_explicit_connection(constructor, tmp_path):
    with pytest.raises(FileNotFoundError):
        constructor(connection_string="host=explicit", env_file_path=str(tmp_path / "missing.env"))


@pytest.mark.parametrize("value", [123, b"host=bytes", {"password": "must-not-leak"}, lambda: "host=callable"])
def test_invalid_setting_type_does_not_reach_driver(constructor, value):
    with patch.object(module, "AsyncConnectionPool") as pool, pytest.raises((ValueError, TypeError)) as error:
        constructor(connection_string=value)
    pool.assert_not_called()
    assert "must-not-leak" not in str(error.value)


@pytest.mark.parametrize("client_type", [AsyncConnection, AsyncConnectionPool])
async def test_injected_client_bypasses_loader_and_remains_borrowed(constructor, monkeypatch, client_type):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "not valid conninfo; must not be read")
    client = MagicMock(spec=client_type)
    client.close = AsyncMock()
    with patch.object(module, "load_settings", side_effect=AssertionError("Injected clients must not load settings")):
        instance = constructor(client=client)
        assert instance._client.client is client
        assert not instance.managed_client
        await instance.close()
    client.close.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connection_string": "host=explicit"},
        {"connection_string": ""},
        {"connection_string": SecretString("host=explicit")},
        {"env_file_path": "missing.env"},
        {"env_file_path": ""},
        {"env_file_encoding": "utf-16"},
        {"env_file_encoding": ""},
    ],
)
def test_injected_client_rejects_conflicting_settings_without_reading(constructor, kwargs):
    client = MagicMock(spec=AsyncConnection)
    with (
        patch.object(module, "load_settings", side_effect=AssertionError("Must not read settings")),
        pytest.raises(ValueError, match="cannot be combined"),
    ):
        constructor(client=client, **kwargs)


async def test_store_children_reuse_resolved_client_without_loading_again(monkeypatch, definition_factory):
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "host=initial")
    store = PostgresStore()
    monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "")
    with patch.object(module, "load_settings", side_effect=AssertionError("Must reuse resolved client")):
        collection = store.get_collection(dict, definition=definition_factory())
    assert collection._client is store._client
    assert isinstance(store._client.client, AsyncConnectionPool)
    assert store._client.client.conninfo == "host=initial"
    with patch.object(store._client.client, "close", new_callable=AsyncMock) as close:
        await collection.close()
        close.assert_not_called()
        await store.close()
        close.assert_awaited_once()
