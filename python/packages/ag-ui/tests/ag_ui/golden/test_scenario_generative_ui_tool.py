# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the client-side (declaration-only) tools scenario."""

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
    "thread_id": "thread-gen-ui-tool",
    "run_id": "run-gen-ui-tool",
    "messages": [{"role": "user", "content": "Show me a chart"}],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "render_chart",
                "description": "Render a chart in the UI",
                "parameters": {
                    "type": "object",
                    "properties": {"data": {"type": "array"}},
                },
            },
        }
    ],
}


# ── Golden stream tests ──


async def test_declaration_only_tool_golden_sequence() -> None:
    """Declaration-only tool: TOOL_CALL_START/ARGS emitted, TOOL_CALL_END at stream end."""
    # The LLM calls a client-side tool (no server-side execution)
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="render_chart",
                    call_id="call-chart",
                    arguments='{"data": [1, 2, 3]}',
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()
    stream.assert_no_run_error()

    # Tool call start and args should be present
    stream.assert_has_type("TOOL_CALL_START")
    stream.assert_has_type("TOOL_CALL_ARGS")

    # TOOL_CALL_END should be emitted (via get_pending_without_end)
    stream.assert_has_type("TOOL_CALL_END")
    stream.assert_tool_calls_balanced()


async def test_declaration_only_tool_no_tool_call_result() -> None:
    """Declaration-only tools should NOT produce TOOL_CALL_RESULT events."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="render_chart",
                    call_id="call-chart",
                    arguments='{"data": [1, 2, 3]}',
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    assert "TOOL_CALL_RESULT" not in stream.types(), "Declaration-only tools should not have TOOL_CALL_RESULT"


async def test_declaration_only_tool_text_messages_balanced() -> None:
    """Text messages remain balanced even with declaration-only tools."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="render_chart",
                    call_id="call-chart",
                    arguments='{"data": [1, 2, 3]}',
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_text_messages_balanced()


async def test_declaration_only_tool_messages_snapshot() -> None:
    """MessagesSnapshotEvent includes the tool call for declaration-only tools."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="render_chart",
                    call_id="call-chart",
                    arguments='{"data": [1, 2, 3]}',
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_has_type("MESSAGES_SNAPSHOT")
