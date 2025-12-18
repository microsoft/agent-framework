# Reliable Streaming with Redis

This sample demonstrates how to implement reliable streaming for durable agents using Redis Streams as a message broker. It enables clients to disconnect and reconnect to ongoing agent responses without losing messages, inspired by [OpenAI's background mode](https://platform.openai.com/docs/guides/background) for the Responses API.

## Key Concepts Demonstrated

- **Reliable message delivery**: Agent responses are persisted to Redis Streams, allowing clients to resume from any point
- **Content negotiation**: Use `Accept: text/plain` for raw terminal output, or `Accept: text/event-stream` for SSE format
- **Server-Sent Events (SSE)**: Standard streaming format that works with `curl`, browsers, and most HTTP clients
- **Cursor-based resumption**: Each SSE event includes an `id` field that can be used to resume the stream
- **Fire-and-forget agent invocation**: The agent runs in the background while the client streams from Redis via an HTTP trigger function

## Environment Setup

See the [README.md](../README.md) file in the parent directory for more information on how to configure the environment, including how to install and run common sample dependencies.

### Additional Requirements: Redis

This sample requires a Redis instance. Start a local Redis instance using Docker:

```bash
docker run -d --name redis -p 6379:6379 redis:latest
```

To verify Redis is running:

```bash
docker ps | grep redis
```

## Running the Sample

Start the Azure Functions host:

```bash
func start
```

### 1. Test Streaming with curl

Open a new terminal and start a travel planning request. Use the `-i` flag to see response headers (including the conversation ID) and `Accept: text/plain` for raw text output:

**Bash (Linux/macOS/WSL):**

```bash
curl -i -N -X POST http://localhost:7071/api/agent/create \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  -d "Plan a 7-day trip to Tokyo, Japan for next month. Include daily activities, restaurant recommendations, and tips for getting around."
```

**PowerShell:**

```powershell
curl -i -N -X POST http://localhost:7071/api/agent/create `
  -H "Content-Type: text/plain" `
  -H "Accept: text/plain" `
  -d "Plan a 7-day trip to Tokyo, Japan for next month. Include daily activities, restaurant recommendations, and tips for getting around."
```

You'll first see the response headers, including:

```text
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
x-conversation-id: @dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890
...
```

Then the agent's response will stream to your terminal in chunks, similar to a ChatGPT-style experience (though not character-by-character).

> **Note:** The `-N` flag in curl disables output buffering, which is essential for seeing the stream in real-time. The `-i` flag includes the HTTP headers in the output.

### 2. Demonstrate Stream Interruption and Resumption

This is the key feature of reliable streaming! Follow these steps to see it in action:

#### Step 1: Start a stream and note the conversation ID

Run the curl command from step 1. Watch for the `x-conversation-id` header in the response - **copy this value**, you'll need it to resume.

```text
x-conversation-id: @dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890
```

#### Step 2: Interrupt the stream

While the agent is still generating text, press **`Ctrl+C`** to interrupt the stream. The agent continues running in the background - your messages are being saved to Redis!

#### Step 3: Resume the stream

Use the conversation ID you copied to resume streaming from where you left off. Include the `Accept: text/plain` header to get raw text output:

**Bash (Linux/macOS/WSL):**

```bash
# Replace with your actual conversation ID from the x-conversation-id header
CONVERSATION_ID="@dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890"

curl -N -H "Accept: text/plain" "http://localhost:7071/api/agent/stream/${CONVERSATION_ID}"
```

**PowerShell:**

```powershell
# Replace with your actual conversation ID from the x-conversation-id header
$conversationId = "@dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890"

curl -N -H "Accept: text/plain" "http://localhost:7071/api/agent/stream/$conversationId"
```

You'll see the **entire response replayed from the beginning**, including the parts you already received before interrupting.

#### Step 4 (Advanced): Resume from a specific cursor

If you're using SSE format, each event includes an `id` field that you can use as a cursor to resume from a specific point:

```bash
# Resume from a specific cursor position
curl -N "http://localhost:7071/api/agent/stream/${CONVERSATION_ID}?cursor=1734567890123-0"
```

### 3. Alternative: SSE Format for Programmatic Clients

If you need the full Server-Sent Events format with cursors for resumable streaming, use `Accept: text/event-stream` (or omit the Accept header):

```bash
curl -i -N -X POST http://localhost:7071/api/agent/create \
  -H "Content-Type: text/plain" \
  -H "Accept: text/event-stream" \
  -d "Plan a 7-day trip to Tokyo, Japan."
```

This returns SSE-formatted events with `id`, `event`, and `data` fields:

```text
id: 1734567890123-0
event: message
data: # 7-Day Tokyo Adventure

id: 1734567890124-0
event: message
data: ## Day 1: Arrival and Exploration

id: 1734567890999-0
event: done
data: [DONE]
```

The `id` field is the Redis stream entry ID - use it as the `cursor` parameter to resume from that exact point.

### Understanding the Response Headers

| Header | Description |
|--------|-------------|
| `x-conversation-id` | The conversation ID (session key). Use this to resume the stream. |
| `Content-Type` | Either `text/plain` or `text/event-stream` depending on your `Accept` header. |
| `Cache-Control` | Set to `no-cache` to prevent caching of the stream. |

## Architecture Overview

```text
┌─────────────┐      POST /agent/create     ┌─────────────────────┐
│   Client    │  (Accept: text/plain or SSE)│  Azure Functions    │
│   (curl)    │ ──────────────────────────► │  (FunctionTriggers) │
└─────────────┘                             └──────────┬──────────┘
       ▲                                               │
       │ Text or SSE stream                  Signal Entity
       │                                               │
       │                                               ▼
       │                                    ┌─────────────────────┐
       │                                    │   AgentEntity       │
       │                                    │   (Durable Entity)  │
       │                                    └──────────┬──────────┘
       │                                               │
       │                                    IAgentResponseHandler
       │                                               │
       │                                               ▼
       │                                    ┌─────────────────────┐
       │                                    │ RedisStreamResponse │
       │                                    │      Handler        │
       │                                    └──────────┬──────────┘
       │                                               │
       │                                     XADD (write)
       │                                               │
       │                                               ▼
       │                                    ┌─────────────────────┐
       └─────────── XREAD (poll) ────────── │   Redis Streams     │
                                            │  (Durable Log)      │
                                            └─────────────────────┘
```

### Data Flow

1. **Client sends prompt**: The `Create` endpoint receives the prompt and generates a new agent thread.

2. **Agent invoked**: The durable entity (`AgentEntity`) is signaled to run the travel planner agent. This is fire-and-forget from the HTTP request's perspective.

3. **Responses captured**: As the agent generates responses, `RedisStreamResponseHandler` (implementing `IAgentResponseHandler`) extracts the text from each `AgentRunResponseUpdate` and publishes it to a Redis Stream keyed by session ID.

4. **Client polls Redis**: The HTTP response streams events by polling the Redis Stream. For SSE format, each event includes the Redis entry ID as the `id` field.

5. **Resumption**: If the client disconnects, it can call the `Stream` endpoint with the conversation ID (from the `x-conversation-id` header) and optionally the last received cursor to resume from that point.

## Message Delivery Guarantees

This sample provides **at-least-once delivery** with the following characteristics:

- **Durability**: Messages are persisted to Redis Streams with configurable TTL (default: 10 minutes).
- **Ordering**: Messages are delivered in order within a session.
- **Resumption**: Clients can resume from any point using cursor-based pagination.
- **Replay**: Clients can replay the entire stream by omitting the cursor.

### Important Considerations

- **No exactly-once delivery**: If a client disconnects exactly when receiving a message, it may receive that message again upon resumption. Clients should handle duplicate messages idempotently.
- **TTL expiration**: Streams expire after the configured TTL. Clients cannot resume streams that have expired.
- **Redis guarantees**: Redis streams are backed by Redis persistence mechanisms (RDB/AOF). Ensure your Redis instance is configured for durability as needed.

## When to Use These Patterns

The patterns demonstrated in this sample are ideal for:

- **Long-running agent tasks**: When agent responses take minutes to complete (e.g., deep research, complex planning)
- **Unreliable network connections**: Mobile apps, unstable WiFi, or connections that may drop
- **Resumable experiences**: Users should be able to close and reopen an app without losing context
- **Background processing**: When you want to fire off a task and check on it later

These patterns may be overkill for:

- **Simple, fast responses**: If responses complete in a few seconds, standard streaming is simpler
- **Stateless interactions**: If there's no need to resume or replay conversations
- **Very high throughput**: Redis adds latency; for maximum throughput, direct streaming may be better

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `REDIS_CONNECTION_STRING` | Redis connection string | `localhost:6379` |
| `REDIS_STREAM_TTL_MINUTES` | How long streams are retained after last write | `10` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | (required) |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI deployment name | (required) |
| `AZURE_OPENAI_KEY` | API key (optional, uses Azure CLI auth if not set) | (optional) |

## Cleanup

To stop and remove the Redis Docker containers:

```bash
docker stop redis
docker rm redis
```

## Disclaimer

> ⚠️ **This sample is for illustration purposes only and is not intended to be production-ready.**
>
> A production implementation should consider:
>
> - Redis cluster configuration for high availability
> - Authentication and authorization for the streaming endpoints
> - Rate limiting and abuse prevention
> - Monitoring and alerting for stream health
> - Graceful handling of Redis failures
