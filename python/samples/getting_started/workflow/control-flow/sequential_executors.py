# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import cast

from typing_extensions import Never

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)

"""
Sample: Sequential workflow with streaming.

Two custom executors run in sequence. The first converts text to uppercase,
the second reverses the text and completes the workflow. The run_stream loop prints events as they occur.

Purpose:
Show how to define explicit Executor classes with @handler methods, wire them in order with
WorkflowBuilder, and consume streaming events. Demonstrate typed WorkflowContext[T_Out, T_W_Out] for outputs,
ctx.send_message to pass intermediate values, and ctx.yield_output to provide workflow outputs.

Prerequisites:
- No external services required.
"""


class UpperCaseExecutor(Executor):
    """Converts an input string to uppercase and forwards it.

    Concepts:
    - @handler methods define invokable steps.
    - WorkflowContext[str] indicates this step emits a string to the next node.
    """

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Transform the input to uppercase and send it downstream."""
        result = text.upper()
        # Pass the intermediate result to the next executor in the chain.
        await ctx.send_message(result)


class ReverseTextExecutor(Executor):
    """Reverses the incoming string and yields workflow output.

    Concepts:
    - Use ctx.yield_output to provide workflow outputs when the terminal result is ready.
    - The terminal node does not forward messages further.
    """

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
        """Reverse the input string and yield the workflow output."""
        result = text[::-1]
        await ctx.yield_output(result)


async def main() -> None:
    """Build a two step sequential workflow and run it with streaming to observe events."""
    # Step 1: Create executor instances.
    upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
    reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")

    # Step 2: Build the workflow graph.
    # Order matters. We connect upper_case_executor -> reverse_text_executor and set the start.
    workflow = (
        WorkflowBuilder()
        .add_edge(upper_case_executor, reverse_text_executor)
        .set_start_executor(upper_case_executor)
        .build()
    )

    # Step 3: Stream events for a single input.
    # The stream will include executor invoke and completion events, plus workflow outputs.
    outputs: list[str] = []
    async for event in workflow.run_stream("hello world"):
        print(f"Event: {event}")
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(cast(str, event.data))

    if outputs:
        print(f"Workflow outputs: {outputs}")


if __name__ == "__main__":
    asyncio.run(main())
