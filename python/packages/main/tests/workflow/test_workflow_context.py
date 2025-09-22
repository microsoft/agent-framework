# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from agent_framework import (
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture

    from agent_framework._workflow._runner_context import InProcRunnerContext


@asynccontextmanager
async def make_context(
    executor_id: str = "exec",
) -> AsyncIterator[tuple[WorkflowContext[object], "InProcRunnerContext"]]:
    from agent_framework._workflow._runner_context import InProcRunnerContext
    from agent_framework._workflow._shared_state import SharedState

    runner_ctx = InProcRunnerContext()
    shared_state = SharedState()
    workflow_ctx: WorkflowContext[object] = WorkflowContext(
        executor_id,
        ["source"],
        shared_state,
        runner_ctx,
    )
    try:
        yield workflow_ctx, runner_ctx
    finally:
        await asyncio.sleep(0)


async def test_executor_cannot_emit_framework_lifecycle_event(caplog: "LogCaptureFixture") -> None:
    async with make_context() as (ctx, runner_ctx):
        caplog.clear()
        with caplog.at_level("WARNING"):
            await ctx.add_event(WorkflowStatusEvent(state=WorkflowRunState.IN_PROGRESS))

        events: list[WorkflowEvent] = await runner_ctx.drain_events()
        assert len(events) == 1
        assert type(events[0]).__name__ == "WorkflowWarningEvent"
        data = getattr(events[0], "data", None)
        assert isinstance(data, str)
        assert "reserved for framework lifecycle notifications" in data
        assert any("attempted to emit WorkflowStatusEvent" in message for message in list(caplog.messages))


async def test_executor_emits_normal_event() -> None:
    async with make_context() as (ctx, runner_ctx):
        await ctx.add_event(WorkflowCompletedEvent("done"))

        events: list[WorkflowEvent] = await runner_ctx.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowCompletedEvent)
