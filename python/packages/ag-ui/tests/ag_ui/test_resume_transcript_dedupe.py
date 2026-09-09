# Copyright (c) Microsoft. All rights reserved.

"""Regression for AG-UI resume with client-replayed transcript (#8140)."""

from agent_framework_ag_ui._run_common import _reconstruct_messages_from_thread_snapshot
from agent_framework_ag_ui._snapshot_session import ThreadSnapshotSession
from agent_framework_ag_ui._snapshots import AGUIThreadSnapshot


def _stored_history() -> list[dict]:
    return [
        {"id": "u1", "role": "user", "content": "please run the tool"},
        {
            "id": "a1",
            "role": "assistant",
            "content": "",
            "toolCalls": [{"id": "c1", "type": "function", "function": {"name": "needs_approval", "arguments": "{}"}}],
        },
    ]


def test_resume_with_replayed_transcript_does_not_duplicate_history():
    """Clients that re-send the full transcript on resume must not double-write."""
    stored = _stored_history()
    incoming = [
        *stored,
        {"id": "u2", "role": "user", "content": "approved"},
    ]

    reconstructed = _reconstruct_messages_from_thread_snapshot(
        stored_messages=stored,
        incoming_messages=incoming,
        stored_interrupt=[{"interruptId": "int-1"}],
    )

    assert [m.get("id") for m in reconstructed] == ["u1", "a1", "u2"]
    assert len(reconstructed) == 3


def test_resume_with_partial_new_turn_still_seeds_history():
    """Non-empty resume suffix is overlapped onto stored history without duplication."""
    stored = _stored_history()
    incoming = [{"id": "u2", "role": "user", "content": "approved"}]

    reconstructed = _reconstruct_messages_from_thread_snapshot(
        stored_messages=stored,
        incoming_messages=incoming,
        stored_interrupt=[{"interruptId": "int-1"}],
    )

    assert [m.get("id") for m in reconstructed] == ["u1", "a1", "u2"]


def test_reconstruct_with_empty_incoming_returns_empty():
    """Empty incoming is unchanged; call sites must use resume seeding instead."""
    stored = _stored_history()

    assert (
        _reconstruct_messages_from_thread_snapshot(
            stored_messages=stored,
            incoming_messages=[],
            stored_interrupt=[{"interruptId": "int-1"}],
        )
        == []
    )


def test_reconcile_resume_messages_empty_vs_replayed():
    """Session-owned reconcile covers interrupt-only and replayed transcript shapes."""
    stored = _stored_history()
    session = ThreadSnapshotSession(
        store=None,
        scope=None,
        thread_id="t1",
        stored=AGUIThreadSnapshot(
            messages=stored,
            state=None,
            interrupt=[{"interruptId": "int-1"}],
            session_state=None,
        ),
    )

    empty = session.reconcile_resume_messages([])
    assert [m.get("id") for m in empty] == ["u1", "a1"]

    replayed = session.reconcile_resume_messages(
        [
            *stored,
            {"id": "u2", "role": "user", "content": "approved"},
        ]
    )
    assert [m.get("id") for m in replayed] == ["u1", "a1", "u2"]
