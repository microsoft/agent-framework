# Copyright (c) Microsoft. All rights reserved.

"""Validate the conditional-write contract of the custom_storage hosting sample."""

from __future__ import annotations

import asyncio
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

from .custom_storage_sample_helpers import FakeContainer, cosmos_store, local_store, make_session

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
_APPROVAL_KEY = "__foundry_agent_approval/0b6c8b52-6f1d-4bb3-9a35-6a1e4c8f7f10"


@pytest.fixture(scope="module")
def sample() -> ModuleType:
    spec = importlib.util.spec_from_file_location("custom_storage_sample", _SAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_sample_does_not_import_private_hosting_types() -> None:
    source = _SAMPLE.read_text(encoding="utf-8")
    assert "_ConditionalSessionStore" not in source
    assert "_SessionStoreConflict" not in source
    assert "agent_framework_foundry_hosting._" not in source


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_conditional_write_contract(sample: ModuleType, kind: str) -> None:
    store = local_store(sample, {}) if kind == "local" else cosmos_store(sample, FakeContainer())

    assert await store.get_with_revision(_APPROVAL_KEY) == (None, None)

    original = make_session("one")
    original.state["nested"] = {"items": ["saved"]}
    first = await store.compare_and_set(_APPROVAL_KEY, original, expected_revision=None)
    original.state["nested"]["items"].append("original changed")
    assert isinstance(first, str) and first
    with pytest.raises(RuntimeError):
        await store.compare_and_set(_APPROVAL_KEY, make_session("dup"), expected_revision=None)

    loaded, revision = await store.get_with_revision(_APPROVAL_KEY)
    assert revision == first
    assert loaded is not None and loaded.session_id == "inner-maf-session"
    assert loaded.state["value"] == "one"
    loaded.state["value"] = "mutated"
    loaded.state["nested"]["items"].append("read changed")
    again, _ = await store.get_with_revision(_APPROVAL_KEY)
    assert again is not None and again.state["value"] == "one"
    assert again.state["nested"] == {"items": ["saved"]}

    second = await store.compare_and_set(_APPROVAL_KEY, make_session("two"), expected_revision=first)
    assert second and second != first
    with pytest.raises(RuntimeError):
        await store.compare_and_set(_APPROVAL_KEY, make_session("stale"), expected_revision=first)
    current, current_revision = await store.get_with_revision(_APPROVAL_KEY)
    assert current is not None and current.state["value"] == "two"
    assert current_revision == second

    with pytest.raises(ValueError):
        await store.compare_and_set(_APPROVAL_KEY, make_session("bad"), expected_revision="")


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_exact_update_of_absent_key_conflicts(sample: ModuleType, kind: str) -> None:
    store = local_store(sample, {}) if kind == "local" else cosmos_store(sample, FakeContainer())
    with pytest.raises(RuntimeError):
        await store.compare_and_set("missing", make_session("x"), expected_revision='"missing"')
    assert await store.get_with_revision("missing") == (None, None)


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_revision_reads_do_not_change_ordinary_write_tokens(sample: ModuleType, kind: str) -> None:
    store = local_store(sample, {}) if kind == "local" else cosmos_store(sample, FakeContainer())
    assert await store.get("alias") is None
    await store.set("alias", make_session("one"))
    _, revision = await store.get_with_revision("alias")
    await store.compare_and_set("alias", make_session("two"), expected_revision=revision)
    with pytest.raises(RuntimeError):
        await store.set("alias", make_session("stale"))


@pytest.mark.parametrize("kind", ["local", "cosmos"])
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_competing_request_views_allow_only_one_conditional_write(
    sample: ModuleType, kind: str, operation: str
) -> None:
    if kind == "local":
        snapshots: dict[Any, Any] = {}
        first, second = local_store(sample, snapshots), local_store(sample, snapshots)
    else:
        container = FakeContainer()
        first, second = cosmos_store(sample, container), cosmos_store(sample, container)

    revision = None
    if operation == "update":
        revision = await first.compare_and_set(_APPROVAL_KEY, make_session("initial"), expected_revision=None)
        assert (await second.get_with_revision(_APPROVAL_KEY))[1] == revision

    outcomes = await asyncio.gather(
        first.compare_and_set(_APPROVAL_KEY, make_session("first"), expected_revision=revision),
        second.compare_and_set(_APPROVAL_KEY, make_session("second"), expected_revision=revision),
        return_exceptions=True,
    )
    successes = [outcome for outcome in outcomes if isinstance(outcome, str)]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, RuntimeError)]
    assert len(successes) == len(conflicts) == 1
    assert successes[0] and successes[0] != revision
    if kind == "cosmos":
        assert isinstance(conflicts[0].__cause__, CosmosHttpResponseError)
    stored, stored_revision = await first.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] in {"first", "second"}
    assert stored_revision == successes[0]


@pytest.mark.parametrize("kind", ["local", "cosmos"])
async def test_stale_delete_does_not_remove_another_requests_snapshot(sample: ModuleType, kind: str) -> None:
    if kind == "local":
        snapshots: dict[Any, Any] = {}
        first, second = local_store(sample, snapshots), local_store(sample, snapshots)
    else:
        container = FakeContainer()
        first, second = cosmos_store(sample, container), cosmos_store(sample, container)

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
    await first.compare_and_set(_APPROVAL_KEY, make_session("a"), expected_revision=None)
    assert await second.get_with_revision(_APPROVAL_KEY) == (None, None)


async def test_local_snapshots_are_shared_only_within_one_provider(sample: ModuleType) -> None:
    config = MagicMock(spec=AgentConfig)
    config.is_hosted = False
    context = FoundryAgentRequestContext()
    provider = sample.CustomSessionStoreProvider()
    other_provider = sample.CustomSessionStoreProvider()
    first = provider.get_store(config=config, platform_context=context)
    same_provider = provider.get_store(config=config, platform_context=context)
    other = other_provider.get_store(config=config, platform_context=context)

    revision = await first.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)

    assert first is not same_provider
    stored, stored_revision = await same_provider.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "one"
    assert stored_revision == revision
    assert await other.get_with_revision(_APPROVAL_KEY) == (None, None)


async def test_cosmos_uses_server_conditions(sample: ModuleType) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    revision = await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    await store.compare_and_set(_APPROVAL_KEY, make_session("two"), expected_revision=revision)
    assert container.calls[0] == ("create", {})
    assert container.calls[1] == ("replace", {"etag": revision, "match_condition": MatchConditions.IfNotModified})
    assert all("/" not in item_id for _, item_id in container.items)


async def test_cosmos_missing_ack_revision_fails(sample: ModuleType) -> None:
    container = FakeContainer()
    container.acknowledgement_etag = None
    store = cosmos_store(sample, container)
    with pytest.raises(RuntimeError, match="ETag"):
        await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    stored, revision = await store.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "one"
    assert revision
    with pytest.raises(RuntimeError):
        await store.compare_and_set(_APPROVAL_KEY, make_session("duplicate"), expected_revision=None)


@pytest.mark.parametrize("condition", ["*", '"stale","1"'])
async def test_cosmos_fake_models_non_exact_if_match(sample: ModuleType, condition: str) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    scope_key, item_id = next(iter(container.items))
    body = {"id": item_id, "scope_key": scope_key, "session": make_session("replaced").to_dict()}

    await container.replace_item(item=item_id, body=body, etag=condition, match_condition=MatchConditions.IfNotModified)

    stored, _ = await store.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "replaced"


@pytest.mark.parametrize(
    "revision",
    ["*", " * ", '"1","2"', '"1", "2"', '"2","1"', 'W/"2"', "2", '"2"\n', '"2"\x00', '"2",*'],
)
async def test_cosmos_rejects_non_exact_revision_before_write(sample: ModuleType, revision: str) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    first = await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    current = await store.compare_and_set(_APPROVAL_KEY, make_session("two"), expected_revision=first)
    calls = len(container.calls)

    with pytest.raises(RuntimeError, match="ETag"):
        await store.compare_and_set(_APPROVAL_KEY, make_session("overwritten"), expected_revision=revision)

    assert len(container.calls) == calls
    stored, stored_revision = await store.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "two"
    assert stored_revision == current


@pytest.mark.parametrize("etag", ['""', '"*"', '"a,b"', '"\xe9"'])
async def test_cosmos_accepts_one_opaque_strong_etag(sample: ModuleType, etag: str) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    container.items[next(iter(container.items))]["_etag"] = etag
    assert (await store.get_with_revision(_APPROVAL_KEY))[1] == etag

    new_revision = await store.compare_and_set(_APPROVAL_KEY, make_session("two"), expected_revision=etag)

    assert new_revision != etag
    stored, _ = await store.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "two"


@pytest.mark.parametrize("etag", [None, "", 42, "*", "unquoted", 'W/"one"', '"one","two"', '"one"\n'])
async def test_cosmos_rejects_invalid_read_etag(sample: ModuleType, etag: object) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    container.items[next(iter(container.items))]["_etag"] = etag

    with pytest.raises(RuntimeError, match="ETag"):
        await store.get_with_revision(_APPROVAL_KEY)
    with pytest.raises(RuntimeError, match="ETag"):
        await store.get(_APPROVAL_KEY)
    with pytest.raises(RuntimeError, match="ETag"):
        await store.delete(_APPROVAL_KEY)
    assert all(call[0] != "delete" for call in container.calls)


@pytest.mark.parametrize("etag", [None, "", 42, "*", "unquoted", 'W/"one"', '"one","two"', '"one"\n'])
async def test_cosmos_rejects_invalid_write_acknowledgement(sample: ModuleType, etag: object) -> None:
    container = FakeContainer()
    container.acknowledgement_etag = etag
    store = cosmos_store(sample, container)

    with pytest.raises(RuntimeError, match="ETag"):
        await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)

    stored, revision = await store.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "one"
    assert revision


async def test_cosmos_rejects_invalid_cached_delete_etag(sample: ModuleType) -> None:
    container = FakeContainer()
    store = cosmos_store(sample, container)
    await store.set(_APPROVAL_KEY, make_session("one"))
    store._etags[_APPROVAL_KEY] = "*"

    with pytest.raises(RuntimeError, match="ETag"):
        await store.delete(_APPROVAL_KEY)

    assert all(call[0] != "delete" for call in container.calls)
    stored, _ = await store.get_with_revision(_APPROVAL_KEY)
    assert stored is not None and stored.state["value"] == "one"


async def test_local_store_keeps_opaque_revision_values(sample: ModuleType) -> None:
    snapshots = {("scope", _APPROVAL_KEY): ("opaque-version", make_session("one").to_dict())}
    store = local_store(sample, snapshots)
    assert (await store.get_with_revision(_APPROVAL_KEY))[1] == "opaque-version"

    revision = await store.compare_and_set(_APPROVAL_KEY, make_session("two"), expected_revision="opaque-version")

    assert revision != "opaque-version"


async def test_cosmos_other_errors_propagate(sample: ModuleType) -> None:
    container = FakeContainer()
    container.create_error = 503
    store = cosmos_store(sample, container)
    with pytest.raises(CosmosHttpResponseError) as exc_info:
        await store.compare_and_set(_APPROVAL_KEY, make_session("one"), expected_revision=None)
    assert not isinstance(exc_info.value, RuntimeError)
