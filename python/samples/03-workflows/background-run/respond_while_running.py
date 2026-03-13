# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

"""
Sample: Responding while the workflow is still running (hot path / cold path)

What this example shows
- A workflow with two parallel paths after a fan-out:
    1) A "hot path" that loops, incrementing a counter each superstep.
    2) A "cold path" that pauses to request human approval via `ctx.request_info()`.
- Using `handle.respond()` inside the poll loop to send the approval while the
  hot path is still iterating, so both paths make progress concurrently.
- If the workflow has already converged when `respond()` is called, the runner
  is automatically resumed — no need to call `run_in_background()` again.

This pattern is useful for workflows where one branch can proceed independently
while another branch waits for external input. With the traditional `run()` API,
the caller must wait for the entire workflow to become idle before sending
responses. With `run_in_background()` + `respond()`, responses can be injected
at any time.

Prerequisites
- No external services required.
"""


# --- Messages ---


@dataclass
class TaskInput:
    """Input message carrying a numeric value for both paths."""

    value: int


@dataclass
class ApprovalRequest:
    """Request sent to the caller for approval."""

    prompt: str


@dataclass
class ApprovalResponse:
    """Response from the caller."""

    approved: bool


# --- Executors ---


class Dispatcher(Executor):
    """Forwards the input to both the hot path and the cold path."""

    @handler
    async def dispatch(self, message: TaskInput, ctx: WorkflowContext[TaskInput]) -> None:
        await ctx.send_message(message)


class HotPathExecutor(Executor):
    """Increments a counter in a self-loop until it reaches a limit, then yields output.

    Each iteration is a separate superstep, so the workflow stays active while
    this executor loops — giving the caller time to respond to requests from
    the cold path.
    """

    def __init__(self, id: str, *, limit: int = 10) -> None:
        super().__init__(id=id)
        self.limit = limit

    @handler
    async def compute(self, message: TaskInput, ctx: WorkflowContext[TaskInput, str]) -> None:
        if message.value < self.limit:
            await asyncio.sleep(0.05)  # Simulate work each iteration
            await ctx.send_message(TaskInput(value=message.value + 1))
        else:
            await ctx.yield_output(f"Hot path done (counted to {message.value})")


class ColdPathExecutor(Executor):
    """Requests human approval before producing output."""

    @handler
    async def request_approval(self, message: TaskInput, ctx: WorkflowContext) -> None:
        ctx.set_state(self.id, message.value)
        await ctx.request_info(
            ApprovalRequest(prompt=f"Approve processing value {message.value}?"),
            ApprovalResponse,
        )

    @response_handler
    async def on_approval(
        self,
        original_request: ApprovalRequest,
        response: ApprovalResponse,
        ctx: WorkflowContext[TaskInput, str],
    ) -> None:
        value = ctx.get_state(self.id)
        if response.approved:
            await ctx.yield_output(f"Cold path approved (value={value})")
        else:
            await ctx.yield_output(f"Cold path rejected (value={value})")


async def main():
    """Run a fan-out workflow and respond to a request inside the poll loop."""
    dispatcher = Dispatcher(id="dispatcher")
    hot_path = HotPathExecutor(id="hot_path", limit=10)
    cold_path = ColdPathExecutor(id="cold_path")

    workflow = (
        WorkflowBuilder(start_executor=dispatcher)
        .add_fan_out_edges(dispatcher, [hot_path, cold_path])
        .add_edge(hot_path, hot_path)  # Self-loop for the hot path
        .build()
    )

    handle = workflow.run_in_background(TaskInput(value=0))

    # Single poll loop: process all events and respond to requests inline.
    # The workflow continues running in the background while we process events.
    outputs: list[str] = []
    while not handle.is_idle:
        for event in await handle.poll():
            if event.type == "request_info" and isinstance(event.data, ApprovalRequest):
                print(f"  Request: {event.data.prompt}")
                print(f"  (hot path still running: is_idle={handle.is_idle})")

                # Respond immediately inside the poll loop.
                await handle.respond({event.request_id: ApprovalResponse(approved=True)})

            elif event.type == "output":
                outputs.append(event.data)
                print(f"  Output: {event.data}")

        # Throttle polling; poll() is non-blocking and returns immediately.
        await asyncio.sleep(0.01)

    # Drain any final events after idle.
    for event in await handle.poll():
        if event.type == "output":
            outputs.append(event.data)
            print(f"  Output: {event.data}")

    print(f"\nAll outputs: {outputs}")

    """
    Sample Output:

      Request: Approve processing value 0?
      (hot path still running: is_idle=False)
      Output: Cold path approved (value=0)
      Output: Hot path done (counted to 10)

    All outputs: ['Cold path approved (value=0)', 'Hot path done (counted to 10)']
    """


if __name__ == "__main__":
    asyncio.run(main())
