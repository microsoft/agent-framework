# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import pytest
from typing_extensions import Never

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.exceptions import WorkflowException


class CounterExecutor(Executor):
    """Executor that accumulates state in both shared state and an instance attribute.

    Shared state is rewound by Workflow.reset() automatically. The instance attribute is
    rewound only because this executor surfaces it via the checkpoint hooks.
    """

    def __init__(self, id: str = "counter") -> None:
        super().__init__(id)
        self.internal_count = 0

    @handler
    async def run(self, msg: int, ctx: WorkflowContext[Never, int]) -> None:
        shared = (ctx.get_state("count") or 0) + 1
        self.internal_count += 1
        ctx.set_state("count", shared)
        await ctx.yield_output(shared)

    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"internal_count": self.internal_count}

    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        self.internal_count = state.get("internal_count", 0)


async def test_state_persists_across_runs_without_reset() -> None:
    """State on a reused instance persists across runs until reset() is called."""
    counter = CounterExecutor()
    wf: Workflow = WorkflowBuilder(start_executor=counter).build()

    r1 = await wf.run(0)
    assert r1.get_outputs() == [1]

    r2 = await wf.run(0)
    assert r2.get_outputs() == [2]
    assert counter.internal_count == 2


async def test_reset_rewinds_shared_and_executor_state() -> None:
    """reset() rewinds shared state and executor checkpoint state to the initial snapshot."""
    counter = CounterExecutor()
    wf: Workflow = WorkflowBuilder(start_executor=counter).build()

    await wf.run(0)
    await wf.run(0)
    assert counter.internal_count == 2

    await wf.reset()
    assert counter.internal_count == 0

    r = await wf.run(0)
    assert r.get_outputs() == [1]


async def test_reset_is_repeatable() -> None:
    """The stored snapshot is isolated, so repeated reset+run cycles are deterministic."""
    counter = CounterExecutor()
    wf: Workflow = WorkflowBuilder(start_executor=counter).build()

    for _ in range(3):
        await wf.reset()
        r = await wf.run(0)
        assert r.get_outputs() == [1]
        assert counter.internal_count == 1


async def test_reset_before_first_run_is_noop() -> None:
    """reset() before the instance has ever run is a no-op and does not raise."""
    counter = CounterExecutor()
    wf: Workflow = WorkflowBuilder(start_executor=counter).build()

    await wf.reset()

    r = await wf.run(0)
    assert r.get_outputs() == [1]


async def test_reset_while_run_active_raises() -> None:
    """reset() is rejected while a run is active on the same instance."""
    counter = CounterExecutor()
    wf: Workflow = WorkflowBuilder(start_executor=counter).build()

    stream = wf.run(0, stream=True)
    try:
        with pytest.raises(WorkflowException, match="while a run is active"):
            await wf.reset()
    finally:
        # Drain the stream so the run finalizes cleanly.
        async for _ in stream:
            pass
