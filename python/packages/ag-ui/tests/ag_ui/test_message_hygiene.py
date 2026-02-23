# Copyright (c) Microsoft. All rights reserved.

from agent_framework import Content, Message

from agent_framework_ag_ui._message_adapters import _deduplicate_messages, _sanitize_tool_history


def test_sanitize_tool_history_filters_out_confirm_changes_only_message() -> None:
    """Test that assistant messages with ONLY confirm_changes are filtered out entirely.

    When an assistant message contains only a confirm_changes tool call (no other tools),
    the entire message should be filtered out because confirm_changes is a synthetic
    tool for the approval UI flow that shouldn't be sent to the LLM.
    """
    messages = [
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    name="confirm_changes",
                    call_id="call_confirm_123",
                    arguments='{"changes": "test"}',
                )
            ],
        ),
        Message(
            role="user",
            contents=[Content.from_text(text='{"accepted": true}')],
        ),
    ]

    sanitized = _sanitize_tool_history(messages)

    # Assistant message with only confirm_changes should be filtered out
    assistant_messages = [
        msg for msg in sanitized if (msg.role if hasattr(msg.role, "value") else str(msg.role)) == "assistant"
    ]
    assert len(assistant_messages) == 0

    # No synthetic tool result should be injected since confirm_changes was filtered out
    tool_messages = [msg for msg in sanitized if (msg.role if hasattr(msg.role, "value") else str(msg.role)) == "tool"]
    assert len(tool_messages) == 0


def test_deduplicate_messages_prefers_non_empty_tool_results() -> None:
    messages = [
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="call1", result="")],
        ),
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="call1", result="result data")],
        ),
    ]

    deduped = _deduplicate_messages(messages)
    assert len(deduped) == 1
    assert deduped[0].contents[0].result == "result data"


def test_convert_approval_results_to_tool_messages() -> None:
    """Test that function_result content in user messages gets converted to tool messages.

    This is a regression test for the MCP tool double-call bug where approved tool
    results ended up in user messages instead of tool messages, causing OpenAI to
    reject the request with 'tool_call_ids did not have response messages'.
    """
    from agent_framework_ag_ui._agent_run import _convert_approval_results_to_tool_messages

    # Simulate what happens after _resolve_approval_responses:
    # A user message contains function_result content (the executed tool result)
    messages = [
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="call_123", name="my_mcp_tool", arguments="{}"),
            ],
        ),
        Message(
            role="user",
            contents=[
                Content.from_function_result(call_id="call_123", result="tool execution result"),
            ],
        ),
    ]

    _convert_approval_results_to_tool_messages(messages)

    # After conversion, the function result should be in a tool message, not user message
    assert len(messages) == 2

    # First message unchanged
    assert messages[0].role == "assistant"

    # Second message should now be role="tool"
    assert messages[1].role == "tool"
    assert messages[1].contents[0].type == "function_result"
    assert messages[1].contents[0].call_id == "call_123"


def test_convert_approval_results_preserves_other_user_content() -> None:
    """Test that user messages with mixed content are handled correctly.

    If a user message has both function_result content and other content (like text),
    the function_result content should be extracted to a tool message while the
    remaining content stays in the user message.
    """
    from agent_framework_ag_ui._agent_run import _convert_approval_results_to_tool_messages

    messages = [
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="call_123", name="my_tool", arguments="{}"),
            ],
        ),
        Message(
            role="user",
            contents=[
                Content.from_text(text="User also said something"),
                Content.from_function_result(call_id="call_123", result="tool result"),
            ],
        ),
    ]

    _convert_approval_results_to_tool_messages(messages)

    # Should have 3 messages now: assistant, tool (with result), user (with text)
    # OpenAI requires tool messages immediately after the assistant message with the tool call
    assert len(messages) == 3

    # First message unchanged
    assert messages[0].role == "assistant"

    # Second message should be tool with result (must come right after assistant per OpenAI requirements)
    assert messages[1].role == "tool"
    assert messages[1].contents[0].type == "function_result"

    # Third message should be user with just text
    assert messages[2].role == "user"
    assert len(messages[2].contents) == 1
    assert messages[2].contents[0].type == "text"


def test_sanitize_tool_history_filters_confirm_changes_keeps_other_tools() -> None:
    """Test that confirm_changes is filtered but other tools are preserved.

    When an assistant message contains both a real tool call and confirm_changes,
    confirm_changes should be filtered out while the real tool call is kept.
    No synthetic result is injected for confirm_changes since it's filtered.
    """
    messages = [
        # User asks something
        Message(
            role="user",
            contents=[Content.from_text(text="What time is it?")],
        ),
        # Assistant calls MCP tool + confirm_changes
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="call_1", name="get_datetime", arguments="{}"),
                Content.from_function_call(call_id="call_c1", name="confirm_changes", arguments="{}"),
            ],
        ),
        # Tool result for the actual MCP tool
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="call_1", result="2024-01-01 12:00:00")],
        ),
        # User asks something else
        Message(
            role="user",
            contents=[Content.from_text(text="What's the date?")],
        ),
    ]

    sanitized = _sanitize_tool_history(messages)

    # Find the assistant message
    assistant_messages = [
        msg for msg in sanitized if (msg.role if hasattr(msg.role, "value") else str(msg.role)) == "assistant"
    ]
    assert len(assistant_messages) == 1

    # Assistant message should only have get_datetime, not confirm_changes
    function_call_names = [c.name for c in assistant_messages[0].contents if c.type == "function_call"]
    assert "get_datetime" in function_call_names
    assert "confirm_changes" not in function_call_names

    # Only one tool message (for call_1), no synthetic for confirm_changes
    tool_messages = [msg for msg in sanitized if (msg.role if hasattr(msg.role, "value") else str(msg.role)) == "tool"]
    assert len(tool_messages) == 1
    assert str(tool_messages[0].contents[0].call_id) == "call_1"


def test_sanitize_tool_history_filters_confirm_changes_from_assistant_messages() -> None:
    """Test that confirm_changes is removed from assistant messages sent to LLM.

    This is a regression test for the human-in-the-loop bug where the LLM would see
    confirm_changes with function_arguments containing the original steps (e.g., 5 steps)
    even when the user only approved a subset (e.g., 2 steps), causing the LLM to
    respond with "Here's your 5-step plan" instead of "Here's your 2-step plan".
    """
    messages = [
        Message(
            role="user",
            contents=[Content.from_text(text="Build a robot")],
        ),
        # Assistant message with both generate_task_steps and confirm_changes
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="call_1",
                    name="generate_task_steps",
                    arguments='{"steps": [{"description": "Step 1"}, {"description": "Step 2"}]}',
                ),
                Content.from_function_call(
                    call_id="call_c1",
                    name="confirm_changes",
                    arguments='{"function_arguments": {"steps": [{"description": "Step 1"}, {"description": "Step 2"}]}}',
                ),
            ],
        ),
        # Approval response
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=True,
                    id="call_1",
                    function_call=Content.from_function_call(
                        call_id="call_1",
                        name="generate_task_steps",
                        arguments='{"steps": [{"description": "Step 1"}]}',  # Only 1 step approved
                    ),
                ),
            ],
        ),
    ]

    sanitized = _sanitize_tool_history(messages)

    # Find the assistant message in sanitized output
    assistant_messages = [
        msg for msg in sanitized if (msg.role if hasattr(msg.role, "value") else str(msg.role)) == "assistant"
    ]

    assert len(assistant_messages) == 1

    # The assistant message should NOT contain confirm_changes
    assistant_contents = assistant_messages[0].contents or []
    function_call_names = [c.name for c in assistant_contents if c.type == "function_call"]
    assert "generate_task_steps" in function_call_names
    assert "confirm_changes" not in function_call_names

    # No synthetic tool result for confirm_changes (it was filtered from the message)
    tool_messages = [msg for msg in sanitized if (msg.role if hasattr(msg.role, "value") else str(msg.role)) == "tool"]
    # No tool results expected since there are no completed tool calls
    # (the approval response is handled separately by the framework)
    tool_call_ids = {str(msg.contents[0].call_id) for msg in tool_messages}
    assert "call_c1" not in tool_call_ids  # No synthetic result for confirm_changes
