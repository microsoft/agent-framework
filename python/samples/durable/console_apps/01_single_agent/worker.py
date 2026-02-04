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

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def create_joker_agent() -> ChatAgent:
    """Create the Joker agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured Joker agent
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="Joker",
        instructions="You are good at telling jokes.",
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
    """Set up the worker with agents registered.
    
    Args:
        worker: The DurableTaskSchedulerWorker instance
        
    Returns:
        DurableAIAgentWorker with agents registered
    """
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker)
    
    # Create and register the Joker agent
    logger.debug("Creating and registering Joker agent...")
    joker_agent = create_joker_agent()
    agent_worker.add_agent(joker_agent)
    
    logger.debug(f"✓ Registered agent: {joker_agent.name}")
    logger.debug(f"  Entity name: dafx-{joker_agent.name}")
    
    return agent_worker


async def main():
    """Main entry point for the worker process."""
    logger.debug("Starting Durable Task Agent Worker...")
    
    # Create a worker using the helper function
    worker = get_worker()
    
    # Setup worker with agents
    setup_worker(worker)
    
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
        logger.debug("Worker shutdown initiated")
    
    logger.debug("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
