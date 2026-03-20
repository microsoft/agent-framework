# Copyright (c) Microsoft. All rights reserved.

"""Tests for TOOL_CALL_RESULT event emission on approval resume flows."""

from __future__ import annotations

import json
from typing import Any

from agent_framework import AgentResponseUpdate, Content, FunctionTool
from conftest import StubAgent

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._agent_run import run_agent_stream


def _make_weather_tool() -> FunctionTool:
    """Create a real executable weather tool with approval_mode='always_require'."""

    def get_weather(city: str) -> str:
        return f"Sunny in {city}"

    return FunctionTool(
        name="get_weather",
        description="Get the weather for a city",
        func=get_weather,
        approval_mode="always_require",
    )


async def test_approval_resume_emits_tool_call_result() -> None:
    """After approving a tool call, the resume stream should contain a TOOL_CALL_RESULT event.

    The message format follows the AG-UI approval pattern:
    - assistant message with tool_calls
    - tool message with {"accepted": true} content and toolCallId
    """
    tool_name = "get_weather"
    call_id = "call_abc123"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="The weather is sunny.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    # Build resume messages: user query, assistant tool call, approval response
    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather in Seattle?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-approval-result",
        "run_id": "run-resume",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    event_types = [getattr(e, "type", None) for e in events]

    assert "RUN_STARTED" in event_types, f"Expected RUN_STARTED, got types: {event_types}"
    assert "RUN_FINISHED" in event_types, f"Expected RUN_FINISHED, got types: {event_types}"

    # TOOL_CALL_RESULT must be present for the approved tool
    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]

    assert len(tool_result_events) > 0, (
        f"Expected at least one TOOL_CALL_RESULT event for the approved tool, "
        f"but found none. Event types in stream: {event_types}"
    )

    result_event = tool_result_events[0]
    assert result_event.tool_call_id == call_id, (
        f"Expected TOOL_CALL_RESULT with tool_call_id={call_id}, got tool_call_id={result_event.tool_call_id}"
    )
    # Verify the result contains the actual tool execution output
    assert result_event.content == "Sunny in Seattle"


async def test_approval_resume_result_has_content() -> None:
    """TOOL_CALL_RESULT event from an approved tool should contain the execution result."""
    tool_name = "get_weather"
    call_id = "call_content_check"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="Done.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Check the weather"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Portland"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-result-content",
        "run_id": "run-resume-2",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 1

    result_event = tool_result_events[0]
    assert result_event.tool_call_id == call_id
    assert result_event.role == "tool"
    # Verify the result contains the actual tool execution output (string returned directly)
    assert result_event.content == "Sunny in Portland"


async def test_no_approval_no_extra_tool_result() -> None:
    """When no approval response is present, no extra TOOL_CALL_RESULT events should be emitted."""
    agent = StubAgent(updates=[AgentResponseUpdate(contents=[Content.from_text(text="Hello.")], role="assistant")])
    config = AgentConfig()

    input_data: dict[str, Any] = {
        "thread_id": "thread-no-approval",
        "run_id": "run-normal",
        "messages": [{"role": "user", "content": "Hi"}],
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 0, f"Unexpected TOOL_CALL_RESULT events: {tool_result_events}"


async def test_rejection_does_not_emit_tool_call_result() -> None:
    """Rejected tool calls should not produce TOOL_CALL_RESULT events."""
    tool_name = "get_weather"
    call_id = "call_rejected"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="OK, I won't check.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Denver"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": False}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-rejection",
        "run_id": "run-rejected",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 0, (
        f"Expected no TOOL_CALL_RESULT for rejected tool, got {len(tool_result_events)}"
    )


def _make_temperature_tool() -> FunctionTool:
    """Create a real executable temperature tool with approval_mode='always_require'."""

    def get_temperature(city: str) -> str:
        return f"72F in {city}"

    return FunctionTool(
        name="get_temperature",
        description="Get the temperature for a city",
        func=get_temperature,
        approval_mode="always_require",
    )


async def test_mixed_approve_reject_emits_only_approved_tool_result() -> None:
    """When one tool call is approved and another rejected, only the approved one produces a TOOL_CALL_RESULT event."""
    weather_tool = _make_weather_tool()
    temperature_tool = _make_temperature_tool()
    approved_call_id = "call_approved"
    rejected_call_id = "call_rejected"

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="Here are the results.")], role="assistant")],
        default_options={"tools": [weather_tool, temperature_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Weather and temperature in Seattle?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": approved_call_id,
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                },
                {
                    "id": rejected_call_id,
                    "type": "function",
                    "function": {
                        "name": "get_temperature",
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                },
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": approved_call_id,
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": False}),
            "toolCallId": rejected_call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-mixed",
        "run_id": "run-mixed",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]

    # Only the approved tool call should produce a TOOL_CALL_RESULT event
    assert len(tool_result_events) == 1, (
        f"Expected exactly 1 TOOL_CALL_RESULT (approved only), got {len(tool_result_events)}"
    )
    assert tool_result_events[0].tool_call_id == approved_call_id
    assert tool_result_events[0].content == "Sunny in Seattle"


async def test_approval_resume_zero_updates_emits_tool_result() -> None:
    """When the agent produces zero updates, TOOL_CALL_RESULT events should still be emitted via the fallback path."""
    tool_name = "get_weather"
    call_id = "call_zero_updates"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Boston"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-zero-updates",
        "run_id": "run-zero-updates",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    event_types = [getattr(e, "type", None) for e in events]
    assert "RUN_STARTED" in event_types

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 1, (
        f"Expected 1 TOOL_CALL_RESULT in zero-updates fallback path, got {len(tool_result_events)}"
    )
    assert tool_result_events[0].tool_call_id == call_id
    assert tool_result_events[0].content == "Sunny in Boston"


async def test_resolve_approval_responses_returns_only_approved() -> None:
    """_resolve_approval_responses should return only approved results; rejection results go into messages only."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import _resolve_approval_responses

    weather_tool = _make_weather_tool()
    temperature_tool = _make_temperature_tool()
    approved_call_id = "call_a"
    rejected_call_id = "call_r"

    messages: list[Any] = [
        Message(role="user", contents=[Content.from_text(text="Hi")]),
        Message(
            role="assistant",
            contents=[
                Content(
                    type="function_approval_request",
                    id=approved_call_id,
                    function_call=Content(
                        type="function_call",
                        name="get_weather",
                        call_id=approved_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
                Content(
                    type="function_approval_request",
                    id=rejected_call_id,
                    function_call=Content(
                        type="function_call",
                        name="get_temperature",
                        call_id=rejected_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
            ],
        ),
        Message(
            role="user",
            contents=[
                Content(
                    type="function_approval_response",
                    id=approved_call_id,
                    approved=True,
                    function_call=Content(
                        type="function_call",
                        name="get_weather",
                        call_id=approved_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
                Content(
                    type="function_approval_response",
                    id=rejected_call_id,
                    approved=False,
                    function_call=Content(
                        type="function_call",
                        name="get_temperature",
                        call_id=rejected_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
            ],
        ),
    ]

    agent = StubAgent(
        updates=[],
        default_options={"tools": [weather_tool, temperature_tool]},
    )

    results = await _resolve_approval_responses(messages, [weather_tool, temperature_tool], agent, {})

    # Return value should only contain approved results
    assert len(results) == 1
    assert results[0].call_id == approved_call_id
    assert results[0].type == "function_result"

    # Rejection result should be written into messages (by _replace_approval_contents_with_results)
    all_contents = [c for msg in messages for c in msg.contents]
    rejection_results = [c for c in all_contents if c.type == "function_result" and c.call_id == rejected_call_id]
    assert len(rejection_results) == 1
    assert "rejected" in str(rejection_results[0].result).lower()
