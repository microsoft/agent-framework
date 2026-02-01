"""Client application for starting a multi-agent concurrent orchestration.

This client connects to the Durable Task Scheduler and starts an orchestration
that runs two agents (physicist and chemist) concurrently, then retrieves and
displays the aggregated results.

Prerequisites: 
- The worker must be running with both agents and orchestration registered
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running
"""

import asyncio
import json
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


def run_client(client: DurableTaskSchedulerClient, prompt: str = "What is temperature?") -> None:
    """Run client to start and monitor the orchestration.
    
    Args:
        client: The DurableTaskSchedulerClient instance
        prompt: The prompt to send to both agents
    """
    # Start the orchestration with the prompt as input
    instance_id = client.schedule_new_orchestration(    # type: ignore
        orchestrator="multi_agent_concurrent_orchestration",
        input=prompt,
    )
    
    logger.info(f"Orchestration started with instance ID: {instance_id}")
    logger.debug("Waiting for orchestration to complete...")
    
    # Retrieve the final state
    metadata = client.wait_for_orchestration_completion(
        instance_id=instance_id,
    )
    
    if metadata and metadata.runtime_status.name == "COMPLETED":
        result = metadata.serialized_output
        
        logger.debug("Orchestration completed successfully!")
                
        # Parse and display the result
        if result:
            result_json = json.loads(result) if isinstance(result, str) else result
            logger.info("Orchestration Results:\n%s", json.dumps(result_json, indent=2))
        
    elif metadata:
        logger.error(f"Orchestration ended with status: {metadata.runtime_status.name}")
        if metadata.serialized_output:
            logger.error(f"Output: {metadata.serialized_output}")
    else:
        logger.error("Orchestration did not complete within the timeout period")


async def main() -> None:
    """Main entry point for the client application."""
    logger.debug("Starting Durable Task Multi-Agent Orchestration Client...")
    
    # Create client using helper function
    client = get_client()
    
    try:
        run_client(client)
    except Exception as e:
        logger.exception(f"Error during orchestration: {e}")
    finally:
        logger.debug("Client shutting down")


if __name__ == "__main__":
    asyncio.run(main())
