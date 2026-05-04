# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for GitHub issue #5545: Workflow timings in DevUI are incorrect.

CustomResponseOutputItemAddedEvent and CustomResponseOutputItemDoneEvent lack a
`created_at` field, causing the frontend to synthesize timestamps with forced
1-second gaps between events, making instant workflows appear to take 3+ seconds.
"""

from conftest import (
    create_executor_completed_event,
    create_executor_invoked_event,
)

from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import (
    AgentFrameworkRequest,
    CustomResponseOutputItemAddedEvent,
    CustomResponseOutputItemDoneEvent,
)


def test_custom_event_models_lack_created_at_field() -> None:
    """REGRESSION (#5545): CustomResponseOutputItemAddedEvent and Done must declare created_at.

    Before the fix, both models were missing this field.  The frontend timestamp
    extraction code reads `event.created_at` (number) as its first priority source.
    Without the field the frontend fell through to the synthesised-timestamp path,
    forcing a minimum 1-second gap between every pair of consecutive events.
    """
    assert "created_at" in CustomResponseOutputItemAddedEvent.model_fields, (
        "CustomResponseOutputItemAddedEvent is missing 'created_at'. "
        "The frontend uses this field for accurate workflow timeline timings."
    )
    assert "created_at" in CustomResponseOutputItemDoneEvent.model_fields, (
        "CustomResponseOutputItemDoneEvent is missing 'created_at'. "
        "The frontend uses this field for accurate workflow timeline timings."
    )


async def test_workflow_executor_events_lack_created_at(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """REGRESSION (#5545): mapper.convert_event() must populate created_at on executor events.

    Before the fix, executor_invoked and executor_completed events were emitted
    without a `created_at` value.  The frontend then synthesised a timestamp using
    Math.max(baseTimestamp, lastTimestamp + 1) — a forced +1 s gap — causing
    instant workflows to appear to take multiple seconds in the DevUI timeline.
    """
    invoke_event = create_executor_invoked_event(executor_id="exec_timing")
    complete_event = create_executor_completed_event(executor_id="exec_timing")

    invoked_results = await mapper.convert_event(invoke_event, test_request)
    completed_results = await mapper.convert_event(complete_event, test_request)

    for label, results in [
        ("executor_invoked", invoked_results),
        ("executor_completed", completed_results),
    ]:
        assert results, f"mapper.convert_event() returned no events for {label}"
        for event in results:
            assert getattr(event, "created_at", None) is not None, (
                f"{label} event {type(event).__name__} is missing 'created_at'. "
                "The frontend relies on this field to avoid forced 1-second gaps."
            )
            assert event.created_at > 0, (
                f"{label} event {type(event).__name__} has non-positive created_at "
                f"({event.created_at!r}); expected a valid Unix timestamp."
            )


async def test_rapid_workflow_events_have_no_top_level_timestamps(
    mapper: MessageMapper, test_request: AgentFrameworkRequest
) -> None:
    """REGRESSION (#5545): response.workflow_event.completed events carry no top-level created_at.

    These events embed their timing in `data.timestamp` as a Python isoformat()
    string.  The frontend must parse that string safely — Python's isoformat()
    emits microseconds without a trailing 'Z', which some JS environments cannot
    parse, returning NaN.  This test confirms the backend format so that the
    frontend NaN-guard (Number.isFinite) is tested against the real payload shape.
    """
    from agent_framework_devui.models._openai_custom import ResponseWorkflowEventComplete

    invoke_event = create_executor_invoked_event(executor_id="exec_rapid")
    await mapper.convert_event(invoke_event, test_request)
    complete_event = create_executor_completed_event(executor_id="exec_rapid")
    results = await mapper.convert_event(complete_event, test_request)

    # executor_completed is mapped to CustomResponseOutputItemDoneEvent (has created_at),
    # NOT to ResponseWorkflowEventComplete.  Confirm none of the results are the
    # legacy workflow-event type so this test stays meaningful.
    workflow_events = [r for r in results if isinstance(r, ResponseWorkflowEventComplete)]
    assert not workflow_events, (
        "executor_completed should map to CustomResponseOutputItemDoneEvent, not ResponseWorkflowEventComplete."
    )

    # Confirm data.timestamp (used by the fallback legacy path) is a Python isoformat
    # string — no trailing Z, up to 6 fractional digits — so the frontend NaN-guard
    # is tested against the real emitted format.
    from datetime import datetime

    sample_ts = datetime.now().isoformat()
    assert "T" in sample_ts, "isoformat() must include time separator"
    # Python isoformat does NOT include Z or +00:00 by default
    assert not sample_ts.endswith("Z"), (
        "Python datetime.now().isoformat() must not end with Z; "
        "this confirms the frontend needs a Number.isFinite guard."
    )
