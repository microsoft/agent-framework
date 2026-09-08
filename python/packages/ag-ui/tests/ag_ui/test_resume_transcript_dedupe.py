# Copyright (c) Microsoft. All rights reserved.

"""Regression for AG-UI resume with client-replayed transcript (#8140)."""

from agent_framework_ag_ui._run_common import _reconstruct_messages_from_thread_snapshot


def test_resume_with_replayed_transcript_does_not_duplicate_history():
    """Clients that re-send the full transcript on resume must not double-write."""
    stored = [
        {"id": "u1", "role": "user", "content": "please run the tool"},
        {
            "id": "a1",
            "role": "assistant",
            "content": "",
            "toolCalls": [{"id": "c1", "type": "function", "function": {"name": "needs_approval", "arguments": "{}"}}],
        },
    ]
    # Reference AG-UI client replays the same transcript plus the resume turn.
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
    stored = [
        {"id": "u1", "role": "user", "content": "please run the tool"},
        {
            "id": "a1",
            "role": "assistant",
            "content": "",
            "toolCalls": [{"id": "c1", "type": "function", "function": {"name": "needs_approval", "arguments": "{}"}}],
        },
    ]
    incoming = [{"id": "u2", "role": "user", "content": "approved"}]

    reconstructed = _reconstruct_messages_from_thread_snapshot(
        stored_messages=stored,
        incoming_messages=incoming,
        stored_interrupt=[{"interruptId": "int-1"}],
    )

    assert [m.get("id") for m in reconstructed] == ["u1", "a1", "u2"]


def test_reconstruct_with_empty_incoming_returns_empty():
    """Empty incoming is unchanged; call sites must use resume_seeded_messages instead.

    Approval / checkpoint-only resumes commonly send ``messages: []``. The
    reconstructor intentionally returns that empty list so callers can distinguish
    \"no new turn\" from \"replayed transcript\" and fall back to seeding.
    """
    stored = [
        {"id": "u1", "role": "user", "content": "please run the tool"},
        {
            "id": "a1",
            "role": "assistant",
            "content": "",
            "toolCalls": [{"id": "c1", "type": "function", "function": {"name": "needs_approval", "arguments": "{}"}}],
        },
    ]

    assert (
        _reconstruct_messages_from_thread_snapshot(
            stored_messages=stored,
            incoming_messages=[],
            stored_interrupt=[{"interruptId": "int-1"}],
        )
        == []
    )
