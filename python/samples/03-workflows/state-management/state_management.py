# Copyright (c) Microsoft. All rights reserved.

"""
State Management Workflow Sample

Demonstrates sharing state across workflow steps using workflow state.
An email is stored by ID in state, classified by a spam detector agent,
then routed conditionally to either draft a reply or flag as spam.

What you'll learn:
- Using ctx.set_state / ctx.get_state to decouple payloads from messages
- Passing lightweight references between steps
- Combining state management with conditional routing

Related samples:
- ../branching/ — Conditional routing between steps
- ../checkpoints/ — Save and resume workflow state

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatAgent,
    ChatMessage,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel
from typing_extensions import Never

EMAIL_STATE_PREFIX = "email:"
CURRENT_EMAIL_ID_KEY = "current_email_id"


# <step_definitions>
class DetectionResultAgent(BaseModel):
    """Structured output returned by the spam detection agent."""

    is_spam: bool
    reason: str


class EmailResponse(BaseModel):
    """Structured output returned by the email assistant agent."""

    response: str


@dataclass
class DetectionResult:
    """Internal detection result enriched with the state email_id."""

    is_spam: bool
    reason: str
    email_id: str


@dataclass
class Email:
    """In-memory record stored in state to avoid re-sending large bodies on edges."""

    email_id: str
    email_content: str


def get_condition(expected_result: bool):
    """Create a condition predicate for DetectionResult.is_spam."""

    def condition(message: Any) -> bool:
        if not isinstance(message, DetectionResult):
            return True
        return message.is_spam == expected_result

    return condition


@executor(id="store_email")
async def store_email(email_text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    """Persist the raw email content in state and trigger spam detection."""
    new_email = Email(email_id=str(uuid4()), email_content=email_text)
    ctx.set_state(f"{EMAIL_STATE_PREFIX}{new_email.email_id}", new_email)
    ctx.set_state(CURRENT_EMAIL_ID_KEY, new_email.email_id)

    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage("user", text=new_email.email_content)], should_respond=True)
    )


@executor(id="to_detection_result")
async def to_detection_result(response: AgentExecutorResponse, ctx: WorkflowContext[DetectionResult]) -> None:
    """Parse spam detection JSON and enrich with email_id from state."""
    parsed = DetectionResultAgent.model_validate_json(response.agent_response.text)
    email_id: str = ctx.get_state(CURRENT_EMAIL_ID_KEY)
    await ctx.send_message(DetectionResult(is_spam=parsed.is_spam, reason=parsed.reason, email_id=email_id))


@executor(id="submit_to_email_assistant")
async def submit_to_email_assistant(detection: DetectionResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    """Forward non-spam email content to the drafting agent."""
    if detection.is_spam:
        raise RuntimeError("This executor should only handle non-spam messages.")
    email: Email = ctx.get_state(f"{EMAIL_STATE_PREFIX}{detection.email_id}")
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage("user", text=email.email_content)], should_respond=True)
    )


@executor(id="finalize_and_send")
async def finalize_and_send(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    """Validate the drafted reply and yield the final output."""
    parsed = EmailResponse.model_validate_json(response.agent_response.text)
    await ctx.yield_output(f"Email sent: {parsed.response}")


@executor(id="handle_spam")
async def handle_spam(detection: DetectionResult, ctx: WorkflowContext[Never, str]) -> None:
    """Yield output describing why the email was marked as spam."""
    if detection.is_spam:
        await ctx.yield_output(f"Email marked as spam: {detection.reason}")
    else:
        raise RuntimeError("This executor should only handle spam messages.")
# </step_definitions>


def create_spam_detection_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You are a spam detection assistant that identifies spam emails. "
            "Always return JSON with fields is_spam (bool) and reason (string)."
        ),
        default_options={"response_format": DetectionResultAgent},
        name="spam_detection_agent",
    )


def create_email_assistant_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You are an email assistant that helps users draft responses to emails with professionalism. "
            "Return JSON with a single field 'response' containing the drafted reply."
        ),
        default_options={"response_format": EmailResponse},
        name="email_assistant_agent",
    )


# <workflow_definition>
async def main() -> None:
    workflow = (
        WorkflowBuilder(start_executor="store_email")
        .register_agent(create_spam_detection_agent, name="spam_detection_agent")
        .register_agent(create_email_assistant_agent, name="email_assistant_agent")
        .register_executor(lambda: store_email, name="store_email")
        .register_executor(lambda: to_detection_result, name="to_detection_result")
        .register_executor(lambda: submit_to_email_assistant, name="submit_to_email_assistant")
        .register_executor(lambda: finalize_and_send, name="finalize_and_send")
        .register_executor(lambda: handle_spam, name="handle_spam")
        .add_edge("store_email", "spam_detection_agent")
        .add_edge("spam_detection_agent", "to_detection_result")
        .add_edge("to_detection_result", "submit_to_email_assistant", condition=get_condition(False))
        .add_edge("to_detection_result", "handle_spam", condition=get_condition(True))
        .add_edge("submit_to_email_assistant", "email_assistant_agent")
        .add_edge("email_assistant_agent", "finalize_and_send")
        .build()
    )
# </workflow_definition>

    # <running>
    current_file = Path(__file__)
    resources_path = current_file.parent.parent.parent / "_assets" / "sample_data" / "spam.txt"
    if resources_path.exists():
        email = resources_path.read_text(encoding="utf-8")
    else:
        print("Unable to find resource file, using default text.")
        email = "You are a WINNER! Click here for a free lottery offer!!!"

    events = await workflow.run(email)
    outputs = events.get_outputs()
    if outputs:
        print(f"Final result: {outputs[0]}")
    # </running>


if __name__ == "__main__":
    asyncio.run(main())
