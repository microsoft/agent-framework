# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Case,
    Default,
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from azure.identity import AzureCliCredential

"""
Switch-Case Edge Group (with Agent Classifier)

What it does:
- Classifies email with an agent, parses the result, and branches using `add_switch_case_edge_group`.
- Demonstrates `Case`/`Default` behavior with an agent-produced boolean.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
"""


@dataclass
class SpamDetectorResponse:
    """A data class to hold the email message content."""

    email: str
    is_spam: bool = False


class SubmitToSpamClassifier(Executor):
    """Wrap email string into AgentExecutorRequest and send to classifier by target_id."""

    def __init__(self, classifier_id: str, id: str | None = None):
        super().__init__(id=id)
        self._classifier_id = classifier_id

    @handler
    async def submit(self, email: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        user_msg = ChatMessage(ChatRole.USER, text=email)
        await ctx.send_message(
            AgentExecutorRequest(messages=[user_msg], should_respond=True),
            target_id=self._classifier_id,
        )


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


class ParseAndRoute(Executor):
    """Parse AgentExecutorResponse into SpamDetectorResponse for routing."""

    @handler
    async def route(self, response: AgentExecutorResponse, ctx: WorkflowContext[Any]) -> None:
        text = response.agent_run_response.text.strip().upper()
        is_spam = "SPAM" in text and "NOT_SPAM" not in text
        await ctx.send_message(SpamDetectorResponse(email="<redacted>", is_spam=is_spam))


async def main():
    """Main function to run the workflow."""
    # Create agent classifier
    chat_client = AzureChatClient(credential=AzureCliCredential())
    spam_classifier = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email spam classifier. Given ONLY the email body, respond with exactly one token: "
                "'SPAM' or 'NOT_SPAM'."
            )
        ),
        id="spam_classifier",
    )

    # Step 1: Create the executors.
    submitter = SubmitToSpamClassifier(spam_classifier.id, id="submitter")
    send_response = SendResponse(id="send_response")
    remove_spam = RemoveSpam(id="remove_spam")
    router = ParseAndRoute(id="router")

    # Step 2: Build the workflow with the defined edges with conditions.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(submitter)
        .add_edge(submitter, spam_classifier)
        .add_edge(spam_classifier, router)
        .add_switch_case_edge_group(
            router,
            [
                Case(condition=lambda x: x.is_spam, target=remove_spam),
                Default(target=send_response),
            ],
        )
        .build()
    )

    # Step 3: Run the workflow with an input message.
    async for event in workflow.run_streaming("This is a spam."):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
