"""Client application for starting a human-in-the-loop content generation orchestration.

This client connects to the Durable Task Scheduler and demonstrates the HITL pattern
by starting an orchestration, sending approval/rejection events, and monitoring progress.

Prerequisites: 
- The worker must be running with the agent, orchestration, and activities registered
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running
"""

import asyncio
import json
import logging
import os
import time

from azure.identity import DefaultAzureCredential
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
from durabletask.client import OrchestrationState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
HUMAN_APPROVAL_EVENT = "HumanApproval"


def get_client(
    taskhub: str | None = None,
    endpoint: str | None = None,
    log_handler: logging.Handler | None = None
) -> DurableTaskSchedulerClient:
    """Create a configured DurableTaskSchedulerClient.
    
    Args:
        taskhub: Task hub name (defaults to TASKHUB env var or "default")
        endpoint: Scheduler endpoint (defaults to ENDPOINT env var or "http://localhost:8080")
        log_handler: Optional logging handler for client logging
        
    Returns:
        Configured DurableTaskSchedulerClient instance
    """
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")
    
    logger.debug(f"Using taskhub: {taskhub_name}")
    logger.debug(f"Using endpoint: {endpoint_url}")
    
    credential = None if endpoint_url == "http://localhost:8080" else DefaultAzureCredential()
    
    return DurableTaskSchedulerClient(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler
    )


def _log_completion_result(
    metadata: OrchestrationState | None,
) -> None:
    """Log the orchestration completion result.
    
    Args:
        metadata: The orchestration metadata
    """
    if metadata and metadata.runtime_status.name == "COMPLETED":
        result = metadata.serialized_output
        
        logger.debug(f"Orchestration completed successfully!")
        
        if result:
            try:
                result_dict = json.loads(result)
                logger.info("Final Result: %s", json.dumps(result_dict, indent=2))
            except json.JSONDecodeError:
                logger.debug(f"Result: {result}")
        
    elif metadata:
        logger.error(f"Orchestration ended with status: {metadata.runtime_status.name}")
        if metadata.serialized_output:
            logger.error(f"Output: {metadata.serialized_output}")
    else:
        logger.error("Orchestration did not complete within the timeout period")


def _wait_and_log_completion(
    client: DurableTaskSchedulerClient,
    instance_id: str,
    timeout: int = 60
) -> None:
    """Wait for orchestration completion and log the result.
    
    Args:
        client: The DurableTaskSchedulerClient instance
        instance_id: The orchestration instance ID
        timeout: Maximum time to wait for completion in seconds
    """
    logger.debug("Waiting for orchestration to complete...")
    metadata = client.wait_for_orchestration_completion(
        instance_id=instance_id,
        timeout=timeout
    )
    
    _log_completion_result(metadata)


def send_approval(
    client: DurableTaskSchedulerClient,
    instance_id: str,
    approved: bool,
    feedback: str = ""
) -> None:
    """Send approval or rejection event to the orchestration.
    
    Args:
        client: The DurableTaskSchedulerClient instance
        instance_id: The orchestration instance ID
        approved: Whether to approve or reject
        feedback: Optional feedback message (used when rejected)
    """
    approval_data = {
        "approved": approved,
        "feedback": feedback
    }
    
    logger.debug(f"Sending {'APPROVAL' if approved else 'REJECTION'} to instance {instance_id}")
    if feedback:
        logger.debug(f"Feedback: {feedback}")
    
    # Raise the external event
    client.raise_orchestration_event(
        instance_id=instance_id,
        event_name=HUMAN_APPROVAL_EVENT,
        data=approval_data
    )
    
    logger.debug("Event sent successfully")


def wait_for_notification(
    client: DurableTaskSchedulerClient,
    instance_id: str,
    timeout_seconds: int = 10
) -> bool:
    """Wait for the orchestration to reach a notification point.
    
    Polls the orchestration status until it appears to be waiting for approval.
    
    Args:
        client: The DurableTaskSchedulerClient instance
        instance_id: The orchestration instance ID
        timeout_seconds: Maximum time to wait
        
    Returns:
        True if notification detected, False if timeout
    """
    logger.debug("Waiting for orchestration to reach notification point...")
    
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            metadata = client.get_orchestration_state(
                instance_id=instance_id,
            )
            
            if metadata:
                # Check if we're waiting for approval by examining custom status
                if metadata.serialized_custom_status:
                    try:
                        custom_status = json.loads(metadata.serialized_custom_status)
                        # Handle both string and dict custom status
                        status_str = custom_status if isinstance(custom_status, str) else str(custom_status)
                        if status_str.lower().startswith("requesting human feedback"):
                            logger.debug("Orchestration is requesting human feedback")
                            return True
                    except (json.JSONDecodeError, AttributeError):
                        # If it's not JSON, treat as plain string
                        if metadata.serialized_custom_status.lower().startswith("requesting human feedback"):
                            logger.debug("Orchestration is requesting human feedback")
                            return True
                
                # Check for terminal states
                if metadata.runtime_status.name == "COMPLETED":
                    logger.debug("Orchestration already completed")
                    return False
                elif metadata.runtime_status.name == "FAILED":
                    logger.error("Orchestration failed")
                    return False
        except Exception as e:
            logger.debug(f"Status check: {e}")
        
        time.sleep(1)
    
    logger.warning("Timeout waiting for notification")
    return False


def run_interactive_client(client: DurableTaskSchedulerClient) -> None:
    """Run an interactive client that prompts for user input and handles approval workflow.
    
    Args:
        client: The DurableTaskSchedulerClient instance
    """
    # Get user inputs
    logger.debug("Content Generation - Human-in-the-Loop")
    
    topic = input("Enter the topic for content generation: ").strip()
    if not topic:
        topic = "The benefits of cloud computing"
        logger.info(f"Using default topic: {topic}")
    
    max_attempts_str = input("Enter max review attempts (default: 3): ").strip()
    max_review_attempts = int(max_attempts_str) if max_attempts_str else 3
    
    timeout_hours_str = input("Enter approval timeout in hours (default: 5): ").strip()
    timeout_hours = float(timeout_hours_str) if timeout_hours_str else 5.0
    approval_timeout_seconds = int(timeout_hours * 3600)
    
    payload = {
        "topic": topic,
        "max_review_attempts": max_review_attempts,
        "approval_timeout_seconds": approval_timeout_seconds
    }
    
    logger.debug(f"Configuration: Topic={topic}, Max attempts={max_review_attempts}, Timeout={timeout_hours}h")
    
    # Start the orchestration
    logger.debug("Starting content generation orchestration...")
    instance_id = client.schedule_new_orchestration(    # type: ignore
        orchestrator="content_generation_hitl_orchestration",
        input=payload,
    )
    
    logger.info(f"Orchestration started with instance ID: {instance_id}")
    
    # Review loop
    attempt = 1
    while attempt <= max_review_attempts:
        logger.info(f"Review Attempt {attempt}/{max_review_attempts}")
        
        # Wait for orchestration to reach notification point
        logger.debug("Waiting for content generation...")
        if not wait_for_notification(client, instance_id, timeout_seconds=120):
            logger.error("Failed to receive notification. Orchestration may have completed or failed.")
            break
        
        logger.info("Content is ready for review! Please review the content in the worker logs.")
        
        # Get user decision
        while True:
            decision = input("Do you approve this content? (yes/no): ").strip().lower()
            if decision in ['yes', 'y', 'no', 'n']:
                break
            logger.info("Please enter 'yes' or 'no'")
        
        approved = decision in ['yes', 'y']
        
        if approved:
            logger.debug("Sending approval...")
            send_approval(client, instance_id, approved=True)
            logger.info("Approval sent. Waiting for orchestration to complete...")
            _wait_and_log_completion(client, instance_id, timeout=60)
            break
        else:
            feedback = input("Enter feedback for improvement: ").strip()
            if not feedback:
                feedback = "Please revise the content."
            
            logger.debug("Sending rejection with feedback...")
            send_approval(client, instance_id, approved=False, feedback=feedback)
            logger.info("Rejection sent. Content will be regenerated...")
            
            attempt += 1
            
            if attempt > max_review_attempts:
                logger.info(f"Maximum review attempts ({max_review_attempts}) reached.")
                _wait_and_log_completion(client, instance_id, timeout=30)
                break
            
            # Small pause before next iteration
            time.sleep(2)


async def main() -> None:
    """Main entry point for the client application."""
    logger.debug("Starting Durable Task HITL Content Generation Client")
    
    # Create client using helper function
    client = get_client()
    
    try:
        run_interactive_client(client)
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Error during orchestration: {e}")
    finally:
        logger.debug("Client shutting down")


if __name__ == "__main__":
    asyncio.run(main())
