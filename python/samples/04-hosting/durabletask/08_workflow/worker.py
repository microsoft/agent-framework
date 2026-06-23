# Copyright (c) Microsoft. All rights reserved.

"""Worker that hosts a MAF Workflow as a durable orchestration (no Azure Functions).

This sample shows how to run an agent-framework ``Workflow`` on a standalone
Durable Task worker using ``DurableAIAgentWorker.configure_workflow``. The worker
auto-registers:

- a durable entity for each agent executor,
- a durable activity for each non-agent executor, and
- the workflow orchestrator (named ``WORKFLOW_ORCHESTRATOR_NAME``).

The workflow classifies an email and conditionally routes it: spam is handled by
a non-agent executor, while legitimate email is drafted by a second agent and
"sent" by another non-agent executor.

Prerequisites:
- Set ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_MODEL``.
- Sign in with Azure CLI (``az login``) for ``AzureCliCredential``.
- Start a Durable Task Scheduler (e.g. the DTS emulator on ``localhost:8080``).

Run the worker (this process), then run ``client.py`` in another process.
"""

import asyncio
import logging
import os
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutorResponse,
    Case,
    Default,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import DurableAIAgentWorker
from agent_framework.foundry import FoundryChatClient, FoundryChatOptions
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from pydantic import BaseModel, ValidationError
from typing_extensions import Never

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPAM_AGENT_NAME = "SpamDetectionAgent"
EMAIL_AGENT_NAME = "EmailAssistantAgent"

SPAM_DETECTION_INSTRUCTIONS = (
    "You are a spam detection assistant that identifies spam emails. "
    "Return JSON with fields is_spam (bool) and reason (string)."
)
EMAIL_ASSISTANT_INSTRUCTIONS = (
    "You are an email assistant that drafts professional replies to legitimate emails. "
    "Return JSON with a single field 'response' containing the drafted reply."
)


class SpamDetectionResult(BaseModel):
    """Structured output from the spam detection agent."""

    is_spam: bool
    reason: str


class EmailResponse(BaseModel):
    """Structured output from the email assistant agent."""

    response: str


class SpamHandlerExecutor(Executor):
    """Non-agent executor that finalizes spam emails."""

    @handler
    async def handle_spam_result(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
        text = agent_response.agent_response.text
        try:
            result = SpamDetectionResult.model_validate_json(text)
            reason = result.reason
        except ValidationError:
            reason = "Invalid JSON from agent"
        await ctx.yield_output(f"Email marked as spam: {reason}")


class EmailSenderExecutor(Executor):
    """Non-agent executor that 'sends' the drafted reply."""

    @handler
    async def handle_email_response(
        self, agent_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]
    ) -> None:
        text = agent_response.agent_response.text
        try:
            email = EmailResponse.model_validate_json(text)
            reply = email.response
        except ValidationError:
            reply = "Error generating response."
        await ctx.yield_output(f"Email sent: {reply}")


def is_spam_detected(message: Any) -> bool:
    """Routing condition: True when the spam agent flagged the email as spam."""
    if not isinstance(message, AgentExecutorResponse):
        return False
    try:
        return SpamDetectionResult.model_validate_json(message.agent_response.text).is_spam
    except Exception:
        return False


def _create_chat_client() -> FoundryChatClient:
    """Create an Azure AI Foundry chat client using AzureCliCredential."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AsyncAzureCliCredential(),
    )


def create_workflow() -> Workflow:
    """Build the conditional spam-detection workflow."""
    chat_client = _create_chat_client()

    spam_agent = Agent(
        client=chat_client,
        name=SPAM_AGENT_NAME,
        instructions=SPAM_DETECTION_INSTRUCTIONS,
        default_options=FoundryChatOptions[Any](response_format=SpamDetectionResult),
    )
    email_agent = Agent(
        client=chat_client,
        name=EMAIL_AGENT_NAME,
        instructions=EMAIL_ASSISTANT_INSTRUCTIONS,
        default_options=FoundryChatOptions[Any](response_format=EmailResponse),
    )

    spam_handler = SpamHandlerExecutor(id="spam_handler")
    email_sender = EmailSenderExecutor(id="email_sender")

    return (
        WorkflowBuilder(start_executor=spam_agent)
        .add_switch_case_edge_group(
            spam_agent,
            [
                Case(condition=is_spam_detected, target=spam_handler),
                Default(target=email_agent),
            ],
        )
        .add_edge(email_agent, email_sender)
        .build()
    )


def get_worker(
    taskhub: str | None = None, endpoint: str | None = None, log_handler: logging.Handler | None = None
) -> DurableTaskSchedulerWorker:
    """Create a configured DurableTaskSchedulerWorker."""
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")

    credential = None if endpoint_url == "http://localhost:8080" else AzureCliCredential()

    return DurableTaskSchedulerWorker(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler,
    )


def setup_worker(worker: DurableTaskSchedulerWorker) -> DurableAIAgentWorker:
    """Register the workflow (agents + activities + orchestrator) on the worker."""
    agent_worker = DurableAIAgentWorker(worker)

    workflow = create_workflow()
    # One call wires up: agent entities, non-agent executor activities, and the
    # workflow orchestrator (registered as WORKFLOW_ORCHESTRATOR_NAME).
    agent_worker.configure_workflow(workflow)
    logger.info("✓ Configured workflow with %d executors", len(workflow.executors))

    return agent_worker


async def main() -> None:
    """Start the worker and block until interrupted."""
    worker = get_worker()
    setup_worker(worker)

    logger.info("Worker is ready and listening for work items. Press Ctrl+C to stop.")
    try:
        worker.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker shutdown initiated")

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
