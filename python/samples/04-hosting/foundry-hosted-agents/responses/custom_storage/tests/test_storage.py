# Copyright (c) Microsoft. All rights reserved.

"""Focused, account-free checks of scoped Cosmos snapshots and conditional writes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import AgentSession
from agent_framework_foundry_hosting import FoundryRequestScope
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.core import MatchConditions
from azure.cosmos.aio import ContainerProxy
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError


@pytest.fixture
def sample() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sample_custom_storage", Path(__file__).parents[1] / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope(user: str = "user", sandbox: str = "sandbox") -> FoundryRequestScope:
    return FoundryRequestScope(session_id=sandbox, user_id=user, call_id="call", is_hosted=True)


async def test_cosmos_canonical_keys_conditional_writes_and_delete(sample: ModuleType) -> None:
    container = MagicMock(spec=ContainerProxy)
    container.read_item = AsyncMock(side_effect=CosmosResourceNotFoundError(message="Missing."))
    container.create_item = AsyncMock(return_value={"_etag": "v1"})
    container.replace_item = AsyncMock(side_effect=[{"_etag": "v2"}, {"_etag": "v3"}])
    container.delete_item = AsyncMock()
    store = sample.CosmosSessionStore(container=container, scope=_scope())
    snapshot = AgentSession(session_id="inner-maf-id")

    assert await store.get("conversation") is None
    await store.set("conversation", snapshot)
    await store.set("conversation", snapshot)
    await store.set("response", snapshot)
    await store.set("conversation", snapshot)
    body = container.create_item.await_args_list[0].kwargs["body"]
    assert body["id"] != snapshot.session_id
    assert body["scope_key"] == _scope().storage_key
    assert body["session"]["session_id"] == snapshot.session_id
    writes = container.replace_item.await_args_list
    assert [call.kwargs["etag"] for call in writes] == ["v1", "v2"]
    assert all(call.kwargs["match_condition"] is MatchConditions.IfNotModified for call in writes)

    container.read_item.side_effect = None
    container.read_item.return_value = {**body, "_etag": "v3"}
    loaded = await store.get("conversation")
    assert loaded is not None and loaded.session_id == "inner-maf-id"
    await store.delete("conversation")
    assert container.delete_item.await_args is not None
    assert container.delete_item.await_args.kwargs["etag"] == "v3"
    assert container.delete_item.await_args.kwargs["partition_key"] == _scope().storage_key
    await store.set("conversation", snapshot)
    container.upsert_item.assert_not_called()


async def test_cosmos_conflicts_missing_etags_and_scope_mismatch_fail_closed(sample: ModuleType) -> None:
    container = MagicMock(spec=ContainerProxy)
    snapshot = AgentSession(session_id="inner")
    store = sample.CosmosSessionStore(container=container, scope=_scope())
    container.create_item = AsyncMock(side_effect=CosmosHttpResponseError(status_code=409, message="Exists."))
    with pytest.raises(RuntimeError, match="Another request advanced"):
        await store.set("key", snapshot)

    body = {"id": store._item_id("key"), "scope_key": _scope().storage_key, "session": snapshot.to_dict()}
    container.read_item = AsyncMock(return_value=body)
    with pytest.raises(RuntimeError, match="missing its ETag"):
        await store.get("key")
    container.read_item.return_value = {**body, "_etag": "stale"}
    assert await store.get("key") is not None
    container.replace_item = AsyncMock(side_effect=CosmosHttpResponseError(status_code=412, message="Stale."))
    with pytest.raises(RuntimeError, match="Another request advanced"):
        await store.set("key", snapshot)
    container.delete_item = AsyncMock(side_effect=CosmosHttpResponseError(status_code=412, message="Stale."))
    with pytest.raises(RuntimeError, match="Another request advanced"):
        await store.delete("key")
    for scope in (_scope(user="other-user"), _scope(sandbox="other-sandbox")):
        container.read_item.return_value = {**body, "scope_key": scope.storage_key, "_etag": "v1"}
        with pytest.raises(RuntimeError, match="trusted user and sandbox"):
            await store.get("key")
    container.upsert_item.assert_not_called()


async def test_local_snapshots_preserve_user_sandbox_and_cas_semantics(sample: ModuleType) -> None:
    provider = sample.CustomSessionStoreProvider()
    config = MagicMock(spec=AgentConfig, is_hosted=False)
    context = FoundryAgentRequestContext(user_id="user", session_id="sandbox")
    first = provider.get_store(config=config, platform_context=context)
    second = provider.get_store(config=config, platform_context=context)
    await first.set("key", AgentSession(session_id="inner"))
    loaded = await second.get("key")
    assert loaded is not None and loaded.session_id == "inner"
    await first.set("key", AgentSession(session_id="newer"))
    with pytest.raises(RuntimeError, match="Another request advanced"):
        await second.set("key", loaded)
    for isolated in (
        FoundryAgentRequestContext(user_id="other-user", session_id="sandbox"),
        FoundryAgentRequestContext(user_id="user", session_id="other-sandbox"),
    ):
        store = provider.get_store(config=config, platform_context=isolated)
        assert await store.get("key") is None
    await first.delete("key")
    assert await second.get("key") is None


def test_provider_rejects_missing_or_mismatched_trusted_identity(
    sample: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = MagicMock(spec=AgentConfig, is_hosted=True, session_id="sandbox")
    constructor = MagicMock()
    monkeypatch.setattr(sample, "CosmosClient", constructor)
    for context in (
        FoundryAgentRequestContext(user_id="user", session_id="other", call_id="call"),
        FoundryAgentRequestContext(session_id="sandbox", call_id="call"),
        FoundryAgentRequestContext(user_id="user", session_id="sandbox"),
    ):
        with pytest.raises(RuntimeError):
            sample.CustomSessionStoreProvider().get_store(config=config, platform_context=context)
    constructor.assert_not_called()


async def test_provider_owns_only_its_managed_identity_backend(
    sample: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://cosmos.test")
    monkeypatch.setenv("COSMOS_DATABASE_NAME", "database")
    monkeypatch.setenv("COSMOS_CONTAINER_NAME", "container")
    credential, client = MagicMock(), MagicMock()
    credential.close, client.close = AsyncMock(), AsyncMock()
    identity, constructor = MagicMock(return_value=credential), MagicMock(return_value=client)
    monkeypatch.setattr(sample, "ManagedIdentityCredential", identity)
    monkeypatch.setattr(sample, "CosmosClient", constructor)
    provider = sample.CustomSessionStoreProvider()
    config = MagicMock(spec=AgentConfig, is_hosted=True, session_id="sandbox")
    first = provider.get_store(config=config, platform_context=FoundryAgentRequestContext(user_id="user", call_id="a"))
    second = provider.get_store(config=config, platform_context=FoundryAgentRequestContext(user_id="user", call_id="b"))
    assert first is not second
    assert first._scope_key == second._scope_key == _scope().storage_key
    constructor.assert_called_once_with(url="https://cosmos.test", credential=credential)
    await provider.close()
    await provider.close()
    client.close.assert_awaited_once()
    credential.close.assert_awaited_once()
