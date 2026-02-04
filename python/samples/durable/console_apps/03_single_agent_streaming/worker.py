# Copyright (c) Microsoft. All rights reserved.

"""Worker process for hosting a TravelPlanner agent with reliable Redis streaming.

This worker registers the TravelPlanner agent with the Durable Task Scheduler
and uses RedisStreamCallback to persist streaming responses to Redis for reliable delivery.

Prerequisites: 
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME 
  (plus AZURE_OPENAI_API_KEY or Azure CLI authentication)
- Start a Durable Task Scheduler (e.g., using Docker)
- Start Redis (e.g., docker run -d --name redis -p 6379:6379 redis:latest)
"""

import asyncio
import logging
import os
from datetime import timedelta

import redis.asyncio as aioredis
from agent_framework import AgentResponseUpdate, ChatAgent
from agent_framework.azure import (
    AgentCallbackContext,
    AgentResponseCallbackProtocol,
    AzureOpenAIChatClient,
    DurableAIAgentWorker,
)
from azure.identity import AzureCliCredential, DefaultAzureCredential
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker

from redis_stream_response_handler import RedisStreamResponseHandler
from tools import get_local_events, get_weather_forecast

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
REDIS_CONNECTION_STRING = os.environ.get("REDIS_CONNECTION_STRING", "redis://localhost:6379")
REDIS_STREAM_TTL_MINUTES = int(os.environ.get("REDIS_STREAM_TTL_MINUTES", "10"))


async def get_stream_handler() -> RedisStreamResponseHandler:
    """Create a new Redis stream handler for each request.

    This avoids event loop conflicts by creating a fresh Redis client
    in the current event loop context.
    """
    # Create a new Redis client in the current event loop
    redis_client = aioredis.from_url(  # type: ignore[reportUnknownMemberType]
        REDIS_CONNECTION_STRING,
        encoding="utf-8",
        decode_responses=False,
    )

    return RedisStreamResponseHandler(
        redis_client=redis_client,
        stream_ttl=timedelta(minutes=REDIS_STREAM_TTL_MINUTES),
    )


class RedisStreamCallback(AgentResponseCallbackProtocol):
    """Callback that writes streaming updates to Redis Streams for reliable delivery.

    This enables clients to disconnect and reconnect without losing messages.
    """

    def __init__(self) -> None:
        self._sequence_numbers: dict[str, int] = {}  # Track sequence per thread

    async def on_streaming_response_update(
        self,
        update: AgentResponseUpdate,
        context: AgentCallbackContext,
    ) -> None:
        """Write streaming update to Redis Stream.

        Args:
            update: The streaming response update chunk.
            context: The callback context with thread_id, agent_name, etc.
        """
        thread_id = context.thread_id
        if not thread_id:
            logger.warning("No thread_id available for streaming update")
            return

        if not update.text:
            return

        text = update.text

        # Get or initialize sequence number for this thread
        if thread_id not in self._sequence_numbers:
            self._sequence_numbers[thread_id] = 0

        sequence = self._sequence_numbers[thread_id]

        try:
            # Use context manager to ensure Redis client is properly closed
            async with await get_stream_handler() as stream_handler:
                # Write chunk to Redis Stream using public API
                await stream_handler.write_chunk(thread_id, text, sequence)

                self._sequence_numbers[thread_id] += 1

                logger.debug(
                    "[%s][%s] Wrote chunk to Redis: seq=%d, text=%s",
                    context.agent_name,
                    thread_id[:8],
                    sequence,
                    text,
                )
        except Exception as ex:
            logger.error(f"Error writing to Redis stream: {ex}", exc_info=True)

    async def on_agent_response(self, response: object, context: AgentCallbackContext) -> None:
        """Write end-of-stream marker when agent completes.

        Args:
            response: The final agent response.
            context: The callback context.
        """
        thread_id = context.thread_id
        if not thread_id:
            return

        sequence = self._sequence_numbers.get(thread_id, 0)

        try:
            # Use context manager to ensure Redis client is properly closed
            async with await get_stream_handler() as stream_handler:
                # Write end-of-stream marker using public API
                await stream_handler.write_completion(thread_id, sequence)

                logger.info(
                    "[%s][%s] Agent completed, wrote end-of-stream marker",
                    context.agent_name,
                    thread_id[:8],
                )

                # Clean up sequence tracker
                self._sequence_numbers.pop(thread_id, None)
        except Exception as ex:
            logger.error(f"Error writing end-of-stream marker: {ex}", exc_info=True)


def create_travel_agent() -> "ChatAgent":
    """Create the TravelPlanner agent using Azure OpenAI.
    
    Returns:
        ChatAgent: The configured TravelPlanner agent with travel planning tools.
    """
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="TravelPlanner",
        instructions="""You are an expert travel planner who creates detailed, personalized travel itineraries.
When asked to plan a trip, you should:
1. Create a comprehensive day-by-day itinerary
2. Include specific recommendations for activities, restaurants, and attractions
3. Provide practical tips for each destination
4. Consider weather and local events when making recommendations
5. Include estimated times and logistics between activities

Always use the available tools to get current weather forecasts and local events
for the destination to make your recommendations more relevant and timely.

Format your response with clear headings for each day and include emoji icons
to make the itinerary easy to scan and visually appealing.""",
        tools=[get_weather_forecast, get_local_events],
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
        log_handler: Optional log handler for worker logging
        
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
    """Set up the worker with the TravelPlanner agent and Redis streaming callback.
    
    Args:
        worker: The DurableTaskSchedulerWorker instance
        
    Returns:
        DurableAIAgentWorker with agent and callback registered
    """
    # Create the Redis streaming callback
    redis_callback = RedisStreamCallback()
    
    # Wrap it with the agent worker
    agent_worker = DurableAIAgentWorker(worker, callback=redis_callback)
    
    # Create and register the TravelPlanner agent
    logger.debug("Creating and registering TravelPlanner agent...")
    travel_agent = create_travel_agent()
    agent_worker.add_agent(travel_agent)
    
    logger.debug(f"✓ Registered agent: {travel_agent.name}")
    
    return agent_worker


async def main():
    """Main entry point for the worker process."""
    logger.debug("Starting Durable Task Agent Worker with Redis Streaming...")
    
    # Create a worker using the helper function
    worker = get_worker()
    
    # Setup worker with agent and callback
    setup_worker(worker)
    
    # Start the worker
    logger.debug("Worker started and listening for requests...")
    worker.start()
    
    try:
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.debug("Worker shutting down...")
    finally:
        worker.stop()
        logger.debug("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
