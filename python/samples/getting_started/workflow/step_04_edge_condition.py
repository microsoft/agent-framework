# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    executor,
)
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
This sample demonstrates conditional routing using edge conditions to create decision-based workflows.

Workflow:
1) A Spam Detection Agent analyzes an email and returns a structured DetectionResult.
2) If not spam -> route to Email Assistant Agent -> Send Email Executor.
3) If spam -> route to Handle Spam Executor.

Notes:
- Uses structured output models (Pydantic) for both agents to mirror the .NET JSON schema approach.
- Conditions operate on AgentExecutorResponse, extracting structured results when available.
"""


class DetectionResult(BaseModel):
    """Represents the result of spam detection."""

    is_spam: bool
    reason: str
    # The agent must include the email content in the detection result for downstream use.
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
            # Prefer parsing the structured value if available
            detection = DetectionResult.model_validate_json(message.agent_run_response.text)
            return detection.is_spam == expected_result
        except Exception:
            # Fail closed if parsing fails
            return False

    return condition


@executor(id="send_email")
async def handle_email_response(response: AgentExecutorResponse, ctx: WorkflowContext[None]) -> None:
    # Parse the JSON response directly to EmailResponse
    email_response = EmailResponse.model_validate_json(response.agent_run_response.text)
    await ctx.add_event(WorkflowCompletedEvent(f"Email sent:\n{email_response.response}"))


@executor(id="handle_spam")
async def handle_spam_classifier_response(response: AgentExecutorResponse, ctx: WorkflowContext[None]) -> None:
    # Parse the JSON response directly to DetectionResult
    detection = DetectionResult.model_validate_json(response.agent_run_response.text)
    if detection.is_spam:
        await ctx.add_event(WorkflowCompletedEvent(f"Email marked as spam: {detection.reason}"))
    else:
        raise RuntimeError("This executor should only handle spam messages.")


@executor(id="to_email_assistant_request")
async def to_email_assistant_request(
    response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
) -> None:
    """Transform detection result into an AgentExecutorRequest for the email assistant.

    Extracts DetectionResult.email_content and forwards it as a user message.
    """
    detection = DetectionResult.model_validate_json(response.agent_run_response.text)
    user_msg = ChatMessage(ChatRole.USER, text=detection.email_content)
    await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def main() -> None:
    # Create agents
    chat_client = AzureChatClient(credential=AzureCliCredential())

    spam_detection_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are a spam detection assistant that identifies spam emails. "
                "Always return JSON with fields is_spam (bool), reason (string), and email_content (string). "
                "Include the original email content in email_content."
            ),
            response_format=DetectionResult,
        ),
        id="spam_detection_agent",
    )

    email_assistant_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email assistant that helps users draft professional responses to emails. "
                "Your input may be a JSON object that includes 'email_content'; base your reply on that content. "
                "Return JSON with a single field 'response' containing the drafted reply."
            ),
            response_format=EmailResponse,
        ),
        id="email_assistant_agent",
    )

    # Build the workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_detection_agent)
        # Not spam path: transform response -> request for assistant -> assistant -> send email
        .add_edge(spam_detection_agent, to_email_assistant_request, condition=get_condition(False))
        .add_edge(to_email_assistant_request, email_assistant_agent)
        .add_edge(email_assistant_agent, handle_email_response)
        # Spam path: send to spam handler
        .add_edge(spam_detection_agent, handle_spam_classifier_response, condition=get_condition(True))
        .build()
    )

    # Read Email content from the sample resource file.
    email_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "workflow", "resources", "email.txt"
    )

    with open(email_path) as email_file:  # noqa: ASYNC230
        email = email_file.read()

    # Execute the workflow. Since the start is an AgentExecutor, pass an AgentExecutorRequest.
    request = AgentExecutorRequest(messages=[ChatMessage(ChatRole.USER, text=email)], should_respond=True)
    async for event in workflow.run_streaming(request):
        if isinstance(event, WorkflowCompletedEvent):
            print(f"{event}")

    """
    Sample Output:

    Processing email:
    Subject: Team Meeting Follow-up - Action Items

    Hi Sarah,

    I wanted to follow up on our team meeting this morning and share the action items we discussed:

    1. Update the project timeline by Friday
    2. Schedule client presentation for next week
    3. Review the budget allocation for Q4

    Please let me know if you have any questions or if I missed anything from our discussion.

    Best regards,
    Alex Johnson
    Project Manager
    Tech Solutions Inc.
    alex.johnson@techsolutions.com
    (555) 123-4567
    ----------------------------------------

    WorkflowCompletedEvent(data=Email sent:
    Hi Alex,

    Thank you for the follow-up and for summarizing the action items from this morning's meeting. The points you listed accurately reflect our discussion, and I don't have any additional items to add at this time.

    I will update the project timeline by Friday, begin scheduling the client presentation for next week, and start reviewing the Q4 budget allocation. If any questions or issues arise, I'll reach out.

    Thank you again for outlining the next steps.

    Best regards,
    Sarah)
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
