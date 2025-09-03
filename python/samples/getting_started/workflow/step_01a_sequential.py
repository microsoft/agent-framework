# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.workflow import (
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    executor,
)

"""
Sequential Workflow (basic)

What it does:
- Defines two methods decorated with the `@executor` decorator.
- The two methods are are run sequentially: uppercase then reverse.
- Emits a WorkflowCompletedEvent with the final result.

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
    events = await workflow.run("hello world")
    print(events.get_completed_event())

    """
    Sample Output:

    WorkflowCompletedEvent(data=DLROW OLLEH)
    """


if __name__ == "__main__":
    asyncio.run(main())
