"""Worker process for hosting a single Azure OpenAI-powered agent using Durable Task.

This worker registers agents as durable entities and continuously listens for requests.
The worker should run as a background service, processing incoming agent requests.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Start a Durable Task Scheduler (e.g., using Docker)
"""

import asyncio
import logging
import os

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_durabletask import DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_joker_agent():
    """Create the Joker agent using Azure OpenAI.
    
    Returns:
        AgentProtocol: The configured Joker agent
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name="Joker",
        instructions="You are good at telling jokes.",
    )


async def main():
    """Main entry point for the worker process."""
    logger.info("Starting Durable Task Agent Worker...")
    
    # Get environment variables for taskhub and endpoint with defaults
    taskhub_name = os.getenv("TASKHUB", "default")
    endpoint = os.getenv("ENDPOINT", "http://localhost:8080")

    logger.info(f"Using taskhub: {taskhub_name}")
    logger.info(f"Using endpoint: {endpoint}")

    # Set credential to None for emulator, or DefaultAzureCredential for Azure
    credential = None if endpoint == "http://localhost:8080" else DefaultAzureCredential()
    
    # Create a worker using Azure Managed Durable Task
    worker = DurableTaskSchedulerWorker(
        host_address=endpoint,
        secure_channel=endpoint != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential
    )
    
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker)
    
    # Create and register the Joker agent
    logger.info("Creating and registering Joker agent...")
    joker_agent = create_joker_agent()
    agent_worker.add_agent(joker_agent)
    
    logger.info(f"✓ Registered agent: {joker_agent.name}")
    logger.info(f"  Entity name: dafx-{joker_agent.name}")
    logger.info("")
    logger.info("Worker is ready and listening for requests...")
    logger.info("Press Ctrl+C to stop.")
    logger.info("")
    
    try:
        # Start the worker (this blocks until stopped)
        worker.start()
        
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker shutdown initiated")
    
    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
