# Copyright (c) Microsoft. All rights reserved.

"""Tests for server-side AG-UI approval state storage."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep

import pytest
from typing_extensions import Self

from agent_framework_ag_ui._approval_lifecycle import ApprovalCapacityError, ApprovalExecutionOwner
from agent_framework_ag_ui._approval_state import InMemoryAGUIApprovalStateStore, approval_state_thread_id


def test_approval_state_thread_id_allows_unscoped_thread() -> None:
    assert approval_state_thread_id(scope=None, thread_id="thread-1") == "thread-1"


def test_approval_state_thread_id_scopes_thread() -> None:
    scoped_thread_id = approval_state_thread_id(scope="tenant-a", thread_id="thread-1")

    assert scoped_thread_id != "thread-1"
    assert "tenant-a" in scoped_thread_id
    assert "thread-1" in scoped_thread_id


@pytest.mark.parametrize("scope", ["", object()])
def test_approval_state_thread_id_rejects_invalid_scope(scope: object) -> None:
    with pytest.raises(ValueError, match="scope must be a non-empty string"):
        approval_state_thread_id(scope=scope, thread_id="thread-1")


def test_approval_state_store_rejects_invalid_max_entries() -> None:
    with pytest.raises(ValueError, match="max_entries must be greater than 0"):
        InMemoryAGUIApprovalStateStore(max_entries=0)


def test_approval_state_store_registers_explicit_execution_owner() -> None:
    store = InMemoryAGUIApprovalStateStore()

    store.register(
        owner=ApprovalExecutionOwner.DEFERRED,
        thread_ids=["thread-1", "provider-thread-1"],
        name="write_record",
        arguments="{}",
        request_id="request-1",
        interrupt_id="approval-1",
        server_label=None,
    )

    occurrence = store.lifecycle.pending_occurrence(thread_id="thread-1", interrupt_id="approval-1")
    assert occurrence is not None
    assert occurrence.owner is ApprovalExecutionOwner.DEFERRED
    assert store.lifecycle.pending_occurrence(thread_id="provider-thread-1", interrupt_id="request-1") is occurrence


def test_approval_state_store_does_not_evict_active_entries() -> None:
    store = InMemoryAGUIApprovalStateStore(max_entries=1)
    store.register(
        owner=ApprovalExecutionOwner.LOCAL,
        thread_ids=["thread-1"],
        name="write_record",
        arguments="{}",
        request_id="request-1",
        interrupt_id="approval-1",
    )

    with pytest.raises(ApprovalCapacityError):
        store.register(
            owner=ApprovalExecutionOwner.LOCAL,
            thread_ids=["thread-2"],
            name="write_record",
            arguments="{}",
            request_id="request-2",
            interrupt_id="approval-2",
        )

    assert store.lifecycle.pending_interrupt_ids(thread_id="thread-1") == {"approval-1"}


def test_approval_state_store_does_not_evict_active_middleware_state() -> None:
    store = InMemoryAGUIApprovalStateStore(max_entries=1)
    store.set_tool_approval_state("thread-1", {"call_id": "call-1"})

    with pytest.raises(ApprovalCapacityError):
        store.set_tool_approval_state("thread-2", {"call_id": "call-2"})

    assert store.get_tool_approval_state("thread-1") == {"call_id": "call-1"}
    assert store.get_tool_approval_state("thread-2") is None


def test_approval_state_store_enforces_capacity_across_concurrent_first_writes() -> None:
    """Concurrent first writes cannot reserve more middleware slots than configured."""
    store = InMemoryAGUIApprovalStateStore(max_entries=1)
    start = Barrier(2)

    class SlowCopy:
        def __deepcopy__(self, memo: dict[int, object]) -> Self:
            del memo
            sleep(0.05)
            return self

    def write(thread_id: str) -> str:
        start.wait(timeout=2)
        try:
            store.set_tool_approval_state(thread_id, {"call_id": thread_id, "slow": SlowCopy()})
        except ApprovalCapacityError:
            return "rejected"
        return "stored"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, ["thread-1", "thread-2"]))

    assert sorted(outcomes) == ["rejected", "stored"]
    assert sum(store.has_tool_approval_state(thread_id) for thread_id in ["thread-1", "thread-2"]) == 1
