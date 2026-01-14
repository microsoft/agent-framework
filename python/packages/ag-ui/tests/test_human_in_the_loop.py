# Copyright (c) Microsoft. All rights reserved.

"""Tests for human in the loop (function approval requests)."""

from agent_framework import AgentResponseUpdate, FunctionApprovalRequestContent, FunctionCallContent

from agent_framework_ag_ui._events import AgentFrameworkEventBridge


async def test_function_approval_request_emission():
    """Test that CustomEvent is emitted for FunctionApprovalRequestContent."""
    # Set require_confirmation=False to test just the function_approval_request event
    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        require_confirmation=False,
    )

    # Create approval request
    func_call = FunctionCallContent(
        call_id="call_123",
        name="send_email",
        arguments={"to": "user@example.com", "subject": "Test"},
    )
    approval_request = FunctionApprovalRequestContent(
        id="approval_001",
        function_call=func_call,
    )

    update = AgentResponseUpdate(contents=[approval_request])
    events = await bridge.from_agent_run_update(update)

    # Should emit ToolCallEndEvent + CustomEvent for approval request
    assert len(events) == 2

    # First event: ToolCallEndEvent to close the tool call
    assert events[0].type == "TOOL_CALL_END"
    assert events[0].tool_call_id == "call_123"

    # Second event: CustomEvent with approval details
    event = events[1]
    assert event.type == "CUSTOM"
    assert event.name == "function_approval_request"
    assert event.value["id"] == "approval_001"
    assert event.value["function_call"]["call_id"] == "call_123"
    assert event.value["function_call"]["name"] == "send_email"
    assert event.value["function_call"]["arguments"]["to"] == "user@example.com"
    assert event.value["function_call"]["arguments"]["subject"] == "Test"


async def test_function_approval_request_with_confirm_changes():
    """Test that confirm_changes is also emitted when require_confirmation=True."""
    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        require_confirmation=True,
    )

    func_call = FunctionCallContent(
        call_id="call_456",
        name="delete_file",
        arguments={"path": "/tmp/test.txt"},
    )
    approval_request = FunctionApprovalRequestContent(
        id="approval_002",
        function_call=func_call,
    )

    update = AgentResponseUpdate(contents=[approval_request])
    events = await bridge.from_agent_run_update(update)

    # Should emit: ToolCallEndEvent, CustomEvent, and confirm_changes (Start, Args, End) = 5 events
    assert len(events) == 5

    # Check ToolCallEndEvent
    assert events[0].type == "TOOL_CALL_END"
    assert events[0].tool_call_id == "call_456"

    # Check function_approval_request CustomEvent
    assert events[1].type == "CUSTOM"
    assert events[1].name == "function_approval_request"

    # Check confirm_changes tool call events
    assert events[2].type == "TOOL_CALL_START"
    assert events[2].tool_call_name == "confirm_changes"
    assert events[3].type == "TOOL_CALL_ARGS"
    # Verify confirm_changes includes function info for Dojo UI
    import json

    args = json.loads(events[3].delta)
    assert args["function_name"] == "delete_file"
    assert args["function_call_id"] == "call_456"
    assert args["function_arguments"] == {"path": "/tmp/test.txt"}
    assert args["steps"] == [
        {
            "description": "Execute delete_file",
            "status": "enabled",
        }
    ]
    assert events[4].type == "TOOL_CALL_END"


async def test_multiple_approval_requests():
    """Test handling multiple approval requests in one update."""
    # Set require_confirmation=False to simplify the test
    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        require_confirmation=False,
    )

    func_call_1 = FunctionCallContent(
        call_id="call_1",
        name="create_event",
        arguments={"title": "Meeting"},
    )
    approval_1 = FunctionApprovalRequestContent(
        id="approval_1",
        function_call=func_call_1,
    )

    func_call_2 = FunctionCallContent(
        call_id="call_2",
        name="book_room",
        arguments={"room": "Conference A"},
    )
    approval_2 = FunctionApprovalRequestContent(
        id="approval_2",
        function_call=func_call_2,
    )

    update = AgentResponseUpdate(contents=[approval_1, approval_2])
    events = await bridge.from_agent_run_update(update)

    # Should emit ToolCallEndEvent + CustomEvent for each approval (4 events total)
    assert len(events) == 4

    # Events should alternate: End, Custom, End, Custom
    assert events[0].type == "TOOL_CALL_END"
    assert events[0].tool_call_id == "call_1"

    assert events[1].type == "CUSTOM"
    assert events[1].name == "function_approval_request"
    assert events[1].value["id"] == "approval_1"

    assert events[2].type == "TOOL_CALL_END"
    assert events[2].tool_call_id == "call_2"

    assert events[3].type == "CUSTOM"
    assert events[3].name == "function_approval_request"
    assert events[3].value["id"] == "approval_2"


async def test_function_approval_request_sets_stop_flag():
    """Test that function approval request sets should_stop_after_confirm flag.

    This ensures the orchestrator stops the run after emitting the approval request,
    allowing the UI to send back an approval response.
    """
    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
    )

    assert bridge.should_stop_after_confirm is False

    func_call = FunctionCallContent(
        call_id="call_stop_test",
        name="get_datetime",
        arguments={},
    )
    approval_request = FunctionApprovalRequestContent(
        id="approval_stop_test",
        function_call=func_call,
    )

    update = AgentResponseUpdate(contents=[approval_request])
    await bridge.from_agent_run_update(update)

    assert bridge.should_stop_after_confirm is True
