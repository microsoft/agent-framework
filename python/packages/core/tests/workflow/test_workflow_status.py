# Copyright (c) Microsoft. All rights reserved.

"""Tests for the ``Workflow.status`` property."""

from dataclasses import dataclass

import pytest

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    handler,
    response_handler,
)
from agent_framework._workflows._executor import Executor as _Executor
from agent_framework._workflows._request_info_mixin import RequestInfoMixin


class PassThroughExecutor(Executor):
    """Executor that yields its input as a workflow output and stops."""

    @handler
    async def passthrough(self, msg: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(msg)


class FailingExecutor(Executor):
    """Executor that raises at runtime to drive the FAILED status."""

    @handler
    async def fail(self, msg: int, ctx: WorkflowContext) -> None:  # pragma: no cover - invoked via workflow
        raise RuntimeError("boom")


@dataclass
class _ApprovalRequest:
    prompt: str
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            import uuid

            self.request_id = str(uuid.uuid4())


class ApprovalExecutor(_Executor, RequestInfoMixin):
    """Executor that issues a single request_info call and finalizes on response."""

    def __init__(self, id: str = "approval"):
        super().__init__(id=id)

    @handler
    async def start(self, message: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.request_info(_ApprovalRequest(prompt=message), bool)

    @response_handler
    async def on_response(
        self, original_request: _ApprovalRequest, approved: bool, ctx: WorkflowContext[str, str]
    ) -> None:
        await ctx.yield_output(f"approved={approved}")


def _build_passthrough_workflow() -> Workflow:
    executor = PassThroughExecutor(id="p")
    return WorkflowBuilder(start_executor=executor, output_from=[executor]).build()


def _build_failing_workflow() -> Workflow:
    # FailingExecutor has no workflow_output_types, so we leave designation
    # implicit; the deprecation warning is filtered at call sites that need it.
    return WorkflowBuilder(start_executor=FailingExecutor(id="f")).build()


def _build_approval_workflow() -> Workflow:
    executor = ApprovalExecutor(id="approval")
    return WorkflowBuilder(start_executor=executor, output_from=[executor]).build()


async def test_status_default_is_idle_before_first_run():
    wf = _build_passthrough_workflow()
    assert wf.status is WorkflowRunState.IDLE


async def test_status_is_idle_after_successful_run():
    wf = _build_passthrough_workflow()
    await wf.run("hello")
    assert wf.status is WorkflowRunState.IDLE


async def test_status_is_failed_after_failure():
    wf = _build_failing_workflow()
    with pytest.raises(RuntimeError, match="boom"):
        await wf.run(0)
    assert wf.status is WorkflowRunState.FAILED


async def test_status_transitions_during_streaming_run():
    """Workflow.status mirrors the most recent emitted status event."""
    wf = _build_passthrough_workflow()
    observed: list[WorkflowRunState] = []

    async for event in wf.run("hi", stream=True):
        if isinstance(event, WorkflowEvent) and event.type == "status":
            # By the time a status event surfaces to the consumer, the property
            # must already reflect that state (updated in lockstep with emission).
            assert wf.status == event.state
            observed.append(event.state)  # type: ignore

    # IN_PROGRESS must precede IDLE; both must appear.
    assert WorkflowRunState.IN_PROGRESS in observed
    assert observed[-1] is WorkflowRunState.IDLE
    assert wf.status is WorkflowRunState.IDLE


async def test_status_idle_with_pending_requests_then_resolves_to_idle():
    wf = _build_approval_workflow()

    request_event: WorkflowEvent | None = None
    async for event in wf.run("please approve", stream=True):
        if isinstance(event, WorkflowEvent) and event.type == "request_info":
            request_event = event

    assert request_event is not None
    assert wf.status is WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

    async for _ in wf.run(stream=True, responses={request_event.request_id: True}):
        pass

    assert wf.status is WorkflowRunState.IDLE


async def test_status_in_progress_pending_requests_observed_mid_run():
    """While streaming, status reaches IN_PROGRESS_PENDING_REQUESTS after a request_info event."""
    wf = _build_approval_workflow()
    seen_states: list[WorkflowRunState] = []

    async for event in wf.run("please approve", stream=True):
        if isinstance(event, WorkflowEvent) and event.type == "status":
            seen_states.append(event.state)  # type: ignore

    assert WorkflowRunState.IN_PROGRESS in seen_states
    assert WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS in seen_states
    assert seen_states[-1] is WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
    assert wf.status is WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
