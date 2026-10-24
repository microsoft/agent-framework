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
