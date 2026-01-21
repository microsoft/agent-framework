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

from agent_framework.azure import DurableAIAgentClient
from azure.identity import DefaultAzureCredential
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_client(
    taskhub: str | None = None,
    endpoint: str | None = None,
    log_handler: logging.Handler | None = None
) -> DurableAIAgentClient:
    """Create a configured DurableAIAgentClient.
    
    Args:
        taskhub: Task hub name (defaults to TASKHUB env var or "default")
        endpoint: Scheduler endpoint (defaults to ENDPOINT env var or "http://localhost:8080")
        log_handler: Optional logging handler for client logging
        
    Returns:
        Configured DurableAIAgentClient instance
    """
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")
    
    logger.debug(f"Using taskhub: {taskhub_name}")
    logger.debug(f"Using endpoint: {endpoint_url}")
    
    credential = None if endpoint_url == "http://localhost:8080" else DefaultAzureCredential()
    
    dts_client = DurableTaskSchedulerClient(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler
    )
    
    return DurableAIAgentClient(dts_client)


def run_client(agent_client: DurableAIAgentClient) -> None:
    """Run client interactions with the Joker agent.
    
    Args:
        agent_client: The DurableAIAgentClient instance
    """
    # Get a reference to the Joker agent
    logger.debug("Getting reference to Joker agent...")
    joker = agent_client.get_agent("Joker")
    
    # Create a new thread for the conversation
    thread = joker.get_new_thread()
    logger.debug(f"Thread ID: {thread.session_id}")
    logger.info("Start chatting with the Joker agent! (Type 'exit' to quit)")
    
    # Interactive conversation loop
    while True:
        # Get user input
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            logger.info("\nExiting...")
            break
        
        # Check for exit command
        if user_message.lower() == "exit":
            logger.info("Goodbye!")
            break
        
        # Skip empty messages
        if not user_message:
            continue
        
        # Send message to agent and get response
        try:
            response = joker.run(user_message, thread=thread)
            logger.info(f"Joker: {response.text} \n")
        except Exception as e:
            logger.error(f"Error getting response: {e}")
    
    logger.info("Conversation completed.")


async def main() -> None:
    """Main entry point for the client application."""
    logger.debug("Starting Durable Task Agent Client...")
    
    # Create client using helper function
    agent_client = get_client()
    
    try:
        run_client(agent_client)
    except Exception as e:
        logger.exception(f"Error during agent interaction: {e}")
    finally:
        logger.debug("Client shutting down")


if __name__ == "__main__":
    asyncio.run(main())
