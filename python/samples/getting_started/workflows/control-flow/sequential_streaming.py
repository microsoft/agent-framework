# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from typing_extensions import Never

"""
Sample: Foundational sequential workflow with streaming using function-style executors.

Two lightweight steps run in order. The first converts text to uppercase.
The second reverses the text and yields the workflow output. Events are printed as they arrive from a streaming run.

Purpose:
Show how to declare executors with the @executor decorator, connect them with WorkflowBuilder,
pass intermediate values using ctx.send_message, and yield final output using ctx.yield_output().
Demonstrate how streaming exposes executor_invoked events (type='executor_invoked') and
executor_completed events (type='executor_completed') for observability.

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
    # Step 1: Build the workflow with the defined edges.
    # Order matters. upper_case_executor runs first, then reverse_text_executor.
    workflow = (
        WorkflowBuilder(start_executor="upper_case_executor")
        .register_executor(lambda: to_upper_case, name="upper_case_executor")
        .register_executor(lambda: reverse_text, name="reverse_text_executor")
        .add_edge("upper_case_executor", "reverse_text_executor")
        .build()
    )

    # Step 2: Run the workflow and stream events in real time.
    async for event in workflow.run("hello world", stream=True):
        # You will see executor invoke and completion events as the workflow progresses.
        print(f"Event: {event}")
        if event.type == "output":
            print(f"Workflow completed with result: {event.data}")

    """
    Sample Output:

    Event: executor_invoked event (type='executor_invoked', executor_id=upper_case_executor)
    Event: executor_completed event (type='executor_completed', executor_id=upper_case_executor)
    Event: executor_invoked event (type='executor_invoked', executor_id=reverse_text_executor)
    Event: executor_completed event (type='executor_completed', executor_id=reverse_text_executor)
    Event: output event (type='output', data='DLROW OLLEH', executor_id=reverse_text_executor)
    Workflow completed with result: DLROW OLLEH
    """


if __name__ == "__main__":
    asyncio.run(main())
