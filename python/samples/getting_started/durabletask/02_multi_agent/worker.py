"""Worker process for hosting multiple agents with different tools using Durable Task.

This worker registers two agents - a weather assistant and a math assistant - each
with their own specialized tools. This demonstrates how to host multiple agents
with different capabilities in a single worker process.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Start a Durable Task Scheduler (e.g., using Docker)
"""

import asyncio
import logging
import os
from typing import Any

from agent_framework.azure import AzureOpenAIChatClient, DurableAIAgentWorker
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent names
WEATHER_AGENT_NAME = "WeatherAgent"
MATH_AGENT_NAME = "MathAgent"


def get_weather(location: str) -> dict[str, Any]:
    """Get current weather for a location."""
    logger.info(f"🔧 [TOOL CALLED] get_weather(location={location})")
    result = {
        "location": location,
        "temperature": 72,
        "conditions": "Sunny",
        "humidity": 45,
    }
    logger.info(f"✓ [TOOL RESULT] {result}")
    return result


def calculate_tip(bill_amount: float, tip_percentage: float = 15.0) -> dict[str, Any]:
    """Calculate tip amount and total bill."""
    logger.info(
        f"🔧 [TOOL CALLED] calculate_tip(bill_amount={bill_amount}, tip_percentage={tip_percentage})"
    )
    tip = bill_amount * (tip_percentage / 100)
    total = bill_amount + tip
    result = {
        "bill_amount": bill_amount,
        "tip_percentage": tip_percentage,
        "tip_amount": round(tip, 2),
        "total": round(total, 2),
    }
    logger.info(f"✓ [TOOL RESULT] {result}")
    return result


def create_weather_agent():
    """Create the Weather agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured Weather agent with weather tool
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name=WEATHER_AGENT_NAME,
        instructions="You are a helpful weather assistant. Provide current weather information.",
        tools=[get_weather],
    )


def create_math_agent():
    """Create the Math agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured Math agent with calculation tools
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name=MATH_AGENT_NAME,
        instructions="You are a helpful math assistant. Help users with calculations like tip calculations.",
        tools=[calculate_tip],
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
    """Set up the worker with multiple agents registered.
    
    Args:
        worker: The DurableTaskSchedulerWorker instance
        
    Returns:
        DurableAIAgentWorker with agents registered
    """
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker)
    
    # Create and register both agents
    logger.debug("Creating and registering agents...")
    weather_agent = create_weather_agent()
    math_agent = create_math_agent()
    
    agent_worker.add_agent(weather_agent)
    agent_worker.add_agent(math_agent)
    
    logger.debug(f"✓ Registered agents: {weather_agent.name}, {math_agent.name}")
    
    return agent_worker


async def main():
    """Main entry point for the worker process."""
    logger.debug("Starting Durable Task Multi-Agent Worker...")
    
    # Create a worker using the helper function
    worker = get_worker()
    
    # Setup worker with agents
    setup_worker(worker)
    
    logger.info("Worker is ready and listening for requests...")
    logger.info("Press Ctrl+C to stop. \n")
    
    try:
        # Start the worker (this blocks until stopped)
        worker.start()
        
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.debug("Worker shutdown initiated")
    
    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
