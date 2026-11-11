# Copyright (c) Microsoft. All rights reserved.

"""Validate the optimistic-concurrency session store in the custom_storage hosting sample."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosHttpResponseError

from .custom_storage_sample_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    FakeContainer,
    cosmos_store,
    local_store,
    make_session,
)

pytestmark = pytest.mark.filterwarnings("ignore:.*SessionStore is experimental.*")

_SAMPLE = (
    Path(__file__).resolve().parents[4]
    / "samples"
    / "04-hosting"
    / "foundry-hosted-agents"
    / "responses"
    / "custom_storage"
    / "main.py"
)


@pytest.fixture(scope="module")
def sample() -> ModuleType:
    spec = importlib.util.spec_from_file_location("custom_storage_sample", _SAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stores(sample: ModuleType, kind: str) -> tuple[Any, Any]:
    if kind == "local":
        snapshots: dict[Any, Any] = {}
        return local_store(sample, snapshots), local_store(sample, snapshots)
    container = FakeContainer()
    return cosmos_store(sample, container), cosmos_store(sample, container)


async def test_sample_uses_only_the_public_session_store_contract() -> None:
    source = _SAMPLE.read_text(encoding="utf-8")
    assert "agent_framework_foundry_hosting._" not in source
    assert "compare_and_set" not in source
    assert "get_with_revision" not in source


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_get_set_roundtrip_returns_independent_snapshots(sample: ModuleType, kind: str) -> None:
    store, _ = _stores(sample, kind)
    assert await store.get("alias") is None
    original = make_session("one")
    await store.set("alias", original)
    original.state["value"] = "mutated"
    loaded = await store.get("alias")
    assert loaded is not None and loaded.state["value"] == "one"
    loaded.state["value"] = "two"
    await store.set("alias", loaded)
    current = await store.get("alias")
    assert current is not None and current.state["value"] == "two"


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_stale_request_view_cannot_overwrite_newer_session(sample: ModuleType, kind: str) -> None:
    first, second = _stores(sample, kind)
    await first.set("alias", make_session("initial"))
    assert await second.get("alias") is not None
    await second.set("alias", make_session("newer"))
    with pytest.raises(RuntimeError, match="reload before writing"):
        await first.set("alias", make_session("stale"))
    current = await second.get("alias")
    assert current is not None and current.state["value"] == "newer"


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_competing_creates_allow_only_one_writer(sample: ModuleType, kind: str) -> None:
    first, second = _stores(sample, kind)
    assert await first.get("alias") is None
    assert await second.get("alias") is None
    await first.set("alias", make_session("first"))
    with pytest.raises(RuntimeError, match="reload before writing"):
        await second.set("alias", make_session("second"))
    current = await second.get("alias")
    assert current is not None and current.state["value"] == "first"


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_stale_delete_does_not_remove_another_requests_snapshot(sample: ModuleType, kind: str) -> None:
    first, second = _stores(sample, kind)
    await first.set("alias", make_session("initial"))
    assert await second.get("alias") is not None
    await second.set("alias", make_session("newer"))
    with pytest.raises(RuntimeError):
        await first.delete("alias")
    current = await second.get("alias")
    assert current is not None and current.state["value"] == "newer"
    await second.delete("alias")
    await second.delete("alias")
    assert await second.get("alias") is None


async def test_local_store_scopes_are_isolated(sample: ModuleType) -> None:
    snapshots: dict[Any, Any] = {}
    first = local_store(sample, snapshots, "scope-a")
    second = local_store(sample, snapshots, "scope-b")
    await first.set("alias", make_session("a"))
    assert await second.get("alias") is None


async def test_local_snapshots_are_shared_only_within_one_provider(sample: ModuleType) -> None:
    config = MagicMock(spec=AgentConfig)
    config.is_hosted = False
    context = FoundryAgentRequestContext()
    provider = sample.CustomSessionStoreProvider()
    first = provider.get_store(config=config, platform_context=context)
    same_provider = provider.get_store(config=config, platform_context=context)
    other = sample.CustomSessionStoreProvider().get_store(config=config, platform_context=context)

    await first.set("alias", make_session("one"))

    assert first is not same_provider
    stored = await same_provider.get("alias")
    assert stored is not None and stored.state["value"] == "one"
    assert await other.get("alias") is None


async def test_cosmos_uses_server_side_create_and_exact_etag_conditions(sample: ModuleType) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    await store.set("alias", make_session("one"))
    await store.set("alias", make_session("two"))
    await store.delete("alias")
    assert container.calls == [
        ("create", {}),
        ("replace", {"etag": '"1"', "match_condition": MatchConditions.IfNotModified}),
        ("delete", {"etag": '"2"', "match_condition": MatchConditions.IfNotModified}),
    ]


async def test_cosmos_rejects_stored_session_without_etag(sample: ModuleType) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    await store.set("alias", make_session("one"))
    for item in container.items.values():
        del item["_etag"]
    with pytest.raises(RuntimeError, match="missing its ETag"):
        await cosmos_store(sample, container).get("alias")


async def test_cosmos_other_errors_propagate(sample: ModuleType) -> None:
    container = FakeContainer()
    container.create_error = 503
    with pytest.raises(CosmosHttpResponseError) as exc_info:
        await cosmos_store(sample, container).set("alias", make_session("one"))
    assert not isinstance(exc_info.value, RuntimeError)
