# Copyright (c) Microsoft. All rights reserved.

"""Tests for backend tool rendering."""

from typing import cast

from ag_ui.core import (
    TextMessageContentEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import AgentRunResponseUpdate, FunctionCallContent, FunctionResultContent, TextContent

from agent_framework_ag_ui._events import AgentFrameworkEventBridge


async def test_tool_call_flow():
    """Test complete tool call flow: call -> args -> end -> result."""
    bridge = AgentFrameworkEventBridge(run_id="test-run", thread_id="test-thread")

    # Step 1: Tool call starts
    tool_call = FunctionCallContent(
        call_id="weather-123",
        name="get_weather",
        arguments={"location": "Seattle"},
    )

    update1 = AgentRunResponseUpdate(contents=[tool_call])
    events1 = await bridge.from_agent_run_update(update1)

    # Should have: ToolCallStartEvent, ToolCallArgsEvent
    assert len(events1) == 2
    assert isinstance(events1[0], ToolCallStartEvent)
    assert isinstance(events1[1], ToolCallArgsEvent)

    start_event = events1[0]
    assert start_event.tool_call_id == "weather-123"
    assert start_event.tool_call_name == "get_weather"

    args_event = events1[1]
    assert "Seattle" in args_event.delta

    # Step 2: Tool result comes back
    tool_result = FunctionResultContent(
        call_id="weather-123",
        result="Weather in Seattle: Rainy, 52°F",
    )

    update2 = AgentRunResponseUpdate(contents=[tool_result])
    events2 = await bridge.from_agent_run_update(update2)

    # Should have: ToolCallEndEvent, ToolCallResultEvent, MessagesSnapshotEvent
    assert len(events2) == 3
    assert isinstance(events2[0], ToolCallEndEvent)
    assert isinstance(events2[1], ToolCallResultEvent)

    end_event = events2[0]
    assert end_event.tool_call_id == "weather-123"

    result_event = events2[1]
    assert result_event.tool_call_id == "weather-123"
    assert "Seattle" in result_event.content
    assert "Rainy" in result_event.content


async def test_text_with_tool_call():
    """Test agent response with both text and tool calls."""
    bridge = AgentFrameworkEventBridge(run_id="test-run", thread_id="test-thread")

    # Agent says something then calls a tool
    text_content = TextContent(text="Let me check the weather for you.")
    tool_call = FunctionCallContent(
        call_id="weather-456",
        name="get_forecast",
        arguments={"location": "San Francisco", "days": 3},
    )

    update = AgentRunResponseUpdate(contents=[text_content, tool_call])
    events = await bridge.from_agent_run_update(update)

    # Should have: TextMessageStart, TextMessageContent, ToolCallStart, ToolCallArgs
    assert len(events) == 4

    assert isinstance(events[0], TextMessageStartEvent)
    assert isinstance(events[1], TextMessageContentEvent)
    assert isinstance(events[2], ToolCallStartEvent)
    assert isinstance(events[3], ToolCallArgsEvent)

    text_event = events[1]
    assert "check the weather" in text_event.delta

    tool_start = events[2]
    assert tool_start.tool_call_name == "get_forecast"


async def test_multiple_tool_results():
    """Test handling multiple tool results in sequence."""
    bridge = AgentFrameworkEventBridge(run_id="test-run", thread_id="test-thread")

    # Multiple tool results
    results = [
        FunctionResultContent(call_id="tool-1", result="Result 1"),
        FunctionResultContent(call_id="tool-2", result="Result 2"),
        FunctionResultContent(call_id="tool-3", result="Result 3"),
    ]

    update = AgentRunResponseUpdate(contents=results)
    events = await bridge.from_agent_run_update(update)

    # Should have 3 pairs of ToolCallEndEvent + ToolCallResultEvent = 6 events
    assert len(events) == 6

    # Verify the pattern: End, Result, End, Result, End, Result
    for i in range(3):
        end_idx = i * 2
        result_idx = i * 2 + 1

        assert isinstance(events[end_idx], ToolCallEndEvent)
        assert isinstance(events[result_idx], ToolCallResultEvent)

        end_event = cast(ToolCallEndEvent, events[end_idx])
        result_event = cast(ToolCallResultEvent, events[result_idx])

        assert end_event.tool_call_id == f"tool-{i + 1}"
        assert result_event.tool_call_id == f"tool-{i + 1}"
        assert f"Result {i + 1}" in result_event.content
