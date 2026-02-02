# Copyright (c) Microsoft. All rights reserved.
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
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Use DefaultAzureCredential and run az login before executing the sample.
- Familiarity with WorkflowBuilder, executors, conditional edges, and streaming runs.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Role,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel, ValidationError
from typing_extensions import Never

from agent_framework_azurefunctions import AgentFunctionApp

logger = logging.getLogger(__name__)

# Environment variable names
AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"

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
    try:
        parsed = DetectionResultAgent.model_validate_json(response.agent_response.text)
    except ValidationError:
        # Fallback for empty or invalid response (e.g. due to content filtering)
        parsed = DetectionResultAgent(is_spam=True, reason="Agent execution failed or yielded invalid JSON.")

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
    parsed = EmailResponse.model_validate_json(response.agent_response.text)
    await ctx.yield_output(f"Email sent: {parsed.response}")


@executor(id="handle_spam")
async def handle_spam(detection: DetectionResult, ctx: WorkflowContext[Never, str]) -> None:
    """Yield output describing why the email was marked as spam."""
    if detection.is_spam:
        await ctx.yield_output(f"Email marked as spam: {detection.reason}")
    else:
        raise RuntimeError("This executor should only handle spam messages.")


# ============================================================================
# Workflow Creation
# ============================================================================


def _build_client_kwargs() -> dict[str, Any]:
    """Build Azure OpenAI client configuration from environment variables."""
    endpoint = os.getenv(AZURE_OPENAI_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(f"{AZURE_OPENAI_ENDPOINT_ENV} environment variable is required.")

    deployment = os.getenv(AZURE_OPENAI_DEPLOYMENT_ENV)
    if not deployment:
        raise RuntimeError(f"{AZURE_OPENAI_DEPLOYMENT_ENV} environment variable is required.")

    client_kwargs: dict[str, Any] = {
        "endpoint": endpoint,
        "deployment_name": deployment,
    }

    api_key = os.getenv(AZURE_OPENAI_API_KEY_ENV)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = AzureCliCredential()

    return client_kwargs


def _create_workflow() -> Workflow:
    """Create the email classification workflow with conditional routing."""
    client_kwargs = _build_client_kwargs()
    chat_client = AzureOpenAIChatClient(**client_kwargs)

    spam_detection_agent = chat_client.as_agent(
        instructions=(
            "You are a spam detection assistant that identifies spam emails. "
            "Always return JSON with fields is_spam (bool) and reason (string)."
        ),
        default_options={"response_format": DetectionResultAgent},
        name="spam_detection_agent",
    )

    email_assistant_agent = chat_client.as_agent(
        instructions=(
            "You are an email assistant that helps users draft responses to emails with professionalism. "
            "Return JSON with a single field 'response' containing the drafted reply."
        ),
        default_options={"response_format": EmailResponse},
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

    return workflow


# ============================================================================
# Application Entry Point
# ============================================================================


def launch(durable: bool = True) -> AgentFunctionApp | None:
    """Launch the function app or DevUI.

    Args:
        durable: If True, returns AgentFunctionApp for Azure Functions.
                 If False, launches DevUI for local MAF development.
    """
    if durable:
        # Azure Functions mode with Durable Functions
        # SharedState is enabled by default, which this sample requires for storing emails
        workflow = _create_workflow()
        app = AgentFunctionApp(workflow=workflow, enable_health_check=True)
        return app
    else:
        # Pure MAF mode with DevUI for local development
        from pathlib import Path

        from agent_framework.devui import serve
        from dotenv import load_dotenv

        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)

        logger.info("Starting Workflow Shared State Sample in MAF mode")
        logger.info("Available at: http://localhost:8096")
        logger.info("\nThis workflow demonstrates:")
        logger.info("- Shared state to decouple large payloads from messages")
        logger.info("- Structured agent outputs with Pydantic models")
        logger.info("- Conditional routing based on detection results")
        logger.info("\nFlow: store_email -> spam_detection -> branch (spam/not spam)")

        workflow = _create_workflow()
        serve(entities=[workflow], port=8096, auto_open=True)

        return None


# Default: Azure Functions mode
# Run with `python function_app.py --maf` for pure MAF mode with DevUI
app = launch(durable=True)


if __name__ == "__main__":
    import sys

    if "--maf" in sys.argv:
        # Run in pure MAF mode with DevUI
        launch(durable=False)
    else:
        print("Usage: python function_app.py --maf")
        print("  --maf    Run in pure MAF mode with DevUI (http://localhost:8096)")
        print("\nFor Azure Functions mode, use: func start")
