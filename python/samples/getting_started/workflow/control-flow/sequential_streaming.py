# Copyright (c) Microsoft. All rights reserved.

import asyncio

from typing_extensions import Never

from agent_framework import WorkflowBuilder, WorkflowContext, WorkflowOutputEvent, executor

"""
Sample: Foundational sequential workflow with streaming using function-style executors.

Two lightweight steps run in order. The first converts text to uppercase.
The second reverses the text and yields the workflow output. Events are printed as they arrive from run_stream.

Purpose:
Show how to declare executors with the @executor decorator, connect them with WorkflowBuilder,
pass intermediate values using ctx.send_message, and yield final output using ctx.yield_output().
Demonstrate how streaming exposes ExecutorInvokedEvent and ExecutorCompletedEvent for observability.

Prerequisites:
- No external services required.
"""


# Step 1: Define methods using the executor decorator.
@executor(id="upper_case_executor")
async def to_upper_case(text: str, ctx: WorkflowContext[str]) -> None:
    """Transform the input to uppercase and forward it to the next step.

    Concepts:
    - The @executor decorator registers this function as a workflow node.
    - WorkflowContext[str] indicates that this node emits a string payload downstream.
    """
    result = text.upper()

    # Send the intermediate result to the next executor in the workflow graph.
    await ctx.send_message(result)


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[Never, str]) -> None:
    """Reverse the input and yield the workflow output.

    Concepts:
    - Terminal nodes yield output using ctx.yield_output().
    - The workflow completes when it becomes idle (no more work to do).
    """
    result = text[::-1]

    # Yield the final output for this workflow run.
    await ctx.yield_output(result)


async def main():
    """Build a two-step sequential workflow and run it with streaming to observe events."""
    # Step 2: Build the workflow with the defined edges.
    # Order matters. upper_case_executor runs first, then reverse_text_executor.
    workflow = WorkflowBuilder().add_edge(to_upper_case, reverse_text).set_start_executor(to_upper_case).build()

    # Step 3: Run the workflow and stream events in real time.
    async for event in workflow.run_stream("hello world"):
        # You will see executor invoke and completion events as the workflow progresses.
        print(f"Event: {event}")
        if isinstance(event, WorkflowOutputEvent):
            print(f"Workflow completed with result: {event.data}")

    """
    Sample Output:

    Event: ExecutorInvokedEvent(executor_id=upper_case_executor)
    Event: ExecutorCompletedEvent(executor_id=upper_case_executor)
    Event: ExecutorInvokedEvent(executor_id=reverse_text_executor)
    Event: ExecutorCompletedEvent(executor_id=reverse_text_executor)
    Event: WorkflowOutputEvent(data='DLROW OLLEH', source_executor_id=reverse_text_executor)
    Workflow completed with result: DLROW OLLEH
    """


if __name__ == "__main__":
    asyncio.run(main())
