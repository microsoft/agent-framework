# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.workflow import WorkflowBuilder, WorkflowCompletedEvent, WorkflowContext, executor

"""
Sequential Workflow (streaming)

What it does:
- Same as step_01a but streams events as they occur.
- Useful to observe `ExecutorInvokeEvent` and `WorkflowCompletedEvent`.

Prerequisites:
- No external services required.
"""


# Step 1: Define methods using the executor decorator.
@executor(id="upper_case_executor")
async def to_upper_case(text: str, ctx: WorkflowContext[str]) -> None:
    """Execute the task by converting the input string to uppercase."""
    result = text.upper()

    # Send the result to the next executor in the workflow.
    await ctx.send_message(result)


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[str]) -> None:
    """Execute the task by reversing the input string."""
    result = text[::-1]

    # Send the result with a workflow completion event.
    await ctx.add_event(WorkflowCompletedEvent(result))


async def main():
    """Main function to run the workflow."""
    # Step 2: Build the workflow with the defined edges.
    workflow = WorkflowBuilder().add_edge(to_upper_case, reverse_text).set_start_executor(to_upper_case).build()

    # Step 3: Run the workflow with an initial message.
    completion_event = None
    async for event in workflow.run_streaming("hello world"):
        print(f"Event: {event}")
        if isinstance(event, WorkflowCompletedEvent):
            # The WorkflowCompletedEvent contains the final result.
            completion_event = event

    # Print the final result.
    if completion_event:
        print(f"Workflow completed with result: {completion_event.data}")

    """
    Sample Output:

    Event: ExecutorInvokeEvent(executor_id=upper_case_executor)
    Event: ExecutorCompletedEvent(executor_id=upper_case_executor)
    Event: ExecutorInvokeEvent(executor_id=reverse_text_executor)
    Event: WorkflowCompletedEvent(data=DLROW OLLEH)
    Event: ExecutorCompletedEvent(executor_id=reverse_text_executor)
    Workflow completed with result: DLROW OLLEH
    """


if __name__ == "__main__":
    asyncio.run(main())
