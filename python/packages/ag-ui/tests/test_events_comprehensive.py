# Copyright (c) Microsoft. All rights reserved.

"""Comprehensive tests for AgentFrameworkEventBridge (_events.py)."""

import json

from agent_framework import (
    AgentRunResponseUpdate,
    FunctionApprovalRequestContent,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)


async def test_basic_text_message_conversion():
    """Test basic TextContent to AG-UI events."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    update = AgentRunResponseUpdate(contents=[TextContent(text="Hello")])
    events = await bridge.from_agent_run_update(update)

    assert len(events) == 2
    assert events[0].type == "TEXT_MESSAGE_START"
    assert events[0].role == "assistant"
    assert events[1].type == "TEXT_MESSAGE_CONTENT"
    assert events[1].delta == "Hello"


async def test_text_message_streaming():
    """Test streaming TextContent with multiple chunks."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    update1 = AgentRunResponseUpdate(contents=[TextContent(text="Hello ")])
    update2 = AgentRunResponseUpdate(contents=[TextContent(text="world")])

    events1 = await bridge.from_agent_run_update(update1)
    events2 = await bridge.from_agent_run_update(update2)

    # First update: START + CONTENT
    assert len(events1) == 2
    assert events1[0].type == "TEXT_MESSAGE_START"
    assert events1[1].delta == "Hello "

    # Second update: just CONTENT (same message)
    assert len(events2) == 1
    assert events2[0].type == "TEXT_MESSAGE_CONTENT"
    assert events2[0].delta == "world"

    # Both content events should have same message_id
    assert events1[1].message_id == events2[0].message_id


async def test_skip_text_content_for_structured_outputs():
    """Test that text content is skipped when skip_text_content=True."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread", skip_text_content=True)

    update = AgentRunResponseUpdate(contents=[TextContent(text='{"result": "data"}')])
    events = await bridge.from_agent_run_update(update)

    # No events should be emitted
    assert len(events) == 0


async def test_tool_call_with_name():
    """Test FunctionCallContent with name emits ToolCallStartEvent."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    update = AgentRunResponseUpdate(contents=[FunctionCallContent(name="search_web", call_id="call_123")])
    events = await bridge.from_agent_run_update(update)

    assert len(events) == 1
    assert events[0].type == "TOOL_CALL_START"
    assert events[0].tool_call_name == "search_web"
    assert events[0].tool_call_id == "call_123"


async def test_tool_call_streaming_args():
    """Test streaming tool call arguments."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    # First chunk: name only
    update1 = AgentRunResponseUpdate(contents=[FunctionCallContent(name="search_web", call_id="call_123")])
    events1 = await bridge.from_agent_run_update(update1)

    # Second chunk: arguments chunk 1 (name can be empty string for continuation)
    update2 = AgentRunResponseUpdate(
        contents=[FunctionCallContent(name="", call_id="call_123", arguments='{"query": "')]
    )
    events2 = await bridge.from_agent_run_update(update2)

    # Third chunk: arguments chunk 2
    update3 = AgentRunResponseUpdate(contents=[FunctionCallContent(name="", call_id="call_123", arguments='AI"}')])
    events3 = await bridge.from_agent_run_update(update3)

    # First update: ToolCallStartEvent
    assert len(events1) == 1
    assert events1[0].type == "TOOL_CALL_START"

    # Second update: ToolCallArgsEvent
    assert len(events2) == 1
    assert events2[0].type == "TOOL_CALL_ARGS"
    assert events2[0].delta == '{"query": "'

    # Third update: ToolCallArgsEvent
    assert len(events3) == 1
    assert events3[0].type == "TOOL_CALL_ARGS"
    assert events3[0].delta == 'AI"}'

    # All should have same tool_call_id
    assert events1[0].tool_call_id == events2[0].tool_call_id == events3[0].tool_call_id


async def test_tool_result_with_dict():
    """Test FunctionResultContent with dict result."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    result_data = {"status": "success", "count": 42}
    update = AgentRunResponseUpdate(contents=[FunctionResultContent(call_id="call_123", result=result_data)])
    events = await bridge.from_agent_run_update(update)

    # Should emit ToolCallEndEvent + ToolCallResultEvent
    assert len(events) == 2
    assert events[0].type == "TOOL_CALL_END"
    assert events[0].tool_call_id == "call_123"

    assert events[1].type == "TOOL_CALL_RESULT"
    assert events[1].tool_call_id == "call_123"
    assert events[1].role == "tool"
    # Result should be JSON-serialized
    assert json.loads(events[1].content) == result_data


async def test_tool_result_with_string():
    """Test FunctionResultContent with string result."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    update = AgentRunResponseUpdate(contents=[FunctionResultContent(call_id="call_123", result="Search complete")])
    events = await bridge.from_agent_run_update(update)

    assert len(events) == 2
    assert events[0].type == "TOOL_CALL_END"
    assert events[1].type == "TOOL_CALL_RESULT"
    assert events[1].content == "Search complete"


async def test_tool_result_with_none():
    """Test FunctionResultContent with None result."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    update = AgentRunResponseUpdate(contents=[FunctionResultContent(call_id="call_123", result=None)])
    events = await bridge.from_agent_run_update(update)

    assert len(events) == 2
    assert events[0].type == "TOOL_CALL_END"
    assert events[1].type == "TOOL_CALL_RESULT"
    assert events[1].content == ""


async def test_multiple_tool_results_in_sequence():
    """Test multiple tool results processed sequentially."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    update = AgentRunResponseUpdate(
        contents=[
            FunctionResultContent(call_id="call_1", result="Result 1"),
            FunctionResultContent(call_id="call_2", result="Result 2"),
        ]
    )
    events = await bridge.from_agent_run_update(update)

    # Each result emits: ToolCallEndEvent + ToolCallResultEvent = 4 events total
    assert len(events) == 4
    assert events[0].tool_call_id == "call_1"
    assert events[1].tool_call_id == "call_1"
    assert events[2].tool_call_id == "call_2"
    assert events[3].tool_call_id == "call_2"


async def test_function_approval_request_basic():
    """Test FunctionApprovalRequestContent conversion."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    func_call = FunctionCallContent(
        call_id="call_123",
        name="send_email",
        arguments={"to": "user@example.com", "subject": "Test"},
    )
    approval = FunctionApprovalRequestContent(
        id="approval_001",
        function_call=func_call,
    )

    update = AgentRunResponseUpdate(contents=[approval])
    events = await bridge.from_agent_run_update(update)

    # Should emit: ToolCallEndEvent + CustomEvent
    assert len(events) == 2

    # First: ToolCallEndEvent to close the tool call
    assert events[0].type == "TOOL_CALL_END"
    assert events[0].tool_call_id == "call_123"

    # Second: CustomEvent with approval details
    assert events[1].type == "CUSTOM"
    assert events[1].name == "function_approval_request"
    assert events[1].value["id"] == "approval_001"
    assert events[1].value["function_call"]["name"] == "send_email"


async def test_empty_predict_state_config():
    """Test behavior with no predictive state configuration."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={},  # Empty config
    )

    # Tool call with arguments
    update = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="write_doc", call_id="call_1", arguments='{"content": "test"}'),
            FunctionResultContent(call_id="call_1", result="Done"),
        ]
    )
    events = await bridge.from_agent_run_update(update)

    # Should NOT emit StateDeltaEvent or confirm_changes
    event_types = [e.type for e in events]
    assert "STATE_DELTA" not in event_types
    assert "STATE_SNAPSHOT" not in event_types

    # Should have: ToolCallStart, ToolCallArgs, ToolCallEnd, ToolCallResult, MessagesSnapshot
    # MessagesSnapshotEvent is emitted after tool results to track the conversation
    assert event_types == [
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
        "MESSAGES_SNAPSHOT",
    ]


async def test_tool_not_in_predict_state_config():
    """Test tool that doesn't match any predict_state_config entry."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "document": {"tool": "write_document", "tool_argument": "content"},
        },
    )

    # Different tool name
    update = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="search_web", call_id="call_1", arguments='{"query": "AI"}'),
            FunctionResultContent(call_id="call_1", result="Results"),
        ]
    )
    events = await bridge.from_agent_run_update(update)

    # Should NOT emit StateDeltaEvent or confirm_changes
    event_types = [e.type for e in events]
    assert "STATE_DELTA" not in event_types
    assert "STATE_SNAPSHOT" not in event_types


async def test_state_management_tracking():
    """Test current_state and pending_state_updates tracking."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    initial_state = {"document": ""}
    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "document": {"tool": "write_doc", "tool_argument": "content"},
        },
        current_state=initial_state,
    )

    # Streaming tool call
    update1 = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="write_doc", call_id="call_1"),
            FunctionCallContent(name="", call_id="call_1", arguments='{"content": "Hello"}'),
        ]
    )
    await bridge.from_agent_run_update(update1)

    # Check pending_state_updates was populated
    assert "document" in bridge.pending_state_updates
    assert bridge.pending_state_updates["document"] == "Hello"

    # Tool result should update current_state
    update2 = AgentRunResponseUpdate(contents=[FunctionResultContent(call_id="call_1", result="Done")])
    await bridge.from_agent_run_update(update2)

    # current_state should be updated
    assert bridge.current_state["document"] == "Hello"

    # pending_state_updates should be cleared
    assert len(bridge.pending_state_updates) == 0


async def test_wildcard_tool_argument():
    """Test tool_argument='*' uses all arguments as state value."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "recipe": {"tool": "create_recipe", "tool_argument": "*"},
        },
        current_state={},
    )

    # Complete tool call with dict arguments
    update = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(
                name="create_recipe",
                call_id="call_1",
                arguments={"title": "Pasta", "ingredients": ["pasta", "sauce"]},
            ),
            FunctionResultContent(call_id="call_1", result="Created"),
        ]
    )
    events = await bridge.from_agent_run_update(update)

    # Find StateDeltaEvent
    delta_events = [e for e in events if e.type == "STATE_DELTA"]
    assert len(delta_events) > 0

    # Value should be the entire arguments dict
    delta = delta_events[0].delta[0]
    assert delta["path"] == "/recipe"
    assert delta["value"] == {"title": "Pasta", "ingredients": ["pasta", "sauce"]}


async def test_run_lifecycle_events():
    """Test RunStartedEvent and RunFinishedEvent creation."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    started = bridge.create_run_started_event()
    assert started.type == "RUN_STARTED"
    assert started.run_id == "test_run"
    assert started.thread_id == "test_thread"

    finished = bridge.create_run_finished_event(result={"status": "complete"})
    assert finished.type == "RUN_FINISHED"
    assert finished.run_id == "test_run"
    assert finished.thread_id == "test_thread"
    assert finished.result == {"status": "complete"}


async def test_message_lifecycle_events():
    """Test TextMessageStartEvent and TextMessageEndEvent creation."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    start = bridge.create_message_start_event("msg_123", role="assistant")
    assert start.type == "TEXT_MESSAGE_START"
    assert start.message_id == "msg_123"
    assert start.role == "assistant"

    end = bridge.create_message_end_event("msg_123")
    assert end.type == "TEXT_MESSAGE_END"
    assert end.message_id == "msg_123"


async def test_state_event_creation():
    """Test StateSnapshotEvent and StateDeltaEvent creation helpers."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    # StateSnapshotEvent
    snapshot = bridge.create_state_snapshot_event({"document": "content"})
    assert snapshot.type == "STATE_SNAPSHOT"
    assert snapshot.snapshot == {"document": "content"}

    # StateDeltaEvent with JSON Patch
    delta = bridge.create_state_delta_event([{"op": "replace", "path": "/document", "value": "new content"}])
    assert delta.type == "STATE_DELTA"
    assert len(delta.delta) == 1
    assert delta.delta[0]["op"] == "replace"
    assert delta.delta[0]["path"] == "/document"
    assert delta.delta[0]["value"] == "new content"


async def test_state_snapshot_after_tool_result():
    """Test StateSnapshotEvent emission after tool result with pending updates."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "document": {"tool": "write_doc", "tool_argument": "content"},
        },
        current_state={"document": ""},
    )

    # Tool call with streaming args
    update1 = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="write_doc", call_id="call_1"),
            FunctionCallContent(name="", call_id="call_1", arguments='{"content": "Test"}'),
        ]
    )
    await bridge.from_agent_run_update(update1)

    # Tool result should trigger StateSnapshotEvent
    update2 = AgentRunResponseUpdate(contents=[FunctionResultContent(call_id="call_1", result="Done")])
    events = await bridge.from_agent_run_update(update2)

    # Should have: ToolCallEnd, ToolCallResult, StateSnapshot, ToolCallStart (confirm_changes), ToolCallArgs, ToolCallEnd
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) == 1
    assert snapshot_events[0].snapshot["document"] == "Test"


async def test_message_id_persistence_across_chunks():
    """Test that message_id persists across multiple text chunks."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    # First chunk
    update1 = AgentRunResponseUpdate(contents=[TextContent(text="Hello ")])
    events1 = await bridge.from_agent_run_update(update1)
    message_id = events1[0].message_id

    # Second chunk
    update2 = AgentRunResponseUpdate(contents=[TextContent(text="world")])
    events2 = await bridge.from_agent_run_update(update2)

    # Should use same message_id
    assert events2[0].message_id == message_id
    assert bridge.current_message_id == message_id


async def test_tool_call_id_tracking():
    """Test tool_call_id tracking across streaming chunks."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    # First chunk with name
    update1 = AgentRunResponseUpdate(contents=[FunctionCallContent(name="search", call_id="call_1")])
    await bridge.from_agent_run_update(update1)

    assert bridge.current_tool_call_id == "call_1"
    assert bridge.current_tool_call_name == "search"

    # Second chunk with args but no name
    update2 = AgentRunResponseUpdate(contents=[FunctionCallContent(name="", call_id="call_1", arguments='{"q":"AI"}')])
    events2 = await bridge.from_agent_run_update(update2)

    # Should still track same tool call
    assert bridge.current_tool_call_id == "call_1"
    assert events2[0].tool_call_id == "call_1"


async def test_tool_name_reset_after_result():
    """Test current_tool_call_name is reset after tool result."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "document": {"tool": "write_doc", "tool_argument": "content"},
        },
    )

    # Tool call
    update1 = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="write_doc", call_id="call_1"),
            FunctionCallContent(name="", call_id="call_1", arguments='{"content": "Test"}'),
        ]
    )
    await bridge.from_agent_run_update(update1)

    assert bridge.current_tool_call_name == "write_doc"

    # Tool result with predictive state (should trigger confirm_changes and reset)
    update2 = AgentRunResponseUpdate(contents=[FunctionResultContent(call_id="call_1", result="Done")])
    await bridge.from_agent_run_update(update2)

    # Tool name should be reset
    assert bridge.current_tool_call_name is None


async def test_function_approval_with_wildcard_argument():
    """Test function approval with wildcard * argument."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "payload": {"tool": "submit", "tool_argument": "*"},
        },
    )

    approval_content = FunctionApprovalRequestContent(
        id="approval_1",
        function_call=FunctionCallContent(
            name="submit", call_id="call_1", arguments='{"key1": "value1", "key2": "value2"}'
        ),
    )

    update = AgentRunResponseUpdate(contents=[approval_content])
    events = await bridge.from_agent_run_update(update)

    # Should emit StateSnapshotEvent with entire parsed args as value
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) == 1
    assert snapshot_events[0].snapshot["payload"] == {"key1": "value1", "key2": "value2"}


async def test_function_approval_missing_argument():
    """Test function approval when specified argument is not in parsed args."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={
            "data": {"tool": "process", "tool_argument": "missing_field"},
        },
    )

    approval_content = FunctionApprovalRequestContent(
        id="approval_1",
        function_call=FunctionCallContent(name="process", call_id="call_1", arguments='{"other_field": "value"}'),
    )

    update = AgentRunResponseUpdate(contents=[approval_content])
    events = await bridge.from_agent_run_update(update)

    # Should not emit StateSnapshotEvent since argument not found
    snapshot_events = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshot_events) == 0


async def test_empty_predict_state_config_no_deltas():
    """Test with empty predict_state_config (no predictive updates)."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread", predict_state_config={})

    # Tool call with arguments
    update = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="search", call_id="call_1"),
            FunctionCallContent(name="", call_id="call_1", arguments='{"query": "test"}'),
        ]
    )
    events = await bridge.from_agent_run_update(update)

    # Should not emit any StateDeltaEvents
    delta_events = [e for e in events if e.type == "STATE_DELTA"]
    assert len(delta_events) == 0


async def test_tool_with_no_matching_config():
    """Test tool call for tool not in predict_state_config."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}},
    )

    # Tool call for different tool
    update = AgentRunResponseUpdate(
        contents=[
            FunctionCallContent(name="search_web", call_id="call_1"),
            FunctionCallContent(name="", call_id="call_1", arguments='{"query": "test"}'),
        ]
    )
    events = await bridge.from_agent_run_update(update)

    # Should not emit StateDeltaEvents
    delta_events = [e for e in events if e.type == "STATE_DELTA"]
    assert len(delta_events) == 0


async def test_tool_call_without_name_or_id():
    """Test handling FunctionCallContent with no name and no call_id."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(run_id="test_run", thread_id="test_thread")

    # This should not crash but log an error
    update = AgentRunResponseUpdate(contents=[FunctionCallContent(name="", call_id="", arguments='{"arg": "val"}')])
    events = await bridge.from_agent_run_update(update)

    # Should emit ToolCallArgsEvent with generated ID
    assert len(events) >= 1


async def test_state_delta_count_logging():
    """Test that state delta count increments and logs at intervals."""
    from agent_framework_ag_ui._events import AgentFrameworkEventBridge

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config={"doc": {"tool": "write", "tool_argument": "text"}},
    )

    # Emit multiple state deltas with different content each time
    for i in range(15):
        update = AgentRunResponseUpdate(
            contents=[
                FunctionCallContent(name="", call_id="call_1", arguments=f'{{"text": "Content variation {i}"}}'),
            ]
        )
        # Set the tool name to match config
        bridge.current_tool_call_name = "write"
        await bridge.from_agent_run_update(update)

    # State delta count should have incremented (one per unique state update)
    assert bridge.state_delta_count >= 1
