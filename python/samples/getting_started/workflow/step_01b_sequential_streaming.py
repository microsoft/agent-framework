# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

"""
Sequential Workflow (streaming)

What it does:
- Same as step_01a but streams events as they occur.
- Useful to observe `ExecutorInvokeEvent` and `WorkflowCompletedEvent`.

Prerequisites:
- No external services required.
"""


class UpperCaseExecutor(Executor):
    """An executor that converts text to uppercase."""

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Execute the task by converting the input string to uppercase."""
        result = text.upper()

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)


class ReverseTextExecutor(Executor):
    """An executor that reverses text."""

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext[Any]) -> None:
        """Execute the task by reversing the input string."""
        result = text[::-1]

        # Send the result with a workflow completion event.
        await ctx.add_event(WorkflowCompletedEvent(result))


async def main():
    """Main function to run the workflow."""
    # Step 1: Create the executors.
    upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
    reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")

    # Step 2: Build the workflow with the defined edges.
    workflow = (
        WorkflowBuilder()
        .add_edge(upper_case_executor, reverse_text_executor)
        .set_start_executor(upper_case_executor)
        .build()
    )

    # Step 3: Run the workflow with an initial message.
    completion_event = None
    async for event in workflow.run_streaming("hello world"):
        print(f"Event: {event}")
        if isinstance(event, WorkflowCompletedEvent):
            # The WorkflowCompletedEvent contains the final result.
            completion_event = event

    if completion_event:
        print(f"Workflow completed with result: {completion_event.data}")


if __name__ == "__main__":
    asyncio.run(main())
