# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Checkpoint hydration and new input in one workflow.run

Purpose:
Show how to restore a persisted checkpoint and apply a new user turn in a
single ``workflow.run`` call instead of the older two-step hydrate-then-run
pattern (#7863).

What you learn:
- How ``message`` and ``checkpoint_id`` can be combined on ``Workflow.run``
- That checkpoint restore runs before the new message is seeded
- That streaming and non-streaming share the same combined API
- That the prior two-step pattern remains valid for hosts that prefer it

Pipeline:
1) A stateful start executor accumulates each turn and yields the history
2) Turn 1 runs to completion and persists checkpoints
3) A fresh workflow instance resumes with ``run(message=..., checkpoint_id=...)``

Prerequisites:
- Basic understanding of workflow executors, edges, and checkpoint storage
"""

import asyncio
import sys
from typing import Any

from agent_framework import (
    Executor,
    InMemoryCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class HistoryExecutor(Executor):
    """Accumulates each turn's text and yields the full history."""

    def __init__(self, id: str) -> None:
        super().__init__(id=id)
        self._history: list[str] = []

    @handler
    async def accumulate(self, text: str, ctx: WorkflowContext[Any, list[str]]) -> None:
        self._history.append(text)
        print(f"HistoryExecutor: recorded {text!r}; history={self._history}")
        await ctx.yield_output(list(self._history))

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        return {"history": list(self._history)}

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        self._history = list(state.get("history", []))


def _build(storage: InMemoryCheckpointStorage):
    start = HistoryExecutor(id="history")
    return WorkflowBuilder(
        name="hydrate-with-input-sample",
        start_executor=start,
        checkpoint_storage=storage,
    ).build()


async def main() -> None:
    storage = InMemoryCheckpointStorage()

    # Turn 1 — fresh run
    workflow = _build(storage)
    result1 = await workflow.run("hello")
    print(f"Turn 1 outputs: {result1.get_outputs()}")

    latest = await storage.get_latest(workflow_name=workflow.name)
    if latest is None:
        raise RuntimeError("Expected a checkpoint after turn 1")

    # Turn 2 — restore + new input in one call (non-streaming)
    resumed = _build(storage)
    result2 = await resumed.run("again", checkpoint_id=latest.checkpoint_id)
    print(f"Turn 2 outputs: {result2.get_outputs()}")

    latest = await storage.get_latest(workflow_name=workflow.name)
    if latest is None:
        raise RuntimeError("Expected a checkpoint after turn 2")

    # Turn 3 — same combined API with streaming
    streamed = _build(storage)
    print("Turn 3 (streaming):")
    async for event in streamed.run("once more", checkpoint_id=latest.checkpoint_id, stream=True):
        if event.type == "output":
            print(f"  output event: {event.data}")


if __name__ == "__main__":
    asyncio.run(main())
