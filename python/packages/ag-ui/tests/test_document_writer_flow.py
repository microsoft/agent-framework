# Copyright (c) Microsoft. All rights reserved.

"""Tests for document writer predictive state flow with confirm_changes."""

from ag_ui.core import EventType, StateDeltaEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallStartEvent
from agent_framework import FunctionCallContent, FunctionResultContent, TextContent
from agent_framework._types import AgentRunResponseUpdate

from agent_framework_ag_ui._events import AgentFrameworkEventBridge


async def test_streaming_document_with_state_deltas():
    """Test that streaming tool arguments emit progressive StateDeltaEvents."""
    predict_config = {
        "document": {"tool": "write_document_local", "tool_argument": "document"},
    }

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config=predict_config,
    )

    # Simulate streaming tool call - first chunk with name
    tool_call_start = FunctionCallContent(
        call_id="call_123",
        name="write_document_local",
        arguments='{"document":"Once',
    )
    update1 = AgentRunResponseUpdate(contents=[tool_call_start])
    events1 = await bridge.from_agent_run_update(update1)

    # Should have ToolCallStartEvent and ToolCallArgsEvent
    assert any(e.type == EventType.TOOL_CALL_START for e in events1)
    assert any(e.type == EventType.TOOL_CALL_ARGS for e in events1)

    # Second chunk - incomplete JSON, should try partial extraction
    tool_call_chunk2 = FunctionCallContent(call_id="call_123", name="write_document_local", arguments=" upon a time")
    update2 = AgentRunResponseUpdate(contents=[tool_call_chunk2])
    events2 = await bridge.from_agent_run_update(update2)

    # Should emit StateDeltaEvent with partial document
    state_deltas = [e for e in events2 if isinstance(e, StateDeltaEvent)]
    assert len(state_deltas) >= 1

    # Check JSON Patch format
    delta = state_deltas[0]
    assert isinstance(delta.delta, list)
    assert len(delta.delta) > 0
    assert delta.delta[0]["op"] == "replace"
    assert delta.delta[0]["path"] == "/document"
    assert "Once upon a time" in delta.delta[0]["value"]


async def test_confirm_changes_emission():
    """Test that confirm_changes tool call is emitted after predictive tool completion."""
    predict_config = {
        "document": {"tool": "write_document_local", "tool_argument": "document"},
    }

    current_state: dict[str, str] = {}

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config=predict_config,
        current_state=current_state,
    )

    # Set current tool name (simulating earlier tool call start)
    bridge.current_tool_call_name = "write_document_local"
    bridge.pending_state_updates = {"document": "A short story"}

    # Tool result
    tool_result = FunctionResultContent(
        call_id="call_123",
        result="Document written.",
    )

    update = AgentRunResponseUpdate(contents=[tool_result])
    events = await bridge.from_agent_run_update(update)

    # Should have: ToolCallEndEvent, ToolCallResultEvent, StateSnapshotEvent, confirm_changes sequence
    assert any(e.type == EventType.TOOL_CALL_END for e in events)
    assert any(e.type == EventType.TOOL_CALL_RESULT for e in events)
    assert any(e.type == EventType.STATE_SNAPSHOT for e in events)

    # Check for confirm_changes tool call
    confirm_starts = [e for e in events if isinstance(e, ToolCallStartEvent) and e.tool_call_name == "confirm_changes"]
    assert len(confirm_starts) == 1

    confirm_args = [e for e in events if isinstance(e, ToolCallArgsEvent) and e.delta == "{}"]
    assert len(confirm_args) >= 1

    confirm_ends = [e for e in events if isinstance(e, ToolCallEndEvent)]
    # At least 2: one for write_document_local, one for confirm_changes
    assert len(confirm_ends) >= 2

    # Check that stop flag is set
    assert bridge.should_stop_after_confirm is True


async def test_text_suppression_before_confirm():
    """Test that text messages are suppressed when confirm_changes is pending."""
    predict_config = {
        "document": {"tool": "write_document_local", "tool_argument": "document"},
    }

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config=predict_config,
    )

    # Set flag indicating we're waiting for confirmation
    bridge.should_stop_after_confirm = True

    # Text content that should be suppressed
    text = TextContent(text="I have written a story about pirates.")
    update = AgentRunResponseUpdate(contents=[text])

    events = await bridge.from_agent_run_update(update)

    # Should NOT emit TextMessageContentEvent
    text_events = [e for e in events if e.type == EventType.TEXT_MESSAGE_CONTENT]
    assert len(text_events) == 0

    # But should save the text
    assert bridge.suppressed_summary == "I have written a story about pirates."


async def test_no_confirm_for_non_predictive_tools():
    """Test that confirm_changes is NOT emitted for regular tool calls."""
    predict_config = {
        "document": {"tool": "write_document_local", "tool_argument": "document"},
    }

    current_state: dict[str, str] = {}

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config=predict_config,
        current_state=current_state,
    )

    # Different tool (not in predict_state_config)
    bridge.current_tool_call_name = "get_weather"

    tool_result = FunctionResultContent(
        call_id="call_456",
        result="Sunny, 72°F",
    )

    update = AgentRunResponseUpdate(contents=[tool_result])
    events = await bridge.from_agent_run_update(update)

    # Should NOT have confirm_changes
    confirm_starts = [e for e in events if isinstance(e, ToolCallStartEvent) and e.tool_call_name == "confirm_changes"]
    assert len(confirm_starts) == 0

    # Stop flag should NOT be set
    assert bridge.should_stop_after_confirm is False


async def test_state_delta_deduplication():
    """Test that duplicate state values don't emit multiple StateDeltaEvents."""
    predict_config = {
        "document": {"tool": "write_document_local", "tool_argument": "document"},
    }

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config=predict_config,
    )

    # First tool call with document
    tool_call1 = FunctionCallContent(
        call_id="call_1",
        name="write_document_local",
        arguments='{"document":"Same text"}',
    )
    update1 = AgentRunResponseUpdate(contents=[tool_call1])
    events1 = await bridge.from_agent_run_update(update1)

    # Count state deltas
    state_deltas_1 = [e for e in events1 if isinstance(e, StateDeltaEvent)]
    assert len(state_deltas_1) >= 1

    # Second tool call with SAME document (shouldn't emit new delta)
    bridge.current_tool_call_name = "write_document_local"
    tool_call2 = FunctionCallContent(
        call_id="call_2",
        name="write_document_local",
        arguments='{"document":"Same text"}',  # Identical content
    )
    update2 = AgentRunResponseUpdate(contents=[tool_call2])
    events2 = await bridge.from_agent_run_update(update2)

    # Should NOT emit state delta (same value)
    state_deltas_2 = [e for e in events2 if e.type == EventType.STATE_DELTA]
    assert len(state_deltas_2) == 0


async def test_predict_state_config_multiple_fields():
    """Test predictive state with multiple state fields."""
    predict_config = {
        "title": {"tool": "create_post", "tool_argument": "title"},
        "content": {"tool": "create_post", "tool_argument": "body"},
    }

    bridge = AgentFrameworkEventBridge(
        run_id="test_run",
        thread_id="test_thread",
        predict_state_config=predict_config,
    )

    # Tool call with both fields
    tool_call = FunctionCallContent(
        call_id="call_999",
        name="create_post",
        arguments='{"title":"My Post","body":"Post content"}',
    )
    update = AgentRunResponseUpdate(contents=[tool_call])
    events = await bridge.from_agent_run_update(update)

    # Should emit StateDeltaEvent for both fields
    state_deltas = [e for e in events if isinstance(e, StateDeltaEvent)]
    assert len(state_deltas) >= 2

    # Check both fields are present
    paths = [delta.delta[0]["path"] for delta in state_deltas]
    assert "/title" in paths
    assert "/content" in paths
