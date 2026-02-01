"""Client application for starting a spam detection orchestration.

This client connects to the Durable Task Scheduler and starts an orchestration
that uses conditional logic to either handle spam emails or draft professional responses.

Prerequisites: 
- The worker must be running with both agents, orchestration, and activities registered
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running
"""

import asyncio
import logging
import os

from azure.identity import DefaultAzureCredential
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def run_client(
    client: DurableTaskSchedulerClient,
    email_id: str = "email-001",
    email_content: str = "Hello! I wanted to reach out about our upcoming project meeting."
) -> None:
    """Run client to start and monitor the spam detection orchestration.
    
    Args:
        client: The DurableTaskSchedulerClient instance
        email_id: The email ID
        email_content: The email content to analyze
    """
    payload = {
        "email_id": email_id,
        "email_content": email_content,
    }
    
    logger.debug("Starting spam detection orchestration...")
    
    # Start the orchestration with the email payload
    instance_id = client.schedule_new_orchestration(    # type: ignore
        orchestrator="spam_detection_orchestration",
        input=payload,
    )
    
    logger.debug(f"Orchestration started with instance ID: {instance_id}")
    logger.debug("Waiting for orchestration to complete...")
    
    # Retrieve the final state
    metadata = client.wait_for_orchestration_completion(
        instance_id=instance_id,
        timeout=300
    )
    
    if metadata and metadata.runtime_status.name == "COMPLETED":
        result = metadata.serialized_output
        
        logger.debug("Orchestration completed successfully!")
        
        # Parse and display the result
        if result:
            # Remove quotes if present
            if result.startswith('"') and result.endswith('"'):
                result = result[1:-1]
            logger.info(f"Result: {result}")
        
    elif metadata:
        logger.error(f"Orchestration ended with status: {metadata.runtime_status.name}")
        if metadata.serialized_output:
            logger.error(f"Output: {metadata.serialized_output}")
    else:
        logger.error("Orchestration did not complete within the timeout period")


async def main() -> None:
    """Main entry point for the client application."""
    logger.debug("Starting Durable Task Spam Detection Orchestration Client...")
    
    # Create client using helper function
    client = get_client()
    
    try:
        # Test with a legitimate email
        logger.info("TEST 1: Legitimate Email")
        
        run_client(
            client,
            email_id="email-001",
            email_content="Hello! I wanted to reach out about our upcoming project meeting scheduled for next week."
        )
        
        # Test with a spam email
        logger.info("TEST 2: Spam Email")
        
        run_client(
            client,
            email_id="email-002",
            email_content="URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer! Don't miss out!"
        )
        
    except Exception as e:
        logger.exception(f"Error during orchestration: {e}")
    finally:
        logger.debug("")
        logger.debug("Client shutting down")


if __name__ == "__main__":
    asyncio.run(main())
