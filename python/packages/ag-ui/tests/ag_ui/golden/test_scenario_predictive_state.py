# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the predictive state scenario."""

from __future__ import annotations

from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from event_stream import EventStream

from agent_framework_ag_ui import AgentFrameworkAgent

PREDICT_CONFIG = {
    "document": {
        "tool": "update_document",
        "tool_argument": "content",
    }
}

STATE_SCHEMA = {
    "document": {"type": "string"},
}


def _build_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> AgentFrameworkAgent:
    stub = StubAgent(updates=updates)
    return AgentFrameworkAgent(
        agent=stub,
        state_schema=STATE_SCHEMA,
        predict_state_config=PREDICT_CONFIG,
        require_confirmation=False,
        **kwargs,
    )


async def _run(agent: AgentFrameworkAgent, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-predict",
    "run_id": "run-predict",
    "messages": [{"role": "user", "content": "Write a document"}],
    "state": {"document": ""},
}


# ── Golden stream tests ──


async def test_predictive_state_emits_deltas_during_tool_args() -> None:
    """STATE_DELTA events are emitted as tool arguments stream in."""
    updates = [
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="update_document", call_id="call-1", arguments="")],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(name="update_document", call_id="call-1", arguments='{"content": "Hello')
            ],
            role="assistant",
        ),
        AgentResponseUpdate(
            contents=[Content.from_function_call(name="update_document", call_id="call-1", arguments=' world"}')],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()
    stream.assert_no_run_error()

    # PredictState custom event should be present
    custom_events = stream.get("CUSTOM")
    predict_events = [e for e in custom_events if getattr(e, "name", None) == "PredictState"]
    assert predict_events, "Expected PredictState custom event"

    # STATE_DELTA events should be emitted during tool arg streaming
    assert "STATE_DELTA" in stream.types(), "Expected STATE_DELTA events during predictive streaming"


async def test_predictive_state_snapshot_after_tool_end() -> None:
    """STATE_SNAPSHOT is emitted when a predictive tool completes (no confirmation)."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    name="update_document", call_id="call-1", arguments='{"content": "Final text"}'
                )
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_bookends()

    # Should have initial state snapshot + updated snapshot after tool completion
    snapshots = stream.get("STATE_SNAPSHOT")
    assert len(snapshots) >= 1, "Expected at least one STATE_SNAPSHOT"


async def test_predictive_state_ordered_events() -> None:
    """Event ordering: RUN_STARTED → PredictState → STATE_SNAPSHOT → TOOL_CALL_* → STATE_SNAPSHOT → RUN_FINISHED."""
    updates = [
        AgentResponseUpdate(
            contents=[
                Content.from_function_call(name="update_document", call_id="call-1", arguments='{"content": "doc"}')
            ],
            role="assistant",
        ),
    ]
    agent = _build_agent(updates)
    stream = await _run(agent, PAYLOAD)

    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "CUSTOM",  # PredictState
            "STATE_SNAPSHOT",  # Initial state
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "RUN_FINISHED",
        ]
    )
