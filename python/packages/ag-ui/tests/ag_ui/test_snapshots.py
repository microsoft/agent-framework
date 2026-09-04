# Copyright (c) Microsoft. All rights reserved.

"""Tests for AG-UI thread snapshot storage primitives."""

from dataclasses import fields

from agent_framework_ag_ui import AGUIThreadSnapshot, AGUIThreadSnapshotStore, InMemoryAGUIThreadSnapshotStore


def test_thread_snapshot_model_contains_replayable_and_private_snapshot_fields() -> None:
    """The public snapshot model carries replayable data and optional private continuation."""
    assert [field.name for field in fields(AGUIThreadSnapshot)] == ["messages", "state", "interrupt", "session_state"]
    assert AGUIThreadSnapshot().session_state is None


def test_in_memory_snapshot_store_satisfies_snapshot_store_protocol() -> None:
    """The built-in store conforms to the public async store protocol."""
    assert isinstance(InMemoryAGUIThreadSnapshotStore(), AGUIThreadSnapshotStore)


async def test_in_memory_snapshot_store_replaces_latest_snapshot() -> None:
    """Saving the same scoped thread key replaces the previous snapshot."""
    store = InMemoryAGUIThreadSnapshotStore()

    await store.save(
        scope="tenant-a",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(
            messages=[{"id": "first"}],
            state={"count": 1},
            session_state={"provider": {"count": 1}},
        ),
    )
    await store.save(
        scope="tenant-a",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(
            messages=[{"id": "second"}],
            state={"count": 2},
            session_state={"provider": {"count": 2}},
        ),
    )

    snapshot = await store.get(scope="tenant-a", thread_id="thread-1")

    assert snapshot is not None
    assert snapshot.messages == [{"id": "second"}]
    assert snapshot.state == {"count": 2}
    assert snapshot.session_state == {"provider": {"count": 2}}


async def test_in_memory_snapshot_store_defensively_copies_private_continuation() -> None:
    """Private continuation cannot be mutated through saved or returned references."""
    store = InMemoryAGUIThreadSnapshotStore()
    session_state = {"provider": {"count": 1}}
    snapshot = AGUIThreadSnapshot(session_state=session_state)

    await store.save(scope="tenant-a", thread_id="thread-1", snapshot=snapshot)
    session_state["provider"]["count"] = 2
    stored = await store.get(scope="tenant-a", thread_id="thread-1")

    assert stored is not None
    assert stored.session_state is not None
    assert stored.session_state == {"provider": {"count": 1}}
    stored.session_state["provider"]["count"] = 3

    reread = await store.get(scope="tenant-a", thread_id="thread-1")
    assert reread is not None
    assert reread.session_state == {"provider": {"count": 1}}


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

    await store.save(
        scope="tenant-a",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "a1"}], session_state={"private": "a1"}),
    )
    await store.save(
        scope="tenant-a",
        thread_id="thread-2",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "a2"}], session_state={"private": "a2"}),
    )
    await store.save(
        scope="tenant-b",
        thread_id="thread-1",
        snapshot=AGUIThreadSnapshot(messages=[{"id": "b1"}], session_state={"private": "b1"}),
    )

    assert await store.delete(scope="tenant-a", thread_id="thread-1") is True
    assert await store.delete(scope="tenant-a", thread_id="thread-1") is False
    assert await store.get(scope="tenant-a", thread_id="thread-1") is None
    tenant_a_thread_2 = await store.get(scope="tenant-a", thread_id="thread-2")
    assert tenant_a_thread_2 is not None
    assert tenant_a_thread_2.session_state == {"private": "a2"}

    await store.clear(scope="tenant-a")

    assert await store.get(scope="tenant-a", thread_id="thread-2") is None
    tenant_b_thread_1 = await store.get(scope="tenant-b", thread_id="thread-1")
    assert tenant_b_thread_1 is not None
    assert tenant_b_thread_1.session_state == {"private": "b1"}

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


def test_workflow_snapshot_builder_folds_reasoning_into_snapshot() -> None:
    """Streamed reasoning deltas accumulate into a replayable reasoning message."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="step one "))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="step two"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))

    assert builder.build().messages == [{"id": "reason-1", "role": "reasoning", "content": "step one step two"}]


def test_workflow_snapshot_builder_keeps_reasoning_in_emission_order() -> None:
    """Reasoning is replayed where it streamed, not appended after the visible output."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
        ToolCallResultEvent,
        ToolCallStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="planning"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))
    builder.observe(ToolCallStartEvent(tool_call_id="call-a", tool_call_name="toolA"))
    builder.observe(ToolCallResultEvent(message_id="result-a", tool_call_id="call-a", content="resA"))
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="done"))
    builder.observe(TextMessageEndEvent(message_id="text-1"))

    messages = builder.build().messages
    assert [
        (
            message.get("role"),
            [tool_call["id"] for tool_call in message.get("tool_calls", [])]
            or message.get("toolCallId")
            or message.get("content"),
        )
        for message in messages
    ] == [
        ("reasoning", "planning"),
        ("assistant", ["call-a"]),
        ("tool", "call-a"),
        ("assistant", "done"),
    ]


def test_workflow_snapshot_builder_captures_reasoning_encrypted_value() -> None:
    """Encrypted reasoning payloads survive hydration under the protocol's camelCase key."""
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningMessageContentEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="hidden"))
    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id="reason-1", encrypted_value="cipher"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))

    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "hidden", "encryptedValue": "cipher"}
    ]


def test_workflow_snapshot_builder_flushes_reasoning_left_open_at_build() -> None:
    """A run that ends without REASONING_MESSAGE_END still snapshots what streamed."""
    from ag_ui.core import ReasoningMessageContentEvent, ReasoningMessageStartEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="unterminated"))

    assert builder.build().messages == [{"id": "reason-1", "role": "reasoning", "content": "unterminated"}]


def test_workflow_snapshot_builder_separates_consecutive_reasoning_blocks() -> None:
    """A new reasoning message id closes the previous block instead of merging into it."""
    from ag_ui.core import ReasoningMessageContentEvent, ReasoningMessageStartEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="first"))
    # Second block opens without the first ever being closed.
    builder.observe(ReasoningMessageStartEvent(message_id="reason-2", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-2", delta="second"))

    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "first"},
        {"id": "reason-2", "role": "reasoning", "content": "second"},
    ]


def test_workflow_snapshot_builder_folds_reasoning_content_without_a_start_event() -> None:
    """Reasoning deltas are kept even if the opening REASONING_MESSAGE_START was missed."""
    from ag_ui.core import ReasoningMessageContentEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="orphaned"))

    assert builder.build().messages == [{"id": "reason-1", "role": "reasoning", "content": "orphaned"}]


def test_workflow_snapshot_builder_attaches_encrypted_value_after_block_closed() -> None:
    """An encrypted value trailing REASONING_MESSAGE_END still lands on its message."""
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningMessageContentEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="hidden"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))
    builder.observe(
        ReasoningEncryptedValueEvent(subtype="message", entity_id="reason-1", encrypted_value="late-cipher")
    )

    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "hidden", "encryptedValue": "late-cipher"}
    ]


def test_workflow_snapshot_builder_ignores_tool_call_encrypted_values() -> None:
    """A tool-call-scoped encrypted value must not be folded in as reasoning content."""
    from ag_ui.core import ReasoningEncryptedValueEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningEncryptedValueEvent(subtype="tool-call", entity_id="call-a", encrypted_value="cipher"))

    assert builder.build().messages == []


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
