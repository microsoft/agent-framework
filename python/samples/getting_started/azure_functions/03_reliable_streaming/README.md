# Agent Response Callbacks with Redis Streaming

This sample demonstrates how to implement **agent response callbacks** for durable agents using Redis Streams for persistent, reliable message delivery. It shows how to capture streaming agent responses via callbacks and persist them to Redis, enabling clients to disconnect and reconnect without losing messages.

## Key Concepts Demonstrated

- **Durable Agents**: Uses `AgentFunctionApp` for orchestrated background agent execution
- **Persistent Message Delivery**: Agent responses are written to Redis Streams via a callback
- **Redis Streams**: Messages persist with configurable TTL (default 10 minutes) for reliable delivery
- **Cursor-Based Resumption**: Clients can resume from any point using Redis stream entry IDs
- **Fire-and-Forget Invocation**: Agents run asynchronously in the background
- **Agent Response Callbacks**: Demonstrates how to capture and persist streaming agent responses

## Architecture

The sample creates a travel planning agent using the durable agents pattern with Redis streaming:

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agents/TravelPlanner/run` | POST | **Standard:** Starts a durable agent run (returns 202 Accepted) |
| `/api/agent/stream/{conversation_id}` | GET | **Custom:** Streams chunks from Redis with cursor-based resumption |
| `/api/agents/TravelPlanner/run/{conversation_id}` | GET | **Standard:** Check status of agent run |
| `/api/health` | GET | Health check endpoint |

### Flow

1. **Client sends prompt** to `/api/agents/TravelPlanner/run` (standard endpoint)
2. **Function app returns 202 Accepted** with `conversation_id` and `correlation_id`
3. **Agent runs in background** via durable orchestration
4. **Redis callback writes chunks** to Redis Stream as agent generates responses
5. **Client calls** `/api/agent/stream/{conversation_id}` (custom endpoint) to read chunks from Redis
6. **Messages persist with TTL** allowing clients to resume from any cursor position using optional `cursor` parameter

### Components

```python
# Redis callback writes streaming updates to Redis
class RedisStreamCallback(AgentResponseCallbackProtocol):
    async def on_streaming_response_update(self, update, context):
        # Write chunk to Redis Stream with sequence number and timestamp

    async def on_agent_response(self, response, context):
        # Write end-of-stream marker when agent completes

# AgentFunctionApp with durable agents and Redis callback
app = AgentFunctionApp(
    agents=[create_travel_agent()],
    default_callback=redis_callback,
)
```

## Prerequisites

Before running this sample, ensure you have:

1. **Azure OpenAI**: Set up an Azure OpenAI resource with a chat deployment
2. **Redis**: Running locally or in Docker for persistent message storage
3. **Durable Task Scheduler (DTS)**: Running locally for orchestration (see parent README)
4. **Azurite**: Local storage emulator for Azure Functions (see parent README)

### Starting Redis

Start Redis using Docker:

```bash
docker run -d --name redis -p 6379:6379 redis:latest
```

To verify Redis is running:

```bash
docker ps | grep redis
```

**Note:** This sample uses Redis Streams to demonstrate persistent callback storage, which is more robust than in-memory storage for production scenarios.

## Configuration

Update your `local.settings.json` with your Azure OpenAI credentials:

```json
{
  "Values": {
    "AZURE_OPENAI_ENDPOINT": "https://your-resource.openai.azure.com/",
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "your-deployment-name",
    "AZURE_OPENAI_API_KEY": "your-api-key-if-not-using-rbac",
    "REDIS_CONNECTION_STRING": "redis://localhost:6379",
    "REDIS_STREAM_TTL_MINUTES": "10",
    "DURABLE_TASK_SCHEDULER_CONNECTION_STRING": "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
```

Configuration options:
- `REDIS_CONNECTION_STRING`: Connection string for Redis (default: `redis://localhost:6379`)
- `REDIS_STREAM_TTL_MINUTES`: Time-to-live for stream entries in minutes (default: `10`)

## Running the Sample

1. **Start required services** (Redis, DTS, Azurite):
   ```bash
   # Redis (if not already running)
   docker run -d --name redis -p 6379:6379 redis:latest

   # DTS and Azurite (see parent README for instructions)
   ```

2. **Install dependencies**:
   ```bash
   cd python/samples/getting_started/azure_functions/03_reliable_streaming
   pip install -r requirements.txt
   ```

3. **Start the Function App**:
   ```bash
   func start
   ```

## Testing the Sample

### Test 1: Basic Workflow (Standard + Custom Endpoints)

**Step 1:** Start the agent run:

```bash
curl -X POST http://localhost:7071/api/agents/TravelPlanner/run \
  -H "Content-Type: text/plain" \
  -d "Plan a 3-day trip to Tokyo"
```

**Response (202 Accepted):**
```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Plan a 3-day trip to Tokyo",
  "conversation_id": "abc-123-def-456",
  "correlation_id": "xyz-789-ghi-012"
}
```

**Step 2:** Stream chunks from Redis using the custom endpoint:

```bash
curl http://localhost:7071/api/agent/stream/abc-123-def-456 \
  -H "Accept: text/event-stream"
```

**Expected Response (SSE format with chunks):**
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

**Step 3 (Optional):** Resume from a specific cursor:

```bash
# Use a cursor from an earlier SSE event
curl "http://localhost:7071/api/agent/stream/abc-123-def-456?cursor=1734649123456-0" \
  -H "Accept: text/event-stream"
```

### Test 2: Plain Text Format (for terminals)

```bash
# Start the run
RESPONSE=$(curl -s -X POST http://localhost:7071/api/agents/TravelPlanner/run \
  -H "Content-Type: text/plain" \
  -d "Plan a weekend in Paris")

CONV_ID=$(echo $RESPONSE | jq -r .conversation_id)

# Stream in plain text format
curl http://localhost:7071/api/agent/stream/$CONV_ID \
  -H "Accept: text/plain"
```

### Test 3: Reading from Redis using redis-cli

```bash
# Connect to Redis
docker exec -it redis redis-cli

# View all messages for the conversation
XRANGE agent-stream:abc-123-def-456 - +

# Example output:
# 1) 1) "1734649123456-0"
#    2) 1) "text"
#       2) "Here's a wonderful 3-day Tokyo itinerary..."
#       3) "sequence"
#       4) "0"
#       5) "timestamp"
#       6) "1734649123456"
# 2) 1) "1734649123789-0"
#    2) 1) "text"
#       2) "Day 1: Arrival and Shibuya..."
#       3) "sequence"
#       4) "1"
```

### Test 4: Check Agent Status

```bash
curl http://localhost:7071/api/agents/TravelPlanner/run/abc-123-def-456
```

Returns the orchestration status (Running, Completed, Failed, etc.).

### Test 5: Using Python to Read from Redis

```python
import asyncio
from datetime import timedelta
import redis.asyncio as aioredis
from redis_stream_response_handler import RedisStreamResponseHandler

async def read_agent_response(conversation_id: str):
    redis_client = aioredis.from_url("redis://localhost:6379")
    handler = RedisStreamResponseHandler(
        redis_client=redis_client,
        stream_ttl=timedelta(minutes=10)
    )

    async for chunk in handler.read_stream(conversation_id):
        if chunk.is_done:
            print("\n[Agent completed]")
            break
        if chunk.text:
            print(chunk.text, end="", flush=True)

# Usage
asyncio.run(read_agent_response("abc-123-def-456"))
```

### Test 6: Using the demo.http File

If you have VS Code with the REST Client extension:

1. Open `demo.http` in VS Code
2. Click "Send Request" above any test
3. The `conversation_id` is automatically captured for subsequent requests
4. Try the standard `/api/agents/TravelPlanner/run` endpoint to start the agent, then use `/api/agent/stream/{conversation_id}` to read the response

## How It Works

### Durable Agents Pattern

This sample uses the **durable agents pattern** from `AgentFunctionApp`:

1. **Client calls `/run`** → Returns 202 Accepted immediately with `conversation_id`
2. **Durable orchestration starts** → Agent executes in background
3. **Callback writes to Redis** → Each streaming chunk is persisted with sequence number and timestamp
4. **Client reads from Redis** → Using RedisStreamResponseHandler or redis-cli
5. **Cursor-based resumption** → Client can resume from any cursor position

### RedisStreamCallback

The `RedisStreamCallback` class implements `AgentResponseCallbackProtocol`:

**Writing to Redis** (`on_streaming_response_update`):
- Receives streaming updates from the agent
- Writes each chunk to a Redis Stream with metadata (sequence number, timestamp)
- Sets a TTL on the stream (default 10 minutes)

**End-of-stream marker** (`on_agent_response`):
- Called when agent completes
- Writes a marker with `done: true` to signal completion

### Reading from Redis

Clients can read agent responses directly from Redis using the `RedisStreamResponseHandler`:

```python
from redis_stream_response_handler import RedisStreamResponseHandler
import redis.asyncio as aioredis

# Connect to Redis
redis_client = aioredis.from_url("redis://localhost:6379")
handler = RedisStreamResponseHandler(redis_client, stream_ttl=timedelta(minutes=10))

# Read all messages for a conversation
async for chunk in handler.read_stream(conversation_id, cursor=None):
    if chunk.is_done:
        print("Agent completed")
        break
    if chunk.text:
        print(chunk.text, end="")
```

The `read_stream` method supports:
- Reading from beginning (cursor=None) or from a specific cursor
- Automatic handling of stream completion markers
- Error handling for missing or expired streams

## Delivery Guarantees

This pattern provides:

- **At-least-once delivery**: Messages are persisted and can be read multiple times
- **Ordering**: Messages are delivered in the order they were written
- **Durability**: Messages persist until TTL expires (default 10 minutes)
- **Background execution**: Agent runs independently of client connection

However, it does NOT guarantee:

- **Exactly-once delivery**: Clients may receive duplicate messages if they resume from an earlier cursor
- **Infinite retention**: Messages expire after the configured TTL

Clients should handle potential duplicates if necessary (e.g., using sequence numbers).

## Advanced Usage

### Custom TTL

Set a custom TTL for stream entries (in minutes):

```json
{
  "REDIS_STREAM_TTL_MINUTES": "30"
}
```

### Remote Redis

Use a remote Redis instance:

```json
{
  "REDIS_CONNECTION_STRING": "rediss://username:password@your-redis.com:6380"
}
```

### Checking Agent Status

Use the standard durable agents status endpoint:

```bash
curl http://localhost:7071/api/agents/TravelPlanner/run/{conversation_id}
```

This returns the orchestration status (Running, Completed, Failed, etc.).

## Debugging

### Redis CLI Commands

Connect to Redis:
```bash
docker exec -it redis redis-cli
```

Check if stream exists:
```bash
XLEN agent-stream:{conversation_id}
```

View stream contents:
```bash
XRANGE agent-stream:{conversation_id} - +
```

View with entry IDs:
```bash
XREAD STREAMS agent-stream:{conversation_id} 0-0
```

Check TTL:
```bash
TTL agent-stream:{conversation_id}
```

### Logs

Watch the function app logs for:
- Agent execution progress
- Redis write operations
- Client connection/disconnection events

```bash
# Logs show:
[durableagent.samples.redis_streaming] Wrote chunk to Redis: seq=0, len=52
[durableagent.samples.redis_streaming] Agent completed, wrote end-of-stream marker
```

## Cleanup

Stop and remove the Redis container:

```bash
docker stop redis
docker rm redis
```

## Code Structure

```
03_reliable_streaming/
├── function_app.py                    # Main app with AgentFunctionApp and Redis callback
├── redis_stream_response_handler.py   # Redis streaming utilities
├── tools.py                           # Mock travel tools (weather, events)
├── requirements.txt                   # Python dependencies
├── host.json                          # Azure Functions configuration
├── local.settings.json                # Local environment variables
├── demo.http                          # REST Client test file
└── README.md                          # This file
```

## Comparison with Standard Durable Agents

| Feature | Standard Durable Agents | This Sample |
|---------|------------------------|-------------|
| Agent execution | Background orchestration | ✅ Same |
| Client response | 202 Accepted only | ✅ Same |
| Response callback | None | ✅ Writes to Redis Streams |
| Message persistence | None (status only) | ✅ Redis Streams with TTL |
| Resumption | Not supported | ✅ Resume from any cursor |
| Client access | Status endpoint only | ✅ Direct Redis access or RedisStreamResponseHandler |

## Learn More

- [Redis Streams Documentation](https://redis.io/docs/latest/develop/data-types/streams/)
- [Server-Sent Events Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [Microsoft Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
- [Durable Task Framework](https://github.com/Azure/durabletask)
