# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any, cast

from agent_framework import (
    Executor,
    ExecutorCompletedEvent,
    ExecutorInvokedEvent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)
from typing_extensions import Never

"""
Executor I/O Observation

This sample demonstrates how to observe executor input and output data without modifying
executor code. This is useful for debugging, logging, or building monitoring tools.

What this example shows:
- ExecutorInvokedEvent.data contains the input message received by the executor
- ExecutorCompletedEvent.data contains the messages sent via ctx.send_message()
- How to generically observe all executor I/O through workflow streaming events

This approach allows you to instrument any workflow for observability without
changing the executor implementations.

Prerequisites:
- No external services required.
"""


class UpperCaseExecutor(Executor):
    """Convert input text to uppercase and forward to next executor."""

    def __init__(self, id: str = "upper_case"):
        super().__init__(id=id)

    @handler
    async def handle(self, text: str, ctx: WorkflowContext[str]) -> None:
        result = text.upper()
        await ctx.send_message(result)


class ReverseTextExecutor(Executor):
    """Reverse the input text and yield as workflow output."""

    def __init__(self, id: str = "reverse_text"):
        super().__init__(id=id)

    @handler
    async def handle(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
        result = text[::-1]
        await ctx.yield_output(result)


def format_io_data(data: Any) -> str:
    """Format executor I/O data for display.

    This helper formats common data types for readable output.
    Customize based on the types used in your workflow.
    """
    type_name = type(data).__name__

    if data is None:
        return "None"
    if isinstance(data, str):
        preview = data[:80] + "..." if len(data) > 80 else data
        return f"{type_name}: '{preview}'"
    if isinstance(data, list):
        data_list = cast(list[Any], data)
        if len(data_list) == 0:
            return f"{type_name}: []"
        # For sent_messages, show each item with its type
        if len(data_list) <= 3:
            items = [format_io_data(item) for item in data_list]
            return f"{type_name}: [{', '.join(items)}]"
        return f"{type_name}: [{len(data_list)} items]"
    return f"{type_name}: {repr(data)}"


async def main() -> None:
    """Build a workflow and observe executor I/O through streaming events."""
    upper_case = UpperCaseExecutor()
    reverse_text = ReverseTextExecutor()

    workflow = WorkflowBuilder().add_edge(upper_case, reverse_text).set_start_executor(upper_case).build()

    print("Running workflow with executor I/O observation...\n")

    async for event in workflow.run_stream("hello world"):
        if isinstance(event, ExecutorInvokedEvent):
            # The input message received by the executor is in event.data
            print(f"[INVOKED] {event.executor_id}")
            print(f"    Input: {format_io_data(event.data)}")

        elif isinstance(event, ExecutorCompletedEvent):
            # Messages sent via ctx.send_message() are in event.data
            print(f"[COMPLETED] {event.executor_id}")
            if event.data:
                print(f"    Output: {format_io_data(event.data)}")

        elif isinstance(event, WorkflowOutputEvent):
            print(f"[WORKFLOW OUTPUT] {format_io_data(event.data)}")

    """
    Sample Output:

    Running workflow with executor I/O observation...

    [INVOKED] upper_case
        Input: str: 'hello world'
    [COMPLETED] upper_case
        Output: list: [str: 'HELLO WORLD']
    [INVOKED] reverse_text
        Input: str: 'HELLO WORLD'
    [WORKFLOW OUTPUT] str: 'DLROW OLLEH'
    [COMPLETED] reverse_text
    """


if __name__ == "__main__":
    asyncio.run(main())
