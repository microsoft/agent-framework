# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Literal

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
from pydantic import BaseModel

"""
Edge Conditions (with an Agent Classifier)

What it does:
- Classifies email text with an agent (SPAM / NOT_SPAM) and branches directly via edge conditions.
- Uses `AgentExecutor` and structured output via `response_format`.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
"""


class SpamClassification(BaseModel):
    """Structured classifier output for response_format."""

    classification: Literal["SPAM", "NOT_SPAM"]


class SubmitToSpamClassifier(Executor):
    """Wraps the raw email string into an AgentExecutorRequest and sends to the classifier agent."""

    def __init__(self, id: str | None = None):
        super().__init__(id=id)

    @handler
    async def submit(self, email: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        user_msg = ChatMessage(ChatRole.USER, text=email)
        await ctx.send_message(
            AgentExecutorRequest(messages=[user_msg], should_respond=True),
        )


class RemoveSpam(Executor):
    """An executor that removes spam messages."""

    @handler
    async def handle_classifier_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[None],
    ) -> None:
        """Remove the spam message."""
        if not _is_spam_response(response):
            raise RuntimeError("Input is not spam, cannot remove.")

        # Simulate processing delay
        print("Removing spam message...")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Spam message removed."))


def _is_spam_response(response: AgentExecutorResponse) -> bool:
    """Evaluate whether the classifier marked the email as SPAM or NOT_SPAM."""
    return SpamClassification.model_validate_json(response.agent_run_response.text).classification == "SPAM"


async def main():
    """Main function to run the workflow."""
    # 1) Create agents
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Spam classifier: returns strictly "SPAM" or "NOT_SPAM" (structured).
    spam_classifier = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email spam classifier. Given ONLY the email body, respond with exactly one token: "
                "'SPAM' or 'NOT_SPAM'. Do not add explanations."
            ),
            response_format=SpamClassification,
        ),
        id="spam_classifier",
    )

    remove_spam = RemoveSpam(id="remove_spam")
    submitter = SubmitToSpamClassifier(id="submitter")

    # 2) Build the workflow with conditional edges directly from the classifier
    workflow = (
        WorkflowBuilder()
        .set_start_executor(submitter)
        .add_edge(submitter, spam_classifier)
        .add_edge(spam_classifier, remove_spam, condition=_is_spam_response)
        .build()
    )

    # 3) Run the workflow with an input message (email body)
    async for event in workflow.run_streaming("This is a limited-time offer SPAM!"):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
