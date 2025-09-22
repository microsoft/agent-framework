# Copyright (c) Microsoft. All rights reserved.

import asyncio
import random

from agent_framework import Executor, WorkflowBuilder, WorkflowCompletedEvent, WorkflowContext, handler

"""
Sample: Concurrent fan out and fan in with two different tasks that output results of different types.

Purpose:
Show how to construct a parallel branch pattern in workflows. Demonstrate:
- Fan out by targeting multiple executors from one dispatcher.
- Fan in by collecting a list of results from the executors.
- Simple tracing using AgentRunEvent to observe execution order and progress.

Prerequisites:
- Familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
"""


class Dispatcher(Executor):
    """
    The sole purpose of this decorator is to dispatch the input of the workflow to
    other executors.
    """

    @handler
    async def handle(self, numbers: list[int], ctx: WorkflowContext[list[int]]):
        if not numbers:
            raise RuntimeError("Input must be a valid list of integers.")

        await ctx.send_message(numbers)


class Average(Executor):
    """Calculate the average of a list of integers."""

    @handler
    async def handle(self, numbers: list[int], ctx: WorkflowContext[float]):
        average: float = sum(numbers) / len(numbers)
        await ctx.send_message(average)


class Sum(Executor):
    """Calculate the sum of a list of integers."""

    @handler
    async def handle(self, numbers: list[int], ctx: WorkflowContext[int]):
        total: int = sum(numbers)
        await ctx.send_message(total)


class Aggregator(Executor):
    """Aggregate the results from the different tasks and emit the `WorkflowCompletedEvent`."""

    @handler
    async def handle(self, results: list[int | float], ctx: WorkflowContext[None]):
        """Receive the results from the source executors.

        The framework will automatically collect messages from the source executors
        and deliver them as a list.

        Args:
            results (list[int | float]): execution results from upstream executors.
                The type annotation must be a list of union types that the upstream
                executors will produce.
            cts (WorkflowContext[None]): A workflow context.
        """
        await ctx.add_event(WorkflowCompletedEvent(data=results))


async def main() -> None:
    # 1) Create the executors
    dispatcher = Dispatcher(id="dispatcher")
    average = Average(id="average")
    summation = Sum(id="summation")
    aggregator = Aggregator(id="aggregator")

    # 2) Build a simple fan out and fan in workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(dispatcher)
        .add_fan_out_edges(dispatcher, [average, summation])
        .add_fan_in_edges([average, summation], aggregator)
        .build()
    )

    # 3) Run the workflow
    completion: WorkflowCompletedEvent | None = None
    async for event in workflow.run_stream([random.randint(1, 100) for _ in range(10)]):
        if isinstance(event, WorkflowCompletedEvent):
            completion = event

    if completion is not None:
        print(completion.data)


if __name__ == "__main__":
    asyncio.run(main())
