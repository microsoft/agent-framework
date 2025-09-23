# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from typing_extensions import Never

from agent_framework import (  # Core chat primitives used to build requests
    AgentExecutor,  # Wraps an LLM agent that can be invoked inside a workflow
    AgentExecutorRequest,  # Input message bundle for an AgentExecutor
    AgentExecutorResponse,  # Output from an AgentExecutor
    ChatMessage,
    Role,
    WorkflowBuilder,  # Fluent builder for wiring executors and edges
    WorkflowContext,  # Per-run context and event bus
    executor,  # Decorator to declare a Python function as a workflow executor
)
from agent_framework.azure import AzureChatClient  # Thin client wrapper for Azure OpenAI chat models
from azure.identity import AzureCliCredential  # Uses your az CLI login for credentials
from pydantic import BaseModel  # Structured outputs for safer parsing

"""
Sample: Conditional routing with structured outputs

What this sample is:
- A minimal decision workflow that classifies an inbound email as spam or not spam, then routes to the
appropriate handler.

Purpose:
- Show how to attach boolean edge conditions that inspect an AgentExecutorResponse.
- Demonstrate using Pydantic models as response_format so the agent returns JSON we can validate and parse.
- Illustrate how to transform one agent's structured result into a new AgentExecutorRequest for a downstream agent.

Prerequisites:
- You understand the basics of WorkflowBuilder, executors, and events in this framework.
- You know the concept of edge conditions and how they gate routes using a predicate function.
- Azure OpenAI access is configured for AzureChatClient. You should be logged in with Azure CLI (AzureCliCredential)
and have the Azure OpenAI environment variables set as documented in the getting started chat client README.
- The sample email resource file exists at workflow/resources/email.txt.

High level flow:
1) spam_detection_agent reads an email and returns DetectionResult.
2) If not spam, we transform the detection output into a user message for email_assistant_agent, then finish by
yielding the drafted reply as workflow output.
3) If spam, we short circuit to a spam handler that yields a spam notice as workflow output.

Output:
- The final workflow output is printed to stdout, either with a drafted reply or a spam notice.

Notes:
- Conditions read the agent response text and validate it into DetectionResult for robust routing.
- Executors are small and single purpose to keep control flow easy to follow.
- The workflow completes when it becomes idle, not via explicit completion events.
"""


class DetectionResult(BaseModel):
    """Represents the result of spam detection."""

    # is_spam drives the routing decision taken by edge conditions
    is_spam: bool
    # Human readable rationale from the detector
    reason: str
    # The agent must include the original email so downstream agents can operate without reloading content
    email_content: str


class EmailResponse(BaseModel):
    """Represents the response from the email assistant."""

    # The drafted reply that a user could copy or send
    response: str


def get_condition(expected_result: bool):
    """Create a condition callable that routes based on DetectionResult.is_spam."""

    # The returned function will be used as an edge predicate.
    # It receives whatever the upstream executor produced.
    def condition(message: Any) -> bool:
        # Defensive guard. If a non AgentExecutorResponse appears, let the edge pass to avoid dead ends.
        if not isinstance(message, AgentExecutorResponse):
            return True

        try:
            # Prefer parsing a structured DetectionResult from the agent JSON text.
            # Using model_validate_json ensures type safety and raises if the shape is wrong.
            detection = DetectionResult.model_validate_json(message.agent_run_response.text)
            # Route only when the spam flag matches the expected path.
            return detection.is_spam == expected_result
        except Exception:
            # Fail closed on parse errors so we do not accidentally route to the wrong path.
            # Returning False prevents this edge from activating.
            return False

    return condition


@executor(id="send_email")
async def handle_email_response(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    # Downstream of the email assistant. Parse a validated EmailResponse and yield the workflow output.
    email_response = EmailResponse.model_validate_json(response.agent_run_response.text)
    await ctx.yield_output(f"Email sent:\n{email_response.response}")


@executor(id="handle_spam")
async def handle_spam_classifier_response(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    # Spam path. Confirm the DetectionResult and yield the workflow output. Guard against accidental non spam input.
    detection = DetectionResult.model_validate_json(response.agent_run_response.text)
    if detection.is_spam:
        await ctx.yield_output(f"Email marked as spam: {detection.reason}")
    else:
        # This indicates the routing predicate and executor contract are out of sync.
        raise RuntimeError("This executor should only handle spam messages.")


@executor(id="to_email_assistant_request")
async def to_email_assistant_request(
    response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
) -> None:
    """Transform detection result into an AgentExecutorRequest for the email assistant.

    Extracts DetectionResult.email_content and forwards it as a user message.
    """
    # Bridge executor. Converts a structured DetectionResult into a ChatMessage and forwards it as a new request.
    detection = DetectionResult.model_validate_json(response.agent_run_response.text)
    user_msg = ChatMessage(Role.USER, text=detection.email_content)
    await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def main() -> None:
    # Create agents
    # AzureCliCredential uses your current az login. This avoids embedding secrets in code.
    chat_client = AzureChatClient(credential=AzureCliCredential())

    # Agent 1. Classifies spam and returns a DetectionResult object.
    # response_format enforces that the LLM returns parsable JSON for the Pydantic model.
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

    # Agent 2. Drafts a professional reply. Also uses structured JSON output for reliability.
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

    # Build the workflow graph.
    # Start at the spam detector.
    # If not spam, hop to a transformer that creates a new AgentExecutorRequest,
    # then call the email assistant, then finalize.
    # If spam, go directly to the spam handler and finalize.
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
    # This keeps the sample deterministic since the model sees the same email every run.
    email_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "resources", "email.txt")

    with open(email_path) as email_file:  # noqa: ASYNC230
        email = email_file.read()

    # Execute the workflow. Since the start is an AgentExecutor, pass an AgentExecutorRequest.
    # The workflow completes when it becomes idle (no more work to do).
    request = AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=email)], should_respond=True)
    events = await workflow.run(request)
    outputs = events.get_outputs()
    if outputs:
        print(f"Workflow output: {outputs[0]}")

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

Workflow output: Email sent:
    Hi Alex,

    Thank you for the follow-up and for summarizing the action items from this morning's meeting. The points you listed accurately reflect our discussion, and I don't have any additional items to add at this time.

    I will update the project timeline by Friday, begin scheduling the client presentation for next week, and start reviewing the Q4 budget allocation. If any questions or issues arise, I'll reach out.

    Thank you again for outlining the next steps.

    Best regards,
    Sarah
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
