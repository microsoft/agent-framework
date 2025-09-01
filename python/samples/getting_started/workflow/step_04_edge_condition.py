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
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from azure.identity import AzureCliCredential

"""
Edge Conditions (with an Agent Classifier)

What it does:
- Classifies email text with an agent (SPAM / NOT_SPAM), parses the result, and branches via edge conditions.
- Shows minimal agent integration with clear, deterministic routing.

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
    """Wraps the raw email string into an AgentExecutorRequest and sends to the classifier agent."""

    def __init__(self, classifier_id: str, id: str | None = None):
        super().__init__(id=id)
        self._classifier_id = classifier_id

    @handler
    async def submit(self, email: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        user_msg = ChatMessage(ChatRole.USER, text=email)
        # Preserve original email for downstream executors
        await ctx.set_shared_state("original_email", email)
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
    """Parses the classifier AgentExecutorResponse and emits a SpamDetectorResponse for routing."""

    @handler
    async def route(self, response: AgentExecutorResponse, ctx: WorkflowContext[Any]) -> None:
        text = response.agent_run_response.text.strip().upper()
        is_spam = "SPAM" in text and "NOT_SPAM" not in text
        original = await ctx.get_shared_state("original_email")
        await ctx.send_message(SpamDetectorResponse(email=str(original) if original else "", is_spam=is_spam))


async def main():
    """Main function to run the workflow."""
    # 1) Create agents
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Spam classifier: returns strictly "SPAM" or "NOT_SPAM".
    spam_classifier = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email spam classifier. Given ONLY the email body, respond with exactly one token: "
                "'SPAM' or 'NOT_SPAM'. Do not add explanations."
            )
        ),
        id="spam_classifier",
    )

    send_response = SendResponse(id="send_response")
    remove_spam = RemoveSpam(id="remove_spam")
    router = ParseAndRoute(id="router")
    submitter = SubmitToSpamClassifier(classifier_id=spam_classifier.id, id="submitter")

    # 2) Build the workflow with conditional edges after routing
    workflow = (
        WorkflowBuilder()
        .set_start_executor(submitter)
        .add_edge(submitter, spam_classifier)
        .add_edge(spam_classifier, router)
        .add_edge(router, send_response, condition=lambda x: not x.is_spam)
        .add_edge(router, remove_spam, condition=lambda x: x.is_spam)
        .build()
    )

    # 3) Run the workflow with an input message (email body)
    async for event in workflow.run_streaming("This is a limited-time offer SPAM!!!"):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
