# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the backend (server-side) tools scenario."""

from __future__ import annotations

from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from event_stream import EventStream

from agent_framework_ag_ui import AgentFrameworkAgent


def _build_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> AgentFrameworkAgent:
    stub = StubAgent(updates=updates)
    return AgentFrameworkAgent(agent=stub, **kwargs)


async def _run(agent: AgentFrameworkAgent, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-tools",
    "run_id": "run-tools",
    "messages": [{"role": "user", "content": "What's the weather?"}],
}


# ── Golden stream tests ──


async def test_tool_call_lifecycle_golden_sequence() -> None:
    """Assert the full event sequence for a tool call → result → text response."""
    updates = [
        # LLM calls the tool
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments='{"city": "SF"}')],
            role="assistant",
        ),
        # Tool result comes back
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F and sunny")],
            role="assistant",
        ),
        # LLM responds with text
        AgentResponseUpdate(
            contents=[Content.from_text(text="It's 72°F and sunny in SF!")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",  # Synthetic start for tool-only message
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "TOOL_CALL_RESULT",
            "TEXT_MESSAGE_END",  # End of synthetic message
            "TEXT_MESSAGE_START",  # New message for text response
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "MESSAGES_SNAPSHOT",
            "RUN_FINISHED",
        ]
    )


async def test_tool_calls_balanced() -> None:
    """Every TOOL_CALL_START has a matching TOOL_CALL_END."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments='{"city": "SF"}')],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="It's 72°F!")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_tool_calls_balanced()


async def test_text_messages_balanced_with_tools() -> None:
    """Text messages are properly balanced even around tool calls."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments='{"city": "SF"}')],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="It's 72°F!")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_text_messages_balanced()


async def test_tool_call_id_matches_result() -> None:
    """TOOL_CALL_START and TOOL_CALL_RESULT reference the same tool_call_id."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments="{}")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    start = stream.first("TOOL_CALL_START")
    result = stream.first("TOOL_CALL_RESULT")
    assert start.tool_call_id == result.tool_call_id == "call-1"


async def test_tool_result_content_preserved() -> None:
    """TOOL_CALL_RESULT event carries the tool's result content."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments="{}")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F and sunny")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    result = stream.first("TOOL_CALL_RESULT")
    assert result.content == "72°F and sunny"


async def test_no_run_error_on_tool_flow() -> None:
    """Tool call flow doesn't produce RUN_ERROR."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments="{}")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_no_run_error()
    stream.assert_bookends()


async def test_multiple_sequential_tool_calls() -> None:
    """Multiple sequential tool calls each produce balanced START/END pairs."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="tool_a", call_id="call-a", arguments="{}")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-a", result="result-a")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="tool_b", call_id="call-b", arguments="{}")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-b", result="result-b")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="Done!")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_tool_calls_balanced()
    stream.assert_text_messages_balanced()
    stream.assert_bookends()

    # Both tool calls should appear
    starts = stream.get("TOOL_CALL_START")
    assert len(starts) == 2
    assert {s.tool_call_name for s in starts} == {"tool_a", "tool_b"}


async def test_messages_snapshot_includes_tool_calls() -> None:
    """MessagesSnapshotEvent includes tool call and result messages."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments='{"city":"SF"}')],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_result(call_id="call-1", result="72°F")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_text(text="It's warm!")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_has_type("MESSAGES_SNAPSHOT")
    snapshot = stream.messages_snapshot()
    # Should have: user message, assistant with tool_calls, tool result, assistant text
    assert len(snapshot) >= 3
