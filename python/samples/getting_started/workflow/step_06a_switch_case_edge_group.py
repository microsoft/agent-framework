# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Case,
    Default,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    executor,
)
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Step 06a — Switch-Case Edge Group (Uncertain branch)

This sample mirrors the .NET version by:
- Using a spam detection agent that can be uncertain (three-way decision)
- Storing the email once in shared state and carrying an email_id in the detection result
- Routing with a switch-case edge group: NotSpam → Email Assistant → Send; Spam → HandleSpam; Default → HandleUncertain
"""


EMAIL_STATE_PREFIX = "email:"
CURRENT_EMAIL_ID_KEY = "current_email_id"


class DetectionResultAgent(BaseModel):
    """Structured output returned by the spam detection agent."""

    spam_decision: Literal["NotSpam", "Spam", "Uncertain"]
    reason: str


class EmailResponse(BaseModel):
    """Structured output returned by the email assistant agent."""

    response: str


@dataclass
class DetectionResult:
    spam_decision: str
    reason: str
    email_id: str


@dataclass
class Email:
    email_id: str
    email_content: str


def get_case(expected_decision: str):
    def condition(message: Any) -> bool:
        return isinstance(message, DetectionResult) and message.spam_decision == expected_decision

    return condition


@executor(id="store_email")
async def store_email(email_text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    new_email = Email(email_id=str(uuid4()), email_content=email_text)
    await ctx.set_shared_state(f"{EMAIL_STATE_PREFIX}{new_email.email_id}", new_email)
    await ctx.set_shared_state(CURRENT_EMAIL_ID_KEY, new_email.email_id)

    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(ChatRole.USER, text=new_email.email_content)], should_respond=True)
    )


@executor(id="to_detection_result")
async def to_detection_result(response: AgentExecutorResponse, ctx: WorkflowContext[DetectionResult]) -> None:
    parsed = DetectionResultAgent.model_validate_json(response.agent_run_response.text)
    email_id: str = await ctx.get_shared_state(CURRENT_EMAIL_ID_KEY)
    await ctx.send_message(DetectionResult(spam_decision=parsed.spam_decision, reason=parsed.reason, email_id=email_id))


@executor(id="submit_to_email_assistant")
async def submit_to_email_assistant(detection: DetectionResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    if detection.spam_decision != "NotSpam":
        raise RuntimeError("This executor should only handle NotSpam messages.")

    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(ChatRole.USER, text=email.email_content)], should_respond=True)
    )


@executor(id="finalize_and_send")
async def finalize_and_send(response: AgentExecutorResponse, ctx: WorkflowContext[None]) -> None:
    parsed = EmailResponse.model_validate_json(response.agent_run_response.text)
    await ctx.add_event(WorkflowCompletedEvent(f"Email sent: {parsed.response}"))


@executor(id="handle_spam")
async def handle_spam(detection: DetectionResult, ctx: WorkflowContext[None]) -> None:
    if detection.spam_decision == "Spam":
        await ctx.add_event(WorkflowCompletedEvent(f"Email marked as spam: {detection.reason}"))
    else:
        raise RuntimeError("This executor should only handle Spam messages.")


@executor(id="handle_uncertain")
async def handle_uncertain(detection: DetectionResult, ctx: WorkflowContext[None]) -> None:
    if detection.spam_decision == "Uncertain":
        email: Email | None = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")
        await ctx.add_event(
            WorkflowCompletedEvent(
                f"Email marked as uncertain: {detection.reason}. Email content: {getattr(email, 'email_content', '')}"
            )
        )
    else:
        raise RuntimeError("This executor should only handle Uncertain messages.")


async def main():
    """Main function to run the workflow."""
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Agents
    spam_detection_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are a spam detection assistant that identifies spam emails. "
                "Be less confident in your assessments. "
                "Always return JSON with fields 'spam_decision' (one of NotSpam, Spam, Uncertain) "
                "and 'reason' (string)."
            ),
            response_format=DetectionResultAgent,
        ),
        id="spam_detection_agent",
    )

    email_assistant_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email assistant that helps users draft responses to emails with professionalism."
            ),
            response_format=EmailResponse,
        ),
        id="email_assistant_agent",
    )

    # Build workflow: store -> detection agent -> to_detection_result -> switch (NotSpam/Spam/Default)
    workflow = (
        WorkflowBuilder()
        .set_start_executor(store_email)
        .add_edge(store_email, spam_detection_agent)
        .add_edge(spam_detection_agent, to_detection_result)
        .add_switch_case_edge_group(
            to_detection_result,
            [
                Case(condition=get_case("NotSpam"), target=submit_to_email_assistant),
                Case(condition=get_case("Spam"), target=handle_spam),
                Default(target=handle_uncertain),
            ],
        )
        .add_edge(submit_to_email_assistant, email_assistant_agent)
        .add_edge(email_assistant_agent, finalize_and_send)
        .build()
    )

    # Read ambiguous email if available; else default text
    resources_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "ambiguous_email.txt")
    if os.path.exists(resources_path):
        with open(resources_path, encoding="utf-8") as f:  # noqa: ASYNC230
            email = f.read()
    else:
        email = (
            "Hey there, I noticed you might be interested in our latest offer—no pressure, but it expires soon. "
            "Let me know if you'd like more details."
        )

    # Run
    async for event in workflow.run_streaming(email):
        if isinstance(event, WorkflowCompletedEvent):
            print(f"{event}")


if __name__ == "__main__":
    asyncio.run(main())
