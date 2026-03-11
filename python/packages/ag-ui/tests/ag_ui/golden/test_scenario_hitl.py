# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the HITL (human-in-the-loop) approval scenario."""

from __future__ import annotations

import json
from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from event_stream import EventStream

from agent_framework_ag_ui import AgentFrameworkAgent

PREDICT_CONFIG = {
    "tasks": {
        "tool": "generate_task_steps",
        "tool_argument": "steps",
    }
}

STATE_SCHEMA = {
    "tasks": {"type": "array", "items": {"type": "object"}},
}


def _build_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> AgentFrameworkAgent:
    stub = StubAgent(updates=updates)
    return AgentFrameworkAgent(
        agent=stub,
        state_schema=STATE_SCHEMA,
        predict_state_config=PREDICT_CONFIG,
        require_confirmation=True,
        **kwargs,
    )


async def _run(agent: AgentFrameworkAgent, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


STEPS = [
    {"description": "Step 1: Plan", "status": "enabled"},
    {"description": "Step 2: Execute", "status": "enabled"},
]


PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-hitl",
    "run_id": "run-hitl",
    "messages": [{"role": "user", "content": "Plan my tasks"}],
    "state": {"tasks": []},
}


# ── Turn 1: Tool call → confirm_changes → interrupt ──


async def test_hitl_turn1_golden_sequence() -> None:
    """Turn 1 emits tool call, confirm_changes, and finishes with interrupt."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="generate_task_steps",
                    call_id="call-steps",
                    arguments=json.dumps({"steps": STEPS}),
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    # Should have: tool call start/args/end for the primary tool,
    # then TOOL_CALL_END, STATE_SNAPSHOT, confirm_changes cycle
    stream.assert_bookends()
    stream.assert_no_run_error()

    # confirm_changes tool call should be present
    tool_starts = stream.get("TOOL_CALL_START")
    tool_names = [getattr(s, "tool_call_name", None) for s in tool_starts]
    assert "generate_task_steps" in tool_names
    assert "confirm_changes" in tool_names

    # RUN_FINISHED should have interrupt metadata
    finished = stream.last("RUN_FINISHED")
    interrupt = getattr(finished, "interrupt", None)
    assert interrupt is not None, "Expected interrupt in RUN_FINISHED"
    assert len(interrupt) > 0


async def test_hitl_turn1_tool_calls_balanced() -> None:
    """All tool calls in turn 1 (primary + confirm_changes) are balanced."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="generate_task_steps",
                    call_id="call-steps",
                    arguments=json.dumps({"steps": STEPS}),
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_tool_calls_balanced()


async def test_hitl_turn1_text_messages_balanced() -> None:
    """Text messages are balanced even in the approval flow."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="generate_task_steps",
                    call_id="call-steps",
                    arguments=json.dumps({"steps": STEPS}),
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_text_messages_balanced()


# ── Turn 2: Resume with approval → confirmation message → no interrupt ──


async def test_hitl_turn2_resume_with_approval() -> None:
    """Resuming with confirm_changes result emits confirmation text and finishes cleanly."""
    # Turn 2: user sends confirm_changes result as resume
    # The agent wrapper sees a confirm_changes response and emits a confirmation message
    confirm_result = json.dumps(
        {
            "accepted": True,
            "steps": STEPS,
        }
    )

    # Build payload with resume containing the approval
    # For confirm_changes, the messages should include the tool result
    payload: dict[str, Any] = {
        "thread_id": "thread-hitl",
        "run_id": "run-hitl-2",
        "messages": [
            {"role": "user", "content": "Plan my tasks"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "confirm-id-1",
                        "type": "function",
                        "function": {"name": "confirm_changes", "arguments": json.dumps({"steps": STEPS})},
                    }
                ],
            },
            {
                "role": "tool",
                "toolCallId": "confirm-id-1",
                "content": confirm_result,
            },
        ],
        "state": {"tasks": []},
    }

    # In turn 2, the agent sees the confirm_changes result and emits a confirmation text
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_text(text="Tasks confirmed!")],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, payload)

    stream.assert_bookends()
    stream.assert_text_messages_balanced()
    stream.assert_no_run_error()

    # Should have text message content (the confirmation message)
    text_events = stream.get("TEXT_MESSAGE_CONTENT")
    assert text_events, "Expected confirmation text message"

    # RUN_FINISHED should NOT have interrupt (approval completed)
    finished = stream.last("RUN_FINISHED")
    interrupt = getattr(finished, "interrupt", None)
    assert not interrupt, f"Expected no interrupt after approval, got {interrupt}"
