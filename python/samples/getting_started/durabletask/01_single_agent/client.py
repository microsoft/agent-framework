"""Client application for interacting with a Durable Task hosted agent.

This client connects to the Durable Task Scheduler and sends requests to
registered agents, demonstrating how to interact with agents from external processes.

Prerequisites: 
- The worker must be running with the agent registered
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running
"""

import asyncio
import logging
import os

from agent_framework_durabletask import DurableAIAgentClient
from azure.identity import DefaultAzureCredential
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point for the client application."""
    logger.info("Starting Durable Task Agent Client...")
    
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
    
    # Wrap it with the agent client
    agent_client = DurableAIAgentClient(client)
    
    # Get a reference to the Joker agent
    logger.info("Getting reference to Joker agent...")
    joker = agent_client.get_agent("Joker")
    
    # Create a new thread for the conversation
    thread = joker.get_new_thread()
    
    logger.info(f"Created conversation thread: {thread.session_id}")
    logger.info("")
    
    try:
        # First message
        message1 = "Tell me a short joke about cloud computing."
        logger.info(f"User: {message1}")
        logger.info("")
        
        # Run the agent - this blocks until the response is ready
        response1 = joker.run(message1, thread=thread)
        logger.info(f"Agent: {response1.text}")
        logger.info("")
        
        # Second message - continuing the conversation
        message2 = "Now tell me one about Python programming."
        logger.info(f"User: {message2}")
        logger.info("")
        
        response2 = joker.run(message2, thread=thread)
        logger.info(f"Agent: {response2.text}")
        logger.info("")
        
        logger.info(f"Conversation completed successfully!")
        logger.info(f"Thread ID: {thread.session_id}")
        
    except Exception as e:
        logger.exception(f"Error during agent interaction: {e}")
    finally:
        logger.info("Client shutting down")


if __name__ == "__main__":
    asyncio.run(main())
