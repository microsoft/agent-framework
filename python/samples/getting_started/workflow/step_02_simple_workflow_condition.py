# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    output_message_types,
)

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


@output_message_types(bool)
class DetectSpamExecutor(Executor[str]):
    """An executor that determines if a message is spam."""

    def __init__(self, spam_keywords: list[str], id: str | None = None):
        """Initialize the executor with spam keywords."""
        super().__init__(id=id)
        self._spam_keywords = spam_keywords

    @override
    async def _execute(self, data: str, ctx: WorkflowContext) -> None:
        """Determine if the input string is spam."""
        result = any(keyword in data.lower() for keyword in self._spam_keywords)

        await ctx.send_message(result)


@output_message_types()
class RespondToMessageExecutor(Executor[bool]):
    """An executor that responds to a message based on spam detection."""

    @override
    async def _execute(self, data: bool, ctx: WorkflowContext) -> None:
        """Respond with a message based on whether the input is spam."""
        if data is True:
            raise RuntimeError("Input is spam, cannot respond.")

        # Simulate processing delay
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Message processed successfully."))


@output_message_types()
class RemoveSpamExecutor(Executor[bool]):
    """An executor that removes spam messages."""

    @override
    async def _execute(self, data: bool, ctx: WorkflowContext) -> None:
        """Remove the spam message."""
        if data is False:
            raise RuntimeError("Input is not spam, cannot remove.")

        # Simulate processing delay
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Spam message removed."))


async def main():
    """Main function to run the workflow."""
    spam_keywords = ["spam", "advertisement", "offer"]
    detect_spam_executor = DetectSpamExecutor(spam_keywords)
    respond_to_message_executor = RespondToMessageExecutor()
    remove_spam_executor = RemoveSpamExecutor()

    workflow = (
        WorkflowBuilder()
        .set_start_executor(detect_spam_executor)
        .add_edge(detect_spam_executor, respond_to_message_executor, condition=lambda x: x is False)
        .add_edge(detect_spam_executor, remove_spam_executor, condition=lambda x: x is True)
        .build()
    )

    async for event in workflow.run_stream("This is a spam."):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
