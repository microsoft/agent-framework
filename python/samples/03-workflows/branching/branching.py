# Copyright (c) Microsoft. All rights reserved.

"""
Branching (Conditional Routing) Workflow Sample

Demonstrates conditional routing between workflow steps using edge conditions.
An email is classified as spam or not-spam, then routed to the appropriate handler.

What you'll learn:
- Attaching boolean edge conditions to route messages
- Using Pydantic models as response_format for structured agent output
- Transforming one agent's result into a new request for a downstream agent

Related samples:
- ../sequential/ — Linear step-by-step workflows
- ../state-management/ — Share state across steps with conditional routing

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
import os
from typing import Any

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


# <step_definitions>
class DetectionResult(BaseModel):
    """Represents the result of spam detection."""

    is_spam: bool
    reason: str
    email_content: str


class EmailResponse(BaseModel):
    """Represents the response from the email assistant."""

    response: str


def get_condition(expected_result: bool):
    """Create a condition callable that routes based on DetectionResult.is_spam."""

    def condition(message: Any) -> bool:
        if not isinstance(message, AgentExecutorResponse):
            return True
        try:
            detection = DetectionResult.model_validate_json(message.agent_response.text)
            return detection.is_spam == expected_result
        except Exception:
            return False

    return condition


@executor(id="send_email")
async def handle_email_response(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    email_response = EmailResponse.model_validate_json(response.agent_response.text)
    await ctx.yield_output(f"Email sent:\n{email_response.response}")


@executor(id="handle_spam")
async def handle_spam_classifier_response(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    detection = DetectionResult.model_validate_json(response.agent_response.text)
    if detection.is_spam:
        await ctx.yield_output(f"Email marked as spam: {detection.reason}")
    else:
        raise RuntimeError("This executor should only handle spam messages.")


@executor(id="to_email_assistant_request")
async def to_email_assistant_request(
    response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
) -> None:
    """Transform detection result into an AgentExecutorRequest for the email assistant."""
    detection = DetectionResult.model_validate_json(response.agent_response.text)
    user_msg = ChatMessage("user", text=detection.email_content)
    await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))
# </step_definitions>


def create_spam_detector_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You are a spam detection assistant that identifies spam emails. "
            "Always return JSON with fields is_spam (bool), reason (string), and email_content (string). "
            "Include the original email content in email_content."
        ),
        name="spam_detection_agent",
        default_options={"response_format": DetectionResult},
    )


def create_email_assistant_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You are an email assistant that helps users draft professional responses to emails. "
            "Your input may be a JSON object that includes 'email_content'; base your reply on that content. "
            "Return JSON with a single field 'response' containing the drafted reply."
        ),
        name="email_assistant_agent",
        default_options={"response_format": EmailResponse},
    )


# <workflow_definition>
async def main() -> None:
    workflow = (
        WorkflowBuilder(start_executor="spam_detection_agent")
        .register_agent(create_spam_detector_agent, name="spam_detection_agent")
        .register_agent(create_email_assistant_agent, name="email_assistant_agent")
        .register_executor(lambda: to_email_assistant_request, name="to_email_assistant_request")
        .register_executor(lambda: handle_email_response, name="send_email")
        .register_executor(lambda: handle_spam_classifier_response, name="handle_spam")
        # Not-spam path
        .add_edge("spam_detection_agent", "to_email_assistant_request", condition=get_condition(False))
        .add_edge("to_email_assistant_request", "email_assistant_agent")
        .add_edge("email_assistant_agent", "send_email")
        # Spam path
        .add_edge("spam_detection_agent", "handle_spam", condition=get_condition(True))
        .build()
    )
# </workflow_definition>

    # <running>
    # Read email content from the sample resource file
    email_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "..", "_assets", "sample_data", "email.txt")

    if os.path.exists(email_path):
        with open(email_path) as email_file:  # noqa: ASYNC230
            email = email_file.read()
    else:
        email = (
            "Subject: Team Meeting Follow-up\n\n"
            "Hi Sarah,\n\nI wanted to follow up on our team meeting this morning.\n"
            "Best regards,\nAlex Johnson"
        )

    request = AgentExecutorRequest(messages=[ChatMessage("user", text=email)], should_respond=True)
    events = await workflow.run(request)
    outputs = events.get_outputs()
    if outputs:
        print(f"Workflow output: {outputs[0]}")
    # </running>


if __name__ == "__main__":
    asyncio.run(main())
