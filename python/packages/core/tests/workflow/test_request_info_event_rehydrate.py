# Copyright (c) Microsoft. All rights reserved.

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_framework import (
    FileCheckpointStorage,
    InMemoryCheckpointStorage,
    InProcRunnerContext,
    WorkflowBuilder,
    WorkflowRunState,
)
from agent_framework._workflows._checkpoint_encoding import (
    _PICKLE_MARKER,
    encode_checkpoint_value,
)
from agent_framework._workflows._events import WorkflowEvent
from agent_framework._workflows._state import State

from .test_request_info_and_response import (
    ApprovalRequiredExecutor,
    CalculationRequest,
    MultiRequestExecutor,
    UserApprovalRequest,
)


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


async def test_checkpoint_with_pending_request_info_events():
    """Test that request info events are properly serialized in checkpoints and can be restored."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        # Use file-based storage to test full serialization
        storage = FileCheckpointStorage(temp_dir)

        # Create workflow with checkpointing enabled
        executor = ApprovalRequiredExecutor(id="approval_executor")
        workflow = WorkflowBuilder(start_executor=executor, checkpoint_storage=storage).build()

        # Step 1: Run workflow to completion to ensure checkpoints are created
        request_info_event: WorkflowEvent | None = None
        async for event in workflow.run("checkpoint test operation", stream=True):
            if event.type == "request_info":
                request_info_event = event

        # Verify request was emitted
        assert request_info_event is not None
        assert isinstance(request_info_event.data, UserApprovalRequest)
        assert request_info_event.data.prompt == "Please approve the operation: checkpoint test operation"
        assert request_info_event.source_executor_id == "approval_executor"

        # Step 2: List checkpoints to find the one with our pending request
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        assert len(checkpoints) > 0, "No checkpoints were created during workflow execution"

        # Find the checkpoint with our pending request
        checkpoint_with_request = None
        for checkpoint in checkpoints:
            if request_info_event.request_id in checkpoint.pending_request_info_events:
                checkpoint_with_request = checkpoint
                break

        assert checkpoint_with_request is not None, "No checkpoint found with pending request info event"

        # Step 3: Verify the pending request info event was properly serialized
        serialized_event = checkpoint_with_request.pending_request_info_events[request_info_event.request_id]
        assert serialized_event.data
        assert serialized_event.request_type is UserApprovalRequest
        assert serialized_event.request_id == request_info_event.request_id
        assert serialized_event.source_executor_id == "approval_executor"

        # Step 4: Create a fresh workflow and restore from checkpoint
        new_executor = ApprovalRequiredExecutor(id="approval_executor")
        restored_workflow = WorkflowBuilder(start_executor=new_executor, checkpoint_storage=storage).build()

        # Step 5: Resume from checkpoint and verify the request can be continued
        completed = False
        restored_request_event: WorkflowEvent | None = None
        async for event in restored_workflow.run(checkpoint_id=checkpoint_with_request.checkpoint_id, stream=True):
            # Should re-emit the pending request info event
            if event.type == "request_info" and event.request_id == request_info_event.request_id:
                restored_request_event = event
            elif event.type == "status" and event.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
                completed = True

        assert completed, "Workflow should reach idle with pending requests state after restoration"
        assert restored_request_event is not None, "Restored request info event should be emitted"

        # Verify the restored event matches the original
        assert restored_request_event.source_executor_id == request_info_event.source_executor_id
        assert isinstance(restored_request_event.data, UserApprovalRequest)
        assert restored_request_event.data.prompt == request_info_event.data.prompt
        assert restored_request_event.data.context == request_info_event.data.context

        # Step 6: Provide response to the restored request and complete the workflow
        final_completed = False
        async for event in restored_workflow.run(
            stream=True,
            responses={
                request_info_event.request_id: True  # Approve the request
            },
        ):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                final_completed = True

        assert final_completed, "Workflow should complete after providing response to restored request"

        # Step 7: Verify the executor state was properly restored and response was processed
        assert new_executor.approval_received is True
        expected_result = "Operation approved: Please approve the operation: checkpoint test operation"
        assert new_executor.final_result == expected_result


async def test_checkpoint_restore_with_responses_does_not_reemit_handled_requests():
    """Test that request_info events are not re-emitted when responses are provided with checkpoint restore.

    When calling run(checkpoint_id=..., responses=...), the workflow restores from a checkpoint
    that contains pending request_info events. Because responses are provided for those events,
    they should NOT be re-emitted in the event stream - they are considered "handled".

    Note: The workflow's internal state tracking still sees the request_info events (before filtering),
    so the final status may be IDLE_WITH_PENDING_REQUESTS even though the requests were handled.
    The key behavior we're testing is that the CALLER doesn't see the request_info events.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        # Use file-based storage to test full serialization
        storage = FileCheckpointStorage(temp_dir)

        # Create workflow with checkpointing enabled
        executor = ApprovalRequiredExecutor(id="approval_executor")
        workflow = WorkflowBuilder(start_executor=executor, checkpoint_storage=storage).build()

        # Step 1: Run workflow until it emits a request_info event
        request_info_event: WorkflowEvent | None = None
        async for event in workflow.run("test pending request suppression", stream=True):
            if event.type == "request_info":
                request_info_event = event

        assert request_info_event is not None
        request_id = request_info_event.request_id

        # Step 2: Find the checkpoint with the pending request
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        checkpoint_with_request = None
        for checkpoint in checkpoints:
            if request_id in checkpoint.pending_request_info_events:
                checkpoint_with_request = checkpoint
                break

        assert checkpoint_with_request is not None

        # Step 3: Create a fresh workflow and restore from checkpoint WITH responses in one call
        new_executor = ApprovalRequiredExecutor(id="approval_executor")
        restored_workflow = WorkflowBuilder(start_executor=new_executor, checkpoint_storage=storage).build()

        # Track all emitted events
        emitted_events: list[WorkflowEvent] = []
        async for event in restored_workflow.run(
            checkpoint_id=checkpoint_with_request.checkpoint_id,
            responses={request_id: True},  # Provide response for the pending request
            stream=True,
        ):
            emitted_events.append(event)

        # Step 4: Verify the request_info event was NOT re-emitted to the caller
        reemitted_request_info_events = [
            e for e in emitted_events if e.type == "request_info" and e.request_id == request_id
        ]
        assert len(reemitted_request_info_events) == 0, (
            f"request_info event should NOT be re-emitted when response is provided. "
            f"Found {len(reemitted_request_info_events)} request_info events with request_id={request_id}"
        )

        # Step 5: Verify the response was processed by checking executor state
        assert new_executor.approval_received is True, "Response should have been processed by the executor"
        assert new_executor.final_result == (
            "Operation approved: Please approve the operation: test pending request suppression"
        )


async def test_checkpoint_restore_with_partial_responses_reemits_unhandled_requests():
    """Test that only unhandled request_info events are re-emitted when partial responses are provided.

    When calling run(checkpoint_id=..., responses=...) with responses for only some of the
    pending requests, only the unhandled request_info events should be re-emitted.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)

        # Create workflow with multiple requests
        executor = MultiRequestExecutor(id="multi_executor")
        workflow = WorkflowBuilder(start_executor=executor, checkpoint_storage=storage).build()

        # Step 1: Run workflow until it emits multiple request_info events
        request_events: list[WorkflowEvent] = []
        async for event in workflow.run("start batch", stream=True):
            if event.type == "request_info":
                request_events.append(event)

        assert len(request_events) == 2

        # Find the approval and calculation requests
        approval_event = next((e for e in request_events if isinstance(e.data, UserApprovalRequest)), None)
        calc_event = next((e for e in request_events if isinstance(e.data, CalculationRequest)), None)
        assert approval_event is not None
        assert calc_event is not None

        # Step 2: Find the checkpoint with pending requests
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        checkpoint_with_requests = None
        for checkpoint in checkpoints:
            has_approval = approval_event.request_id in checkpoint.pending_request_info_events
            has_calc = calc_event.request_id in checkpoint.pending_request_info_events
            if has_approval and has_calc:
                checkpoint_with_requests = checkpoint
                break

        assert checkpoint_with_requests is not None

        # Step 3: Restore from checkpoint with ONLY the approval response (not the calculation)
        new_executor = MultiRequestExecutor(id="multi_executor")
        restored_workflow = WorkflowBuilder(start_executor=new_executor, checkpoint_storage=storage).build()

        emitted_events: list[WorkflowEvent] = []
        async for event in restored_workflow.run(
            checkpoint_id=checkpoint_with_requests.checkpoint_id,
            responses={approval_event.request_id: True},  # Only respond to approval
            stream=True,
        ):
            emitted_events.append(event)

        # Step 4: Verify the approval request_info was NOT re-emitted
        reemitted_approval_events = [
            e for e in emitted_events if e.type == "request_info" and e.request_id == approval_event.request_id
        ]
        assert len(reemitted_approval_events) == 0, (
            "Approval request_info should NOT be re-emitted since response was provided"
        )

        # Step 5: Verify the calculation request_info WAS re-emitted (no response provided)
        reemitted_calc_events = [
            e for e in emitted_events if e.type == "request_info" and e.request_id == calc_event.request_id
        ]
        assert len(reemitted_calc_events) == 1, (
            "Calculation request_info SHOULD be re-emitted since no response was provided"
        )

        # Step 6: Verify workflow is in IDLE_WITH_PENDING_REQUESTS state (calc still pending)
        status_events = [e for e in emitted_events if e.type == "status"]
        final_status = status_events[-1] if status_events else None
        assert final_status is not None
        assert final_status.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS, (
            f"Workflow should be IDLE_WITH_PENDING_REQUESTS, got {final_status.state}"
        )
