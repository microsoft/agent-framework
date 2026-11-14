# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import traceback
from functools import partial
from typing import Any, cast, get_type_hints
from unittest.mock import patch

import duckdb
import pytest
from agent_framework import SecretString, VectorStoreCollectionDefinition, VectorStoreField, load_settings
from agent_framework.exceptions import IntegrationException

from agent_framework_duckdb import DuckDBCollection, DuckDBSettings, DuckDBStore
from agent_framework_duckdb import _vector_store as module


@pytest.fixture(params=["store", "collection"])
def constructor(request):
    if request.param == "store":
        return DuckDBStore
    definition = VectorStoreCollectionDefinition(
        [VectorStoreField("key", name="id", type_="str")], collection_name="test"
    )
    return partial(DuckDBCollection, dict, definition=definition)


def test_public_settings_keep_uri_masked(monkeypatch):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "md:db?motherduck_token=private-test-token")
    assert get_type_hints(DuckDBSettings) == {"connection_string": SecretString | None}
    settings = load_settings(DuckDBSettings, env_prefix="DUCKDB_")
    uri = settings["connection_string"]
    assert isinstance(uri, SecretString)
    assert uri.get_secret_value().endswith("private-test-token")
    assert "private-test-token" not in str(uri)
    assert "private-test-token" not in repr(settings)


@pytest.mark.parametrize("wrapped", [False, True])
def test_explicit_precedes_selected_file_and_environment(constructor, monkeypatch, tmp_path, wrapped):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "environment.duckdb")
    env_file = tmp_path / "selected.env"
    env_file.write_text("DUCKDB_CONNECTION_STRING=file.duckdb\n", encoding="utf-8")
    value = SecretString("explicit.duckdb") if wrapped else "explicit.duckdb"
    instance = constructor(connection_string=value, env_file_path=str(env_file))
    assert isinstance(instance._client._address, SecretString)
    assert instance._client._address.get_secret_value() == "explicit.duckdb"
    assert instance._client._connection is None


def test_selected_file_precedes_environment_and_uses_encoding(constructor, monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "environment.duckdb")
    env_file = tmp_path / "selected.env"
    env_file.write_text("DUCKDB_CONNECTION_STRING=file.duckdb\n", encoding="utf-16")
    instance = constructor(env_file_path=str(env_file), env_file_encoding="utf-16")
    assert instance._client._address.get_secret_value() == "file.duckdb"


def test_environment_precedes_persistent_default(constructor, monkeypatch):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "from-env.duckdb")
    assert constructor()._client._address.get_secret_value() == "from-env.duckdb"
    monkeypatch.delenv("DUCKDB_CONNECTION_STRING")
    assert constructor()._client._address.get_secret_value() == "agent-framework.duckdb"


def test_dotenv_not_discovered_and_no_early_file_created(constructor, monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("DUCKDB_CONNECTION_STRING=from-dotenv.duckdb\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKDB_CONNECTION_STRING", raising=False)
    instance = constructor()
    assert instance._client._address.get_secret_value() == "agent-framework.duckdb"
    assert not (tmp_path / "agent-framework.duckdb").exists()


@pytest.mark.parametrize("value", ["", " \t ", SecretString(""), SecretString("  ")])
def test_empty_explicit_uri_does_not_fall_back(constructor, monkeypatch, value):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "valid.duckdb")
    with pytest.raises(ValueError, match="must not be empty"):
        constructor(connection_string=value)


def test_empty_selected_uri_does_not_fall_back(constructor, monkeypatch, tmp_path):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "valid.duckdb")
    env_file = tmp_path / "selected.env"
    env_file.write_text("DUCKDB_CONNECTION_STRING=''\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must not be empty"):
        constructor(env_file_path=str(env_file))


def test_empty_environment_uri_does_not_fall_back(constructor, monkeypatch):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "")
    with pytest.raises(ValueError, match="must not be empty"):
        constructor()


def test_missing_explicit_env_file_is_not_ignored(constructor, tmp_path):
    with pytest.raises(FileNotFoundError):
        constructor(connection_string="vectors.duckdb", env_file_path=str(tmp_path / "missing"))


@pytest.mark.parametrize("value", [123, b"uri", {"password": "private-test-token"}])
def test_invalid_uri_rejected_without_echoing_value(constructor, value):
    with pytest.raises((ValueError, TypeError)) as error:
        constructor(connection_string=value)
    assert "private-test-token" not in str(error.value)


@pytest.mark.parametrize("bad", [{"threads": 2}, {"": "x"}, {"token": object()}])
def test_invalid_config_rejected_before_connection(constructor, bad):
    with pytest.raises(TypeError, match="config"):
        constructor(config=cast(Any, bad))


async def test_uri_and_config_forwarded_to_single_duckdb_client_without_remote_credentials():
    fake = duckdb.connect(":memory:")
    synthetic_token = SecretString("synthetic-not-a-real-token")
    with patch.object(module.duckdb, "connect", return_value=fake) as connect:
        async with DuckDBStore(
            connection_string=SecretString("md:example"),
            config={"motherduck_token": synthetic_token, "threads": "2"},
        ) as store:
            assert await store.list_collection_names() == []
            assert "synthetic-not-a-real-token" not in repr(store._client._config)
    connect.assert_called_once_with(
        database="md:example",
        config={"motherduck_token": "synthetic-not-a-real-token", "threads": "2"},
    )


async def test_service_uri_from_environment_reaches_duckdb_without_remote_credentials(monkeypatch):
    fake = duckdb.connect(":memory:")
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "md:from-env")
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "synthetic-not-a-real-token")
    with patch.object(module.duckdb, "connect", return_value=fake) as connect:
        async with DuckDBStore() as store:
            assert await store.list_collection_names() == []
    connect.assert_called_once_with(database="md:from-env", config={})


async def test_duckdb_connection_config_is_applied_locally(tmp_path):
    async with DuckDBStore(connection_string=str(tmp_path / "configured.duckdb"), config={"threads": "2"}) as store:
        assert await store.list_collection_names() == []


async def test_connection_failure_does_not_chain_unwrapped_secrets():
    address_secret = "synthetic-address-secret"
    config_secret = "synthetic-config-secret"
    driver_error = duckdb.IOException(f"Could not connect to {address_secret} with token {config_secret}")
    store = DuckDBStore(
        connection_string=SecretString(address_secret),
        config={"motherduck_token": SecretString(config_secret)},
    )
    try:
        with (
            patch.object(module.duckdb, "connect", side_effect=driver_error),
            pytest.raises(IntegrationException, match="DuckDB connection failed") as error,
        ):
            await store.list_collection_names()
        formatted = "".join(traceback.format_exception(type(error.value), error.value, error.value.__traceback__))
        assert error.value.__cause__ is None
        assert error.value.__context__ is None
        assert address_secret not in formatted
        assert config_secret not in formatted
    finally:
        await store.aclose()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connection_string": "file.duckdb"},
        {"connection_string": ""},
        {"config": {"threads": "2"}},
        {"env_file_path": "missing.env"},
        {"env_file_encoding": "utf-16"},
    ],
)
def test_injected_client_rejects_conflicting_settings(constructor, kwargs):
    connection = duckdb.connect(":memory:")
    try:
        with (
            patch.object(module, "load_settings", side_effect=AssertionError("settings must not be loaded")),
            pytest.raises(ValueError, match="cannot be combined"),
        ):
            constructor(client=connection, **kwargs)
    finally:
        connection.close()


async def test_injected_connection_remains_caller_owned(constructor, monkeypatch):
    monkeypatch.setenv("DUCKDB_CONNECTION_STRING", "md:should-not-be-opened")
    connection = duckdb.connect(":memory:")
    try:
        with patch.object(module, "load_settings", side_effect=AssertionError("injected connection bypasses settings")):
            instance = constructor(client=connection)
            assert not instance.managed_client
            await instance.aclose()
            await instance.aclose()
        assert connection.execute("SELECT 42").fetchone() == (42,)
        with pytest.raises(RuntimeError, match="closed"):
            await instance._client.run(lambda client: client.execute("SELECT 1"))
    finally:
        connection.close()


async def test_store_collections_share_one_resolved_connection(tmp_path):
    store = DuckDBStore(connection_string=str(tmp_path / "shared.duckdb"))
    definition = VectorStoreCollectionDefinition(
        [VectorStoreField("key", name="id", type_="str")], collection_name="shared"
    )
    child = store.get_collection(dict, definition=definition)
    assert child._client is store._client
    await child.ensure_collection_exists()
    await child.aclose()
    assert await child.collection_exists()
    await store.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        await child.collection_exists()
