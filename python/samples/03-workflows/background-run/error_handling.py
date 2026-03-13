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
Sample: Background run error handling

What this example shows
- How exceptions raised inside executors are surfaced as failed events
  through the polling interface.
- After a failure, `handle.is_idle` becomes True and the caller can inspect
  the error details from the polled events.
- The workflow can be re-used after a failed background run.

Prerequisites
- No external services required.
"""


class ValidatingExecutor(Executor):
    """Validate input and forward it, or raise if invalid."""

    @handler
    async def validate(self, text: str, ctx: WorkflowContext[str]) -> None:
        if not text.strip():
            raise ValueError("Input must not be empty or whitespace.")
        await ctx.send_message(text.upper())


class OutputExecutor(Executor):
    """Yield the received text as workflow output."""

    @handler
    async def output(self, text: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(text)


def create_workflow():
    """Create a fresh workflow instance."""
    validator = ValidatingExecutor(id="validator")
    output = OutputExecutor(id="output")
    return WorkflowBuilder(start_executor=validator).add_edge(validator, output).build()


async def main():
    """Demonstrate error handling with background run polling."""

    # --- Scenario 1: A successful run ---
    print("=== Scenario 1: Successful run ===")
    workflow = create_workflow()
    handle = workflow.run_in_background("hello")

    all_events: list[WorkflowEvent] = []
    while not handle.is_idle:
        # The workflow continues running in the background while we process events.
        all_events.extend(await handle.poll())
        await asyncio.sleep(0.01)
    all_events.extend(await handle.poll())

    outputs = [e.data for e in all_events if e.type == "output"]
    print(f"Outputs: {outputs}")
    print(f"Handle is idle: {handle.is_idle}")

    # --- Scenario 2: A failing run ---
    print("\n=== Scenario 2: Failing run ===")
    workflow = create_workflow()
    handle = workflow.run_in_background("   ")  # Whitespace triggers the error

    all_events = []
    while not handle.is_idle:
        # The workflow continues running in the background while we process events.
        all_events.extend(await handle.poll())
        # Throttle polling; poll() is non-blocking and returns immediately.
        await asyncio.sleep(0.01)
    all_events.extend(await handle.poll())

    # The handle becomes idle even after a failure.
    print(f"Handle is idle: {handle.is_idle}")

    # Inspect the failed event.
    for event in all_events:
        if event.type == "failed":
            print(f"Error type: {event.details.error_type}")
            print(f"Error message: {event.details.message}")

    # --- Scenario 3: Re-use the workflow after failure ---
    print("\n=== Scenario 3: Re-run after failure ===")
    handle = workflow.run_in_background("world")

    all_events = []
    while not handle.is_idle:
        # The workflow continues running in the background while we process events.
        all_events.extend(await handle.poll())
        await asyncio.sleep(0.01)
    all_events.extend(await handle.poll())

    outputs = [e.data for e in all_events if e.type == "output"]
    print(f"Outputs: {outputs}")

    """
    Sample Output:

    === Scenario 1: Successful run ===
    Outputs: ['HELLO']
    Handle is idle: True

    === Scenario 2: Failing run ===
    Handle is idle: True
    Error type: ValueError
    Error message: Input must not be empty or whitespace.

    === Scenario 3: Re-run after failure ===
    Outputs: ['WORLD']
    """


if __name__ == "__main__":
    asyncio.run(main())
