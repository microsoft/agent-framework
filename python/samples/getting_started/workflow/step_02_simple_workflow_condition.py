# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from dataclasses import dataclass

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

"""
The following sample demonstrates a basic workflow with two executors
that detect spam messages and respond accordingly. The first executor
checks if the input string is spam, and depending on the result, the
workflow takes different paths.
"""


@dataclass
class EmailMessage:
    """A data class to hold the email message content."""

    content: str
    is_spam: bool = False


@output_message_types(EmailMessage)
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

        await ctx.send_message(EmailMessage(content=data, is_spam=result))


@output_message_types()
class RespondToMessageExecutor(Executor[EmailMessage]):
    """An executor that responds to a message based on spam detection."""

    @override
    async def _execute(self, data: EmailMessage, ctx: WorkflowContext) -> None:
        """Respond with a message based on whether the input is spam."""
        if data.is_spam:
            raise RuntimeError("Input is spam, cannot respond.")

        # Simulate processing delay
        print(f"Responding to message: {data.content}")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Message processed successfully."))


@output_message_types()
class RemoveSpamExecutor(Executor[EmailMessage]):
    """An executor that removes spam messages."""

    @override
    async def _execute(self, data: EmailMessage, ctx: WorkflowContext) -> None:
        """Remove the spam message."""
        if data.is_spam is False:
            raise RuntimeError("Input is not spam, cannot remove.")

        # Simulate processing delay
        print(f"Removing spam message: {data.content}")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Spam message removed."))


async def main():
    """Main function to run the workflow."""
    # Keyword based spam detection
    spam_keywords = ["spam", "advertisement", "offer"]

    # Step 1: Create the executors.
    detect_spam_executor = DetectSpamExecutor(spam_keywords, id="detect_spam_executor")
    respond_to_message_executor = RespondToMessageExecutor(id="respond_to_message_executor")
    remove_spam_executor = RemoveSpamExecutor(id="remove_spam_executor")

    # Step 2: Build the workflow with the defined edges with conditions.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(detect_spam_executor)
        .add_edge(
            detect_spam_executor,
            respond_to_message_executor,
            condition=lambda x: x.is_spam is False,
        )
        .add_edge(
            detect_spam_executor,
            remove_spam_executor,
            condition=lambda x: x.is_spam is True,
        )
        .build()
    )

    # Step 3: Run the workflow with an input message.
    async for event in workflow.run_stream("This is a spam."):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
