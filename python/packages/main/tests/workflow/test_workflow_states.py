# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

import pytest
from typing_extensions import Never

from agent_framework import (
    Executor,
    ExecutorFailedEvent,
    InProcRunnerContext,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    SharedState,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEventSource,
    WorkflowFailedEvent,
    WorkflowRunResult,
    WorkflowRunState,
    WorkflowStartedEvent,
    WorkflowStatusEvent,
    handler,
)
from agent_framework import WorkflowContext as WFContext


class FailingExecutor(Executor):
    """Executor that raises at runtime to test failure signaling."""

    @handler
    async def fail(self, msg: int, ctx: WorkflowContext) -> None:  # pragma: no cover - invoked via workflow
        raise RuntimeError("boom")


async def test_executor_failed_and_workflow_failed_events_streaming():
    failing = FailingExecutor(id="f")
    wf: Workflow = WorkflowBuilder().set_start_executor(failing).build()

    events: list[object] = []
    with pytest.raises(RuntimeError, match="boom"):
        async for ev in wf.run_stream(0):
            events.append(ev)

    # Workflow-level failure and FAILED status should be surfaced
    failed_events = [e for e in events if isinstance(e, WorkflowFailedEvent)]
    assert failed_events
    assert all(e.origin is WorkflowEventSource.FRAMEWORK for e in failed_events)
    status = [e for e in events if isinstance(e, WorkflowStatusEvent)]
    assert status and status[-1].state == WorkflowRunState.FAILED
    assert all(e.origin is WorkflowEventSource.FRAMEWORK for e in status)


async def test_executor_failed_event_emitted_on_direct_execute():
    failing = FailingExecutor(id="f")
    ctx = InProcRunnerContext()
    shared_state = SharedState()
    with pytest.raises(RuntimeError, match="boom"):
        await failing.execute(
            0,
            ["START"],
            shared_state,
            ctx,
        )
    drained = await ctx.drain_events()
    failed = [e for e in drained if isinstance(e, ExecutorFailedEvent)]
    assert failed
    assert all(e.origin is WorkflowEventSource.FRAMEWORK for e in failed)


class Requester(Executor):
    """Executor that always requests external info to test idle-with-requests state."""

    @handler
    async def ask(self, _: str, ctx: WorkflowContext[RequestInfoMessage]) -> None:  # pragma: no cover
        await ctx.send_message(RequestInfoMessage())


async def test_idle_with_pending_requests_status_streaming():
    req = Requester(id="req")
    rie = RequestInfoExecutor(id="rie")
    wf = WorkflowBuilder().set_start_executor(req).add_edge(req, rie).build()

    events = [ev async for ev in wf.run_stream("start")]  # Consume stream fully

    # Ensure a request was emitted
    assert any(isinstance(e, RequestInfoEvent) for e in events)
    status_events = [e for e in events if isinstance(e, WorkflowStatusEvent)]
    assert len(status_events) >= 3
    assert status_events[-2].state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS
    assert status_events[-1].state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS


class Completer(Executor):
    """Executor that completes immediately with provided data for testing."""

    @handler
    async def run(self, msg: str, ctx: WorkflowContext[Never, str]) -> None:  # pragma: no cover
        await ctx.yield_output(msg)


async def test_completed_status_streaming():
    c = Completer(id="c")
    wf = WorkflowBuilder().set_start_executor(c).build()
    events = [ev async for ev in wf.run_stream("ok")]  # no raise
    # Last status should be IDLE
    status = [e for e in events if isinstance(e, WorkflowStatusEvent)]
    assert status and status[-1].state == WorkflowRunState.IDLE
    assert all(e.origin is WorkflowEventSource.FRAMEWORK for e in status)


async def test_started_and_completed_event_origins():
    c = Completer(id="c-origin")
    wf = WorkflowBuilder().set_start_executor(c).build()
    events = [ev async for ev in wf.run_stream("payload")]

    started = next(e for e in events if isinstance(e, WorkflowStartedEvent))
    assert started.origin is WorkflowEventSource.FRAMEWORK

    # Check for IDLE status indicating completion
    idle_status = next(
        (e for e in events if isinstance(e, WorkflowStatusEvent) and e.state == WorkflowRunState.IDLE), None
    )
    assert idle_status is not None
    assert idle_status.origin is WorkflowEventSource.FRAMEWORK


async def test_non_streaming_final_state_helpers():
    # Completed case
    c = Completer(id="c")
    wf1 = WorkflowBuilder().set_start_executor(c).build()
    result1: WorkflowRunResult = await wf1.run("done")
    assert result1.get_final_state() == WorkflowRunState.IDLE

    # Idle-with-pending-request case
    req = Requester(id="req")
    rie = RequestInfoExecutor(id="rie")
    wf2 = WorkflowBuilder().set_start_executor(req).add_edge(req, rie).build()
    result2: WorkflowRunResult = await wf2.run("start")
    assert result2.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS


async def test_run_includes_status_events_completed():
    c = Completer(id="c2")
    wf = WorkflowBuilder().set_start_executor(c).build()
    result: WorkflowRunResult = await wf.run("ok")
    timeline = result.status_timeline()
    assert timeline, "Expected status timeline in non-streaming run() results"
    assert timeline[-1].state == WorkflowRunState.IDLE


async def test_run_includes_status_events_idle_with_requests():
    req = Requester(id="req2")
    rie = RequestInfoExecutor(id="rie2")
    wf = WorkflowBuilder().set_start_executor(req).add_edge(req, rie).build()
    result: WorkflowRunResult = await wf.run("start")
    timeline = result.status_timeline()
    assert timeline, "Expected status timeline in non-streaming run() results"
    assert len(timeline) >= 3
    assert timeline[-2].state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS
    assert timeline[-1].state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS


@dataclass
class SnapshotRequest(RequestInfoMessage):
    prompt: str = ""
    draft: str = ""
    iteration: int = 0


class SnapshotRequester(Executor):
    """Executor that emits a rich RequestInfoMessage for persistence tests."""

    def __init__(self, id: str, prompt: str, draft: str) -> None:
        super().__init__(id=id)
        self._prompt = prompt
        self._draft = draft

    @handler
    async def ask(self, _: str, ctx: WorkflowContext[SnapshotRequest]) -> None:  # pragma: no cover - simple helper
        await ctx.send_message(SnapshotRequest(prompt=self._prompt, draft=self._draft, iteration=1))


async def test_request_info_executor_tracks_pending_requests_via_shared_state():
    prompt = "Review the launch copy"
    draft = "Limited edition grinder now $249"
    requester = SnapshotRequester(id="snapshot_req", prompt=prompt, draft=draft)
    request_info = RequestInfoExecutor(id="request_info")

    wf = WorkflowBuilder().set_start_executor(requester).add_edge(requester, request_info).build()

    events = [event async for event in wf.run_stream("start")]
    assert any(isinstance(event, RequestInfoEvent) for event in events)

    pending_map: dict[str, Any] = await wf._shared_state.get(RequestInfoExecutor._PENDING_SHARED_STATE_KEY)  # type: ignore[reportPrivateUsage]
    assert isinstance(pending_map, dict)
    assert len(pending_map) == 1
    snapshot: dict[str, Any] = next(iter(pending_map.values()))
    assert snapshot["prompt"] == prompt
    assert snapshot["draft"] == draft
    assert snapshot.get("iteration") == 1

    request_id: str = snapshot["request_id"]

    request_info_resume = RequestInfoExecutor(id="request_info_resume")
    resume_context: WFContext[Any] = WFContext(
        executor_id=request_info_resume.id,
        source_executor_ids=[wf.__class__.__name__],
        shared_state=wf._shared_state,  # type: ignore[reportPrivateUsage]
        runner_context=wf._runner_context,  # type: ignore[reportPrivateUsage]
    )

    await request_info_resume.handle_response("approve", request_id, resume_context)

    updated_pending: dict[str, Any] = await wf._shared_state.get(RequestInfoExecutor._PENDING_SHARED_STATE_KEY)  # type: ignore[reportPrivateUsage]
    assert isinstance(updated_pending, dict)
    assert request_id not in updated_pending
