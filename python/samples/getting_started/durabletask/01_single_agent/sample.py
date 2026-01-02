"""Single Agent Sample - Durable Task Integration (Combined Worker + Client)

This sample demonstrates running both the worker and client in a single process.
The worker is started first to register the agent, then client operations are
performed against the running worker.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Durable Task Scheduler must be running (e.g., using Docker)

To run this sample:
    python sample.py
"""

import logging
import os

from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_durabletask import DurableAIAgentClient, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
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


def main():
    """Main entry point - runs both worker and client in single process."""
    logger.info("Starting Durable Task Agent Sample (Combined Worker + Client)...")
    
    # Get environment variables for taskhub and endpoint with defaults
    taskhub_name = os.getenv("TASKHUB", "default")
    endpoint = os.getenv("ENDPOINT", "http://localhost:8080")

    logger.info(f"Using taskhub: {taskhub_name}")
    logger.info(f"Using endpoint: {endpoint}")
    logger.info("")

    # Set credential to None for emulator, or DefaultAzureCredential for Azure
    credential = None if endpoint == "http://localhost:8080" else DefaultAzureCredential()
    secure_channel = endpoint != "http://localhost:8080"
    
    # Create and start the worker using a context manager
    with DurableTaskSchedulerWorker(
        host_address=endpoint,
        secure_channel=secure_channel,
        taskhub=taskhub_name,
        token_credential=credential
    ) as worker:
        
        # Wrap with the agent worker
        agent_worker = DurableAIAgentWorker(worker)
        
        # Create and register the Joker agent
        logger.info("Creating and registering Joker agent...")
        joker_agent = create_joker_agent()
        agent_worker.add_agent(joker_agent)
        
        logger.info(f"✓ Registered agent: {joker_agent.name}")
        logger.info(f"  Entity name: dafx-{joker_agent.name}")
        logger.info("")
        
        # Start the worker
        worker.start()
        logger.info("Worker started and listening for requests...")
        logger.info("")
        
        # Create the client
        client = DurableTaskSchedulerClient(
            host_address=endpoint,
            secure_channel=secure_channel,
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
            logger.info(f"Agent: {response1.text}; {response1}")
            logger.info("")
            
            # Second message - continuing the conversation
            message2 = "Now tell me one about Python programming."
            logger.info(f"User: {message2}")
            logger.info("")
            
            response2 = joker.run(message2, thread=thread)
            logger.info(f"Agent: {response2.text}; {response2}")
            logger.info("")
            
            logger.info(f"Conversation completed successfully!")
            logger.info(f"Thread ID: {thread.session_id}")
            
        except Exception as e:
            logger.exception(f"Error during agent interaction: {e}")
        
        logger.info("")
        logger.info("Sample completed. Worker shutting down...")


if __name__ == "__main__":
    load_dotenv()
    main()
