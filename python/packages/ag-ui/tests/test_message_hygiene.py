# Copyright (c) Microsoft. All rights reserved.

from agent_framework import ChatMessage, Content

from agent_framework_ag_ui._message_adapters import _deduplicate_messages, _sanitize_tool_history


def test_sanitize_tool_history_injects_confirm_changes_result() -> None:
    messages = [
        ChatMessage(
            role="assistant",
            contents=[
                Content.from_function_call(
                    name="confirm_changes",
                    call_id="call_confirm_123",
                    arguments='{"changes": "test"}',
                )
            ],
        ),
        ChatMessage(
            role="user",
            contents=[Content.from_text(text='{"accepted": true}')],
        ),
    ]

    sanitized = _sanitize_tool_history(messages)

    tool_messages = [
        msg for msg in sanitized if (msg.role.value if hasattr(msg.role, "value") else str(msg.role)) == "tool"
    ]
    assert len(tool_messages) == 1
    assert str(tool_messages[0].contents[0].call_id) == "call_confirm_123"
    assert tool_messages[0].contents[0].result == "Confirmed"


def test_deduplicate_messages_prefers_non_empty_tool_results() -> None:
    messages = [
        ChatMessage(
            role="tool",
            contents=[Content.from_function_result(call_id="call1", result="")],
        ),
        ChatMessage(
            role="tool",
            contents=[Content.from_function_result(call_id="call1", result="result data")],
        ),
    ]

    deduped = _deduplicate_messages(messages)
    assert len(deduped) == 1
    assert deduped[0].contents[0].result == "result data"
