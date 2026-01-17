# Single Agent with Reliable Streaming

This sample demonstrates how to use Redis Streams with agent response callbacks to enable reliable, resumable streaming for durable agents. Streaming responses are persisted to Redis, allowing clients to disconnect and reconnect without losing messages.

## Key Concepts Demonstrated

- Using `AgentResponseCallbackProtocol` to capture streaming agent responses.
- Persisting streaming chunks to Redis Streams for reliable delivery.
- Non-blocking agent execution with `options={"wait_for_response": False}` (fire-and-forget mode).
- Cursor-based resumption for disconnected clients.
- Decoupling agent execution from response streaming.

## Prerequisites

In addition to the common setup in the parent [README.md](../README.md), this sample requires Redis:

```bash
docker run -d --name redis -p 6379:6379 redis:latest
```

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

Additional environment variables for this sample:

```bash
# Optional: Redis Configuration
REDIS_CONNECTION_STRING=redis://localhost:6379
REDIS_STREAM_TTL_MINUTES=10
```

## Running the Sample

With the environment setup, you can run the sample using the combined approach or separate worker and client processes:

**Option 1: Combined (Recommended for Testing)**

```bash
cd samples/getting_started/durabletask/03_single_agent_streaming
python sample.py
```

**Option 2: Separate Processes**

Start the worker in one terminal:

```bash
python worker.py
```

In a new terminal, run the client:

```bash
python client.py
```

The client will send a travel planning request to the TravelPlanner agent and stream the response from Redis in real-time:

```
================================================================================
TravelPlanner Agent - Redis Streaming Demo
================================================================================

You: Plan a 3-day trip to Tokyo with emphasis on culture and food

TravelPlanner (streaming from Redis):
--------------------------------------------------------------------------------
# Your Amazing 3-Day Tokyo Adventure! 🗾

Let me create the perfect cultural and culinary journey through Tokyo...

## Day 1: Traditional Tokyo & First Impressions
...
(continues streaming)
...

✓ Response complete!
```


## How It Works

### Redis Streaming Callback

The `RedisStreamCallback` class implements `AgentResponseCallbackProtocol` to capture streaming updates and persist them to Redis:

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

### Worker Registration

The worker registers the agent with the Redis streaming callback:

```python
redis_callback = RedisStreamCallback()
agent_worker = DurableAIAgentWorker(worker, callback=redis_callback)
agent_worker.add_agent(create_travel_agent())
```

### Client Streaming

The client uses fire-and-forget mode to start the agent and streams from Redis:

```python
# Start agent run with wait_for_response=False for non-blocking execution
travel_planner.run(user_message, thread=thread, options={"wait_for_response": False})

# Stream response from Redis while the agent is processing
async with await get_stream_handler() as stream_handler:
    async for chunk in stream_handler.read_stream(thread_id):
        if chunk.text:
            print(chunk.text, end="", flush=True)
        elif chunk.is_done:
            break
```

**Fire-and-Forget Mode**: Use `options={"wait_for_response": False}` to enable non-blocking execution. The `run()` method signals the agent and returns immediately, allowing the client to stream from Redis without blocking.

### Cursor-Based Resumption

Clients can resume streaming from any point after disconnection:

```python
cursor = "1734649123456-0"  # Entry ID from previous stream
async with await get_stream_handler() as stream_handler:
    async for chunk in stream_handler.read_stream(thread_id, cursor=cursor):
        # Process chunk
```

## Viewing Agent State

You can view the state of the TravelPlanner agent in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can view:
   - The state of the TravelPlanner agent entity (dafx-TravelPlanner)
   - Conversation history and current state
   - How the durable agents extension manages conversation context with streaming

