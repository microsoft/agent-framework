# Copyright (c) Microsoft. All rights reserved.

"""Tests for AG-UI confirm_changes snapshot payload cleaning and tool result preservation."""

from __future__ import annotations

import json
from typing import Any

from agent_framework import Content, Message

from agent_framework_ag_ui._agent_run import _clean_resolved_approvals_from_snapshot


def test_clean_resolved_approvals_from_snapshot_confirm_changes_flow() -> None:
    """Verify that _clean_resolved_approvals_from_snapshot replaces confirm_changes
    approval payloads (whose toolCallId is confirm_id) with the executed tool results
    from resolved_messages (whose call_id is the original tool call ID).
    """
    original_call_id = "call_orig_123"
    confirm_call_id = "call_confirm_456"

    # Snapshot message sent by client containing confirm_changes response payload
    snapshot_messages: list[dict[str, Any]] = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": original_call_id,
                    "type": "function",
                    "function": {"name": "apply_changes", "arguments": "{}"},
                },
                {
                    "id": confirm_call_id,
                    "type": "function",
                    "function": {"name": "confirm_changes", "arguments": "{}"},
                },
            ],
        },
        {
            "role": "tool",
            "toolCallId": confirm_call_id,
            "content": json.dumps({"accepted": True, "steps": []}),
        },
    ]

    # Executed tool results returned after approval resolution
    resolved_messages: list[Message] = [
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id=original_call_id, result="Changes applied successfully.")],
        )
    ]

    _clean_resolved_approvals_from_snapshot(snapshot_messages, resolved_messages)

    # The confirm_changes tool message payload must no longer contain the raw {"accepted": true} JSON
    tool_msg = snapshot_messages[1]
    assert tool_msg["toolCallId"] == confirm_call_id
    assert tool_msg["content"] == "Changes applied successfully."
    assert "accepted" not in tool_msg["content"]


def test_clean_resolved_approvals_from_snapshot_confirm_changes_rejection() -> None:
    """Verify that rejected confirm_changes responses clean out the approval payload."""
    confirm_call_id = "call_confirm_789"

    snapshot_messages: list[dict[str, Any]] = [
        {
            "role": "tool",
            "toolCallId": confirm_call_id,
            "content": json.dumps({"accepted": False}),
        },
    ]

    resolved_messages: list[Message] = []

    _clean_resolved_approvals_from_snapshot(snapshot_messages, resolved_messages)

    tool_msg = snapshot_messages[0]
    assert tool_msg["content"] == "Changes declined."
    assert "accepted" not in tool_msg["content"]
