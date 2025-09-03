# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from uuid import uuid4

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
Shared State (with an Agent Reply)

What it does:
- Stores email content once in shared state; downstream steps read it by ID.
- Branches on spam detection; NOT_SPAM path calls a reply agent and finalizes; SPAM path marks it.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` reply agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
"""

EMAIL_STATE_PREFIX = "email:"


@dataclass
class DetectionResult:
    """Spam detection outcome tied to an email stored in shared state."""

    is_spam: bool
    reason: str
    email_id: str


@dataclass
class Email:
    """Email entity stored in shared state, looked up by email_id."""

    email_id: str
    email_content: str


class SpamDetection(Executor):
    """Classify spam and persist the email content in shared state once."""

    def __init__(self, spam_keywords: list[str], id: str | None = None):
        super().__init__(id=id)
        self._spam_keywords = [k.lower() for k in spam_keywords]

    @handler
    async def detect(self, message: str, ctx: WorkflowContext[DetectionResult]) -> None:
        # Create a new email record and store in shared state under a namespaced key
        new_email = Email(email_id=str(uuid4()), email_content=message)
        await ctx.set_shared_state(f"{EMAIL_STATE_PREFIX}{new_email.email_id}", new_email)

        text = message.lower()
        matched = [k for k in self._spam_keywords if k in text]
        is_spam = bool(matched)
        reason = "; ".join(sorted(set(matched))) if matched else "not spam"

        await ctx.send_message(DetectionResult(is_spam=is_spam, reason=reason, email_id=new_email.email_id))


class SubmitToReplyAgent(Executor):
    """Read stored email and submit an AgentExecutorRequest to the reply agent."""

    def __init__(self, reply_agent_id: str, id: str | None = None):
        super().__init__(id=id)
        self._reply_agent_id = reply_agent_id

    @handler
    async def submit(self, detection: DetectionResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        if detection.is_spam:
            raise RuntimeError("This executor should only handle non-spam messages.")

        email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")

        user_msg = ChatMessage(
            ChatRole.USER,
            text=(
                "Please draft a concise, professional reply to the following email.\n\n"
                f"Email:\n{email.email_content.strip()}"
            ),
        )

        await ctx.send_message(
            AgentExecutorRequest(messages=[user_msg], should_respond=True),
            target_id=self._reply_agent_id,
        )


class FinalizeAndSend(Executor):
    """Convert the agent response to a final completion event (simulate sending)."""

    @handler
    async def send(self, response: AgentExecutorResponse, ctx: WorkflowContext[None]) -> None:
        await ctx.add_event(WorkflowCompletedEvent(f"Email sent: {response.agent_run_response.text}"))


class HandleSpam(Executor):
    """Handle spam by emitting a completion event with the reason."""

    @handler
    async def handle(self, detection: DetectionResult, ctx: WorkflowContext[None]) -> None:
        if detection.is_spam:
            await ctx.add_event(WorkflowCompletedEvent(f"Email marked as spam: {detection.reason}"))
        else:
            raise RuntimeError("This executor should only handle spam messages.")


async def main() -> None:
    # Simple keyword-based spam detection for demo purposes
    spam_keywords = ["winner", "lottery", "free", "offer", "advertisement", "click here", "spam"]

    # Create Azure agent client and a reply agent
    chat_client = AzureChatClient(credential=AzureCliCredential())

    reply_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=("You are a helpful email assistant. Draft concise, professional replies.")
        ),
        id="reply_agent",
    )

    # Create executors
    spam_detector = SpamDetection(spam_keywords, id="spam_detector")
    submitter = SubmitToReplyAgent(reply_agent_id=reply_agent.id, id="submit_reply_agent")
    sender = FinalizeAndSend(id="send_email")
    spam_handler = HandleSpam(id="handle_spam")

    # Build the workflow with conditional routing, showcasing shared state usage
    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_detector)
        .add_edge(spam_detector, submitter, condition=lambda res: not res.is_spam)
        .add_edge(spam_detector, spam_handler, condition=lambda res: res.is_spam)
        .add_edge(submitter, reply_agent)
        .add_edge(reply_agent, sender)
        .build()
    )

    # Try a non-spam email first, then a spammy one to show both branches
    print("\n--- Non-spam path (shared state read in assistant) ---")
    async for evt in workflow.run_streaming("Hello team, can we meet at 3pm tomorrow to discuss the roadmap?"):
        print(f"Event: {evt}")

    print("\n--- Spam path ---")
    async for evt in workflow.run_streaming("You are a WINNER! Click here for a free lottery offer!!!"):
        print(f"Event: {evt}")


if __name__ == "__main__":
    asyncio.run(main())
