# Copyright (c) Microsoft. All rights reserved.

"""Shared state across executors: store an email once, reuse it downstream.

This sample mirrors the .NET "shared states" example in a Pythonic way:
- The first executor generates an email ID and stores the email content in shared state.
- A spam detection result with that ID is routed conditionally.
- If not spam, the assistant retrieves the email content from shared state to draft a reply,
  which is then "sent" by the final executor. If spam, a handler marks it as spam.

Key concept: WorkflowContext exposes get_shared_state/set_shared_state for cross-executor data.
"""

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

# "Scoped" key prefix to emulate scoping (like .NET's EmailState scope)
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


@dataclass
class EmailResponse:
    """Assistant-generated response that will be sent by the sender executor."""

    response: str


class SpamDetectionExecutor(Executor):
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


class EmailAssistantExecutor(Executor):
    """Draft a professional reply by retrieving the original email from shared state."""

    @handler
    async def draft(self, detection: DetectionResult, ctx: WorkflowContext[EmailResponse]) -> None:
        if detection.is_spam:
            raise RuntimeError("This executor should only handle non-spam messages.")

        email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")

        # Keep it simple and deterministic for a sample; no external LLM calls here.
        body = email.email_content.strip().replace("\n", " ")
        reply = (
            "Hello,\n\n"
            "Thanks for your message. Here's an initial, professional reply draft "
            'based on the original email: "'
            f"{body}"
            '"\n\nBest regards,\nYour Assistant'
        )

        await ctx.send_message(EmailResponse(response=reply))


class SendEmailExecutor(Executor):
    """Simulate sending the email by emitting a WorkflowCompletedEvent."""

    @handler
    async def send(self, response: EmailResponse, ctx: WorkflowContext[None]) -> None:
        await ctx.add_event(WorkflowCompletedEvent(f"Email sent: {response.response}"))


class HandleSpamExecutor(Executor):
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

    # Create executors
    spam_detector = SpamDetectionExecutor(spam_keywords, id="spam_detector")
    email_assistant = EmailAssistantExecutor(id="email_assistant")
    sender = SendEmailExecutor(id="send_email")
    spam_handler = HandleSpamExecutor(id="handle_spam")

    # Build the workflow with conditional routing, showcasing shared state usage
    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_detector)
        .add_edge(spam_detector, email_assistant, condition=lambda res: not res.is_spam)
        .add_edge(email_assistant, sender)
        .add_edge(spam_detector, spam_handler, condition=lambda res: res.is_spam)
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
