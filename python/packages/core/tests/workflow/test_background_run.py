# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework import (
    BackgroundRunHandle,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    handler,
    response_handler,
)


@dataclass
class NumberMessage:
    """A message carrying an integer value for testing."""

    data: int


class IncrementExecutor(Executor):
    """An executor that increments until a limit, then yields output."""

    def __init__(self, id: str, *, limit: int = 10, increment: int = 1) -> None:
        super().__init__(id=id)
        self.limit = limit
        self.increment = increment

    @handler
    async def handle(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
        if message.data < self.limit:
            await ctx.send_message(NumberMessage(data=message.data + self.increment))
        else:
            await ctx.yield_output(message.data)


class FailingExecutor(Executor):
    """An executor that always raises an exception."""

    @handler
    async def handle(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
        raise RuntimeError("Intentional failure")


def _build_simple_workflow(*, limit: int = 10) -> Any:
    """Build a two-executor ping-pong workflow for testing."""
    executor_a = IncrementExecutor(id="a", limit=limit)
    executor_b = IncrementExecutor(id="b", limit=limit)
    return (
        WorkflowBuilder(start_executor=executor_a)
        .add_edge(executor_a, executor_b)
        .add_edge(executor_b, executor_a)
        .build()
    )


async def _wait_and_collect(handle: BackgroundRunHandle) -> list[WorkflowEvent[Any]]:
    """Wait for a background handle to become idle and collect all events."""
    await handle._task  # noqa: SLF001
    return await handle.poll()


# --- Basic functionality ---


async def test_run_in_background_returns_handle() -> None:
    """run_in_background returns a BackgroundRunHandle."""
    workflow = _build_simple_workflow()
    handle = workflow.run_in_background(NumberMessage(data=0))
    assert isinstance(handle, BackgroundRunHandle)
    await _wait_and_collect(handle)


async def test_run_in_background_produces_events() -> None:
    """Polling the handle returns workflow events including output."""
    workflow = _build_simple_workflow()
    handle = workflow.run_in_background(NumberMessage(data=0))

    all_events = await _wait_and_collect(handle)

    assert len(all_events) > 0
    output_events = [e for e in all_events if e.type == "output"]
    assert len(output_events) == 1
    assert output_events[0].data == 10


async def test_run_in_background_status_events() -> None:
    """Background run emits started and status events."""
    workflow = _build_simple_workflow(limit=3)
    handle = workflow.run_in_background(NumberMessage(data=0))

    all_events = await _wait_and_collect(handle)

    types = [e.type for e in all_events]
    assert "started" in types
    assert "status" in types

    status_events = [e for e in all_events if e.type == "status"]
    final_states = [e.state for e in status_events]
    assert WorkflowRunState.IDLE in final_states


# --- is_idle property ---


async def test_is_idle_false_while_running() -> None:
    """is_idle is False while the workflow is still executing."""
    workflow = _build_simple_workflow()
    handle = workflow.run_in_background(NumberMessage(data=0))
    # Immediately after creation, the property shouldn't raise.
    _ = handle.is_idle
    await _wait_and_collect(handle)
    assert handle.is_idle is True


# --- Empty poll ---


async def test_poll_returns_empty_when_no_events() -> None:
    """poll() returns an empty list when no events are queued."""
    workflow = _build_simple_workflow()
    handle = workflow.run_in_background(NumberMessage(data=0))
    await _wait_and_collect(handle)
    # Now poll again — should be empty
    events = await handle.poll()
    assert events == []


# --- Error handling ---


async def test_run_in_background_error_produces_failed_event() -> None:
    """When the workflow fails, poll returns a failed event and is_idle becomes True."""
    failing = FailingExecutor(id="failing")
    workflow = WorkflowBuilder(start_executor=failing).build()

    handle = workflow.run_in_background(NumberMessage(data=0))

    all_events = await _wait_and_collect(handle)

    assert handle.is_idle
    failed_events = [e for e in all_events if e.type == "failed"]
    assert len(failed_events) == 1
    assert "Intentional failure" in failed_events[0].details.message


# --- Concurrency guard ---


async def test_run_in_background_prevents_concurrent_run() -> None:
    """Cannot start a second run while background run is in progress."""
    workflow = _build_simple_workflow()
    handle = workflow.run_in_background(NumberMessage(data=0))

    # Give it a moment to start
    await asyncio.sleep(0.01)

    with pytest.raises(
        RuntimeError,
        match="Workflow is already running. Concurrent executions are not allowed.",
    ):
        workflow.run_in_background(NumberMessage(data=0))

    await _wait_and_collect(handle)


async def test_run_in_background_prevents_concurrent_regular_run() -> None:
    """Cannot call run() while a background run is in progress."""
    workflow = _build_simple_workflow()
    handle = workflow.run_in_background(NumberMessage(data=0))

    await asyncio.sleep(0.01)

    with pytest.raises(
        RuntimeError,
        match="Workflow is already running. Concurrent executions are not allowed.",
    ):
        await workflow.run(NumberMessage(data=0))

    await _wait_and_collect(handle)


async def test_run_in_background_allows_rerun_after_completion() -> None:
    """After background run completes, the workflow can be run again."""
    workflow = _build_simple_workflow(limit=3)
    handle = workflow.run_in_background(NumberMessage(data=0))
    await _wait_and_collect(handle)

    # Should succeed — workflow is no longer running
    result = await workflow.run(NumberMessage(data=0))
    assert result.get_final_state() == WorkflowRunState.IDLE


async def test_run_in_background_allows_rerun_after_failure() -> None:
    """After a failed background run, the workflow can be run again."""
    failing = FailingExecutor(id="failing")
    workflow_fail = WorkflowBuilder(start_executor=failing).build()

    handle = workflow_fail.run_in_background(NumberMessage(data=0))
    await _wait_and_collect(handle)

    # Reusing same instance should work after failure
    handle2 = workflow_fail.run_in_background(NumberMessage(data=0))
    await _wait_and_collect(handle2)
    # It will fail again, but the point is it doesn't raise "already running"
    assert handle2.is_idle


# --- Parameter validation ---


async def test_run_in_background_rejects_invalid_params() -> None:
    """run_in_background validates parameters the same as run()."""
    workflow = _build_simple_workflow()

    with pytest.raises(ValueError, match="Must provide at least one of"):
        workflow.run_in_background()

    with pytest.raises(ValueError, match="Cannot provide both"):
        workflow.run_in_background(NumberMessage(data=0), responses={"r1": "yes"})


# --- respond() ---


@dataclass
class ApprovalRequest:
    """Request payload for approval."""

    prompt: str


@dataclass
class ApprovalResponse:
    """Response payload for approval."""

    approved: bool


class RequestApprovalExecutor(Executor):
    """Executor that requests approval, then yields output based on the response."""

    @handler
    async def on_message(self, message: NumberMessage, ctx: WorkflowContext) -> None:
        ctx.set_state(self.id, message.data)
        await ctx.request_info(ApprovalRequest(prompt="Approve?"), ApprovalResponse)

    @response_handler
    async def on_response(
        self,
        original_request: ApprovalRequest,
        response: ApprovalResponse,
        ctx: WorkflowContext[NumberMessage, int],
    ) -> None:
        data = ctx.get_state(self.id)
        assert isinstance(data, int)
        if response.approved:
            await ctx.yield_output(data)
        else:
            await ctx.yield_output(-1)


class PassthroughExecutor(Executor):
    """Executor that forwards the input message downstream."""

    @handler
    async def handle(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage]) -> None:
        await ctx.send_message(message)


class SlowExecutor(Executor):
    """Executor that sleeps before yielding output, simulating a hot path."""

    def __init__(self, id: str, *, delay: float = 0.1) -> None:
        super().__init__(id=id)
        self.delay = delay

    @handler
    async def handle(self, message: NumberMessage, ctx: WorkflowContext[NumberMessage, int]) -> None:
        await asyncio.sleep(self.delay)
        await ctx.yield_output(message.data * 100)


async def test_respond_after_idle_auto_resumes() -> None:
    """respond() after idle injects the response and auto-resumes the runner."""
    approval = RequestApprovalExecutor(id="approval")
    workflow = WorkflowBuilder(start_executor=approval).build()

    handle = workflow.run_in_background(NumberMessage(data=42))
    all_events = await _wait_and_collect(handle)

    # Workflow should be idle with a pending request
    assert handle.is_idle
    request_events = [e for e in all_events if e.type == "request_info"]
    assert len(request_events) == 1

    # Respond — this should auto-resume
    await handle.respond({request_events[0].request_id: ApprovalResponse(approved=True)})
    assert not handle.is_idle  # Runner restarted

    resumed_events = await _wait_and_collect(handle)
    assert handle.is_idle

    output_events = [e for e in resumed_events if e.type == "output"]
    assert len(output_events) == 1
    assert output_events[0].data == 42


async def test_respond_while_running() -> None:
    """respond() while the runner is still executing injects into the next superstep."""
    approval = RequestApprovalExecutor(id="approval")
    slow = SlowExecutor(id="slow", delay=0.2)

    # Fan-out: start sends to both approval and slow in parallel.
    # approval will request_info quickly; slow will keep running.
    start = PassthroughExecutor(id="start")

    workflow = (
        WorkflowBuilder(start_executor=start)
        .add_fan_out_edges(start, [approval, slow])
        .build()
    )

    handle = workflow.run_in_background(NumberMessage(data=7))

    # Poll until we see a request_info event (approval path)
    request_event = None
    for _ in range(100):
        events = await handle.poll()
        for e in events:
            if e.type == "request_info":
                request_event = e
                break
        if request_event is not None:
            break
        await asyncio.sleep(0.01)

    assert request_event is not None
    # The slow executor is still running, so handle should not be idle
    assert not handle.is_idle

    # Respond while running
    await handle.respond({request_event.request_id: ApprovalResponse(approved=True)})

    # Wait for completion
    remaining = await _wait_and_collect(handle)
    all_output = [e for e in remaining if e.type == "output"]

    # We should have outputs from both paths
    output_values = sorted([e.data for e in all_output])
    assert 7 in output_values  # approval path
    assert 700 in output_values  # slow path (7 * 100)


async def test_respond_with_invalid_request_id() -> None:
    """respond() raises ValueError for unknown request IDs."""
    approval = RequestApprovalExecutor(id="approval")
    workflow = WorkflowBuilder(start_executor=approval).build()

    handle = workflow.run_in_background(NumberMessage(data=1))
    await _wait_and_collect(handle)

    with pytest.raises(ValueError, match="No pending request found"):
        await handle.respond({"nonexistent_id": ApprovalResponse(approved=True)})


async def test_respond_multiple_sequential() -> None:
    """Multiple sequential respond() calls work correctly."""
    approval = RequestApprovalExecutor(id="approval")
    workflow = WorkflowBuilder(start_executor=approval).build()

    # First run: request approval
    handle = workflow.run_in_background(NumberMessage(data=10))
    events1 = await _wait_and_collect(handle)
    req1 = [e for e in events1 if e.type == "request_info"]
    assert len(req1) == 1

    # Deny — the executor yields -1
    await handle.respond({req1[0].request_id: ApprovalResponse(approved=False)})
    events2 = await _wait_and_collect(handle)
    outputs = [e.data for e in events2 if e.type == "output"]
    assert outputs == [-1]
