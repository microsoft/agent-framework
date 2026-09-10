# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from functools import partial
from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import SecretString, load_settings
from qdrant_client import AsyncQdrantClient

from agent_framework_qdrant import QdrantCollection, QdrantSettings, QdrantStore


@pytest.fixture(params=["collection", "store"])
def connector_factory(request, definition):
    if request.param == "collection":
        return partial(QdrantCollection, dict, definition=definition, collection_name="test")
    return QdrantStore


def test_settings_wrap_environment_secrets(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://environment.example")
    monkeypatch.setenv("QDRANT_API_KEY", "environment-key")
    settings = load_settings(QdrantSettings, env_prefix="QDRANT_")
    assert settings["url"] == "https://environment.example"
    secret = settings["api_key"]
    assert isinstance(secret, SecretString)
    assert secret.get_secret_value() == "environment-key"
    assert "environment-key" not in repr(settings)


async def test_constructor_uses_environment_settings(connector_factory, monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://environment.example")
    monkeypatch.setenv("QDRANT_API_KEY", "environment-key")
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client) as factory:
        async with connector_factory():
            pass
    factory.assert_called_once_with(url="https://environment.example", api_key="environment-key")
    client.close.assert_awaited_once()


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
async def test_explicit_env_file_overrides_environment(connector_factory, monkeypatch, tmp_path, encoding):
    monkeypatch.setenv("QDRANT_URL", "https://environment.example")
    monkeypatch.setenv("QDRANT_API_KEY", "environment-key")
    env_file = tmp_path / "qdrant.env"
    env_file.write_text("QDRANT_URL=https://file.example\nQDRANT_API_KEY=file-key\n", encoding=encoding)
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client) as factory:
        async with connector_factory(env_file_path=str(env_file), env_file_encoding=encoding):
            pass
    factory.assert_called_once_with(url="https://file.example", api_key="file-key")


@pytest.mark.parametrize(
    ("api_key", "expected"),
    [
        ("explicit-key", "explicit-key"),
        (SecretString("explicit-key"), "explicit-key"),
        ("", ""),
        (SecretString(""), ""),
    ],
)
async def test_explicit_settings_override_file_and_environment(
    connector_factory,
    monkeypatch,
    tmp_path,
    api_key,
    expected,
):
    monkeypatch.setenv("QDRANT_URL", "https://environment.example")
    monkeypatch.setenv("QDRANT_API_KEY", "environment-key")
    env_file = tmp_path / "qdrant.env"
    env_file.write_text("QDRANT_URL=https://file.example\nQDRANT_API_KEY=file-key\n", encoding="utf-8")
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client) as factory:
        async with connector_factory(
            url="https://explicit.example",
            api_key=api_key,
            env_file_path=str(env_file),
        ):
            pass
    factory.assert_called_once_with(url="https://explicit.example", api_key=expected)


async def test_none_overrides_allow_partial_file_and_environment_settings(connector_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("QDRANT_URL", "https://environment.example")
    monkeypatch.setenv("QDRANT_API_KEY", "environment-key")
    env_file = tmp_path / "qdrant.env"
    env_file.write_text("QDRANT_URL=https://file.example\n", encoding="utf-8")
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client) as factory:
        async with connector_factory(url=None, api_key=None, env_file_path=str(env_file)):
            pass
    factory.assert_called_once_with(url="https://file.example", api_key="environment-key")


async def test_absent_settings_keep_sdk_defaults_without_implicit_dotenv(connector_factory, monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("QDRANT_URL=https://file.example\nQDRANT_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.AsyncQdrantClient", return_value=client) as factory:
        async with connector_factory():
            pass
    factory.assert_called_once_with(url=None, api_key=None)


def test_missing_env_file_fails_before_sdk_creation(connector_factory, tmp_path):
    with (
        patch("agent_framework_qdrant._vector_store.AsyncQdrantClient") as factory,
        pytest.raises(FileNotFoundError),
    ):
        connector_factory(env_file_path=str(tmp_path / "missing.env"))
    factory.assert_not_called()


@pytest.mark.parametrize("settings", [{"url": {}}, {"api_key": 123}])
def test_invalid_settings_fail_before_sdk_creation(connector_factory, settings):
    with (
        patch("agent_framework_qdrant._vector_store.AsyncQdrantClient") as factory,
        pytest.raises(ValueError, match="Invalid type for setting"),
    ):
        connector_factory(**settings)
    factory.assert_not_called()


async def test_injected_client_bypasses_environment_settings(connector_factory, monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "https://unrelated.example")
    monkeypatch.setenv("QDRANT_API_KEY", "unrelated-key")
    client = AsyncMock(spec=AsyncQdrantClient)
    with patch("agent_framework_qdrant._vector_store.load_settings") as loader:
        async with connector_factory(async_client=client) as connector:
            assert connector.async_client is client
    loader.assert_not_called()
    client.close.assert_not_awaited()


@pytest.mark.parametrize("settings", [{"env_file_path": "unused.env"}, {"env_file_encoding": "utf-16"}])
def test_injected_client_rejects_explicit_env_options(connector_factory, settings):
    client = AsyncMock(spec=AsyncQdrantClient)
    with (
        patch("agent_framework_qdrant._vector_store.load_settings") as loader,
        pytest.raises(ValueError, match="connection settings"),
    ):
        connector_factory(async_client=client, **settings)
    loader.assert_not_called()
