# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from typing_extensions import Never

"""
Step 5: Your First Workflow

Chain steps together in a simple sequential workflow.
Each step is an @executor function wired with add_edge().

For more on workflows, see: ../03-workflows/
For docs: https://learn.microsoft.com/agent-framework/get-started/first-workflow
"""


# <define_executors>
@executor(id="greet")
async def greet(name: str, ctx: WorkflowContext[str]) -> None:
    """Step 1: Create a greeting from the input name."""
    result = f"Hello, {name}!"
    print(f"  greet -> {result}")
    await ctx.send_message(result)


@executor(id="shout")
async def shout(text: str, ctx: WorkflowContext[Never, str]) -> None:
    """Step 2: Convert the greeting to uppercase and yield as workflow output."""
    result = text.upper()
    print(f"  shout -> {result}")
    await ctx.yield_output(result)
# </define_executors>


async def main():
    # <build_and_run>
    workflow = (
        WorkflowBuilder(start_executor=greet)
        .add_edge(greet, shout)
        .build()
    )

    events = await workflow.run("World")
    print(f"\nWorkflow output: {events.get_outputs()}")
    # </build_and_run>

    """
    Sample Output:

      greet -> Hello, World!
      shout -> HELLO, WORLD!

    Workflow output: ['HELLO, WORLD!']
    """


if __name__ == "__main__":
    asyncio.run(main())
