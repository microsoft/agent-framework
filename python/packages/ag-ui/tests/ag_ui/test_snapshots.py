# Copyright (c) Microsoft. All rights reserved.

"""Tests for AG-UI thread snapshot storage primitives."""

from dataclasses import fields

from agent_framework_ag_ui import AGUIThreadSnapshot, AGUIThreadSnapshotStore, InMemoryAGUIThreadSnapshotStore


def test_thread_snapshot_model_contains_only_replayable_snapshot_fields() -> None:
    """The public snapshot model is limited to messages, Shared State, and interruption state."""
    assert [field.name for field in fields(AGUIThreadSnapshot)] == ["messages", "state", "interrupt"]


def test_in_memory_snapshot_store_satisfies_snapshot_store_protocol() -> None:
    """The built-in store conforms to the public async store protocol."""
    assert isinstance(InMemoryAGUIThreadSnapshotStore(), AGUIThreadSnapshotStore)


async def test_in_memory_snapshot_store_replaces_latest_snapshot() -> None:
    """Saving the same scoped thread key replaces the previous snapshot."""
    store = InMemoryAGUIThreadSnapshotStore()

    await store.save(
        scope="tenant-a",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "first"}], state={"count": 1}),
    )
    await store.save(
        scope="tenant-a",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "second"}], state={"count": 2}),
    )

    snapshot = await store.get(scope="tenant-a", thread_id="thread-1")

    assert snapshot is not None
    assert snapshot.messages == [{"id": "second"}]
    assert snapshot.state == {"count": 2}


async def test_in_memory_snapshot_store_keeps_scopes_separate() -> None:
    """The same AG-UI Thread id in different Snapshot Scopes addresses different snapshots."""
    store = InMemoryAGUIThreadSnapshotStore()

    await store.save(
        scope="tenant-a",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "a", "role": "user", "content": "from a"}]),
    )
    await store.save(
        scope="tenant-b",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "b", "role": "user", "content": "from b"}]),
    )

    tenant_a_snapshot = await store.get(scope="tenant-a", thread_id="thread-1")
    tenant_b_snapshot = await store.get(scope="tenant-b", thread_id="thread-1")

    assert tenant_a_snapshot is not None
    assert tenant_b_snapshot is not None
    assert tenant_a_snapshot.messages == [{"id": "a", "role": "user", "content": "from a"}]
    assert tenant_b_snapshot.messages == [{"id": "b", "role": "user", "content": "from b"}]


async def test_in_memory_snapshot_store_deletes_and_clears_snapshots() -> None:
    """Delete removes one scoped thread key, while clear can remove a scope or the whole store."""
    store = InMemoryAGUIThreadSnapshotStore()

    await store.save(scope="tenant-a", thread_id="thread-1", snapshot=AGUIThreadSnapshot(messages=[{"id": "a1"}]))
    await store.save(scope="tenant-a", thread_id="thread-2", snapshot=AGUIThreadSnapshot(messages=[{"id": "a2"}]))
    await store.save(scope="tenant-b", thread_id="thread-1", snapshot=AGUIThreadSnapshot(messages=[{"id": "b1"}]))

    assert await store.delete(scope="tenant-a", thread_id="thread-1") is True
    assert await store.delete(scope="tenant-a", thread_id="thread-1") is False
    assert await store.get(scope="tenant-a", thread_id="thread-1") is None
    assert await store.get(scope="tenant-a", thread_id="thread-2") is not None

    await store.clear(scope="tenant-a")

    assert await store.get(scope="tenant-a", thread_id="thread-2") is None
    assert await store.get(scope="tenant-b", thread_id="thread-1") is not None

    await store.clear()

    assert await store.get(scope="tenant-b", thread_id="thread-1") is None


async def test_in_memory_snapshot_store_evicts_oldest_snapshot_when_bounded() -> None:
    """The memory store bounds retained scoped thread snapshots."""
    store = InMemoryAGUIThreadSnapshotStore(max_snapshots=2)

    await store.save(scope="tenant-a", thread_id="thread-1", snapshot=AGUIThreadSnapshot(messages=[{"id": "first"}]))
    await store.save(scope="tenant-a", thread_id="thread-2", snapshot=AGUIThreadSnapshot(messages=[{"id": "second"}]))
    await store.save(scope="tenant-a", thread_id="thread-3", snapshot=AGUIThreadSnapshot(messages=[{"id": "third"}]))

    assert await store.get(scope="tenant-a", thread_id="thread-1") is None
    assert await store.get(scope="tenant-a", thread_id="thread-2") is not None
    assert await store.get(scope="tenant-a", thread_id="thread-3") is not None


def test_workflow_snapshot_builder_splits_tool_call_groups() -> None:
    """Tool calls separated by results or text synthesize provider-valid message groups."""
    from ag_ui.core import (
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
        ToolCallArgsEvent,
        ToolCallResultEvent,
        ToolCallStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ToolCallStartEvent(tool_call_id="call-a", tool_call_name="toolA"))
    builder.observe(ToolCallArgsEvent(tool_call_id="call-a", delta='{"x": 1}'))
    builder.observe(ToolCallResultEvent(message_id="result-a", tool_call_id="call-a", content="resA"))
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="thinking"))
    builder.observe(TextMessageEndEvent(message_id="text-1"))
    builder.observe(ToolCallStartEvent(tool_call_id="call-b", tool_call_name="toolB"))
    builder.observe(ToolCallResultEvent(message_id="result-b", tool_call_id="call-b", content="resB"))

    messages = builder.build().messages
    shapes = [
        (
            message.get("role"),
            [tool_call["id"] for tool_call in message.get("tool_calls", [])] or message.get("toolCallId"),
        )
        for message in messages
    ]
    assert shapes == [
        ("assistant", ["call-a"]),
        ("tool", "call-a"),
        ("assistant", None),
        ("assistant", ["call-b"]),
        ("tool", "call-b"),
    ]


async def test_in_memory_snapshot_store_rejects_invalid_keys() -> None:
    """Key parts must be non-empty strings for every store operation."""
    import pytest

    store = InMemoryAGUIThreadSnapshotStore()
    snapshot = AGUIThreadSnapshot()

    with pytest.raises(ValueError):
        await store.save(scope="", thread_id="thread-1", snapshot=snapshot)
    with pytest.raises(ValueError):
        await store.save(scope="tenant-a", thread_id="", snapshot=snapshot)
    with pytest.raises(TypeError):
        await store.save(scope=123, thread_id="thread-1", snapshot=snapshot)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError):
        await store.get(scope="tenant-a", thread_id="")
    with pytest.raises(TypeError):
        await store.delete(scope=None, thread_id="thread-1")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError):
        await store.clear(scope="")
