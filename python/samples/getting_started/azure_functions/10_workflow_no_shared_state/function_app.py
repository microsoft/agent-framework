# Copyright (c) Microsoft. All rights reserved.
"""Workflow Execution within Durable Functions Orchestrator.

This sample demonstrates running agent framework WorkflowBuilder workflows inside
a Durable Functions orchestrator by manually traversing the workflow graph and
delegating execution to Durable Entities (for agents) and Activities (for other logic).

Key architectural points:
- AgentFunctionApp registers agents as DurableAIAgents.
- WorkflowBuilder uses `DurableAgentDefinition` (a placeholder) to define the graph.
- The orchestrator (`workflow_orchestration`) iterates through the workflow graph.
- When an agent node is encountered, it calls the corresponding `DurableAIAgent` entity.
- When a standard executor node is encountered, it calls an Activity (`ExecuteExecutor`).

This approach allows using the rich structure of `WorkflowBuilder` while leveraging
the statefulness and durability of `DurableAIAgent`s.
"""

import logging
import os
from typing import Any, Dict

from pathlib import Path
from agent_framework import (
    AgentExecutorResponse,
    Case,
    Default,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel, ValidationError
from agent_framework_azurefunctions import AgentFunctionApp
from typing_extensions import Never

logger = logging.getLogger(__name__)

AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"
SPAM_AGENT_NAME = "SpamDetectionAgent"
EMAIL_AGENT_NAME = "EmailAssistantAgent"

SPAM_DETECTION_INSTRUCTIONS = (
    "You are a spam detection assistant that identifies spam emails.\n\n"
    "Analyze the email content for spam indicators including:\n"
    "1. Suspicious language (urgent, limited time, act now, free money, etc.)\n"
    "2. Suspicious links or requests for personal information\n"
    "3. Poor grammar or spelling\n"
    "4. Requests for money or financial information\n"
    "5. Impersonation attempts\n\n"
    "Return a JSON response with:\n"
    "- is_spam: boolean indicating if it's spam\n"
    "- confidence: float between 0.0 and 1.0\n"
    "- reason: detailed explanation of your classification"
)

EMAIL_ASSISTANT_INSTRUCTIONS = (
    "You are an email assistant that helps users draft responses to legitimate emails.\n\n"
    "When you receive an email that has been verified as legitimate:\n"
    "1. Draft a professional and appropriate response\n"
    "2. Match the tone and formality of the original email\n"
    "3. Be helpful and courteous\n"
    "4. Keep the response concise but complete\n\n"
    "Return a JSON response with:\n"
    "- response: the drafted email response"
)


class SpamDetectionResult(BaseModel):
    is_spam: bool
    confidence: float
    reason: str


class EmailResponse(BaseModel):
    response: str


class EmailPayload(BaseModel):
    email_id: str
    email_content: str


def _build_client_kwargs() -> dict[str, Any]:
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


# Executors for non-AI activities (defined at module level)
class SpamHandlerExecutor(Executor):
    """Executor that handles spam emails (non-AI activity)."""

    @handler
    async def handle_spam_result(
        self,
        agent_response: AgentExecutorResponse,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Mark email as spam and log the reason."""
        text = agent_response.agent_response.text
        try:
            spam_result = SpamDetectionResult.model_validate_json(text)
        except ValidationError:
            spam_result = SpamDetectionResult(is_spam=True, reason="Invalid JSON from agent")
        
        message = f"Email marked as spam: {spam_result.reason}"
        await ctx.yield_output(message)


class EmailSenderExecutor(Executor):
    """Executor that sends email responses (non-AI activity)."""

    @handler
    async def handle_email_response(
        self,
        agent_response: AgentExecutorResponse,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Send the drafted email response."""
        text = agent_response.agent_response.text
        try:
            email_response = EmailResponse.model_validate_json(text)
        except ValidationError:
            email_response = EmailResponse(response="Error generating response.")
            
        message = f"Email sent: {email_response.response}"
        await ctx.yield_output(message)


# Condition function for routing
def is_spam_detected(message: Any) -> bool:
    """Check if spam was detected in the email."""
    if not isinstance(message, AgentExecutorResponse):
        return False
    try:
        result = SpamDetectionResult.model_validate_json(message.agent_response.text)
        return result.is_spam
    except Exception:
        return False


def _create_workflow() -> Workflow:
    """Create the workflow definition."""
    client_kwargs = _build_client_kwargs()
    chat_client = AzureOpenAIChatClient(**client_kwargs)

    spam_agent = chat_client.as_agent(
        name=SPAM_AGENT_NAME,
        instructions=SPAM_DETECTION_INSTRUCTIONS,
        default_options={"response_format": SpamDetectionResult},
    )

    email_agent = chat_client.as_agent(
        name=EMAIL_AGENT_NAME,
        instructions=EMAIL_ASSISTANT_INSTRUCTIONS,
        default_options={"response_format": EmailResponse},
    )

    # Executors
    spam_handler = SpamHandlerExecutor(id="spam_handler")
    email_sender = EmailSenderExecutor(id="email_sender")

    # Build workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(spam_agent)
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
    return workflow


def launch(durable: bool = True) -> AgentFunctionApp | None:
    workflow: Workflow | None = None

    if durable:
        # Initialize app
        workflow = _create_workflow()
        

        app = AgentFunctionApp(workflow=workflow)


        return app
    else:
        # Launch the spam detection workflow in DevUI
        from agent_framework.devui import serve
        from dotenv import load_dotenv

        # Load environment variables from .env file
        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)

        logger.info("Starting Multi-Agent Spam Detection Workflow")
        logger.info("Available at: http://localhost:8094")
        logger.info("\nThis workflow demonstrates:")
        logger.info("- Conditional routing based on spam detection")
        logger.info("- Mixing AI agents with non-AI executors (like activity functions)")
        logger.info("- Path 1 (spam): SpamDetector Agent → SpamHandler Executor")
        logger.info("- Path 2 (legitimate): SpamDetector Agent → EmailAssistant Agent → EmailSender Executor")

        workflow = _create_workflow()
        serve(entities=[workflow], port=8094, auto_open=True)

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
