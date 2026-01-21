# Copyright (c) Microsoft. All rights reserved.

"""Client application for interacting with the TravelPlanner agent and streaming from Redis.

This client demonstrates:
1. Sending a travel planning request to the durable agent
2. Streaming the response from Redis in real-time
3. Handling reconnection and cursor-based resumption

Prerequisites: 
- The worker must be running with the TravelPlanner agent registered
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
- Redis must be running
- Durable Task Scheduler must be running
"""

import asyncio
import logging
import os
from datetime import timedelta

import redis.asyncio as aioredis
from agent_framework.azure import DurableAIAgentClient
from azure.identity import DefaultAzureCredential
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

from redis_stream_response_handler import RedisStreamResponseHandler

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


def get_client(
    taskhub: str | None = None,
    endpoint: str | None = None,
    log_handler: logging.Handler | None = None
) -> DurableAIAgentClient:
    """Create a configured DurableAIAgentClient.
    
    Args:
        taskhub: Task hub name (defaults to TASKHUB env var or "default")
        endpoint: Scheduler endpoint (defaults to ENDPOINT env var or "http://localhost:8080")
        log_handler: Optional log handler for client logging
        
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


async def stream_from_redis(thread_id: str, cursor: str | None = None) -> None:
    """Stream agent responses from Redis.
    
    Args:
        thread_id: The conversation/thread ID to stream from
        cursor: Optional cursor to resume from. If None, starts from beginning.
    """
    stream_key = f"agent-stream:{thread_id}"
    logger.info(f"Streaming response from Redis (thread: {thread_id[:8]}...)")
    logger.debug(f"To manually check Redis, run: redis-cli XLEN {stream_key}")
    if cursor:
        logger.info(f"Resuming from cursor: {cursor}")
    
    async with await get_stream_handler() as stream_handler:
        logger.info(f"Stream handler created, starting to read...")
        try:
            chunk_count = 0
            async for chunk in stream_handler.read_stream(thread_id, cursor):
                chunk_count += 1
                logger.debug(f"Received chunk #{chunk_count}: error={chunk.error}, is_done={chunk.is_done}, text_len={len(chunk.text) if chunk.text else 0}")
                
                if chunk.error:
                    logger.error(f"Stream error: {chunk.error}")
                    break
                
                if chunk.is_done:
                    print("\n✓ Response complete!", flush=True)
                    logger.info(f"Stream completed after {chunk_count} chunks")
                    break
                
                if chunk.text:
                    # Print directly to console with flush for immediate display
                    print(chunk.text, end='', flush=True)
            
            if chunk_count == 0:
                logger.warning("No chunks received from Redis stream!")
                logger.warning(f"Check Redis manually: redis-cli XLEN {stream_key}")
                logger.warning(f"View stream contents: redis-cli XREAD STREAMS {stream_key} 0")
                
        except Exception as ex:
            logger.error(f"Error reading from Redis: {ex}", exc_info=True)


def run_client(agent_client: DurableAIAgentClient) -> None:
    """Run client interactions with the TravelPlanner agent.
    
    Args:
        agent_client: The DurableAIAgentClient instance
    """
    # Get a reference to the TravelPlanner agent
    logger.debug("Getting reference to TravelPlanner agent...")
    travel_planner = agent_client.get_agent("TravelPlanner")
    
    # Create a new thread for the conversation
    thread = travel_planner.get_new_thread()
    if not thread.session_id:
        logger.error("Failed to create a new thread with session ID!")
        return
    
    key = thread.session_id.key
    logger.info(f"Thread ID: {key}")
    
    # Get user input
    print("\nEnter your travel planning request:")
    user_message = input("> ").strip()
    
    if not user_message:
        logger.warning("No input provided. Using default message.")
        user_message = "Plan a 3-day trip to Tokyo with emphasis on culture and food"
    
    logger.info(f"\nYou: {user_message}\n")
    logger.info("TravelPlanner (streaming from Redis):")
    logger.info("-" * 80)
    
    # Start the agent run with wait_for_response=False for non-blocking execution
    # This signals the agent to start processing without waiting for completion
    # The agent will execute in the background and write chunks to Redis
    travel_planner.run(user_message, thread=thread, options={"wait_for_response": False})
    
    # Stream the response from Redis
    # This demonstrates that the client can stream from Redis while
    # the agent is still processing (or after it completes)
    asyncio.run(stream_from_redis(str(key)))
    
    logger.info("\nDemo completed!")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Create the client
    client = get_client()
    
    # Run the demo
    run_client(client)
