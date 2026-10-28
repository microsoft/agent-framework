# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import oracledb
import pytest
from agent_framework import SecretString, load_settings
from agent_framework.exceptions import IntegrationException

from agent_framework_oracle import OracleCollection, OracleSettings, OracleStore
from agent_framework_oracle import _vector_store as module


@pytest.fixture(autouse=True)
def isolate_oracle_settings(monkeypatch):
    for name in get_type_hints(OracleSettings):
        monkeypatch.delenv(f"ORACLE_{name.upper()}", raising=False)


@pytest.fixture(params=["store", "collection"])
def constructor(request, definition_factory):
    if request.param == "collection":
        return partial(OracleCollection, dict, definition=definition_factory())
    return OracleStore


def test_public_settings_mask_password(monkeypatch):
    monkeypatch.setenv("ORACLE_DSN", "localhost/service")
    monkeypatch.setenv("ORACLE_USER", "example")
    monkeypatch.setenv("ORACLE_PASSWORD", "private-value")
    monkeypatch.setenv("ORACLE_WALLET_LOCATION", "/wallet")
    monkeypatch.setenv("ORACLE_WALLET_PASSWORD", "wallet-private-value")
    hints = get_type_hints(OracleSettings)
    assert hints["dsn"] == str | None
    assert hints["user"] == str | None
    assert hints["password"] == SecretString | None
    assert hints["wallet_location"] == str | None
    assert hints["wallet_password"] == SecretString | None
    assert hints["access_token"] == SecretString | tuple[str, str] | Callable[[], str | tuple[str, str]] | None
    assert hints["min"] == int | None
    settings = load_settings(OracleSettings, env_prefix="ORACLE_")
    assert settings["dsn"] == "localhost/service"
    assert settings["wallet_location"] == "/wallet"
    password = settings["password"]
    wallet_password = settings["wallet_password"]
    assert isinstance(password, SecretString)
    assert isinstance(wallet_password, SecretString)
    assert password.get_secret_value() == "private-value"
    assert wallet_password.get_secret_value() == "wallet-private-value"
    assert "private-value" not in repr(settings)
    assert "wallet-private-value" not in repr(settings)
    assert "private-value" not in str(password)


@pytest.mark.parametrize("wrapped", [False, True])
def test_explicit_credentials_precede_file_and_environment(constructor, monkeypatch, tmp_path, wrapped):
    monkeypatch.setenv("ORACLE_DSN", "environment")
    monkeypatch.setenv("ORACLE_USER", "environment")
    monkeypatch.setenv("ORACLE_PASSWORD", "environment")
    env_file = tmp_path / "oracle.env"
    env_file.write_text("ORACLE_DSN=file\nORACLE_USER=file\nORACLE_PASSWORD=file\n", encoding="utf-8")
    secret = SecretString("explicit-password") if wrapped else "explicit-password"
    instance = constructor(
        dsn="explicit",
        user="explicit",
        password=secret,
        pool_parameters={"dsn": "mapping", "user": "mapping", "password": SecretString("mapping")},
        env_file_path=str(env_file),
    )
    assert instance._client._dsn == instance._client._user == "explicit"
    assert instance._client._password.get_secret_value() == "explicit-password"
    assert instance._client._pool is None
    assert instance.managed_client


def test_selected_file_precedes_environment_and_supports_encoding(constructor, monkeypatch, tmp_path):
    for name in ("ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_WALLET_PASSWORD"):
        monkeypatch.setenv(name, "environment")
    monkeypatch.setenv("ORACLE_MIN", "1")
    env_file = tmp_path / "oracle.env"
    env_file.write_text(
        "ORACLE_DSN=file\nORACLE_USER=file\nORACLE_PASSWORD=file\nORACLE_WALLET_PASSWORD=file-wallet\nORACLE_MIN=2\n",
        encoding="utf-16",
    )
    instance = constructor(env_file_path=str(env_file), env_file_encoding="utf-16")
    assert instance._client._dsn == instance._client._user == "file"
    assert instance._client._password.get_secret_value() == "file"
    assert instance._client._pool_parameters["min"] == 2
    wallet_password = instance._client._pool_parameters["wallet_password"]
    assert isinstance(wallet_password, SecretString)
    assert wallet_password.get_secret_value() == "file-wallet"
    assert "file-wallet" not in repr(instance._client._pool_parameters)


def test_environment_without_implicit_dotenv(constructor, monkeypatch, tmp_path):
    for name in ("ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD"):
        monkeypatch.setenv(name, "environment")
    (tmp_path / ".env").write_text("ORACLE_DSN=must-not-read\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch("agent_framework._settings.dotenv_values", side_effect=AssertionError("Unexpected .env read")):
        instance = constructor()
    assert instance._client._dsn == "environment"
    assert instance._client._pool is None


def test_invalid_pool_parameter_fails_without_connecting(monkeypatch):
    monkeypatch.setenv("ORACLE_DSN", "dsn")
    monkeypatch.setenv("ORACLE_USER", "user")
    monkeypatch.setenv("ORACLE_PASSWORD", "password")
    monkeypatch.setenv("ORACLE_MAX", "not-an-integer")
    with (
        patch.object(module.oracledb, "create_pool_async") as create,
        pytest.raises(ValueError, match="setting 'max' from environment variable 'ORACLE_MAX'"),
    ):
        OracleStore()
    create.assert_not_called()


def test_pool_parameter_unsupported_by_installed_driver_fails(monkeypatch):
    monkeypatch.setenv("ORACLE_DSN", "dsn")
    monkeypatch.setenv("ORACLE_USER", "user")
    monkeypatch.setenv("ORACLE_PASSWORD", "password")
    monkeypatch.setenv("ORACLE_POOL_ALIAS", "example")
    supported = module._CREATE_POOL_PARAMETER_NAMES - {"pool_alias"}
    monkeypatch.setattr(module, "_CREATE_POOL_PARAMETER_NAMES", supported)
    with pytest.raises(ValueError, match="pool_alias"):
        OracleStore()


def test_unknown_explicit_pool_parameter_fails_without_connecting():
    pool_parameters: Any = {"maxx": 8}
    with patch.object(module.oracledb, "create_pool_async") as create, pytest.raises(ValueError, match="maxx"):
        OracleStore(
            dsn="dsn",
            user="user",
            password="password",
            pool_parameters=pool_parameters,
        )
    create.assert_not_called()


@pytest.mark.parametrize("empty", ["dsn", "user", "password"])
def test_empty_named_connection_values_fail_without_connecting(constructor, empty):
    settings = {"dsn": "dsn", "user": "user", "password": "password"}
    settings[empty] = ""
    with patch.object(module.oracledb, "create_pool_async") as create, pytest.raises(ValueError):
        constructor(**settings)
    create.assert_not_called()


def test_missing_selected_file_is_not_ignored(constructor, tmp_path):
    with pytest.raises(FileNotFoundError):
        constructor(dsn="explicit", user="explicit", password="explicit", env_file_path=str(tmp_path / "missing.env"))


@pytest.mark.parametrize("option", ["dsn", "user", "password", "pool_parameters", "env_file_path", "env_file_encoding"])
def test_borrowed_client_rejects_connection_options(constructor, option):
    client = MagicMock(spec=oracledb.AsyncConnection)
    value = {"min": 1} if option == "pool_parameters" else "not-read"
    with pytest.raises(ValueError, match="cannot be combined"):
        constructor(client=client, **{option: value})


@pytest.mark.parametrize("client_type", [oracledb.AsyncConnection, oracledb.AsyncConnectionPool])
async def test_borrowed_client_bypasses_settings_and_remains_open(constructor, client_type):
    client = MagicMock(spec=client_type)
    client.close = AsyncMock()
    with patch.object(module, "load_settings", side_effect=AssertionError("Unexpected settings read")):
        instance = constructor(client=client)
        assert not instance.managed_client
        await instance.close()
        await instance.close()
    client.close.assert_not_awaited()


def test_invalid_client_type_is_rejected(constructor):
    with pytest.raises(TypeError, match="client"):
        constructor(client=object())


async def test_store_shares_client_without_rereading_settings(monkeypatch, definition_factory):
    monkeypatch.setenv("ORACLE_DSN", "one")
    monkeypatch.setenv("ORACLE_USER", "user")
    monkeypatch.setenv("ORACLE_PASSWORD", "password")
    store = OracleStore()
    monkeypatch.setenv("ORACLE_DSN", "two")
    with patch.object(module, "load_settings", side_effect=AssertionError("Unexpected settings read")):
        collection = store.get_collection(dict, definition=definition_factory())
    assert collection._client is store._client
    assert not collection.managed_client
    await collection.close()
    assert not store._client._closed
    await store.close()
    assert store._client._closed


async def test_owned_pool_is_lazy_and_closed_once():
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    pool.close = AsyncMock()
    store = OracleStore(dsn="dsn", user="user", password=SecretString("password"))
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        async with store:
            assert store._client._pool is None
            assert await store._client._get_client() is pool
            assert await store._client._get_client() is pool
        await store.close()
    create.assert_called_once_with(dsn="dsn", user="user", password="password", min=0, max=4)
    pool.close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="closed"):
        await store._client._get_client()


async def test_absent_named_connection_values_are_deferred_to_driver():
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    store = OracleStore()
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        assert await store._client._get_client() is pool
    create.assert_called_once_with(min=0, max=4)


async def test_access_token_auth_does_not_require_user_or_password(monkeypatch):
    monkeypatch.setenv("ORACLE_DSN", "dsn")
    monkeypatch.setenv("ORACLE_ACCESS_TOKEN", "environment-token")
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    store = OracleStore()
    token = store._client._pool_parameters["access_token"]
    assert isinstance(token, SecretString)
    assert token.get_secret_value() == "environment-token"
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        assert await store._client._get_client() is pool
    create.assert_called_once_with(dsn="dsn", access_token="environment-token", min=0, max=4)


async def test_explicit_access_token_preserves_tuple_and_callable_forms():
    token_tuple = ("token", "private-key")

    def token_provider() -> tuple[str, str]:
        return token_tuple

    for access_token in (token_tuple, token_provider):
        pool = MagicMock(spec=oracledb.AsyncConnectionPool)
        store = OracleStore(dsn="dsn", pool_parameters={"access_token": access_token})
        with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
            assert await store._client._get_client() is pool
        create.assert_called_once_with(dsn="dsn", access_token=access_token, min=0, max=4)


async def test_host_and_service_name_do_not_require_dsn():
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    store = OracleStore(
        user="user",
        password="password",
        pool_parameters={"host": "db.example.com", "service_name": "service"},
    )
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        assert await store._client._get_client() is pool
    create.assert_called_once_with(
        user="user",
        password="password",
        host="db.example.com",
        service_name="service",
        min=0,
        max=4,
    )


async def test_public_pool_parameters_precedence(monkeypatch):
    monkeypatch.setenv("ORACLE_DSN", "environment-dsn")
    monkeypatch.setenv("ORACLE_USER", "environment-user")
    monkeypatch.setenv("ORACLE_PASSWORD", "environment-password")
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    store = OracleStore(
        dsn="named-dsn",
        user="named-user",
        password="named-password",
        pool_parameters={
            "dsn": "pool-dsn",
            "user": "pool-user",
            "password": SecretString("pool-password"),
            "min": 1,
        },
    )
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        assert await store._client._get_client() is pool
    create.assert_called_once_with(
        dsn="named-dsn",
        user="named-user",
        password="named-password",
        min=1,
        max=4,
    )


async def test_pool_parameters_forward_installed_driver_options_not_in_settings(monkeypatch):
    future_value = object()
    pool_parameters: Any = {"future_option": future_value}
    monkeypatch.setattr(module, "_CREATE_POOL_PARAMETER_NAMES", module._CREATE_POOL_PARAMETER_NAMES | {"future_option"})
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    store = OracleStore(
        dsn="dsn",
        user="user",
        password="password",
        pool_parameters=pool_parameters,
    )
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        assert await store._client._get_client() is pool
    create.assert_called_once_with(
        dsn="dsn",
        user="user",
        password="password",
        min=0,
        max=4,
        future_option=future_value,
    )


async def test_owned_pool_forwards_typed_environment_parameters(monkeypatch):
    values = {
        "ORACLE_DSN": "dsn",
        "ORACLE_USER": "user",
        "ORACLE_PASSWORD": "password",
        "ORACLE_MIN": "1",
        "ORACLE_MAX": "8",
        "ORACLE_HOMOGENEOUS": "false",
        "ORACLE_TCP_CONNECT_TIMEOUT": "1.5",
        "ORACLE_WALLET_LOCATION": "/wallet",
        "ORACLE_WALLET_PASSWORD": "wallet-password",
        "ORACLE_HOME": "/ignored",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    pool.close = AsyncMock()
    store = OracleStore()
    with patch.object(module.oracledb, "create_pool_async", return_value=pool) as create:
        assert await store._client._get_client() is pool
        await store.close()
    create.assert_called_once_with(
        dsn="dsn",
        user="user",
        password="password",
        min=1,
        max=8,
        homogeneous=False,
        tcp_connect_timeout=1.5,
        wallet_location="/wallet",
        wallet_password="wallet-password",
    )
    pool.close.assert_awaited_once()


async def test_owned_pool_uses_driver_factory_without_connecting():
    store = OracleStore(dsn="localhost:1521/unused", user="unused", password="unused")
    try:
        pool = await store._client._get_client()
        assert isinstance(pool, oracledb.AsyncConnectionPool)
        assert await store._client._get_client() is pool
    finally:
        await store.close()


async def test_pooled_writes_commit_or_rollback_but_borrowed_connection_does_not():
    connection = MagicMock(spec=oracledb.AsyncConnection)
    connection.commit = AsyncMock()
    connection.rollback = AsyncMock()
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    pool.acquire.return_value.__aenter__.return_value = connection
    for client in (pool, connection):
        owner = module._Client(client=client)
        async with owner.connection(write=True):
            pass
        try:
            async with owner.connection(write=True):
                raise ValueError("caller failure")
        except ValueError:
            pass
    connection.commit.assert_awaited_once()
    connection.rollback.assert_awaited_once()
    assert pool.acquire.call_count == 2


async def test_driver_connection_failure_is_chained_without_leaking_credentials():
    pool = MagicMock(spec=oracledb.AsyncConnectionPool)
    pool.acquire.side_effect = oracledb.OperationalError("connection refused")
    owner = module._Client(client=pool)
    with pytest.raises(IntegrationException, match="Oracle operation failed") as error:
        async with owner.connection():
            pytest.fail("Acquisition should fail before yielding.")
    assert isinstance(error.value.__cause__, oracledb.OperationalError)
