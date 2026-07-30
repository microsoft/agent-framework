# Copyright (c) Microsoft. All rights reserved.

import pytest

import agent_framework.azure as azure
import agent_framework.foundry as foundry

_foundry = pytest.importorskip("agent_framework_foundry")
_foundry_hosting = pytest.importorskip("agent_framework_foundry_hosting")
_foundry_local = pytest.importorskip("agent_framework_foundry_local")

FoundryChatClient = _foundry.FoundryChatClient
FoundryMemoryProvider = _foundry.FoundryMemoryProvider
FoundrySessionStore = _foundry_hosting.FoundrySessionStore
ResponsesHostServer = _foundry_hosting.ResponsesHostServer
FoundryLocalClient = _foundry_local.FoundryLocalClient


def test_foundry_namespace_exposes_cloud_and_local_symbols() -> None:
    assert foundry.FoundryChatClient is FoundryChatClient
    assert foundry.FoundryMemoryProvider is FoundryMemoryProvider
    assert foundry.FoundrySessionStore is FoundrySessionStore
    assert foundry.ResponsesHostServer is ResponsesHostServer
    assert foundry.FoundryLocalClient is FoundryLocalClient
    assert "FoundryChatClient" in dir(foundry)
    assert "FoundryLocalClient" in dir(foundry)
    assert "FoundrySessionStore" in dir(foundry)
    assert "ResponsesHostServer" in dir(foundry)


def test_azure_namespace_no_longer_exposes_foundry_symbols() -> None:
    assert "FoundryChatClient" not in dir(azure)
    assert "FoundryLocalClient" not in dir(azure)

    with pytest.raises(AttributeError, match="Module `azure` has no attribute FoundryChatClient\\."):
        _ = azure.FoundryChatClient  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
