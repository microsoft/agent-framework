"""Worker process for hosting a writer agent with human-in-the-loop orchestration.

This worker registers a WriterAgent and an orchestration function that implements
a human-in-the-loop review workflow. The orchestration pauses for external events
(human approval/rejection) with timeout handling, and iterates based on feedback.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Start a Durable Task Scheduler (e.g., using Docker)
"""

import asyncio
from collections.abc import Generator
from datetime import timedelta
import logging
import os
from typing import Any, cast

from agent_framework import AgentResponse, ChatAgent
from agent_framework.azure import AzureOpenAIChatClient, DurableAIAgentOrchestrationContext, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.task import ActivityContext, OrchestrationContext, Task, when_any  # type: ignore
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from pydantic import BaseModel, ValidationError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
WRITER_AGENT_NAME = "WriterAgent"
HUMAN_APPROVAL_EVENT = "HumanApproval"


class ContentGenerationInput(BaseModel):
    """Input for content generation orchestration."""
    topic: str
    max_review_attempts: int = 3
    approval_timeout_seconds: float = 300  # 5 minutes for demo (72 hours in production)


class GeneratedContent(BaseModel):
    """Structured output from writer agent."""
    title: str
    content: str


class HumanApproval(BaseModel):
    """Human approval decision."""
    approved: bool
    feedback: str = ""


def create_writer_agent() -> "ChatAgent":
    """Create the Writer agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured Writer agent
    """
    instructions = (
        "You are a professional content writer who creates high-quality articles on various topics. "
        "You write engaging, informative, and well-structured content that follows best practices for readability and accuracy. "
        "Return your response as JSON with 'title' and 'content' fields."
        "Limit response to 300 words or less."
    )
    
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name=WRITER_AGENT_NAME,
        instructions=instructions,
    )


def notify_user_for_approval(context: ActivityContext, content: dict[str, str]) -> str:
    """Activity function to notify user for approval.
    
    Args:
        context: The activity context
        content: The generated content dictionary
    """
    model = GeneratedContent.model_validate(content)
    logger.info("NOTIFICATION: Please review the following content for approval:")
    logger.info(f"Title: {model.title or '(untitled)'}")
    logger.info(f"Content: {model.content}")
    logger.info("Use the client to send approval or rejection.")
    return "Notification sent to user for approval."

def publish_content(context: ActivityContext, content: dict[str, str]) -> str:
    """Activity function to publish approved content.
    
    Args:
        context: The activity context
        content: The generated content dictionary
    """
    model = GeneratedContent.model_validate(content)
    logger.info("PUBLISHING: Content has been published successfully:")
    logger.info(f"Title: {model.title or '(untitled)'}")
    logger.info(f"Content: {model.content}")
    return "Published content successfully."


def content_generation_hitl_orchestration(
    context: OrchestrationContext, 
    payload_raw: Any
) -> Generator[Task[Any], Any, dict[str, str]]:
    """Human-in-the-loop orchestration for content generation with approval workflow.
    
    This orchestration:
    1. Generates initial content using WriterAgent
    2. Loops up to max_review_attempts times:
       a. Notifies user for approval
       b. Waits for approval event or timeout
       c. If approved: publishes and returns
       d. If rejected: incorporates feedback and regenerates
       e. If timeout: raises TimeoutError
    3. Raises RuntimeError if max attempts exhausted
    
    Args:
        context: The orchestration context
        payload_raw: The input payload
        
    Returns:
        dict: Result with published content
        
    Raises:
        ValueError: If input is invalid or agent returns no content
        TimeoutError: If human approval times out
        RuntimeError: If max review attempts exhausted
    """
    logger.debug("[Orchestration] Starting HITL content generation orchestration")
    
    # Validate input
    if not isinstance(payload_raw, dict):
        raise ValueError("Content generation input is required")
    
    try:
        payload = ContentGenerationInput.model_validate(payload_raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid content generation input: {exc}") from exc
    
    logger.debug(f"[Orchestration] Topic: {payload.topic}")
    logger.debug(f"[Orchestration] Max attempts: {payload.max_review_attempts}")
    logger.debug(f"[Orchestration] Approval timeout: {payload.approval_timeout_seconds}s")
    
    # Wrap the orchestration context to access agents
    agent_context = DurableAIAgentOrchestrationContext(context)
    
    # Get the writer agent
    writer = agent_context.get_agent(WRITER_AGENT_NAME)
    writer_thread = writer.get_new_thread()

    logger.info(f"ThreadID: {writer_thread.session_id}")
    
    # Generate initial content
    logger.info("[Orchestration] Generating initial content...")
    
    initial_response: AgentResponse = yield writer.run(
        messages=f"Write a short article about '{payload.topic}'.",
        thread=writer_thread,
            options={"response_format": GeneratedContent},
    )
    content = cast(GeneratedContent, initial_response.value)
    
    if not isinstance(content, GeneratedContent):
        raise ValueError("Agent returned no content after extraction.")
    
    logger.debug(f"[Orchestration] Initial content generated: {content.title}")
    
    # Review loop
    attempt = 0
    while attempt < payload.max_review_attempts:
        attempt += 1
        logger.debug(f"[Orchestration] Review iteration #{attempt}/{payload.max_review_attempts}")

        context.set_custom_status(f"Requesting human feedback (Attempt {attempt}, timeout {payload.approval_timeout_seconds}s)")
        
        # Notify user for approval
        yield context.call_activity(
            "notify_user_for_approval", 
            input=content.model_dump()
        )

        logger.debug("[Orchestration] Waiting for human approval or timeout...")
        
        # Wait for approval event or timeout
        approval_task: Task[Any] = context.wait_for_external_event(HUMAN_APPROVAL_EVENT)  # type: ignore
        timeout_task: Task[Any] = context.create_timer(  # type: ignore
            context.current_utc_datetime + timedelta(seconds=payload.approval_timeout_seconds)
        )
        
        # Race between approval and timeout
        winner_task = yield when_any([approval_task, timeout_task])  # type: ignore
        
        if winner_task == approval_task:
            # Approval received before timeout
            logger.debug("[Orchestration] Received human approval event")

            context.set_custom_status("Content reviewed by human reviewer.")
            
            # Parse approval
            approval_data: Any = approval_task.get_result() # type: ignore
            logger.debug(f"[Orchestration] Approval data: {approval_data}")
            
            # Handle different formats of approval_data
            if isinstance(approval_data, dict):
                approval = HumanApproval.model_validate(approval_data)
            elif isinstance(approval_data, str):
                # Try to parse as boolean-like string
                lower_data = approval_data.lower().strip()
                if lower_data in {"true", "yes", "approved", "y", "1"}:
                    approval = HumanApproval(approved=True, feedback="")
                elif lower_data in {"false", "no", "rejected", "n", "0"}:
                    approval = HumanApproval(approved=False, feedback="")
                else:
                    approval = HumanApproval(approved=False, feedback=approval_data)
            else:
                approval = HumanApproval(approved=False, feedback=str(approval_data))   # type: ignore
            
            if approval.approved:
                # Content approved - publish and return
                logger.debug("[Orchestration] Content approved! Publishing...")
                context.set_custom_status("Content approved by human reviewer. Publishing...")
                publish_task: Task[Any] = context.call_activity(
                    "publish_content",
                    input=content.model_dump()
                )
                yield publish_task
                
                logger.debug("[Orchestration] Content published successfully")
                return {"content": content.content, "title": content.title}
            
            # Content rejected - incorporate feedback and regenerate
            logger.debug(f"[Orchestration] Content rejected. Feedback: {approval.feedback}")
            
            # Check if we've exhausted attempts
            if attempt >= payload.max_review_attempts:
                context.set_custom_status("Max review attempts exhausted.")
                # Max attempts exhausted
                logger.error(f"[Orchestration] Max attempts ({payload.max_review_attempts}) exhausted")
                break
            
            context.set_custom_status(f"Content rejected by human reviewer. Regenerating...")
            
            rewrite_prompt = (
                "The content was rejected by a human reviewer. Please rewrite the article incorporating their feedback.\n\n"
                f"Human Feedback: {approval.feedback or 'No specific feedback provided.'}"
            )
            
            logger.debug("[Orchestration] Regenerating content with feedback...")

            logger.warning(f"Regenerating with ThreadID: {writer_thread.session_id}")
            
            rewrite_response: AgentResponse = yield writer.run(
                messages=rewrite_prompt,
                thread=writer_thread,
                    options={"response_format": GeneratedContent},
            )
            rewritten_content = cast(GeneratedContent, rewrite_response.value)
            
            if not isinstance(rewritten_content, GeneratedContent):
                raise ValueError("Agent returned no content after rewrite.")
            
            content = rewritten_content
            logger.debug(f"[Orchestration] Content regenerated: {content.title}")
            
        else:
            # Timeout occurred
            logger.error(f"[Orchestration] Approval timeout after {payload.approval_timeout_seconds}s")
            
            raise TimeoutError(
                f"Human approval timed out after {payload.approval_timeout_seconds} second(s)."
            )
    
    # If we exit the loop without returning, max attempts were exhausted
    context.set_custom_status("Max review attempts exhausted.")
    raise RuntimeError(
        f"Content could not be approved after {payload.max_review_attempts} iteration(s)."
    )


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
    
    # Create and register the writer agent
    logger.debug("Creating and registering Writer agent...")
    writer_agent = create_writer_agent()
    agent_worker.add_agent(writer_agent)
    
    logger.debug(f"✓ Registered agent: {writer_agent.name}")
    
    # Register activity functions
    logger.debug("Registering activity functions...")
    worker.add_activity(notify_user_for_approval)  # type: ignore
    worker.add_activity(publish_content)  # type: ignore
    logger.debug(f"✓ Registered activity: notify_user_for_approval")
    logger.debug(f"✓ Registered activity: publish_content")
    
    # Register the orchestration function
    logger.debug("Registering orchestration function...")
    worker.add_orchestrator(content_generation_hitl_orchestration) # type: ignore
    logger.debug(f"✓ Registered orchestration: {content_generation_hitl_orchestration.__name__}")
    
    return agent_worker


async def main():
    """Main entry point for the worker process."""
    logger.debug("Starting Durable Task HITL Content Generation Worker...")
    
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
