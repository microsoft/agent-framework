# Copyright (c) Microsoft. All rights reserved.

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from agent_framework import InMemoryCheckpointStorage, InProcRunnerContext
from agent_framework._workflows._checkpoint_encoding import DATACLASS_MARKER, encode_checkpoint_value
from agent_framework._workflows._checkpoint_summary import get_checkpoint_summary
from agent_framework._workflows._events import RequestInfoEvent
from agent_framework._workflows._shared_state import SharedState


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
    request_info_event = RequestInfoEvent(
        request_id="request-123",
        source_executor_id="review_gateway",
        request_data=MockRequest(),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(request_info_event)

    checkpoint_id = await runner_context.create_checkpoint(SharedState(), iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    assert checkpoint is not None
    assert checkpoint.pending_request_info_events
    assert "request-123" in checkpoint.pending_request_info_events
    assert "request_type" in checkpoint.pending_request_info_events["request-123"]

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


async def test_rehydrate_fails_when_request_type_missing() -> None:
    """Rehydration should fail is the request type is missing or fails to import."""
    request_info_event = RequestInfoEvent(
        request_id="request-123",
        source_executor_id="review_gateway",
        request_data=MockRequest(),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(request_info_event)

    checkpoint_id = await runner_context.create_checkpoint(SharedState(), iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    assert checkpoint is not None
    assert checkpoint.pending_request_info_events
    assert "request-123" in checkpoint.pending_request_info_events
    assert "request_type" in checkpoint.pending_request_info_events["request-123"]

    # Modify the checkpoint to simulate missing request type
    checkpoint.pending_request_info_events["request-123"]["request_type"] = "nonexistent.module:MissingRequest"

    # Rehydrate the context
    with pytest.raises(ImportError):
        await runner_context.apply_checkpoint(checkpoint)


async def test_rehydrate_fails_when_request_type_mismatch() -> None:
    """Rehydration should fail if the request type is mismatched."""
    request_info_event = RequestInfoEvent(
        request_id="request-123",
        source_executor_id="review_gateway",
        request_data=MockRequest(),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(request_info_event)

    checkpoint_id = await runner_context.create_checkpoint(SharedState(), iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    assert checkpoint is not None
    assert checkpoint.pending_request_info_events
    assert "request-123" in checkpoint.pending_request_info_events
    assert "request_type" in checkpoint.pending_request_info_events["request-123"]

    # Modify the checkpoint to simulate mismatched request type in the serialized data
    checkpoint.pending_request_info_events["request-123"]["data"][DATACLASS_MARKER] = (
        "nonexistent.module:MissingRequest"
    )

    # Rehydrate the context
    with pytest.raises(TypeError):
        await runner_context.apply_checkpoint(checkpoint)


async def test_pending_requests_in_summary() -> None:
    """Test that pending requests are correctly summarized in the checkpoint summary."""
    request_info_event = RequestInfoEvent(
        request_id="request-123",
        source_executor_id="review_gateway",
        request_data=MockRequest(),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(request_info_event)

    checkpoint_id = await runner_context.create_checkpoint(SharedState(), iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    assert checkpoint is not None
    summary = get_checkpoint_summary(checkpoint)

    assert summary.checkpoint_id == checkpoint_id
    assert summary.status == "awaiting request response"

    assert len(summary.pending_request_info_events) == 1
    pending_event = summary.pending_request_info_events[0]
    assert isinstance(pending_event, RequestInfoEvent)
    assert pending_event.request_id == "request-123"

    assert pending_event.source_executor_id == "review_gateway"
    assert pending_event.request_type is MockRequest
    assert pending_event.response_type is bool
    assert isinstance(pending_event.data, MockRequest)


async def test_request_info_event_serializes_non_json_payloads() -> None:
    req_1 = RequestInfoEvent(
        request_id="req-1",
        source_executor_id="source",
        request_data=TimedApproval(issued_at=datetime(2024, 5, 4, 12, 30, 45)),
        response_type=bool,
    )
    req_2 = RequestInfoEvent(
        request_id="req-2",
        source_executor_id="source",
        request_data=SlottedApproval(note="slot-based"),
        response_type=bool,
    )

    runner_context = InProcRunnerContext(InMemoryCheckpointStorage())
    await runner_context.add_request_info_event(req_1)
    await runner_context.add_request_info_event(req_2)

    checkpoint_id = await runner_context.create_checkpoint(SharedState(), iteration_count=1)
    checkpoint = await runner_context.load_checkpoint(checkpoint_id)

    # Should be JSON serializable despite datetime/slots
    serialized = json.dumps(encode_checkpoint_value(checkpoint))
    deserialized = json.loads(serialized)

    assert "value" in deserialized
    deserialized = deserialized["value"]

    assert "pending_request_info_events" in deserialized
    pending_request_info_events = deserialized["pending_request_info_events"]
    assert "req-1" in pending_request_info_events
    assert isinstance(pending_request_info_events["req-1"]["data"]["value"]["issued_at"], str)

    assert "req-2" in pending_request_info_events
    assert pending_request_info_events["req-2"]["data"]["value"]["note"] == "slot-based"
