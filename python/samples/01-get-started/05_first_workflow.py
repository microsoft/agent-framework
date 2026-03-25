# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)
from typing_extensions import Never

"""
First Workflow — Chain executors with edges

This sample builds a minimal workflow with two steps:
1. Convert text to uppercase (class-based executor)
2. Reverse the text (function-based executor)

No external services are required.
"""


# <create_workflow>
# Step 1: A class-based executor that converts text to uppercase
class UpperCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Convert input to uppercase and forward to the next node."""
        await ctx.send_message(text.upper())


# Step 2: A function-based executor that reverses the string and yields output
@executor(id="reverse_text")
async def reverse_text(text: str, ctx: WorkflowContext[Never, str]) -> None:
    """Reverse the string and yield the final workflow output."""
    await ctx.yield_output(text[::-1])


def create_workflow():
    """Build the workflow: UpperCase → reverse_text."""
    upper = UpperCase(id="upper_case")
    return WorkflowBuilder(start_executor=upper).add_edge(upper, reverse_text).build()
# </create_workflow>


async def main() -> None:
    # <run_workflow>
    workflow = create_workflow()

    events = await workflow.run("hello world")
    print(f"Output: {events.get_outputs()}")
    print(f"Final state: {events.get_final_state()}")
    # </run_workflow>

    """
    Expected output:
      Output: ['DLROW OLLEH']
      Final state: WorkflowRunState.IDLE
    """


if __name__ == "__main__":
    asyncio.run(main())
