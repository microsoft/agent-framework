# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from typing import Any

from agent_framework import Content, Message

from agent_framework_ag_ui._agent_run import (
    _clean_resolved_approvals_from_snapshot,
    _confirm_changes_target_call_id,
)


def _confirm_snapshot(
    *,
    original_call_id: str,
    confirm_call_id: str,
    accepted: bool,
) -> list[dict[str, Any]]:
    return [
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
                    "function": {
                        "name": "confirm_changes",
                        "arguments": json.dumps({"function_call_id": original_call_id}),
                    },
                },
            ],
        },
        {
            "role": "tool",
            "toolCallId": confirm_call_id,
            "content": json.dumps({"accepted": accepted, "steps": []}),
        },
    ]


def test_confirm_changes_target_ignores_non_list_tool_calls() -> None:
    snapshot_messages: list[dict[str, Any]] = [
        {
            "role": "assistant",
            "tool_calls": {"id": "call_confirm"},
        }
    ]

    target_call_id = _confirm_changes_target_call_id(snapshot_messages, "call_confirm", {})

    assert target_call_id is None


def test_confirm_changes_target_rejects_malformed_arguments_json() -> None:
    snapshot_messages: list[dict[str, Any]] = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_confirm",
                    "type": "function",
                    "function": {
                        "name": "confirm_changes",
                        "arguments": "{not-json",
                    },
                }
            ],
        }
    ]

    target_call_id = _confirm_changes_target_call_id(snapshot_messages, "call_confirm", {})

    assert target_call_id is None


def test_confirm_changes_snapshot_uses_original_call_id_with_multiple_results() -> None:
    snapshot_messages = _confirm_snapshot(
        original_call_id="call_target",
        confirm_call_id="call_confirm",
        accepted=True,
    )
    resolved_messages = [
        Message(
            role="tool",
            contents=[
                Content.from_function_result(call_id="call_old", result="old result"),
                Content.from_function_result(call_id="call_target", result="target result"),
            ],
        )
    ]

    _clean_resolved_approvals_from_snapshot(snapshot_messages, resolved_messages)

    assert snapshot_messages[1]["content"] == "target result"


def test_confirm_changes_snapshot_accepts_explicit_payload_call_id() -> None:
    snapshot_messages: list[dict[str, Any]] = [
        {
            "role": "tool",
            "toolCallId": "call_confirm",
            "content": json.dumps({"accepted": True, "function_call_id": "call_target"}),
        }
    ]
    resolved_messages = [
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="call_target", result="target result")],
        )
    ]

    _clean_resolved_approvals_from_snapshot(snapshot_messages, resolved_messages)

    assert snapshot_messages[0]["content"] == "target result"


def test_confirm_changes_snapshot_cleans_rejection_without_results() -> None:
    snapshot_messages = _confirm_snapshot(
        original_call_id="call_target",
        confirm_call_id="call_confirm",
        accepted=False,
    )

    _clean_resolved_approvals_from_snapshot(snapshot_messages, [])

    assert snapshot_messages[1]["content"] == "Changes declined."


def test_confirm_changes_snapshot_keeps_accepted_payload_when_target_result_is_missing() -> None:
    snapshot_messages = _confirm_snapshot(
        original_call_id="call_target",
        confirm_call_id="call_confirm",
        accepted=True,
    )
    original_content = snapshot_messages[1]["content"]
    resolved_messages = [
        Message(
            role="tool",
            contents=[
                Content.from_function_result(call_id="call_old_1", result="old result 1"),
                Content.from_function_result(call_id="call_old_2", result="old result 2"),
            ],
        )
    ]

    _clean_resolved_approvals_from_snapshot(snapshot_messages, resolved_messages)

    assert snapshot_messages[1]["content"] == original_content
