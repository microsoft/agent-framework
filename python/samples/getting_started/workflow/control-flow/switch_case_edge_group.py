# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from typing_extensions import Never

from agent_framework import (  # Core chat primitives used to form LLM requests
    AgentExecutor,  # Wraps an agent so it can run inside a workflow
    AgentExecutorRequest,  # Message bundle sent to an AgentExecutor
    AgentExecutorResponse,  # Result returned by an AgentExecutor
    Case,  # Case entry for a switch-case edge group
    ChatMessage,
    Default,  # Default branch when no cases match
    Role,
    WorkflowBuilder,  # Fluent builder for assembling the graph
    WorkflowContext,  # Per-run context and event bus
    executor,  # Decorator to turn a function into a workflow executor
)
from agent_framework.azure import AzureChatClient  # Thin client for Azure OpenAI chat models
from azure.identity import AzureCliCredential  # Uses your az CLI login for credentials
from pydantic import BaseModel  # Structured outputs with validation

"""
Sample: Switch-Case Edge Group with an explicit Uncertain branch.

The workflow stores a single email in shared state, asks a spam detection agent for a three way decision,
then routes with a switch-case group: NotSpam to the drafting assistant, Spam to a spam handler, and
Default to an Uncertain handler.

Purpose:
Demonstrate deterministic one of N routing with switch-case edges. Show how to:
- Persist input once in shared state, then pass around a small typed pointer that carries the email id.
- Validate agent JSON with Pydantic models for robust parsing.
- Keep executor responsibilities narrow. Transform model output to a typed DetectionResult, then route based
on that type.
- Use ctx.yield_output() to provide workflow results - the workflow completes when idle with no pending work.

Prerequisites:
- Familiarity with WorkflowBuilder, executors, edges, and events.
- Understanding of switch-case edge groups and how Case and Default are evaluated in order.
- Working Azure OpenAI configuration for AzureChatClient, with Azure CLI login and required environment variables.
- Access to workflow/resources/ambiguous_email.txt, or accept the inline fallback string.
"""


EMAIL_STATE_PREFIX = "email:"
CURRENT_EMAIL_ID_KEY = "current_email_id"


class DetectionResultAgent(BaseModel):
    """Structured output returned by the spam detection agent."""

    # The agent classifies the email and provides a rationale.
    spam_decision: Literal["NotSpam", "Spam", "Uncertain"]
    reason: str


class EmailResponse(BaseModel):
    """Structured output returned by the email assistant agent."""

    # The drafted professional reply.
    response: str


@dataclass
class DetectionResult:
    # Internal typed payload used for routing and downstream handling.
    spam_decision: str
    reason: str
    email_id: str


@dataclass
class Email:
    # In memory record of the email content stored in shared state.
    email_id: str
    email_content: str


def get_case(expected_decision: str):
    """Factory that returns a predicate matching a specific spam_decision value."""

    def condition(message: Any) -> bool:
        # Only match when the upstream payload is a DetectionResult with the expected decision.
        return isinstance(message, DetectionResult) and message.spam_decision == expected_decision

    return condition


@executor(id="store_email")
async def store_email(email_text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    # Persist the raw email once. Store under a unique key and set the current pointer for convenience.
    new_email = Email(email_id=str(uuid4()), email_content=email_text)
    await ctx.set_shared_state(f"{EMAIL_STATE_PREFIX}{new_email.email_id}", new_email)
    await ctx.set_shared_state(CURRENT_EMAIL_ID_KEY, new_email.email_id)

    # Kick off the detector by forwarding the email as a user message to the spam_detection_agent.
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=new_email.email_content)], should_respond=True)
    )


@executor(id="to_detection_result")
async def to_detection_result(response: AgentExecutorResponse, ctx: WorkflowContext[DetectionResult]) -> None:
    # Parse the detector JSON into a typed model. Attach the current email id for downstream lookups.
    parsed = DetectionResultAgent.model_validate_json(response.agent_run_response.text)
    email_id: str = await ctx.get_shared_state(CURRENT_EMAIL_ID_KEY)
    await ctx.send_message(DetectionResult(spam_decision=parsed.spam_decision, reason=parsed.reason, email_id=email_id))


@executor(id="submit_to_email_assistant")
async def submit_to_email_assistant(detection: DetectionResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    # Only proceed for the NotSpam branch. Guard against accidental misrouting.
    if detection.spam_decision != "NotSpam":
        raise RuntimeError("This executor should only handle NotSpam messages.")

    # Load the original content from shared state using the id carried in DetectionResult.
    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=email.email_content)], should_respond=True)
    )


@executor(id="finalize_and_send")
async def finalize_and_send(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    # Terminal step for the drafting branch. Yield the email response as output.
    parsed = EmailResponse.model_validate_json(response.agent_run_response.text)
    await ctx.yield_output(f"Email sent: {parsed.response}")


@executor(id="handle_spam")
async def handle_spam(detection: DetectionResult, ctx: WorkflowContext[Never, str]) -> None:
    # Spam path terminal. Include the detector's rationale.
    if detection.spam_decision == "Spam":
        await ctx.yield_output(f"Email marked as spam: {detection.reason}")
    else:
        raise RuntimeError("This executor should only handle Spam messages.")


@executor(id="handle_uncertain")
async def handle_uncertain(detection: DetectionResult, ctx: WorkflowContext[Never, str]) -> None:
    # Uncertain path terminal. Surface the original content to aid human review.
    if detection.spam_decision == "Uncertain":
        email: Email | None = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")
        await ctx.yield_output(
            f"Email marked as uncertain: {detection.reason}. Email content: {getattr(email, 'email_content', '')}"
        )
    else:
        raise RuntimeError("This executor should only handle Uncertain messages.")


async def main():
    """Main function to run the workflow."""
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Agents. response_format enforces that the LLM returns JSON that Pydantic can validate.
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

    # Build workflow: store -> detection agent -> to_detection_result -> switch (NotSpam or Spam or Default).
    # The switch-case group evaluates cases in order, then falls back to Default when none match.
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

    # Read ambiguous email if available. Otherwise use a simple inline sample.
    resources_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "resources", "ambiguous_email.txt"
    )
    if os.path.exists(resources_path):
        with open(resources_path, encoding="utf-8") as f:  # noqa: ASYNC230
            email = f.read()
    else:
        print("Unable to find resource file, using default text.")
        email = (
            "Hey there, I noticed you might be interested in our latest offer—no pressure, but it expires soon. "
            "Let me know if you'd like more details."
        )

    # Run and print the outputs from whichever branch completes.
    events = await workflow.run(email)
    outputs = events.get_outputs()
    if outputs:
        for output in outputs:
            print(f"Workflow output: {output}")


if __name__ == "__main__":
    asyncio.run(main())
