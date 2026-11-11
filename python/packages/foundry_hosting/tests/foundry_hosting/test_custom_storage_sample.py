# Copyright (c) Microsoft. All rights reserved.

"""Validate the conditional-write contract of the custom_storage hosting sample."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from agent_framework import AgentSession
from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from agent_framework_foundry_hosting import FoundryRequestScope

_SAMPLE = (
    Path(__file__).resolve().parents[4]
    / "samples"
    / "04-hosting"
    / "foundry-hosted-agents"
    / "responses"
    / "custom_storage"
    / "main.py"
)
_APPROVAL_KEY = "__foundry_agent_approval/0b6c8b52-6f1d-4bb3-9a35-6a1e4c8f7f10"


@pytest.fixture(scope="module")
def sample() -> ModuleType:
    spec = importlib.util.spec_from_file_location("custom_storage_sample", _SAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _session(value: str) -> AgentSession:
    session = AgentSession(session_id="inner-maf-session")
    session.state["value"] = value
    return session


def _http_error(status: int) -> CosmosHttpResponseError:
    if status == 404:
        return CosmosResourceNotFoundError(status_code=404, message="missing")
    return CosmosHttpResponseError(status_code=status, message=f"status {status}")


class _FakeContainer:
    """Server-side create-only and exact-ETag semantics for one partition."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self._version = 0
        self.omit_etag = False
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _stamp(self, body: dict[str, Any]) -> dict[str, Any]:
        self._version += 1
        stored = {**body, "_etag": f'"{self._version}"'}
        self.items[body["scope_key"], body["id"]] = stored
        return {**stored, "_etag": None} if self.omit_etag else dict(stored)

    async def read_item(self, *, item: str, partition_key: str) -> dict[str, Any]:
        stored = self.items.get((partition_key, item))
        if stored is None:
            raise _http_error(404)
        return dict(stored)

    async def create_item(self, *, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create", {}))
        if (body["scope_key"], body["id"]) in self.items:
            raise _http_error(409)
        return self._stamp(body)

    async def replace_item(
        self, *, item: str, body: dict[str, Any], etag: str, match_condition: MatchConditions
    ) -> dict[str, Any]:
        self.calls.append(("replace", {"etag": etag, "match_condition": match_condition}))
        stored = self.items.get((body["scope_key"], item))
        if stored is None:
            raise _http_error(404)
        if stored["_etag"] != etag:
            raise _http_error(412)
        return self._stamp(body)


def _cosmos_store(sample: ModuleType, container: _FakeContainer) -> Any:
    scope = FoundryRequestScope(session_id="sandbox", user_id="user", call_id="call", is_hosted=True)
    return sample.CosmosSessionStore(container=container, scope=scope)


def _local_store(sample: ModuleType, snapshots: dict[Any, Any], scope_key: str = "scope") -> Any:
    return sample.LocalSessionStore(snapshots, scope_key=scope_key)


async def test_sample_does_not_import_private_hosting_types() -> None:
    source = _SAMPLE.read_text(encoding="utf-8")
    assert "_ConditionalSessionStore" not in source
    assert "_SessionStoreConflict" not in source
    assert "agent_framework_foundry_hosting._" not in source


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_conditional_write_contract(sample: ModuleType, kind: str) -> None:
    store = _local_store(sample, {}) if kind == "local" else _cosmos_store(sample, _FakeContainer())

    assert await store.get_with_revision(_APPROVAL_KEY) == (None, None)

    first = await store.compare_and_set(_APPROVAL_KEY, _session("one"), expected_revision=None)
    assert isinstance(first, str) and first
    with pytest.raises(RuntimeError):
        await store.compare_and_set(_APPROVAL_KEY, _session("dup"), expected_revision=None)

    loaded, revision = await store.get_with_revision(_APPROVAL_KEY)
    assert revision == first
    assert loaded is not None and loaded.session_id == "inner-maf-session"
    assert loaded.state["value"] == "one"
    loaded.state["value"] = "mutated"
    again, _ = await store.get_with_revision(_APPROVAL_KEY)
    assert again is not None and again.state["value"] == "one"

    second = await store.compare_and_set(_APPROVAL_KEY, _session("two"), expected_revision=first)
    assert second and second != first
    with pytest.raises(RuntimeError):
        await store.compare_and_set(_APPROVAL_KEY, _session("stale"), expected_revision=first)
    current, current_revision = await store.get_with_revision(_APPROVAL_KEY)
    assert current is not None and current.state["value"] == "two"
    assert current_revision == second

    with pytest.raises(ValueError):
        await store.compare_and_set(_APPROVAL_KEY, _session("bad"), expected_revision="")


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_exact_update_of_absent_key_conflicts(sample: ModuleType, kind: str) -> None:
    store = _local_store(sample, {}) if kind == "local" else _cosmos_store(sample, _FakeContainer())
    with pytest.raises(RuntimeError):
        await store.compare_and_set("missing", _session("x"), expected_revision="some-revision")
    assert await store.get_with_revision("missing") == (None, None)


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_revision_reads_do_not_change_ordinary_write_tokens(sample: ModuleType, kind: str) -> None:
    store = _local_store(sample, {}) if kind == "local" else _cosmos_store(sample, _FakeContainer())
    assert await store.get("alias") is None
    await store.set("alias", _session("one"))
    _, revision = await store.get_with_revision("alias")
    await store.compare_and_set("alias", _session("two"), expected_revision=revision)
    with pytest.raises(RuntimeError):
        await store.set("alias", _session("stale"))


async def test_local_store_scopes_are_isolated(sample: ModuleType) -> None:
    snapshots: dict[Any, Any] = {}
    first = _local_store(sample, snapshots, "scope-a")
    second = _local_store(sample, snapshots, "scope-b")
    await first.compare_and_set(_APPROVAL_KEY, _session("a"), expected_revision=None)
    assert await second.get_with_revision(_APPROVAL_KEY) == (None, None)


async def test_cosmos_uses_server_conditions(sample: ModuleType) -> None:
    container = _FakeContainer()
    store = _cosmos_store(sample, container)
    revision = await store.compare_and_set(_APPROVAL_KEY, _session("one"), expected_revision=None)
    await store.compare_and_set(_APPROVAL_KEY, _session("two"), expected_revision=revision)
    assert container.calls[0] == ("create", {})
    assert container.calls[1] == ("replace", {"etag": revision, "match_condition": MatchConditions.IfNotModified})
    assert all("/" not in item_id for _, item_id in container.items)


async def test_cosmos_missing_ack_revision_fails(sample: ModuleType) -> None:
    container = _FakeContainer()
    container.omit_etag = True
    store = _cosmos_store(sample, container)
    with pytest.raises(RuntimeError, match="ETag"):
        await store.compare_and_set(_APPROVAL_KEY, _session("one"), expected_revision=None)


async def test_cosmos_other_errors_propagate(sample: ModuleType) -> None:
    container = _FakeContainer()

    async def fail(*, body: dict[str, Any]) -> dict[str, Any]:
        raise _http_error(503)

    container.create_item = fail  # type: ignore[method-assign]
    store = _cosmos_store(sample, container)
    with pytest.raises(CosmosHttpResponseError) as exc_info:
        await store.compare_and_set(_APPROVAL_KEY, _session("one"), expected_revision=None)
    assert not isinstance(exc_info.value, RuntimeError)
