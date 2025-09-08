# Copyright (c) Microsoft. All rights reserved.

"""
Spam Detection Workflow Sample for DevUI

The following sample demonstrates a basic workflow with two executors
that detect spam messages and respond accordingly. The first executor
checks if the input string is spam, and depending on the result, the
workflow takes different paths.
"""

import asyncio
from dataclasses import dataclass

from agent_framework.workflow import (
    Case,
    Default,
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)


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
        # Simulate analysis time
        print(f"Analyzing message for spam: {email}")
        await asyncio.sleep(2)  # Add realistic processing delay
        
        result = any(keyword in email.lower() for keyword in self._spam_keywords)
        print(f"Spam detection result: {result}")

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
        await asyncio.sleep(5)

        await ctx.add_event(WorkflowCompletedEvent("Message processed successfully. Message is not spam"))


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
        await asyncio.sleep(5)

        await ctx.add_event(WorkflowCompletedEvent("Spam message removed."))


# Create the workflow instance that DevUI can discover
spam_keywords = ["spam", "advertisement", "offer"]

# Create the executors
spam_detector = SpamDetector(spam_keywords, id="spam_detector")
send_response = SendResponse(id="send_response")
remove_spam = RemoveSpam(id="remove_spam")

# Build the workflow with the defined edges with conditions
workflow = (
    WorkflowBuilder()
    .set_start_executor(spam_detector)
    .add_switch_case_edge_group(
        spam_detector,
        [
            Case(condition=lambda x: x.is_spam, target=remove_spam),
            Default(target=send_response),
        ],
    )
    .build()
)

# Note: Workflow metadata is determined by executors and graph structure


async def main():
    """Main function to run the workflow (for testing outside DevUI)."""
    # Test cases
    test_messages = [
        "Hello, how are you today?",
        "This is a spam advertisement for you!",
        "Check out this amazing offer!",
        "I hope you're having a great day."
    ]
    
    print("Testing Spam Detection Workflow")
    print("-" * 40)
    
    for message in test_messages:
        print(f"\nTesting: '{message}'")
        async for event in workflow.run_stream(message):
            print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())