# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys

from agent_framework.workflow import (
    Executor,
    ExecutorContext,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    output_message_types,
)

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


@output_message_types(str)
class UpperCaseExecutor(Executor[str]):
    """An executor that converts text to uppercase."""

    @override
    async def _execute(self, data: str, ctx: ExecutorContext) -> str:
        """Execute the task by converting the input string to uppercase."""
        result = data.upper()

        await ctx.send_message(result)
        return result


@output_message_types(str)
class ReverseTextExecutor(Executor[str]):
    """An executor that reverses text."""

    @override
    async def _execute(self, data: str, ctx: ExecutorContext) -> str:
        """Execute the task by reversing the input string."""
        result = data[::-1]

        await ctx.send_message(result)
        await ctx.add_event(WorkflowCompletedEvent(result))
        return result


async def main():
    """Main function to run the workflow."""
    upper_case_executor = UpperCaseExecutor()
    reverse_text_executor = ReverseTextExecutor()

    workflow = (
        WorkflowBuilder()
        .add_edge(upper_case_executor, reverse_text_executor)
        .set_start_executor(upper_case_executor)
        .build()
    )

    completion_event = None
    async for event in workflow.run_stream("hello world"):
        print(f"Event: {event}")
        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Workflow completed with result: {completion_event.data}")


if __name__ == "__main__":
    asyncio.run(main())
