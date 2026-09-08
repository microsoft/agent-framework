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


def test_resume_with_interrupt_only_still_seeds_history():
    """Resume payloads that carry only the synthetic response still get history."""
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
