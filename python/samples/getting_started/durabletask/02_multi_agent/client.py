"""Client application for interacting with multiple hosted agents.

This client connects to the Durable Task Scheduler and interacts with two different
agents (WeatherAgent and MathAgent), demonstrating how to work with multiple agents
each with their own specialized capabilities and tools.

Prerequisites: 
- The worker must be running with both agents registered
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
    """Run client interactions with both WeatherAgent and MathAgent.
    
    Args:
        agent_client: The DurableAIAgentClient instance
    """
    logger.debug("Testing WeatherAgent")
    
    # Get reference to WeatherAgent
    weather_agent = agent_client.get_agent("WeatherAgent")
    weather_thread = weather_agent.get_new_thread()
    
    logger.debug(f"Created weather conversation thread: {weather_thread.session_id}")
    
    # Test WeatherAgent
    weather_message = "What is the weather in Seattle?"
    logger.info(f"User: {weather_message}")
    
    weather_response = weather_agent.run(weather_message, thread=weather_thread)
    logger.info(f"WeatherAgent: {weather_response.text} \n")
    
    logger.debug("Testing MathAgent")
    
    # Get reference to MathAgent
    math_agent = agent_client.get_agent("MathAgent")
    math_thread = math_agent.get_new_thread()
    
    logger.debug(f"Created math conversation thread: {math_thread.session_id}")
    
    # Test MathAgent
    math_message = "Calculate a 20% tip on a $50 bill"
    logger.info(f"User: {math_message}")
    
    math_response = math_agent.run(math_message, thread=math_thread)
    logger.info(f"MathAgent: {math_response.text} \n")
    
    logger.debug("Both agents completed successfully!")


async def main() -> None:
    """Main entry point for the client application."""
    logger.debug("Starting Durable Task Multi-Agent Client...")
    
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
