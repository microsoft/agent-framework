# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the workflow HITL (subgraphs) scenario.

Extends the existing test_subgraphs_example_agent.py with EventStream assertions
on full event ordering, balancing, and interrupt structure.
"""

from __future__ import annotations

import json
from typing import Any

from event_stream import EventStream

from agent_framework_ag_ui_examples.agents.subgraphs_agent import subgraphs_agent


async def _run(agent: Any, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


# ── Turn 1: Initial request → flight interrupt ──


async def test_subgraphs_turn1_golden_bookends() -> None:
    """Turn 1 starts with RUN_STARTED and ends with RUN_FINISHED."""
    agent = subgraphs_agent()
    stream = await _run(
        agent,
        {
            "thread_id": "thread-sub-golden-1",
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip to San Francisco"}],
        },
    )
    stream.assert_bookends()


async def test_subgraphs_turn1_no_errors() -> None:
    """Turn 1 completes without errors."""
    agent = subgraphs_agent()
    stream = await _run(
        agent,
        {
            "thread_id": "thread-sub-golden-2",
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip"}],
        },
    )
    stream.assert_no_run_error()


async def test_subgraphs_turn1_has_step_events() -> None:
    """Turn 1 emits STEP_STARTED and STEP_FINISHED for workflow executors."""
    agent = subgraphs_agent()
    stream = await _run(
        agent,
        {
            "thread_id": "thread-sub-golden-3",
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip"}],
        },
    )
    stream.assert_has_type("STEP_STARTED")
    stream.assert_has_type("STEP_FINISHED")


async def test_subgraphs_turn1_interrupt_structure() -> None:
    """Turn 1 RUN_FINISHED carries flight interrupt with correct structure."""
    agent = subgraphs_agent()
    stream = await _run(
        agent,
        {
            "thread_id": "thread-sub-golden-4",
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip to SF"}],
        },
    )

    finished = stream.last("RUN_FINISHED")
    interrupt = getattr(finished, "interrupt", None)
    assert interrupt is not None, "Expected interrupt in RUN_FINISHED"
    assert isinstance(interrupt, list)
    assert len(interrupt) > 0
    assert interrupt[0]["value"]["agent"] == "flights"
    assert len(interrupt[0]["value"]["options"]) == 2


async def test_subgraphs_turn1_text_messages_balanced() -> None:
    """All text messages in turn 1 are properly balanced."""
    agent = subgraphs_agent()
    stream = await _run(
        agent,
        {
            "thread_id": "thread-sub-golden-5",
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip"}],
        },
    )
    stream.assert_text_messages_balanced()


async def test_subgraphs_turn1_ordered_flow() -> None:
    """Turn 1 event ordering: RUN_STARTED → STATE_SNAPSHOT → STEP_* → TOOL_CALL_* → RUN_FINISHED."""
    agent = subgraphs_agent()
    stream = await _run(
        agent,
        {
            "thread_id": "thread-sub-golden-6",
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip"}],
        },
    )
    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "STATE_SNAPSHOT",
            "STEP_STARTED",
            "RUN_FINISHED",
        ]
    )


# ── Multi-turn: Flight selection → hotel interrupt → completion ──


async def test_subgraphs_full_flow_event_ordering() -> None:
    """Complete 3-turn flow maintains proper event ordering throughout."""
    agent = subgraphs_agent()
    thread_id = "thread-sub-golden-full"

    # Turn 1
    stream1 = await _run(
        agent,
        {
            "thread_id": thread_id,
            "run_id": "run-1",
            "messages": [{"role": "user", "content": "Plan a trip to SF from Amsterdam"}],
        },
    )
    stream1.assert_bookends()
    stream1.assert_no_run_error()

    # Extract flight interrupt
    finished1 = stream1.last("RUN_FINISHED")
    interrupt1 = finished1.model_dump()["interrupt"][0]

    # Turn 2: Select flight
    stream2 = await _run(
        agent,
        {
            "thread_id": thread_id,
            "run_id": "run-2",
            "resume": {
                "interrupts": [
                    {
                        "id": interrupt1["id"],
                        "value": json.dumps(
                            {
                                "airline": "United",
                                "departure": "Amsterdam (AMS)",
                                "arrival": "San Francisco (SFO)",
                                "price": "$720",
                                "duration": "12h 15m",
                            }
                        ),
                    }
                ]
            },
        },
    )
    stream2.assert_bookends()
    stream2.assert_no_run_error()

    # Should now have hotel interrupt
    finished2 = stream2.last("RUN_FINISHED")
    interrupt2 = finished2.model_dump()["interrupt"]
    assert interrupt2[0]["value"]["agent"] == "hotels"

    # Turn 3: Select hotel
    stream3 = await _run(
        agent,
        {
            "thread_id": thread_id,
            "run_id": "run-3",
            "resume": {
                "interrupts": [
                    {
                        "id": interrupt2[0]["id"],
                        "value": json.dumps(
                            {
                                "name": "The Ritz-Carlton",
                                "location": "Nob Hill",
                                "price_per_night": "$550/night",
                                "rating": "4.8 stars",
                            }
                        ),
                    }
                ]
            },
        },
    )
    stream3.assert_bookends()
    stream3.assert_no_run_error()
    stream3.assert_text_messages_balanced()

    # Final turn should not have interrupt
    finished3 = stream3.last("RUN_FINISHED")
    final_interrupt = getattr(finished3, "interrupt", None)
    assert not final_interrupt, f"Expected no interrupt after completion, got {final_interrupt}"
