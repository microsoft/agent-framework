# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pymilvus import AsyncMilvusClient

from agent_framework_milvus import MilvusStore

_CLIENT_PATH = "agent_framework_milvus._vector_store.AsyncMilvusClient"


def test_default_uri_when_unset():
    with patch(_CLIENT_PATH) as client_cls:
        client_cls.return_value = MagicMock(spec=AsyncMilvusClient)
        MilvusStore()
        assert client_cls.call_args.kwargs["uri"] == "http://localhost:19530"


def test_uri_from_environment(monkeypatch):
    monkeypatch.setenv("MILVUS_URI", "http://milvus.internal:19530")
    with patch(_CLIENT_PATH) as client_cls:
        client_cls.return_value = MagicMock(spec=AsyncMilvusClient)
        MilvusStore()
        assert client_cls.call_args.kwargs["uri"] == "http://milvus.internal:19530"


def test_explicit_uri_overrides_environment(monkeypatch):
    monkeypatch.setenv("MILVUS_URI", "http://env:19530")
    with patch(_CLIENT_PATH) as client_cls:
        client_cls.return_value = MagicMock(spec=AsyncMilvusClient)
        MilvusStore(uri="http://explicit:19530")
        assert client_cls.call_args.kwargs["uri"] == "http://explicit:19530"


def test_token_and_db_forwarded():
    with patch(_CLIENT_PATH) as client_cls:
        client_cls.return_value = MagicMock(spec=AsyncMilvusClient)
        MilvusStore(uri="http://localhost:19530", token="secret-token", db_name="analytics")
        assert client_cls.call_args.kwargs["token"] == "secret-token"
        assert client_cls.call_args.kwargs["db_name"] == "analytics"


def test_token_from_environment(monkeypatch):
    monkeypatch.setenv("MILVUS_TOKEN", "env-token")
    with patch(_CLIENT_PATH) as client_cls:
        client_cls.return_value = MagicMock(spec=AsyncMilvusClient)
        MilvusStore(uri="http://localhost:19530")
        assert client_cls.call_args.kwargs["token"] == "env-token"


def test_client_creation_error_propagates():
    # The native client error is surfaced directly rather than wrapped.
    with patch(_CLIENT_PATH, side_effect=RuntimeError("boom")), pytest.raises(RuntimeError, match="boom"):
        MilvusStore(uri="http://localhost:19530")


def test_connector_clients_get_unique_connection_alias():
    # pymilvus shares one global connection between clients that resolve to the same alias, so each
    # connector-created client must pass a distinct alias to own an independent connection.
    with patch(_CLIENT_PATH) as client_cls:
        client_cls.return_value = MagicMock(spec=AsyncMilvusClient)
        MilvusStore(uri="http://localhost:19530")
        alias_a = client_cls.call_args.kwargs["alias"]
        MilvusStore(uri="http://localhost:19530")
        alias_b = client_cls.call_args.kwargs["alias"]
    assert alias_a and alias_b, "connector-created clients must request an explicit alias"
    assert alias_a != alias_b, "two connector-created clients must not share a connection alias"


class _FakeConnectionRegistry:
    """Mirrors pymilvus's global alias-keyed connection registry.

    See pymilvus.milvus_client._utils.create_connection: the alias is derived from the uri/auth/db
    unless an explicit ``alias`` kwarg is given, and a connection already registered under that alias
    is shared rather than re-created. ``close`` removes the alias (connections.async_remove_connection).
    """

    def __init__(self) -> None:
        self.live: set[str] = set()

    def connect(self, alias: str) -> None:
        self.live.add(alias)

    def disconnect(self, alias: str) -> None:
        self.live.discard(alias)

    def is_live(self, alias: str) -> bool:
        return alias in self.live


class _FakeAsyncClient:
    def __init__(self, registry: _FakeConnectionRegistry, **kwargs: object) -> None:
        # Explicit alias wins; otherwise fall back to pymilvus's uri-derived shared alias.
        self._using = str(kwargs.get("alias") or f"async-{kwargs.get('uri')}")
        self._registry = registry
        self._registry.connect(self._using)

    async def close(self) -> None:
        self._registry.disconnect(self._using)

    @property
    def connected(self) -> bool:
        return self._registry.is_live(self._using)


async def test_closing_one_store_leaves_independent_store_usable():
    # Regression: before unique aliases, two stores at the same uri shared one connection, so
    # closing the first tore down the connection the second still relied on.
    registry = _FakeConnectionRegistry()
    with patch(_CLIENT_PATH, side_effect=lambda **kwargs: _FakeAsyncClient(registry, **kwargs)):
        store_a = MilvusStore(uri="http://localhost:19530")
        store_b = MilvusStore(uri="http://localhost:19530")

        assert store_a.client._using != store_b.client._using  # type: ignore[attr-defined]
        assert store_a.client.connected and store_b.client.connected  # type: ignore[attr-defined]

        await store_a.aclose()

        assert store_a.client.connected is False  # type: ignore[attr-defined]
        assert store_b.client.connected is True  # type: ignore[attr-defined]
