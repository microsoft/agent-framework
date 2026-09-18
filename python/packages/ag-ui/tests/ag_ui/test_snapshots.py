# Copyright (c) Microsoft. All rights reserved.

"""Tests for AG-UI thread snapshot storage primitives."""

from dataclasses import fields

from agent_framework_ag_ui import AGUIThreadSnapshot, AGUIThreadSnapshotStore, InMemoryAGUIThreadSnapshotStore
from agent_framework_ag_ui._snapshots import _session_id_for_thread


def test_internal_session_id_is_stable_scoped_and_unambiguous() -> None:
    """Internal session identity preserves raw IDs only when no trusted scope is present."""
    raw_thread_id = "shared-thread"
    scoped_session_id = _session_id_for_thread(scope="tenant-a", thread_id=raw_thread_id)

    assert _session_id_for_thread(scope=None, thread_id=raw_thread_id) == raw_thread_id
    assert scoped_session_id == _session_id_for_thread(scope="tenant-a", thread_id=raw_thread_id)
    assert scoped_session_id.startswith("ag-ui:v1:scoped:")
    assert len(scoped_session_id.removeprefix("ag-ui:v1:scoped:")) == 64
    assert scoped_session_id != _session_id_for_thread(scope="tenant-b", thread_id=raw_thread_id)
    assert _session_id_for_thread(scope="ab", thread_id="c") != _session_id_for_thread(scope="a", thread_id="bc")


def test_internal_session_id_keeps_scoped_and_unscoped_namespaces_disjoint() -> None:
    """A client cannot use a scoped internal ID as an unscoped raw Thread ID."""
    scoped_session_id = _session_id_for_thread(scope="tenant-a", thread_id="shared-thread")
    unscoped_session_id = _session_id_for_thread(scope=None, thread_id=scoped_session_id)

    assert unscoped_session_id.startswith("ag-ui:v1:unscoped:")
    assert unscoped_session_id != scoped_session_id
    assert unscoped_session_id == _session_id_for_thread(scope=None, thread_id=scoped_session_id)


def test_internal_session_id_supports_deprecated_legacy_mapping() -> None:
    """The explicit migration escape hatch preserves the legacy raw provider key."""
    assert (
        _session_id_for_thread(
            scope="tenant-a",
            thread_id="shared-thread",
            legacy_session_id_from_thread_id=True,
        )
        == "shared-thread"
    )


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


def test_workflow_snapshot_builder_keeps_encrypted_only_reasoning_ended_before_its_value() -> None:
    """Protected-data-only reasoning survives the no-flow order, where END precedes the value.

    `_emit_text_reasoning` without a flow emits REASONING_MESSAGE_END before
    REASONING_ENCRYPTED_VALUE. The message carries no display text, so closing it at
    REASONING_MESSAGE_END would discard it and leave the encrypted value nothing to
    attach to.
    """
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningEndEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))
    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id="reason-1", encrypted_value="cipher"))
    builder.observe(ReasoningEndEvent(message_id="reason-1"))

    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "", "encryptedValue": "cipher"}
    ]


def test_workflow_snapshot_builder_drops_reasoning_with_neither_text_nor_encrypted_value() -> None:
    """An empty reasoning block with nothing to replay is not synthesized into a message."""
    from ag_ui.core import (
        ReasoningEndEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))
    builder.observe(ReasoningEndEvent(message_id="reason-1"))

    assert builder.build().messages == []


def test_workflow_snapshot_builder_closes_previous_block_on_new_reasoning_start() -> None:
    """A new REASONING_START finalizes a message the previous block left open."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="first"))
    # No REASONING_END: the next block's start has to close this one.
    builder.observe(ReasoningStartEvent(message_id="reason-2"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-2", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-2", delta="second"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-2"))

    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "first"},
        {"id": "reason-2", "role": "reasoning", "content": "second"},
    ]


def test_workflow_snapshot_builder_attaches_encrypted_value_after_intervening_output() -> None:
    """Text arriving between a reasoning message and its encrypted value does not lose the value."""
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningMessageContentEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        TextMessageContentEvent,
        TextMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="thinking"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))
    # Text output flushes the reasoning message before the encrypted value shows up.
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="answer"))
    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id="reason-1", encrypted_value="cipher"))

    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "thinking", "encryptedValue": "cipher"},
        {"id": "text-1", "role": "assistant", "content": "answer"},
    ]


def test_workflow_snapshot_builder_ignores_reasoning_end_for_unopened_message() -> None:
    """A reasoning end event for a message that was never opened is a no-op."""
    from ag_ui.core import ReasoningEndEvent, ReasoningMessageContentEvent, ReasoningMessageStartEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningEndEvent(message_id="never-opened"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="kept"))
    # An end event for a different id must not close the open message.
    builder.observe(ReasoningEndEvent(message_id="other"))

    assert builder.build().messages == [{"id": "reason-1", "role": "reasoning", "content": "kept"}]


def test_workflow_snapshot_builder_ignores_tool_call_encrypted_values() -> None:
    """A tool-call-scoped encrypted value must not be folded in as reasoning content."""
    from ag_ui.core import ReasoningEncryptedValueEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningEncryptedValueEvent(subtype="tool-call", entity_id="call-a", encrypted_value="cipher"))

    assert builder.build().messages == []


def test_workflow_snapshot_builder_preserves_safe_bounded_mcp_replay() -> None:
    """Workflow event synthesis persists model-safe content and private Host replay data."""
    from ag_ui.core import ToolCallResultEvent

    from agent_framework_ag_ui._utils import (
        _AGUI_MCP_TOOL_RESULT_KEY,
        _AGUI_TOOL_RESULT_HOST_PAYLOAD_KEY,
        _AGUI_TOOL_RESULT_MODEL_CONTENT_KEY,
    )
    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    host_content = '{"structuredContent":{"widget":"host"}}'
    builder = _WorkflowSnapshotBuilder([])
    builder.observe(
        ToolCallResultEvent.model_validate(
            {
                "messageId": "result",
                "toolCallId": "mcp-call",
                "content": host_content,
                "role": "tool",
                _AGUI_MCP_TOOL_RESULT_KEY: True,
                _AGUI_TOOL_RESULT_HOST_PAYLOAD_KEY: host_content,
                _AGUI_TOOL_RESULT_MODEL_CONTENT_KEY: [{"type": "text", "text": "Model summary"}],
            }
        )
    )

    message = builder.build().messages[0]
    assert message["content"] == "Model summary"
    assert message[_AGUI_TOOL_RESULT_HOST_PAYLOAD_KEY] == host_content
    assert message[_AGUI_TOOL_RESULT_MODEL_CONTENT_KEY] == [{"type": "text", "text": "Model summary"}]


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


def test_workflow_snapshot_builder_keeps_output_before_later_reasoning() -> None:
    """An output event that streams before reasoning replays before it, not after."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        TextMessageContentEvent,
        TextMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    # An `output` event streams assistant text. The workflow keeps running, so no
    # TextMessageEndEvent arrives before the later `intermediate` event opens reasoning.
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="visible output"))
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="later thought"))

    messages = builder.build().messages
    assert [(message["role"], message.get("content")) for message in messages] == [
        ("assistant", "visible output"),
        ("reasoning", "later thought"),
    ]


def test_workflow_snapshot_builder_keeps_encrypted_only_reasoning_addressable_across_text() -> None:
    """A protected-data-only block flushed by intervening text still receives its value."""
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    # `_emit_text_reasoning` without a flow emits REASONING_MESSAGE_END before the
    # encrypted value, and emits no content event at all when the reasoning carries
    # only protected data. Intervening text must not discard the message the value
    # still has to land on.
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="visible"))
    builder.observe(TextMessageEndEvent(message_id="text-1"))
    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id="reason-1", encrypted_value="enc-1"))

    messages = builder.build().messages
    reasoning = [message for message in messages if message.get("role") == "reasoning"]
    assert reasoning == [{"id": "reason-1", "role": "reasoning", "content": "", "encryptedValue": "enc-1"}]
    assert [message.get("role") for message in messages] == ["reasoning", "assistant"]


def test_workflow_snapshot_builder_splits_text_resumed_after_reasoning() -> None:
    """Text resumed after a reasoning block replays around it under distinct ids."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="part one "))
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="thought"))
    # The provider reuses the text message id when the visible message resumes.
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="part two"))
    builder.observe(TextMessageEndEvent(message_id="text-1"))

    messages = builder.build().messages
    assert [(message["role"], message.get("content")) for message in messages] == [
        ("assistant", "part one "),
        ("reasoning", "thought"),
        ("assistant", "part two"),
    ]
    ids = [message.get("id") for message in messages]
    assert len(set(ids)) == len(ids), f"snapshot replays two messages under one id: {ids}"
    assert ids[0] == "text-1"


def test_workflow_snapshot_builder_keeps_reasoning_before_a_tool_result() -> None:
    """Reasoning that streams before a tool result replays before it."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        ToolCallResultEvent,
        ToolCallStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ToolCallStartEvent(tool_call_id="call-1", tool_call_name="toolA", parent_message_id="msg-1"))
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="deciding"))
    builder.observe(ToolCallResultEvent(message_id="result-1", tool_call_id="call-1", content="done"))

    assert [message.get("role") for message in builder.build().messages] == ["assistant", "reasoning", "tool"]


def test_workflow_snapshot_builder_ignores_repeated_reasoning_start_for_open_block() -> None:
    """A duplicate start for the open block keeps its deltas under a single id."""
    from ag_ui.core import ReasoningMessageContentEvent, ReasoningMessageStartEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="first "))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="second"))

    assert builder.build().messages == [{"id": "reason-1", "role": "reasoning", "content": "first second"}]


def test_workflow_snapshot_reasoning_between_tool_call_and_result_stays_convertible() -> None:
    """Reasoning between a tool call and its result must not break provider adjacency."""
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        ToolCallArgsEvent,
        ToolCallResultEvent,
        ToolCallStartEvent,
    )

    from agent_framework_ag_ui._message_adapters import agui_messages_to_agent_framework
    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ToolCallStartEvent(tool_call_id="call-1", tool_call_name="toolA", parent_message_id="msg-1"))
    builder.observe(ToolCallArgsEvent(tool_call_id="call-1", delta='{"a": 1}'))
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="deciding"))
    builder.observe(ToolCallResultEvent(message_id="result-1", tool_call_id="call-1", content="ok"))

    snapshot = builder.build().messages
    assert [message.get("role") for message in snapshot] == ["assistant", "reasoning", "tool"]

    # Reasoning is UI-only and dropped before provider conversion, so the result has to
    # come back adjacent to the call it belongs to.
    converted = agui_messages_to_agent_framework(snapshot)
    shapes = [(message.role, [content.type for content in message.contents]) for message in converted]
    call_indexes = [index for index, (_, types) in enumerate(shapes) if "function_call" in types]
    result_indexes = [index for index, (_, types) in enumerate(shapes) if "function_result" in types]
    assert call_indexes and result_indexes, shapes
    assert result_indexes[0] == call_indexes[0] + 1, shapes


def test_workflow_snapshot_builder_keeps_reasoning_shell_addressable_after_a_build() -> None:
    """A value arriving after a snapshot is taken still lands on the next one."""
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageEndEvent(message_id="reason-1"))

    # An unclaimed shell is excluded from the snapshot rather than deleted, so a store
    # that saves mid-run does not make the protected value unrecoverable.
    assert builder.build().messages == []

    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id="reason-1", encrypted_value="enc-late"))
    assert builder.build().messages == [
        {"id": "reason-1", "role": "reasoning", "content": "", "encryptedValue": "enc-late"}
    ]


def test_workflow_snapshot_builder_message_id_index_tracks_every_append() -> None:
    """The id index must cover every appended message, or collisions go undetected.

    `_has_synthesized_message_id` is a set lookup because scanning the message list on
    each flush made snapshot building quadratic. That only stays correct while every
    append goes through `_append_synthesized_message`, so pin the invariant rather than
    the timing.
    """
    from ag_ui.core import (
        ReasoningMessageContentEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
        ToolCallArgsEvent,
        ToolCallResultEvent,
        ToolCallStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([{"id": "seed-1", "role": "user", "content": "hi"}])
    builder.observe(ToolCallStartEvent(tool_call_id="call-1", tool_call_name="toolA", parent_message_id="msg-1"))
    builder.observe(ToolCallArgsEvent(tool_call_id="call-1", delta="{}"))
    builder.observe(ReasoningStartEvent(message_id="reason-1"))
    builder.observe(ReasoningMessageStartEvent(message_id="reason-1", role="reasoning"))
    builder.observe(ReasoningMessageContentEvent(message_id="reason-1", delta="why"))
    builder.observe(ToolCallResultEvent(message_id="result-1", tool_call_id="call-1", content="ok"))
    builder.observe(TextMessageStartEvent(message_id="text-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="answer"))
    builder.observe(TextMessageEndEvent(message_id="text-1"))

    messages = builder.build().messages
    appended_ids = {message_id for message in messages if (message_id := message.get("id"))}
    assert appended_ids <= builder._synthesized_message_ids, (  # pyright: ignore[reportPrivateUsage]
        "an append bypassed `_append_synthesized_message`, so the id index is stale: "
        f"missing {appended_ids - builder._synthesized_message_ids}"  # pyright: ignore[reportPrivateUsage]
    )


def test_workflow_snapshot_builder_keeps_encrypted_reasoning_across_concurrent_text() -> None:
    """Concurrent output must not discard a reasoning block awaiting its encrypted value.

    Event order captured from a live fan-out workflow on gpt-5-mini: with a flow, the
    encrypted value is emitted right after REASONING_MESSAGE_START and before
    REASONING_MESSAGE_END, and the provider sends it twice. The reasoning carries no
    visible text, so a concurrent executor's text message landing in the gap before the
    value arrives used to flush an empty message and lose the value.
    """
    from ag_ui.core import (
        ReasoningEncryptedValueEvent,
        ReasoningEndEvent,
        ReasoningMessageEndEvent,
        ReasoningMessageStartEvent,
        ReasoningStartEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    reasoning_id = "rs_0773abc2200cb36b006aa02287c0d0819"
    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ReasoningStartEvent(message_id=reasoning_id))
    builder.observe(ReasoningMessageStartEvent(message_id=reasoning_id, role="reasoning"))
    # A concurrently scheduled executor emits its own message here.
    builder.observe(TextMessageStartEvent(message_id="concurrent-1", role="assistant"))
    builder.observe(TextMessageContentEvent(message_id="concurrent-1", delta="from the other branch"))
    builder.observe(TextMessageEndEvent(message_id="concurrent-1"))
    # The provider emits the value twice for one item; both must be idempotent.
    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id=reasoning_id, encrypted_value="enc"))
    builder.observe(ReasoningEncryptedValueEvent(subtype="message", entity_id=reasoning_id, encrypted_value="enc"))
    builder.observe(ReasoningMessageEndEvent(message_id=reasoning_id))
    builder.observe(ReasoningEndEvent(message_id=reasoning_id))

    messages = builder.build().messages
    assert [message.get("role") for message in messages] == ["reasoning", "assistant"]
    assert messages[0] == {"id": reasoning_id, "role": "reasoning", "content": "", "encryptedValue": "enc"}


def test_workflow_snapshot_builder_keeps_both_interleaved_text_messages_without_starts() -> None:
    """Content events for a second message must not overwrite the first one's text.

    `_observe_text_start` flushes an open message under a different id; the no-start path
    used to overwrite it and lose the content. Concurrently scheduled executors reach
    this by interleaving content events, which a live fan-out workflow does.
    """
    from ag_ui.core import TextMessageContentEvent

    from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

    builder = _WorkflowSnapshotBuilder([])
    builder.observe(TextMessageContentEvent(message_id="from-agent-a", delta="branch A"))
    builder.observe(TextMessageContentEvent(message_id="from-agent-b", delta="branch B"))

    assert builder.build().messages == [
        {"id": "from-agent-a", "role": "assistant", "content": "branch A"},
        {"id": "from-agent-b", "role": "assistant", "content": "branch B"},
    ]
