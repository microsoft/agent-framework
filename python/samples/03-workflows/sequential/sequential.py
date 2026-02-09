# Copyright (c) Microsoft. All rights reserved.

"""
Sequential Workflow Sample

Demonstrates a linear step-by-step workflow where each executor processes
data and forwards it to the next in a chain.

What you'll learn:
- Defining executors as classes (Executor subclass) and functions (@executor)
- Wiring sequential edges with WorkflowBuilder
- Running a workflow and collecting outputs

Related samples:
- ../concurrent/ — Fan-out/fan-in parallel execution
- ../agents-in-workflows/ — Using agents as workflow steps

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)
from typing_extensions import Never


# <workflow_definition>
class UpperCase(Executor):
    """Convert input text to uppercase and forward to the next step."""

    def __init__(self, id: str):
        super().__init__(id=id)

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.upper()
        await ctx.send_message(result)


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[Never, str]) -> None:
    """Reverse the input string and yield as workflow output."""
    result = text[::-1]
    await ctx.yield_output(result)


class ExclamationAdder(Executor):
    """Add exclamation marks to input text using explicit @handler type parameters."""

    def __init__(self, id: str):
        super().__init__(id=id)

    @handler(input=str, output=str)
    async def add_exclamation(self, message, ctx) -> None:  # type: ignore
        result = f"{message}!!!"
        await ctx.send_message(result)  # type: ignore
# </workflow_definition>


# <running>
async def main():
    """Build and run sequential workflows."""

    upper_case = UpperCase(id="upper_case_executor")

    # Workflow 1: Two-step sequential chain
    workflow1 = (
        WorkflowBuilder(start_executor=upper_case)
        .add_edge(upper_case, reverse_text)
        .build()
    )

    print("Workflow 1 (two-step chain):")
    events1 = await workflow1.run("hello world")
    print(events1.get_outputs())
    print("Final state:", events1.get_final_state())

    # Workflow 2: Three-step sequential chain with explicit handler types
    exclamation_adder = ExclamationAdder(id="exclamation_adder")

    workflow2 = (
        WorkflowBuilder(start_executor=upper_case)
        .add_edge(upper_case, exclamation_adder)
        .add_edge(exclamation_adder, reverse_text)
        .build()
    )

    print("\nWorkflow 2 (three-step chain):")
    events2 = await workflow2.run("hello world")
    print(events2.get_outputs())
    print("Final state:", events2.get_final_state())

    """
    Sample Output:

    Workflow 1 (two-step chain):
    ['DLROW OLLEH']
    Final state: WorkflowRunState.IDLE

    Workflow 2 (three-step chain):
    ['!!!DLROW OLLEH']
    Final state: WorkflowRunState.IDLE
    """
# </running>


if __name__ == "__main__":
    asyncio.run(main())
