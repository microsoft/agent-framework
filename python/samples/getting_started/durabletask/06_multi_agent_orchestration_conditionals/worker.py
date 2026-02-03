"""Worker process for hosting spam detection and email assistant agents with conditional orchestration.

This worker registers two domain-specific agents (spam detector and email assistant) and an
orchestration function that routes execution based on spam detection results. Activity functions
handle side effects (spam handling and email sending).

Prerequisites:
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Start a Durable Task Scheduler (e.g., using Docker)
"""

import asyncio
from collections.abc import Generator
import logging
import os
from typing import Any, cast

from agent_framework import AgentResponse, ChatAgent
from agent_framework.azure import AzureOpenAIChatClient, DurableAIAgentOrchestrationContext, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.task import ActivityContext, OrchestrationContext, Task
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from pydantic import BaseModel, ValidationError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent names
SPAM_AGENT_NAME = "SpamDetectionAgent"
EMAIL_AGENT_NAME = "EmailAssistantAgent"


class SpamDetectionResult(BaseModel):
    """Result from spam detection agent."""
    is_spam: bool
    reason: str


class EmailResponse(BaseModel):
    """Result from email assistant agent."""
    response: str


class EmailPayload(BaseModel):
    """Input payload for the orchestration."""
    email_id: str
    email_content: str


def create_spam_agent() -> "ChatAgent":
    """Create the Spam Detection agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured Spam Detection agent
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name=SPAM_AGENT_NAME,
        instructions="You are a spam detection assistant that identifies spam emails.",
    )


def create_email_agent() -> "ChatAgent":
    """Create the Email Assistant agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured Email Assistant agent
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name=EMAIL_AGENT_NAME,
        instructions="You are an email assistant that helps users draft responses to emails with professionalism.",
    )


def handle_spam_email(context: ActivityContext, reason: str) -> str:
    """Activity function to handle spam emails.
    
    Args:
        context: The activity context
        reason: The reason why the email was marked as spam
        
    Returns:
        str: Confirmation message
    """
    logger.debug(f"[Activity] Handling spam email: {reason}")
    return f"Email marked as spam: {reason}"


def send_email(context: ActivityContext, message: str) -> str:
    """Activity function to send emails.
    
    Args:
        context: The activity context
        message: The email message to send
        
    Returns:
        str: Confirmation message
    """
    logger.debug(f"[Activity] Sending email: {message[:50]}...")
    return f"Email sent: {message}"


def spam_detection_orchestration(context: OrchestrationContext, payload_raw: Any) -> Generator[Task[Any], Any, str]:
    """Orchestration that detects spam and conditionally drafts email responses.
    
    This orchestration:
    1. Validates the input payload
    2. Runs the spam detection agent
    3. If spam: calls handle_spam_email activity
    4. If legitimate: runs email assistant agent and calls send_email activity
    
    Args:
        context: The orchestration context
        payload_raw: The input payload dictionary
        
    Returns:
        str: Result message from activity functions
    """
    logger.debug("[Orchestration] Starting spam detection orchestration")
    
    # Validate input
    if not isinstance(payload_raw, dict):
        raise ValueError("Email data is required")
    
    try:
        payload = EmailPayload.model_validate(payload_raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid email payload: {exc}") from exc
    
    logger.debug(f"[Orchestration] Processing email ID: {payload.email_id}")
    
    # Wrap the orchestration context to access agents
    agent_context = DurableAIAgentOrchestrationContext(context)
    
    # Get spam detection agent
    spam_agent = agent_context.get_agent(SPAM_AGENT_NAME)
    
    # Run spam detection
    spam_prompt = (
        "Analyze this email for spam content and return a JSON response with 'is_spam' (boolean) "
        "and 'reason' (string) fields:\n"
        f"Email ID: {payload.email_id}\n"
        f"Content: {payload.email_content}"
    )
    
    logger.info("[Orchestration] Running spam detection agent: %s", spam_prompt)
    spam_result_task = spam_agent.run(
        messages=spam_prompt,
        options={"response_format": SpamDetectionResult},
    )
    
    spam_result_raw: AgentResponse = yield spam_result_task
    spam_result = cast(SpamDetectionResult, spam_result_raw.value)
    
    logger.info("[Orchestration] Spam detection result: is_spam=%s", spam_result.is_spam)
    
    # Branch based on spam detection result
    if spam_result.is_spam:
        logger.debug("[Orchestration] Email is spam, handling...")
        result_task: Task[str] = context.call_activity("handle_spam_email", input=spam_result.reason)
        result: str = yield result_task
        return result
    
    # Email is legitimate - draft a response
    logger.debug("[Orchestration] Email is legitimate, drafting response...")
    
    email_agent = agent_context.get_agent(EMAIL_AGENT_NAME)
    
    email_prompt = (
        "Draft a professional response to this email. Return a JSON response with a 'response' field "
        "containing the reply:\n\n"
        f"Email ID: {payload.email_id}\n"
        f"Content: {payload.email_content}"
    )
    
    logger.info("[Orchestration] Running email assistant agent: %s", email_prompt)
    email_result_task = email_agent.run(
        messages=email_prompt,
        options={"response_format": EmailResponse},
    )
    
    email_result_raw: AgentResponse = yield email_result_task
    email_result = cast(EmailResponse, email_result_raw.value)
    
    logger.debug("[Orchestration] Email response drafted, sending...")
    result_task: Task[str] = context.call_activity("send_email", input=email_result.response)
    result: str = yield result_task

    logger.info("Sent Email: %s", result)
    
    return result


def get_worker(
    taskhub: str | None = None,
    endpoint: str | None = None,
    log_handler: logging.Handler | None = None
) -> DurableTaskSchedulerWorker:
    """Create a configured DurableTaskSchedulerWorker.
    
    Args:
        taskhub: Task hub name (defaults to TASKHUB env var or "default")
        endpoint: Scheduler endpoint (defaults to ENDPOINT env var or "http://localhost:8080")
        log_handler: Optional logging handler for worker logging
        
    Returns:
        Configured DurableTaskSchedulerWorker instance
    """
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")
    
    logger.debug(f"Using taskhub: {taskhub_name}")
    logger.debug(f"Using endpoint: {endpoint_url}")
    
    credential = None if endpoint_url == "http://localhost:8080" else DefaultAzureCredential()
    
    return DurableTaskSchedulerWorker(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler
    )


def setup_worker(worker: DurableTaskSchedulerWorker) -> DurableAIAgentWorker:
    """Set up the worker with agents, orchestrations, and activities registered.
    
    Args:
        worker: The DurableTaskSchedulerWorker instance
        
    Returns:
        DurableAIAgentWorker with agents, orchestrations, and activities registered
    """
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker)
    
    # Create and register both agents
    logger.debug("Creating and registering agents...")
    spam_agent = create_spam_agent()
    email_agent = create_email_agent()
    
    agent_worker.add_agent(spam_agent)
    agent_worker.add_agent(email_agent)
    
    logger.debug(f"✓ Registered agents: {spam_agent.name}, {email_agent.name}")
    
    # Register activity functions
    logger.debug("Registering activity functions...")
    worker.add_activity(handle_spam_email)  # type: ignore[arg-type]
    worker.add_activity(send_email)  # type: ignore[arg-type]
    logger.debug(f"✓ Registered activity: handle_spam_email")
    logger.debug(f"✓ Registered activity: send_email")
    
    # Register the orchestration function
    logger.debug("Registering orchestration function...")
    worker.add_orchestrator(spam_detection_orchestration)   # type: ignore[arg-type]
    logger.debug(f"✓ Registered orchestration: {spam_detection_orchestration.__name__}")
    
    return agent_worker


async def main():
    """Main entry point for the worker process."""
    logger.debug("Starting Durable Task Spam Detection Worker with Orchestration...")
    
    # Create a worker using the helper function
    worker = get_worker()
    
    # Setup worker with agents, orchestrations, and activities
    setup_worker(worker)
    
    logger.debug("Worker is ready and listening for requests...")
    logger.debug("Press Ctrl+C to stop.")
    
    try:
        # Start the worker (this blocks until stopped)
        worker.start()
        
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.debug("Worker shutdown initiated")
    
    logger.debug("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
