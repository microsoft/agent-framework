# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Optional

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
- Demonstrates three paths via `Case`/`Default`: spam, not spam, unknown.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
"""


class SendResponse(Executor):
    """Respond to a message that is explicitly NOT spam."""

    @handler
    async def handle_classifier_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[None],
    ) -> None:
        """Respond only when the classifier marked it NOT spam."""
        if _tri_state(response) is not False:
            raise RuntimeError("Input is not explicitly NOT_SPAM, cannot respond.")

        # Simulate processing delay
        print("Responding to message (NOT_SPAM)")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Message processed successfully."))


class RemoveSpam(Executor):
    """An executor that removes spam messages."""

    @handler
    async def handle_classifier_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[None],
    ) -> None:
        """Remove the spam message."""
        if _tri_state(response) is not True:
            raise RuntimeError("Input is not spam, cannot remove.")

        # Simulate processing delay
        print("Removing spam message (SPAM)")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Spam message removed."))


class HandleUnknown(Executor):
    """Handle messages that could not be confidently classified."""

    @handler
    async def handle_classifier_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[None],
    ) -> None:
        if _tri_state(response) is not None:
            raise RuntimeError("Input is known spam/not_spam, not unknown.")

        print("Unable to classify message. Escalating for review (UNKNOWN).")
        await asyncio.sleep(1)

        await ctx.add_event(WorkflowCompletedEvent("Message requires manual review (UNKNOWN)."))


def _tri_state(response: AgentExecutorResponse) -> Optional[bool]:
    """Return True for SPAM, False for NOT_SPAM, None for UNKNOWN/other."""
    text = (response.agent_run_response.text or "").strip().upper()
    if "NOT_SPAM" in text:
        return False
    if "SPAM" in text and "NOT_SPAM" not in text:
        return True
    return None


async def main():
    """Main function to run the workflow."""
    # Create agent classifier
    chat_client = AzureChatClient(credential=AzureCliCredential())
    spam_classifier = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email spam classifier. Given ONLY the email body, respond with exactly one token: "
                "'SPAM', 'NOT_SPAM', or 'UNKNOWN' if genuinely uncertain."
            )
        ),
        id="spam_classifier",
    )

    # Step 1: Create the executors (keep only the three action executors).
    send_response = SendResponse(id="send_response")
    remove_spam = RemoveSpam(id="remove_spam")
    handle_unknown = HandleUnknown(id="handle_unknown")

    # Step 2: Build the workflow. Start from the classifier and branch by switch-case directly.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_classifier)
        .add_switch_case_edge_group(
            spam_classifier,
            [
                Case(condition=lambda resp: _tri_state(resp) is True, target=remove_spam),
                Case(condition=lambda resp: _tri_state(resp) is False, target=send_response),
                Default(target=handle_unknown),
            ],
        )
        .build()
    )

    # Step 3: Run the workflow with an input message.
    user_msg = ChatMessage(ChatRole.USER, text="This is a spam.")
    request = AgentExecutorRequest(messages=[user_msg], should_respond=True)
    async for event in workflow.run_streaming(request):
        print(f"Event: {event}")


if __name__ == "__main__":
    asyncio.run(main())
