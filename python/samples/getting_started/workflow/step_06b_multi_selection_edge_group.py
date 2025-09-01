# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

"""
Demonstrates a multi-selection edge group.

The first executor detects whether an email is spam. Based on the
result, the workflow uses a selection function to route the message to
one of multiple possible targets. While this sample selects a single
target per input for simplicity, the selection function can return
multiple targets to fan out to several executors at once.
"""


@dataclass
class SpamDetectorResponse:
    """A data class to hold the email message content."""

    email: str
    is_spam: bool = False


class SpamDetector(Executor):
    """An executor that determines if a message is spam."""

    def __init__(self, spam_keywords: list[str], id: str | None = None):
        """Initialize the executor with spam keywords."""
        super().__init__(id=id)
        self._spam_keywords = spam_keywords

    @handler
    async def handle_email(self, email: str, ctx: WorkflowContext[SpamDetectorResponse]) -> None:
        """Determine if the input string is spam."""
        result = any(keyword in email.lower() for keyword in self._spam_keywords)

        await ctx.send_message(SpamDetectorResponse(email=email, is_spam=result))


class SendResponse(Executor):
    """An executor that responds to a message based on spam detection."""

    @handler
    async def handle_detector_response(
        self,
        spam_detector_response: SpamDetectorResponse,
        ctx: WorkflowContext[None],
    ) -> None:
        """Respond with a message based on whether the input is spam."""
        if spam_detector_response.is_spam:
            raise RuntimeError("Input is spam, cannot respond.")

        # Simulate processing delay
        print(f"Responding to message: {spam_detector_response.email}")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Message processed successfully."))


class RemoveSpam(Executor):
    """An executor that removes spam messages."""

    @handler
    async def handle_detector_response(
        self,
        spam_detector_response: SpamDetectorResponse,
        ctx: WorkflowContext[None],
    ) -> None:
        """Remove the spam message."""
        if spam_detector_response.is_spam is False:
            raise RuntimeError("Input is not spam, cannot remove.")

        # Simulate processing delay
        print(f"Removing spam message: {spam_detector_response.email}")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Spam message removed."))


async def main():
    """Main function to run the workflow."""
    # Keyword based spam detection
    spam_keywords = ["spam", "advertisement", "offer"]

    # Step 1: Create the executors.
    spam_detector = SpamDetector(spam_keywords, id="spam_detector")
    send_response = SendResponse(id="send_response")
    remove_spam = RemoveSpam(id="remove_spam")

    # Step 2: Build the workflow using a multi-selection edge group.
    # The selection function returns a list of target IDs to invoke.
    # You can return multiple IDs to execute several targets in parallel.
    def select_targets(result: SpamDetectorResponse, target_ids: list[str]) -> list[str]:
        # target_ids are in the same order as the "targets" list below
        remove_spam_id, send_response_id = target_ids
        return [remove_spam_id] if result.is_spam else [send_response_id]

    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_detector)
        .add_multi_selection_edge_group(spam_detector, [remove_spam, send_response], selection_func=select_targets)
        .build()
    )

    # Step 3: Run the workflow with an input message.
    async for event in workflow.run_streaming("This is a spam."):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
