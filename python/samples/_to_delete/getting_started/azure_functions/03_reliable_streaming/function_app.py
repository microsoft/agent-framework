# Copyright (c) Microsoft. All rights reserved.

"""Reliable streaming for durable agents using Redis Streams.

This sample demonstrates how to implement reliable streaming for durable agents using Redis Streams.

Components used in this sample:
- AzureOpenAIChatClient to create the travel planner agent with tools.
- AgentFunctionApp with a Redis-based callback for persistent streaming.
- Custom HTTP endpoint to resume streaming from any point using cursor-based pagination.

Prerequisites:
- Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
- Redis running (docker run -d --name redis -p 6379:6379 redis:latest)
- DTS and Azurite running (see parent README)
"""

import logging
import os
from datetime import timedelta

import azure.functions as func
import redis.asyncio as aioredis
from agent_framework import AgentResponseUpdate
from agent_framework.azure import (
    AgentCallbackContext,
    AgentFunctionApp,
    AgentResponseCallbackProtocol,
    AzureOpenAIChatClient,
)
from azure.identity import AzureCliCredential
from redis_stream_response_handler import RedisStreamResponseHandler, StreamChunk
from tools import get_local_events, get_weather_forecast

logger = logging.getLogger(__name__)

# Configuration
REDIS_CONNECTION_STRING = os.environ.get("REDIS_CONNECTION_STRING", "redis://localhost:6379")
REDIS_STREAM_TTL_MINUTES = int(os.environ.get("REDIS_STREAM_TTL_MINUTES", "10"))


async def get_stream_handler() -> RedisStreamResponseHandler:
    """Create a new Redis stream handler for each request.

    This avoids event loop conflicts in Azure Functions by creating
    a fresh Redis client in the current event loop context.
    """
    # Create a new Redis client in the current event loop
    redis_client = aioredis.from_url(
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
        self._logger = logging.getLogger("durableagent.samples.redis_streaming")
        self._sequence_numbers = {}  # Track sequence per thread

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
            self._logger.warning("No thread_id available for streaming update")
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

                self._logger.info(
                    "[%s][%s] Wrote chunk to Redis: seq=%d, text=%s",
                    context.agent_name,
                    thread_id[:8],
                    sequence,
                    text,
                )
        except Exception as ex:
            self._logger.error(f"Error writing to Redis stream: {ex}", exc_info=True)

    async def on_agent_response(self, response, context: AgentCallbackContext) -> None:
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

                self._logger.info(
                    "[%s][%s] Agent completed, wrote end-of-stream marker",
                    context.agent_name,
                    thread_id[:8],
                )

                # Clean up sequence tracker
                self._sequence_numbers.pop(thread_id, None)
        except Exception as ex:
            self._logger.error(f"Error writing end-of-stream marker: {ex}", exc_info=True)


# Create the Redis streaming callback
redis_callback = RedisStreamCallback()


# Create the travel planner agent
def create_travel_agent():
    """Create the TravelPlanner agent with tools."""
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


# Create AgentFunctionApp with the Redis callback
app = AgentFunctionApp(
    agents=[create_travel_agent()],
    enable_health_check=True,
    default_callback=redis_callback,
    max_poll_retries=100,  # Increase for longer-running agents
)


# Custom streaming endpoint for reading from Redis
# Use the standard /api/agents/TravelPlanner/run endpoint to start agent runs


@app.function_name("stream")
@app.route(route="agent/stream/{conversation_id}", methods=["GET"])
async def stream(req: func.HttpRequest) -> func.HttpResponse:
    """Resume streaming from a specific cursor position for an existing session.

    This endpoint reads all currently available chunks from Redis for the given
    conversation ID, starting from the specified cursor (or beginning if no cursor).

    Use this endpoint to resume a stream after disconnection. Pass the conversation ID
    and optionally a cursor (Redis entry ID) to continue from where you left off.

    Query Parameters:
        cursor (optional): Redis stream entry ID to resume from. If not provided, starts from beginning.

    Response Headers:
        Content-Type: text/event-stream or text/plain based on Accept header
        x-conversation-id: The conversation/thread ID

    SSE Event Fields (when Accept: text/event-stream):
        id: Redis stream entry ID (use as cursor for resumption)
        event: "message" for content, "done" for completion, "error" for errors
        data: The text content or status message
    """
    try:
        conversation_id = req.route_params.get("conversation_id")
        if not conversation_id:
            return func.HttpResponse(
                "Conversation ID is required.",
                status_code=400,
            )

        # Get optional cursor from query string
        cursor = req.params.get("cursor")

        logger.info(
            f"Resuming stream for conversation {conversation_id} from cursor: {cursor or '(beginning)'}"
        )

        # Check Accept header to determine response format
        accept_header = req.headers.get("Accept", "")
        use_sse_format = "text/plain" not in accept_header.lower()

        # Stream chunks from Redis
        return await _stream_to_client(conversation_id, cursor, use_sse_format)

    except Exception as ex:
        logger.error(f"Error in stream endpoint: {ex}", exc_info=True)
        return func.HttpResponse(
            f"Internal server error: {str(ex)}",
            status_code=500,
        )


async def _stream_to_client(
    conversation_id: str,
    cursor: str | None,
    use_sse_format: bool,
) -> func.HttpResponse:
    """Stream chunks from Redis to the HTTP response.

    Args:
        conversation_id: The conversation ID to stream from.
        cursor: Optional cursor to resume from. If None, streams from the beginning.
        use_sse_format: True to use SSE format, false for plain text.

    Returns:
        HTTP response with all currently available chunks.
    """
    chunks = []

    # Use context manager to ensure Redis client is properly closed
    async with await get_stream_handler() as stream_handler:
        try:
            async for chunk in stream_handler.read_stream(conversation_id, cursor):
                if chunk.error:
                    logger.warning(f"Stream error for {conversation_id}: {chunk.error}")
                    chunks.append(_format_error(chunk.error, use_sse_format))
                    break

                if chunk.is_done:
                    chunks.append(_format_end_of_stream(chunk.entry_id, use_sse_format))
                    break

                if chunk.text:
                    chunks.append(_format_chunk(chunk, use_sse_format))

        except Exception as ex:
            logger.error(f"Error reading from Redis: {ex}", exc_info=True)
            chunks.append(_format_error(str(ex), use_sse_format))

    # Return all chunks
    response_body = "".join(chunks)

    return func.HttpResponse(
        body=response_body,
        mimetype="text/event-stream" if use_sse_format else "text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "x-conversation-id": conversation_id,
        },
    )


def _format_chunk(chunk: StreamChunk, use_sse_format: bool) -> str:
    """Format a text chunk."""
    if use_sse_format:
        return _format_sse_event("message", chunk.text, chunk.entry_id)
    return chunk.text


def _format_end_of_stream(entry_id: str, use_sse_format: bool) -> str:
    """Format end-of-stream marker."""
    if use_sse_format:
        return _format_sse_event("done", "[DONE]", entry_id)
    return "\n"


def _format_error(error: str, use_sse_format: bool) -> str:
    """Format error message."""
    if use_sse_format:
        return _format_sse_event("error", error, None)
    return f"\n[Error: {error}]\n"


def _format_sse_event(event_type: str, data: str, event_id: str | None = None) -> str:
    """Format a Server-Sent Event."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {data}")
    lines.append("")
    return "\n".join(lines) + "\n"
