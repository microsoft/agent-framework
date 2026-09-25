# Copyright (c) Microsoft. All rights reserved.
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import AgentSession, Content, WorkflowCheckpoint, WorkflowCheckpointException
from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import FoundryStateStore, FoundryStorageConflictError

from agent_framework_foundry_hosting import ContextScopedStoreProvider, StoreProvider
from agent_framework_foundry_hosting._state_store import (
    AgentSessionStoreProvider,
    CheckpointStoreProvider,
    FoundryAgentSessionStore,
    FoundryCheckpointStore,
    FoundryFunctionApprovalStore,
    FunctionApprovalStoreProvider,
)


@dataclass
class _NotAllowed:
    """A type outside the built-in safe set, standing in for an application type."""

    value: int


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
    store.create_item = AsyncMock(return_value=SimpleNamespace(etag="etag-1"))
    store.set_item = AsyncMock(return_value=SimpleNamespace(etag="etag-2"))
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


def _platform_context(
    call_id: str = "call-1", user_id: str = "user-1", session_id: str = "sandbox-1"
) -> FoundryAgentRequestContext:
    return FoundryAgentRequestContext(call_id=call_id, user_id=user_id, session_id=session_id)


def test_local_agentserver_state_root_is_test_scoped(tmp_path: Path) -> None:
    """Independent tests must not share the local fallback state directory."""
    state_root = Path(os.environ["AGENTSERVER_STATE_ROOT"])

    assert state_root.is_relative_to(tmp_path)


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


async def test_load_restricts_checkpoint_deserialization() -> None:
    """A checkpoint value naming a type outside the allow set is refused.

    The file and Cosmos checkpoint stores both restrict deserialization this
    way; this store reaches the same decoder, so it restricts it too.
    """
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")
    value = checkpoint.to_dict()
    value["state"] = encode_checkpoint_value({"payload": _NotAllowed(7)})
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=value))

    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(WorkflowCheckpointException),
    ):
        await FoundryCheckpointStore("context-1", _platform_context()).load("checkpoint-1")


async def test_load_accepts_a_declared_checkpoint_type() -> None:
    """A caller can still name the types its checkpoints carry."""
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")
    value = checkpoint.to_dict()
    value["state"] = encode_checkpoint_value({"payload": _NotAllowed(7)})
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=value))

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        result = await FoundryCheckpointStore(
            "context-1",
            _platform_context(),
            allowed_checkpoint_types=[f"{_NotAllowed.__module__}:{_NotAllowed.__qualname__}"],
        ).load("checkpoint-1")

    assert result.state["payload"].value == 7


async def test_list_checkpoints_restricts_checkpoint_deserialization() -> None:
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")
    value = checkpoint.to_dict()
    value["state"] = encode_checkpoint_value({"payload": _NotAllowed(7)})
    store.list_keys = AsyncMock(
        return_value=SimpleNamespace(keys=[SimpleNamespace(key="checkpoint-1")], has_more=False, last_id=None)
    )
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=value))

    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(WorkflowCheckpointException),
    ):
        await FoundryCheckpointStore("context-1", _platform_context()).list_checkpoints(workflow_name="workflow")


async def test_provider_forwards_allowed_checkpoint_types() -> None:
    """A hosted app reaches the option through the provider it actually gets.

    `ResponsesHostServer` builds a `CheckpointStoreProvider` itself on the default
    path, so an option only settable on the store would be out of reach there.
    """
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")
    value = checkpoint.to_dict()
    value["state"] = encode_checkpoint_value({"payload": _NotAllowed(7)})
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=value))

    provider = CheckpointStoreProvider(
        allowed_checkpoint_types=[f"{_NotAllowed.__module__}:{_NotAllowed.__qualname__}"]
    )
    storage = provider.get_store(
        config=_config(is_hosted=False),
        context_id="context-1",
        platform_context=_platform_context(),
    )

    with patch(
        "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
        new=AsyncMock(return_value=store),
    ):
        result = await storage.load("checkpoint-1")

    assert result.state["payload"].value == 7


async def test_provider_restricts_by_default() -> None:
    """Without the option the provider's stores restrict, as before."""
    store = _store()
    checkpoint = _checkpoint("checkpoint-1")
    value = checkpoint.to_dict()
    value["state"] = encode_checkpoint_value({"payload": _NotAllowed(7)})
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=value))

    storage = CheckpointStoreProvider().get_store(
        config=_config(is_hosted=False),
        context_id="context-1",
        platform_context=_platform_context(),
    )

    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(WorkflowCheckpointException),
    ):
        await storage.load("checkpoint-1")


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
    store.get_item = AsyncMock(return_value=SimpleNamespace(value=session.to_dict(), etag="etag-1"))

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


@pytest.mark.parametrize("provider", ["agent", "checkpoint", "approval"])
@pytest.mark.parametrize(
    ("session_id", "user_id", "call_id"),
    [
        (None, "user", "call"),
        ("sandbox", None, "call"),
        ("sandbox", "user", None),
    ],
)
def test_hosted_store_providers_reject_missing_platform_identity(
    provider: str, session_id: str | None, user_id: str | None, call_id: str | None
) -> None:
    context = FoundryAgentRequestContext(session_id=session_id, user_id=user_id, call_id=call_id)
    config = _config(is_hosted=True)
    with pytest.raises(RuntimeError, match="session ID|user ID and call ID"):
        if provider == "agent":
            AgentSessionStoreProvider().get_store(config=config, platform_context=context)
        elif provider == "checkpoint":
            CheckpointStoreProvider().get_store(config=config, context_id="workflow", platform_context=context)
        else:
            FunctionApprovalStoreProvider().get_store(config=config, platform_context=context)


async def test_hosted_store_names_partition_sandbox_and_forward_call_id() -> None:
    names: list[str] = []
    store = _store()

    async def get_store(name: str, *, user_isolation: bool) -> MagicMock:
        assert user_isolation is True
        names.append(name)
        return store

    config = _config(is_hosted=True)
    contexts = [
        _platform_context(call_id="call-1", session_id="../sandbox/" * 100),
        _platform_context(call_id="call-2", session_id="other-sandbox"),
    ]

    with patch("agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create", new=get_store):
        for context in contexts:
            sessions = AgentSessionStoreProvider().get_store(config=config, platform_context=context)
            await sessions.set("response-1", AgentSession())
            checkpoints = CheckpointStoreProvider().get_store(
                config=config, context_id="../../conversation", platform_context=context
            )
            await checkpoints.save(_checkpoint("checkpoint-1"))
            approvals = FunctionApprovalStoreProvider().get_store(
                config=config, platform_context=context, context_id="workflow"
            )
            await approvals.save_approval_request("approval-1", _approval_request("approval-1"))

    assert len(names) == len(set(names)) == 6
    assert all(name.split("/")[1] == "v2" and len(name) <= 128 for name in names)
    assert all("user-1" not in name and "sandbox" not in name and "conversation" not in name for name in names)
    assert {call.kwargs["call_id"] for call in store.create_item.await_args_list} == {"call-1", "call-2"}
    assert {call.kwargs["call_id"] for call in store.set_item.await_args_list} == {"call-1", "call-2"}


async def test_hosted_scope_does_not_read_existing_unscoped_agent_session() -> None:
    context = _platform_context()
    legacy = await FoundryStateStore.get_or_create("agent_sessions", user_isolation=True)
    session = AgentSession(session_id="legacy-session")
    session.state["turn_count"] = 1
    async with legacy:
        await legacy.create_item("response-1", session.to_dict(), call_id=context.call_id)

    scoped = AgentSessionStoreProvider().get_store(config=_config(is_hosted=True), platform_context=context)
    assert await scoped.get("response-1") is None
    assert await scoped.get("response-1") is None

    async with legacy:
        assert await legacy.get_item("response-1", call_id=context.call_id) is not None


async def test_hosted_scope_does_not_read_existing_unscoped_checkpoint_or_approval() -> None:
    context = _platform_context()
    legacy_checkpoint = await FoundryStateStore.get_or_create("checkpoints/conversation-1", user_isolation=True)
    legacy_approval = await FoundryStateStore.get_or_create("function_approvals", user_isolation=True)
    async with legacy_checkpoint:
        await legacy_checkpoint.create_item(
            "checkpoint-1", encode_checkpoint_value(_checkpoint("checkpoint-1").to_dict()), call_id=context.call_id
        )
    async with legacy_approval:
        await legacy_approval.create_item(
            "approval-1", _approval_request("approval-1").to_dict(), call_id=context.call_id
        )

    config = _config(is_hosted=True)
    checkpoints = CheckpointStoreProvider().get_store(
        config=config, context_id="conversation-1", platform_context=context
    )
    approvals = FunctionApprovalStoreProvider().get_store(config=config, platform_context=context)
    with pytest.raises(WorkflowCheckpointException, match="No checkpoint found"):
        await checkpoints.load("checkpoint-1")
    with pytest.raises(KeyError, match="does not exist"):
        await approvals.load_approval_request("approval-1")


async def test_hosted_session_checkpoint_and_approval_data_stay_in_one_sandbox() -> None:
    config = _config(is_hosted=True)
    first_context = _platform_context(session_id="sandbox-1")
    second_context = _platform_context(session_id="sandbox-2")
    sessions = AgentSessionStoreProvider()
    checkpoints = CheckpointStoreProvider()
    approvals = FunctionApprovalStoreProvider()

    first_session_store = sessions.get_store(config=config, platform_context=first_context)
    await first_session_store.set("response-1", AgentSession())
    second_session_store = sessions.get_store(config=config, platform_context=second_context)
    assert await second_session_store.get("response-1") is None
    continued_context = _platform_context(call_id="call-2", session_id="sandbox-1")
    continued_session_store = sessions.get_store(config=config, platform_context=continued_context)
    assert await continued_session_store.get("response-1") is not None

    first_checkpoint_store = checkpoints.get_store(
        config=config, context_id="conversation-1", platform_context=first_context
    )
    await first_checkpoint_store.save(_checkpoint("checkpoint-1"))
    continued_checkpoint_store = checkpoints.get_store(
        config=config, context_id="conversation-1", platform_context=continued_context
    )
    assert await continued_checkpoint_store.load("checkpoint-1") == _checkpoint("checkpoint-1")
    second_checkpoint_store = checkpoints.get_store(
        config=config, context_id="conversation-1", platform_context=second_context
    )
    with pytest.raises(WorkflowCheckpointException, match="No checkpoint found"):
        await second_checkpoint_store.load("checkpoint-1")

    first_approval_store = approvals.get_store(config=config, platform_context=first_context)
    await first_approval_store.save_approval_request("approval-1", _approval_request("approval-1"))
    continued_approval_store = approvals.get_store(config=config, platform_context=continued_context)
    assert await continued_approval_store.load_approval_request("approval-1") == _approval_request("approval-1")
    second_approval_store = approvals.get_store(config=config, platform_context=second_context)
    with pytest.raises(KeyError, match="does not exist"):
        await second_approval_store.load_approval_request("approval-1")
    assert await first_approval_store.load_approval_request("approval-1") == _approval_request("approval-1")


async def test_hosted_approval_context_separates_workflows_in_one_sandbox() -> None:
    config = _config(is_hosted=True)
    context = _platform_context()
    approvals = FunctionApprovalStoreProvider()
    first = approvals.get_store(config=config, platform_context=context, context_id="workflow-1")
    second = approvals.get_store(config=config, platform_context=context, context_id="workflow-2")

    await first.save_approval_request("approval-1", _approval_request("approval-1"))
    with pytest.raises(KeyError, match="does not exist"):
        await second.load_approval_request("approval-1")


async def test_hosted_session_rejects_a_stale_etag_without_overwriting_the_winner() -> None:
    config = _config(is_hosted=True)
    provider = AgentSessionStoreProvider()
    first = provider.get_store(config=config, platform_context=_platform_context("call-1"))
    second = provider.get_store(config=config, platform_context=_platform_context("call-2"))

    assert await first.get("conversation-1") is None
    await first.set("conversation-1", AgentSession())
    first_session = await first.get("conversation-1")
    second_session = await second.get("conversation-1")
    assert first_session is not None and second_session is not None

    first_session.state["winner"] = True
    second_session.state["winner"] = False
    await first.set("conversation-1", first_session)
    with pytest.raises(RuntimeError, match="Another request advanced this agent session"):
        await second.set("conversation-1", second_session)

    current_store = provider.get_store(config=config, platform_context=_platform_context("call-3"))
    current = await current_store.get("conversation-1")
    assert current is not None and current.state["winner"] is True


async def test_concurrent_new_hosted_sessions_conflict_on_create() -> None:
    config = _config(is_hosted=True)
    provider = AgentSessionStoreProvider()
    first = provider.get_store(config=config, platform_context=_platform_context("call-1"))
    second = provider.get_store(config=config, platform_context=_platform_context("call-2"))
    assert await first.get("conversation-1") is None
    assert await second.get("conversation-1") is None

    await first.set("conversation-1", AgentSession())
    with pytest.raises(RuntimeError, match="Another request advanced this agent session"):
        await second.set("conversation-1", AgentSession())


async def test_hosted_previous_response_load_saves_a_new_key_without_predecessor_cas() -> None:
    config = _config(is_hosted=True)
    provider = AgentSessionStoreProvider()
    first = provider.get_store(config=config, platform_context=_platform_context("call-1"))
    initial_session = AgentSession()
    initial_session.state["turn_count"] = 1
    await first.set("response-1", initial_session)

    next_turn = provider.get_store(config=config, platform_context=_platform_context("call-2"))
    continued_session = await next_turn.get("response-1")
    assert continued_session is not None
    continued_session.state["turn_count"] = 2
    await next_turn.set("response-2", continued_session)

    previous = await provider.get_store(config=config, platform_context=_platform_context()).get("response-1")
    current = await provider.get_store(config=config, platform_context=_platform_context()).get("response-2")
    assert previous is not None and previous.state["turn_count"] == 1
    assert current is not None and current.state["turn_count"] == 2


async def test_loaded_session_without_an_etag_fails_closed() -> None:
    store = _store()
    store.get_item = AsyncMock(return_value=SimpleNamespace(value={}, etag=""))
    sessions = AgentSessionStoreProvider().get_store(
        config=_config(is_hosted=True), platform_context=_platform_context()
    )
    with (
        patch(
            "agent_framework_foundry_hosting._state_store.FoundryStateStore.get_or_create",
            new=AsyncMock(return_value=store),
        ),
        pytest.raises(RuntimeError, match="without an ETag"),
    ):
        await sessions.get("conversation-1")
    store.set_item.assert_not_awaited()
