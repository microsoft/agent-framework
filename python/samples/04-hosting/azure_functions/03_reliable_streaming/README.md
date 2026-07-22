# Agent Response Callbacks with Redis Streaming

This sample demonstrates how to use Redis Streams with agent response callbacks to enable reliable, resumable streaming for durable agents. Clients can disconnect and reconnect without losing messages by using cursor-based pagination.

## Key Concepts Demonstrated

- Using `AgentResponseCallbackProtocol` to capture streaming agent responses
- Persisting streaming chunks to Redis Streams for reliable delivery
- Building a custom HTTP endpoint to read from Redis with Server-Sent Events (SSE) format
- Supporting cursor-based resumption for disconnected clients
- Managing Redis client lifecycle with async context managers

## Prerequisites

In addition to the common setup steps in `../README.md`, this sample requires Redis:

```bash
# Start Redis
docker run -d --name redis -p 6379:6379 redis:latest
```

Update `local.settings.json` with your Redis connection string:

```json
{
  "Values": {
    "REDIS_CONNECTION_STRING": "redis://localhost:6379"
  }
}
```

## Running the Sample

### Start the agent run

The agent executes in the background via durable orchestration. The `RedisStreamCallback` persists streaming chunks to Redis:

```bash
curl -X POST http://localhost:7071/api/agents/TravelPlanner/run \
  -H "Content-Type: text/plain" \
  -d "Plan a 3-day trip to Tokyo"
```

Response (202 Accepted):
```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "conversation_id": "abc-123-def-456",
  "correlation_id": "xyz-789"
}
```

### Stream the response from Redis

Use the custom `/api/agent/stream/{conversation_id}` endpoint to read persisted chunks:

```bash
curl http://localhost:7071/api/agent/stream/abc-123-def-456 \
  -H "Accept: text/event-stream"
```

Response (SSE format):
```
id: 1734649123456-0
event: message
data: Here's a wonderful 3-day Tokyo itinerary...

id: 1734649123789-0
event: message
data: Day 1: Arrival and Shibuya...

id: 1734649124012-0
event: done
data: [DONE]
```

### Resume from a cursor

Use a cursor ID from an SSE event to skip already-processed messages:

```bash
curl "http://localhost:7071/api/agent/stream/abc-123-def-456?cursor=1734649123456-0" \
  -H "Accept: text/event-stream"
```

## How It Works

### 1. Redis Callback

The `RedisStreamCallback` class implements `AgentResponseCallbackProtocol` to capture streaming updates:

```python
class RedisStreamCallback(AgentResponseCallbackProtocol):
    async def on_streaming_response_update(self, update, context):
        # Write chunk to Redis Stream
        async with await get_stream_handler() as handler:
            await handler.write_chunk(thread_id, update.text, sequence)

    async def on_agent_response(self, response, context):
        # Write end-of-stream marker
        async with await get_stream_handler() as handler:
            await handler.write_completion(thread_id, sequence)
```

### 2. Custom Streaming Endpoint

The `/api/agent/stream/{conversation_id}` endpoint reads from Redis:

```python
@app.route(route="agent/stream/{conversation_id}", methods=["GET"])
async def stream(req):
    conversation_id = req.route_params.get("conversation_id")
    cursor = req.params.get("cursor")  # Optional

    async with await get_stream_handler() as handler:
        async for chunk in handler.read_stream(conversation_id, cursor):
            # Format and return chunks
```

### 3. Redis Streams

Messages are stored in Redis Streams with automatic TTL (default: 10 minutes):

```
Stream Key: agent-stream:{conversation_id}
Entry: {
  "text": "chunk content",
  "sequence": "0",
  "timestamp": "1734649123456"
}
```