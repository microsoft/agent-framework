# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from typing_extensions import Never

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Sample: Shared state with agents and conditional routing.

Store an email once by id, classify it with a detector agent, then either draft a reply with an assistant
agent or finish with a spam notice. Stream events as the workflow runs.

Purpose:
Show how to:
- Use shared state to decouple large payloads from messages and pass around lightweight references.
- Enforce structured agent outputs with Pydantic models via response_format for robust parsing.
- Route using conditional edges based on a typed intermediate DetectionResult.
- Compose agent backed executors with function style executors and yield the final output when the workflow completes.

Prerequisites:
- Azure OpenAI configured for AzureChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Familiarity with WorkflowBuilder, executors, conditional edges, and streaming runs.
"""

EMAIL_STATE_PREFIX = "email:"
CURRENT_EMAIL_ID_KEY = "current_email_id"


class DetectionResultAgent(BaseModel):
    """Structured output returned by the spam detection agent."""

    is_spam: bool
    reason: str


class EmailResponse(BaseModel):
    """Structured output returned by the email assistant agent."""

    response: str


@dataclass
class DetectionResult:
    """Internal detection result enriched with the shared state email_id for later lookups."""

    is_spam: bool
    reason: str
    email_id: str


@dataclass
class Email:
    """In memory record stored in shared state to avoid re-sending large bodies on edges."""

    email_id: str
    email_content: str


def get_condition(expected_result: bool):
    """Create a condition predicate for DetectionResult.is_spam.

    Contract:
    - If the message is not a DetectionResult, allow it to pass to avoid accidental dead ends.
    - Otherwise, return True only when is_spam matches expected_result.
    """

    def condition(message: Any) -> bool:
        if not isinstance(message, DetectionResult):
            return True
        return message.is_spam == expected_result

    return condition


@executor(id="store_email")
async def store_email(email_text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    """Persist the raw email content in shared state and trigger spam detection.

    Responsibilities:
    - Generate a unique email_id (UUID) for downstream retrieval.
    - Store the Email object under a namespaced key and set the current id pointer.
    - Emit an AgentExecutorRequest asking the detector to respond.
    """
    new_email = Email(email_id=str(uuid4()), email_content=email_text)
    await ctx.set_shared_state(f"{EMAIL_STATE_PREFIX}{new_email.email_id}", new_email)
    await ctx.set_shared_state(CURRENT_EMAIL_ID_KEY, new_email.email_id)

    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=new_email.email_content)], should_respond=True)
    )


@executor(id="to_detection_result")
async def to_detection_result(response: AgentExecutorResponse, ctx: WorkflowContext[DetectionResult]) -> None:
    """Parse spam detection JSON into a structured model and enrich with email_id.

    Steps:
    1) Validate the agent's JSON output into DetectionResultAgent.
    2) Retrieve the current email_id from shared state.
    3) Send a typed DetectionResult for conditional routing.
    """
    parsed = DetectionResultAgent.model_validate_json(response.agent_run_response.text)
    email_id: str = await ctx.get_shared_state(CURRENT_EMAIL_ID_KEY)
    await ctx.send_message(DetectionResult(is_spam=parsed.is_spam, reason=parsed.reason, email_id=email_id))


@executor(id="submit_to_email_assistant")
async def submit_to_email_assistant(detection: DetectionResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    """Forward non spam email content to the drafting agent.

    Guard:
    - This path should only receive non spam. Raise if misrouted.
    """
    if detection.is_spam:
        raise RuntimeError("This executor should only handle non-spam messages.")

    # Load the original content by id from shared state and forward it to the assistant.
    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=email.email_content)], should_respond=True)
    )


@executor(id="finalize_and_send")
async def finalize_and_send(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    """Validate the drafted reply and yield the final output."""
    parsed = EmailResponse.model_validate_json(response.agent_run_response.text)
    await ctx.yield_output(f"Email sent: {parsed.response}")


@executor(id="handle_spam")
async def handle_spam(detection: DetectionResult, ctx: WorkflowContext[Never, str]) -> None:
    """Yield output describing why the email was marked as spam."""
    if detection.is_spam:
        await ctx.yield_output(f"Email marked as spam: {detection.reason}")
    else:
        raise RuntimeError("This executor should only handle spam messages.")


async def main() -> None:
    # Create chat client and agents. response_format enforces structured JSON from each agent.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    spam_detection_agent = chat_client.create_agent(
        instructions=(
            "You are a spam detection assistant that identifies spam emails. "
            "Always return JSON with fields is_spam (bool) and reason (string)."
        ),
        response_format=DetectionResultAgent,
        name="spam_detection_agent",
    )

    email_assistant_agent = chat_client.create_agent(
        instructions=(
            "You are an email assistant that helps users draft responses to emails with professionalism. "
            "Return JSON with a single field 'response' containing the drafted reply."
        ),
        response_format=EmailResponse,
        name="email_assistant_agent",
    )

    # Build the workflow graph with conditional edges.
    # Flow:
    #   store_email -> spam_detection_agent -> to_detection_result -> branch:
    #     False -> submit_to_email_assistant -> email_assistant_agent -> finalize_and_send
    #     True  -> handle_spam
    workflow = (
        WorkflowBuilder()
        .set_start_executor(store_email)
        .add_edge(store_email, spam_detection_agent)
        .add_edge(spam_detection_agent, to_detection_result)
        .add_edge(to_detection_result, submit_to_email_assistant, condition=get_condition(False))
        .add_edge(to_detection_result, handle_spam, condition=get_condition(True))
        .add_edge(submit_to_email_assistant, email_assistant_agent)
        .add_edge(email_assistant_agent, finalize_and_send)
        .build()
    )

    # Read an email from resources/spam.txt if available; otherwise use a default sample.
    resources_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
        "resources",
        "spam.txt",
    )
    if os.path.exists(resources_path):
        with open(resources_path, encoding="utf-8") as f:  # noqa: ASYNC230
            email = f.read()
    else:
        print("Unable to find resource file, using default text.")
        email = "You are a WINNER! Click here for a free lottery offer!!!"

    # Run and print the final result. Streaming surfaces intermediate execution events as well.
    events = await workflow.run(email)
    outputs = events.get_outputs()

    if outputs:
        print(f"Final result: {outputs[0]}")

    """
    Sample Output:

    Final result: Email marked as spam: This email exhibits several common spam and scam characteristics:
    unrealistic claims of large cash winnings, urgent time pressure, requests for sensitive personal and financial
    information, and a demand for a processing fee. The sender impersonates a generic lottery commission, and the
    message contains a suspicious link. All these are typical of phishing and lottery scam emails.
    """


if __name__ == "__main__":
    asyncio.run(main())
