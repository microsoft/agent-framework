# Copyright (c) Microsoft. All rights reserved.
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentSession, Content, WorkflowCheckpoint, WorkflowCheckpointException
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import FoundryStorageConflictError

from agent_framework_foundry_hosting import ContextScopedStoreProvider, StoreProvider
from agent_framework_foundry_hosting._state_store import (
    AgentSessionStoreProvider,
    CheckpointStoreProvider,
    FoundryAgentSessionStore,
    FoundryCheckpointStore,
    FoundryFunctionApprovalStore,
    FunctionApprovalStoreProvider,
)


def _checkpoint(
    checkpoint_id: str, *, workflow_name: str = "workflow", timestamp: str = "2026-01-01T00:00:00+00:00"
) -> WorkflowCheckpoint:
    return WorkflowCheckpoint(
        workflow_name=workflow_name,
        graph_signature_hash="graph-hash",
        checkpoint_id=checkpoint_id,
        timestamp=timestamp,
    )


def _store() -> MagicMock:
    store = MagicMock()
    store.__aenter__ = AsyncMock(return_value=store)
    store.__aexit__ = AsyncMock(return_value=None)
    store.create_item = AsyncMock()
    store.set_item = AsyncMock()
    store.get_item = AsyncMock()
    store.list_keys = AsyncMock()
    store.delete_item = AsyncMock()
    return store


def _config(*, is_hosted: bool) -> AgentConfig:
    return AgentConfig(
        agent_name="",
        agent_version="",
        agent_id="",
        is_hosted=is_hosted,
        project_endpoint="",
        project_id="",
        session_id="",
        port=8088,
        appinsights_connection_string="",
        otlp_endpoint="",
        sse_keepalive_interval=0,
    )


def _platform_context(call_id: str = "call-1", user_id: str = "user-1") -> FoundryAgentRequestContext:
    return FoundryAgentRequestContext(call_id=call_id, user_id=user_id)


def test_storage_providers_use_public_abstraction() -> None:
    assert issubclass(CheckpointStoreProvider, ContextScopedStoreProvider)
    assert not issubclass(CheckpointStoreProvider, StoreProvider)
    assert issubclass(FunctionApprovalStoreProvider, StoreProvider)
    assert issubclass(AgentSessionStoreProvider, StoreProvider)


async def test_save_uses_context_scoped_store() -> None:
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ) as get_or_create:
        result = await FoundryCheckpointStore("context-1", _platform_context()).save(checkpoint)

    assert result == "checkpoint-1"
    get_or_create.assert_awaited_once_with("checkpoints/context-1", user_isolation=True)
    store.set_item.assert_awaited_once_with("checkpoint-1", checkpoint.to_dict(), call_id="call-1")


async def test_load_returns_checkpoint() -> None:
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=checkpoint.to_dict()))

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        result = await FoundryCheckpointStore("context-1", _platform_context()).load("checkpoint-1")

    assert result == checkpoint
    store.get_item.assert_awaited_once_with("checkpoint-1", call_id="call-1")


async def test_load_raises_for_missing_checkpoint() -> None:
    store = _store()
    store.get_item = AsyncMock(return_value=None)

    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(WorkflowCheckpointException, match="No checkpoint found with ID missing"),
    ):
        await FoundryCheckpointStore("context-1", _platform_context()).load("missing")


async def test_list_checkpoints_paginates_and_filters_by_workflow() -> None:
    store = _store()
    matching = _checkpoint("checkpoint-1")
    other = _checkpoint("checkpoint-2", workflow_name="other")
    store.list_keys = AsyncMock(
        side_effect=[
            SimpleNamespace(keys=[SimpleNamespace(key="checkpoint-1")], has_more=True, last_id="cursor-1"),
            SimpleNamespace(
                keys=[SimpleNamespace(key="deleted"), SimpleNamespace(key="checkpoint-2")], has_more=False, last_id=None
            ),
        ]
    )
    store.get_item = AsyncMock(
        side_effect=[
            SimpleNamespace(value=matching.to_dict()),
            None,
            SimpleNamespace(value=other.to_dict()),
        ]
    )

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        result = await FoundryCheckpointStore("context-1", _platform_context()).list_checkpoints(
            workflow_name="workflow"
        )

    assert result == [matching]
    assert store.list_keys.await_args_list[0].kwargs == {"after": None, "call_id": "call-1"}
    assert store.list_keys.await_args_list[1].kwargs == {"after": "cursor-1", "call_id": "call-1"}
    assert all(call.kwargs == {"call_id": "call-1"} for call in store.get_item.await_args_list)


@pytest.mark.parametrize(("deleted_id", "expected"), [("item-id", True), (None, False)])
async def test_delete_reports_whether_checkpoint_existed(deleted_id: str | None, expected: bool) -> None:
    store = _store()
    store.delete_item = AsyncMock(return_value=SimpleNamespace(id=deleted_id))

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        result = await FoundryCheckpointStore("context-1", _platform_context()).delete("checkpoint-1")

    assert result is expected
    store.delete_item.assert_awaited_once_with("checkpoint-1", call_id="call-1")


async def test_get_latest_uses_timestamp_and_list_ids_filters() -> None:
    storage = FoundryCheckpointStore("context-1", _platform_context())
    older = _checkpoint("older", timestamp="2026-01-01T00:00:00+00:00")
    newer = _checkpoint("newer", timestamp="2026-01-02T00:00:00+00:00")
    storage.list_checkpoints = AsyncMock(return_value=[newer, older])  # zuban:ignore

    assert await storage.get_latest(workflow_name="workflow") == newer
    assert await storage.list_checkpoint_ids(workflow_name="workflow") == ["newer", "older"]


async def test_get_latest_returns_none_when_no_checkpoints_exist() -> None:
    storage = FoundryCheckpointStore("context-1", _platform_context())
    storage.list_checkpoints = AsyncMock(return_value=[])  # zuban:ignore

    assert await storage.get_latest(workflow_name="workflow") is None


@pytest.mark.parametrize("is_hosted", [True, False])
def test_checkpoint_storage_provider_creates_request_scoped_storage(is_hosted: bool) -> None:
    provider = CheckpointStoreProvider()
    config = _config(is_hosted=is_hosted)
    first_context = _platform_context("call-1")
    second_context = _platform_context("call-2")

    first = provider.get_store(config=config, context_id="context-1", platform_context=first_context)
    second = provider.get_store(config=config, context_id="context-1", platform_context=second_context)

    assert type(first) is FoundryCheckpointStore
    assert type(second) is FoundryCheckpointStore
    assert second is not first
    assert first.platform_context is first_context
    assert second.platform_context is second_context


@pytest.mark.parametrize(
    "create_store",
    [
        lambda: FoundryCheckpointStore("", _platform_context()),
        lambda: CheckpointStoreProvider().get_store(
            config=_config(is_hosted=True), context_id="", platform_context=_platform_context()
        ),
    ],
)
def test_checkpoint_stores_require_context_id(create_store: Callable[[], Any]) -> None:
    with pytest.raises(ValueError, match="context_id must be provided"):
        create_store()


def _approval_request(approval_request_id: str) -> Content:
    function_call = Content.from_function_call(
        "call-1",
        "delete_file",
        arguments='{"path": "/foo"}',
        additional_properties={"server_label": "my_server"},
    )
    return Content.from_function_approval_request(approval_request_id, function_call)


async def test_save_and_load_function_approval_request() -> None:
    store = _store()
    request = _approval_request("approval-1")
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=request.to_dict()))

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ) as get_or_create:
        storage = FoundryFunctionApprovalStore(_platform_context())
        await storage.save_approval_request("approval-1", request)
        loaded = await storage.load_approval_request("approval-1")

    assert get_or_create.await_count == 2
    get_or_create.assert_awaited_with("function_approvals", user_isolation=True)
    store.create_item.assert_awaited_once_with("approval-1", request.to_dict(), call_id="call-1")
    store.get_item.assert_awaited_once_with("approval-1", call_id="call-1")
    assert loaded == request
    function_call = loaded.function_call
    assert function_call is not None
    assert function_call.name == "delete_file"
    assert function_call.additional_properties["server_label"] == "my_server"


async def test_save_duplicate_function_approval_request_raises() -> None:
    store = _store()
    store.create_item = AsyncMock(side_effect=FoundryStorageConflictError("already exists"))

    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(ValueError, match="Approval request with ID 'approval-1' already exists"),
    ):
        await FoundryFunctionApprovalStore(_platform_context()).save_approval_request(
            "approval-1", _approval_request("approval-1")
        )


async def test_load_missing_function_approval_request_raises() -> None:
    store = _store()
    store.get_item = AsyncMock(return_value=None)

    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(KeyError, match="Approval request with ID 'missing' does not exist"),
    ):
        await FoundryFunctionApprovalStore(_platform_context()).load_approval_request("missing")


@pytest.mark.parametrize("is_hosted", [True, False])
def test_function_approval_storage_provider_uses_foundry_store(is_hosted: bool) -> None:
    provider = FunctionApprovalStoreProvider()
    config = _config(is_hosted=is_hosted)
    platform_context = _platform_context()

    storage = provider.get_store(config=config, platform_context=platform_context)

    assert type(storage) is FoundryFunctionApprovalStore
    assert storage.platform_context is platform_context


def test_function_approval_storage_provider_creates_request_scoped_storage() -> None:
    with patch("agent_framework_foundry_hosting._state_store.FoundryFunctionApprovalStore") as storage_type:
        provider = FunctionApprovalStoreProvider()
        config = _config(is_hosted=False)
        first_context = _platform_context("call-1")
        second_context = _platform_context("call-2")
        provider.get_store(config=config, platform_context=first_context)
        provider.get_store(config=config, platform_context=second_context)

    assert storage_type.call_args_list[0].args == (first_context,)
    assert storage_type.call_args_list[1].args == (second_context,)


async def test_set_agent_session_uses_scoped_store() -> None:
    store = _store()
    session = AgentSession(session_id="agent-session-1")
    session.state["turn_count"] = 2

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ) as get_or_create:
        await FoundryAgentSessionStore(_platform_context()).set("storage-session-1", session)

    get_or_create.assert_awaited_once_with("agent_sessions", user_isolation=True)
    store.set_item.assert_awaited_once_with("storage-session-1", session.to_dict(), call_id="call-1")


async def test_get_agent_session_returns_deserialized_session() -> None:
    store = _store()
    session = AgentSession(session_id="agent-session-1")
    session.state["turn_count"] = 2
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=session.to_dict()))

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ) as get_or_create:
        result = await FoundryAgentSessionStore(_platform_context()).get("storage-session-1")

    assert result is not None
    assert result.to_dict() == session.to_dict()
    assert result is not session
    get_or_create.assert_awaited_once_with("agent_sessions", user_isolation=True)
    store.get_item.assert_awaited_once_with("storage-session-1", call_id="call-1")


async def test_get_missing_agent_session_returns_none() -> None:
    store = _store()
    store.get_item = AsyncMock(return_value=None)

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        result = await FoundryAgentSessionStore(_platform_context()).get("missing")

    assert result is None


async def test_delete_agent_session_is_idempotent() -> None:
    store = _store()

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        await FoundryAgentSessionStore(_platform_context()).delete("storage-session-1")

    store.delete_item.assert_awaited_once_with("storage-session-1", call_id="call-1")


@pytest.mark.parametrize("is_hosted", [True, False])
def test_agent_session_storage_provider_uses_foundry_store(is_hosted: bool) -> None:
    provider = AgentSessionStoreProvider()
    config = _config(is_hosted=is_hosted)
    platform_context = _platform_context()

    storage = provider.get_store(config=config, platform_context=platform_context)

    assert type(storage) is FoundryAgentSessionStore
    assert storage.platform_context is platform_context


def test_agent_session_storage_provider_creates_request_scoped_storage() -> None:
    with patch("agent_framework_foundry_hosting._state_store.FoundryAgentSessionStore") as storage_type:
        provider = AgentSessionStoreProvider()
        config = _config(is_hosted=False)
        first_context = _platform_context("call-1")
        second_context = _platform_context("call-2")
        provider.get_store(config=config, platform_context=first_context)
        provider.get_store(config=config, platform_context=second_context)

    assert storage_type.call_args_list[0].args == (first_context,)
    assert storage_type.call_args_list[1].args == (second_context,)
