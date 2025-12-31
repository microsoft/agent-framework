"""Client application for starting a single agent chaining orchestration.

This client connects to the Durable Task Scheduler and starts an orchestration
that runs a writer agent twice sequentially on the same thread, demonstrating
how conversation context is maintained across multiple agent invocations.

Prerequisites: 
- The worker must be running with the writer agent and orchestration registered
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


async def main() -> None:
    """Main entry point for the client application."""
    logger.info("Starting Durable Task Single Agent Chaining Orchestration Client...")
    
    # Get environment variables for taskhub and endpoint with defaults
    taskhub_name = os.getenv("TASKHUB", "default")
    endpoint = os.getenv("ENDPOINT", "http://localhost:8080")

    logger.info(f"Using taskhub: {taskhub_name}")
    logger.info(f"Using endpoint: {endpoint}")
    logger.info("")

    # Set credential to None for emulator, or DefaultAzureCredential for Azure
    credential = None if endpoint == "http://localhost:8080" else DefaultAzureCredential()
    
    # Create a client using Azure Managed Durable Task
    client = DurableTaskSchedulerClient(
        host_address=endpoint,
        secure_channel=endpoint != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential
    )
    
    logger.info("Starting single agent chaining orchestration...")
    logger.info("")
    
    try:
        # Start the orchestration
        instance_id = client.schedule_new_orchestration(
            orchestrator="single_agent_chaining_orchestration",
            input="",
        )
        
        logger.info(f"Orchestration started with instance ID: {instance_id}")
        logger.info("Waiting for orchestration to complete...")
        logger.info("")
        
        # Retrieve the final state
        metadata = client.wait_for_orchestration_completion(
            instance_id=instance_id,
            timeout=300
        )
        
        if metadata and metadata.runtime_status.name == "COMPLETED":
            result = metadata.serialized_output
            
            logger.info("=" * 80)
            logger.info("Orchestration completed successfully!")
            logger.info("=" * 80)
            logger.info("")
            logger.info("Results:")
            logger.info("")
            
            # Parse and display the result
            if result:
                final_text = json.loads(result)
                logger.info("Final refined sentence:")
                logger.info(f"  {final_text}")
                logger.info("")
            
            logger.info("=" * 80)
            
        elif metadata:
            logger.error(f"Orchestration ended with status: {metadata.runtime_status.name}")
            if metadata.serialized_output:
                logger.error(f"Output: {metadata.serialized_output}")
        else:
            logger.error("Orchestration did not complete within the timeout period")
        
    except Exception as e:
        logger.exception(f"Error during orchestration: {e}")
    finally:
        logger.info("")
        logger.info("Client shutting down")


if __name__ == "__main__":
    asyncio.run(main())
