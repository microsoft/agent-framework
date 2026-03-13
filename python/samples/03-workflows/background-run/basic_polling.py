# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
)

"""
Sample: Background run with polling

What this example shows
- Starting a workflow in the background with `workflow.run_in_background()`.
- Polling for events at your own pace with `handle.poll()`.
- Checking when the workflow reaches an idle state with `handle.is_idle`.

This pattern is useful when a consumer needs to pull events on demand rather
than being pushed events via streaming. The workflow (producer) runs in a
background asyncio task and buffers events into an internal queue. The caller
(consumer) drains that queue whenever it is ready.

Prerequisites
- No external services required.
"""


class UpperCase(Executor):
    """Convert text to uppercase and forward it."""

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.upper()
        await ctx.send_message(result)


class ReverseText(Executor):
    """Reverse text and yield it as workflow output."""

    @handler
    async def reverse(self, text: str, ctx: WorkflowContext[str, str]) -> None:
        result = text[::-1]
        await ctx.yield_output(result)


async def main():
    """Run a simple workflow in the background and poll for events."""
    upper_case = UpperCase(id="upper_case")
    reverse_text = ReverseText(id="reverse_text")

    workflow = WorkflowBuilder(start_executor=upper_case).add_edge(upper_case, reverse_text).build()

    # Start the workflow in the background. This returns immediately with a
    # handle that lets the caller pull events at its own pace.
    handle = workflow.run_in_background("hello world")

    # Poll for events until the workflow becomes idle.
    all_events: list[WorkflowEvent] = []
    while not handle.is_idle:
        # The workflow continues running in the background while we process events.
        events = await handle.poll()
        all_events.extend(events)
        await asyncio.sleep(0.01)

    # Drain any remaining events produced just before idle was detected.
    all_events.extend(await handle.poll())

    # Print all collected events.
    print("Events received:")
    for event in all_events:
        print(f"  type={event.type}", end="")
        if event.type == "output":
            print(f"  data={event.data!r}", end="")
        print()

    # Extract outputs.
    outputs = [e.data for e in all_events if e.type == "output"]
    print(f"\nOutputs: {outputs}")
    print(f"Handle is idle: {handle.is_idle}")

    """
    Sample Output:

    Events received:
      type=started
      type=status
      type=superstep_started
      type=executor_invoked
      type=executor_completed
      type=superstep_completed
      type=superstep_started
      type=executor_invoked
      type=executor_completed
      type=output  data='DLROW OLLEH'
      type=superstep_completed
      type=status
    Handle is idle: True
    Outputs: ['DLROW OLLEH']
    """


if __name__ == "__main__":
    asyncio.run(main())
