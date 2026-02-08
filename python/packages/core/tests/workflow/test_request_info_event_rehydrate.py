# Copyright (c) Microsoft. All rights reserved.

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_framework import InMemoryCheckpointStorage, InProcRunnerContext
from agent_framework._workflows._checkpoint_encoding import (
    _PICKLE_MARKER,
    encode_checkpoint_value,
)
from agent_framework._workflows._events import WorkflowEvent
from agent_framework._workflows._state import State


@dataclass
class MockRequest: ...


@dataclass(kw_only=True)
class SimpleApproval:
    prompt: str = ""
    draft: str = ""
    iteration: int = 0


@dataclass(slots=True)
class SlottedApproval:
    note: str = ""


@dataclass
class TimedApproval:
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


async def test_rehydrate_request_info_event() -> None:
    """Rehydration should succeed for valid request info events."""
    request_info_event = WorkflowEvent.request_info(
        request_id="request-123",
        source_executor_id="review_gateway",
        request_data=MockRequest(),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(request_info_event)

    checkpoint_id = await runner_context.create_checkpoint("test_name", "test_hash", State(), None, iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    assert checkpoint is not None
    assert checkpoint.pending_request_info_events
    assert "request-123" in checkpoint.pending_request_info_events
    assert checkpoint.pending_request_info_events["request-123"].request_type is MockRequest

    # Rehydrate the context
    await runner_context.apply_checkpoint(checkpoint)

    pending_requests = await runner_context.get_pending_request_info_events()
    assert "request-123" in pending_requests
    rehydrated_event = pending_requests["request-123"]
    assert rehydrated_event.request_id == "request-123"
    assert rehydrated_event.source_executor_id == "review_gateway"
    assert rehydrated_event.request_type is MockRequest
    assert rehydrated_event.response_type is bool
    assert isinstance(rehydrated_event.data, MockRequest)


async def test_request_info_event_serializes_non_json_payloads() -> None:
    req_1 = WorkflowEvent.request_info(
        request_id="req-1",
        source_executor_id="source",
        request_data=TimedApproval(issued_at=datetime(2024, 5, 4, 12, 30, 45)),
        response_type=bool,
    )
    req_2 = WorkflowEvent.request_info(
        request_id="req-2",
        source_executor_id="source",
        request_data=SlottedApproval(note="slot-based"),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(req_1)
    await runner_context.add_request_info_event(req_2)

    checkpoint_id = await runner_context.create_checkpoint("test_name", "test_hash", State(), None, iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    # Should be JSON serializable despite datetime/slots
    serialized = json.dumps(encode_checkpoint_value(checkpoint))
    assert isinstance(serialized, str)

    # Verify the structure contains pickled data for the request data fields
    deserialized = json.loads(serialized)
    assert _PICKLE_MARKER in deserialized  # checkpoint itself is pickled

    # Verify we can rehydrate the checkpoint correctly
    await runner_context.apply_checkpoint(checkpoint)
    pending = await runner_context.get_pending_request_info_events()

    assert "req-1" in pending
    rehydrated_1 = pending["req-1"]
    assert isinstance(rehydrated_1.data, TimedApproval)
    assert rehydrated_1.data.issued_at == datetime(2024, 5, 4, 12, 30, 45)

    assert "req-2" in pending
    rehydrated_2 = pending["req-2"]
    assert isinstance(rehydrated_2.data, SlottedApproval)
    assert rehydrated_2.data.note == "slot-based"
