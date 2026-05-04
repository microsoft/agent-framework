# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for GitHub issue #5545: Workflow timings in DevUI are incorrect.

CustomResponseOutputItemAddedEvent and CustomResponseOutputItemDoneEvent lack a
`created_at` field, causing the frontend to synthesize timestamps with forced
1-second gaps between events, making instant workflows appear to take 3+ seconds.
"""

import pytest

from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import (
    CustomResponseOutputItemAddedEvent,
    CustomResponseOutputItemDoneEvent,
)

from conftest import (
    create_executor_completed_event,
    create_executor_failed_event,
    create_executor_invoked_event,
)


def test_custom_event_models_lack_created_at_field() -> None:
    """CustomResponseOutputItemAddedEvent and CustomResponseOutputItemDoneEvent
    should have a created_at field but currently do not.

    Without created_at, the frontend cannot use real timestamps and falls back to
    synthesizing timestamps with Math.max(baseTimestamp, lastTimestamp + 1),
    forcing a minimum 1-second gap between sequential events.
    """
    model_fields_added = CustomResponseOutputItemAddedEvent.model_fields
    assert "created_at" in model_fields_added, (
        "CustomResponseOutputItemAddedEvent is missing 'created_at' field. "
        "Without it, the frontend synthesizes timestamps with forced 1-second gaps, "
        "causing instant workflows to appear to take multiple seconds in the timeline."
    )

    model_fields_done = CustomResponseOutputItemDoneEvent.model_fields
    assert "created_at" in model_fields_done, (
        "CustomResponseOutputItemDoneEvent is missing 'created_at' field. "
        "Without it, the frontend synthesizes timestamps with forced 1-second gaps, "
        "causing instant workflows to appear to take multiple seconds in the timeline."
    )


async def test_workflow_executor_events_lack_created_at(
    mapper: MessageMapper, test_request: "AgentFrameworkRequest"  # type: ignore[name-defined]
) -> None:
    """Events emitted by the mapper for executor_invoked/completed/failed
    should carry a created_at timestamp, but currently do not.

    This is the root cause of the bug: executor events produced by the mapper
    have no created_at, so the frontend cannot use real event timestamps.
    """
    invoked_event = create_executor_invoked_event("test_exec")
    completed_event = create_executor_completed_event("test_exec")
    failed_event = create_executor_failed_event("test_exec")

    invoked_results = await mapper.convert_event(invoked_event, test_request)
    # Set up context so completed event can be processed (needs prior invoked)
    completed_results = await mapper.convert_event(completed_event, test_request)
    failed_results = await mapper.convert_event(failed_event, test_request)

    assert invoked_results, "mapper.convert_event should return events for executor_invoked"
    assert completed_results, "mapper.convert_event should return events for executor_completed"
    assert failed_results, "mapper.convert_event should return events for executor_failed"

    for event in invoked_results:
        assert getattr(event, "created_at", None) is not None, (
            f"executor_invoked mapped event {type(event).__name__} lacks 'created_at'. "
            "This causes the frontend workflow timeline to show incorrect multi-second gaps."
        )

    for event in completed_results:
        assert getattr(event, "created_at", None) is not None, (
            f"executor_completed mapped event {type(event).__name__} lacks 'created_at'. "
            "This causes the frontend workflow timeline to show incorrect multi-second gaps."
        )

    for event in failed_results:
        assert getattr(event, "created_at", None) is not None, (
            f"executor_failed mapped event {type(event).__name__} lacks 'created_at'. "
            "This causes the frontend workflow timeline to show incorrect multi-second gaps."
        )


async def test_rapid_workflow_events_have_no_top_level_timestamps(
    mapper: MessageMapper, test_request: "AgentFrameworkRequest"  # type: ignore[name-defined]
) -> None:
    """Rapid back-to-back executor events all lack created_at on the returned objects.

    When multiple executor events fire within the same second (as in a fast workflow),
    the absence of created_at forces the frontend to use lastTimestamp + 1, creating
    artificial 1-second delays per event in the workflow timeline display.
    """
    invoked = create_executor_invoked_event("exec_a")
    completed = create_executor_completed_event("exec_a")

    invoked_events = await mapper.convert_event(invoked, test_request)
    completed_events = await mapper.convert_event(completed, test_request)

    all_events = list(invoked_events or []) + list(completed_events or [])
    assert all_events, "Should have emitted events for both invoked and completed"

    events_with_timestamp = [e for e in all_events if getattr(e, "created_at", None) is not None]
    assert len(events_with_timestamp) == len(all_events), (
        f"Only {len(events_with_timestamp)}/{len(all_events)} executor events have 'created_at'. "
        "All events need timestamps so the frontend can display the real workflow duration "
        "instead of synthesizing timestamps with forced 1-second gaps."
    )
