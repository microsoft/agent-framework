# Reliable Streaming with Redis

This sample demonstrates how to implement reliable streaming for durable agents using Redis Streams as a message broker. It enables clients to disconnect and reconnect to ongoing agent responses without losing messages, inspired by [OpenAI's background mode](https://platform.openai.com/docs/guides/background) for the Responses API.

## Key Concepts Demonstrated

- **Reliable message delivery**: Agent responses are persisted to Redis Streams, allowing clients to resume from any point
- **Real-time streaming**: Chunks are printed to stdout as they arrive (like `tail -f`)
- **Cursor-based resumption**: Each chunk includes an entry ID that can be used to resume the stream
- **Fire-and-forget agent invocation**: The agent runs in the background while the client streams from Redis

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

With the environment setup, you can run the sample:

```bash
cd dotnet/samples/04-hosting/DurableAgents/ConsoleApps/07_ReliableStreaming
dotnet run --framework net10.0
```

The app will prompt you for a travel planning request:

```text
=== Reliable Streaming Sample ===
Enter a travel planning request (or 'exit' to quit):

You: Plan a 7-day trip to Tokyo, Japan for next month. Include daily activities, restaurant recommendations, and tips for getting around.
```

The agent's response will stream to your console in real-time as chunks arrive from Redis:

```text
Starting new conversation: @dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890
Press [Enter] to interrupt the stream.

TravelPlanner: # 7-Day Tokyo Adventure

## Day 1: Arrival and Exploration
...
```

### Demonstrating Stream Interruption and Resumption

This is the key feature of reliable streaming. Follow these steps to see it in action:

1. **Start a stream**: Run the app and enter a travel planning request
2. **Note the conversation ID**: The conversation ID is displayed at the start of the stream (e.g., `Starting new conversation: @dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890`)
3. **Interrupt the stream**: While the agent is still generating text, press **`Enter`** to interrupt. The agent continues running in the background - your messages are being saved to Redis.
4. **Resume the stream**: Press **`Enter`** again to reconnect and resume the stream from the last cursor position. The app will automatically resume from where it left off.

```text
Starting new conversation: @dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890
Press [Enter] to interrupt the stream.

TravelPlanner: # 7-Day Tokyo Adventure

## Day 1: Arrival and Exploration
[Streaming content...]

[Press Enter to interrupt]
Stream cancelled. Press [Enter] to reconnect and resume the stream from the last cursor.
Last cursor: 1734567890123-0

[Press Enter to resume]
Resuming conversation: @dafx-travelplanner@a1b2c3d4e5f67890abcdef1234567890 from cursor: 1734567890123-0

[Stream continues from where it left off...]
```

## Viewing Agent State

You can view the state of the agent in the Durable Task Scheduler dashboard:

1. Open your browser and navigate to `http://localhost:8082`
2. In the dashboard, you can see:
   - **Agents**: View the state of the TravelPlanner agent, including conversation history and current state
   - **Orchestrations**: View any orchestrations that may have been triggered by the agent

The conversation ID displayed in the console output (shown as "Starting new conversation: {conversationId}") corresponds to the agent's conversation thread. You can use this to identify the agent in the dashboard and inspect:

- The agent's conversation state
- Tool calls made by the agent (weather and events lookups)
- The streaming response state

Note that while the console app streams responses from Redis, the agent state in DTS shows the underlying durable agent execution, including all tool calls and conversation context.

## Architecture Overview

```text
┌─────────────┐      stdin (prompt)     ┌─────────────────────┐
│   Client    │  ─────────────────────► │  Console App        │
│  (stdin)    │                         │  (Program.cs)       │
└─────────────┘                         └──────────────┬──────┘
       ▲                                               │
       │ stdout (chunks)                    Signal Entity
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

1. **Client sends prompt**: The console app reads the prompt from stdin and generates a new agent thread.

2. **Agent invoked**: The durable agent is signaled to run the travel planner agent. This is fire-and-forget from the console app's perspective.

3. **Responses captured**: As the agent generates responses, the `RedisStreamResponseHandler` (implementing `IAgentResponseHandler`) extracts the text from each `AgentRunResponseUpdate` and publishes it to a Redis Stream keyed by the agent session's conversation ID.

4. **Client polls Redis**: The console app streams events by polling the Redis Stream and printing chunks to stdout as they arrive.

5. **Resumption**: If the client interrupts the stream (e.g., by pressing Enter in the sample), it can resume from the last cursor position by providing the conversation ID and cursor to the call to resume the stream.

## Message Delivery Guarantees

This sample provides **at-least-once delivery** with the following characteristics:

- **Durability**: Messages are persisted to Redis Streams with configurable TTL (default: 10 minutes).
- **Ordering**: Messages are delivered in order within a session.
- **Real-time**: Chunks are printed as soon as they arrive from Redis.

### Important Considerations

- **No exactly-once delivery**: If a client disconnects exactly when receiving a message, it may receive that message again upon resumption. Clients should handle duplicate messages idempotently.
- **TTL expiration**: Streams expire after the configured TTL. Clients cannot resume streams that have expired.
- **Redis guarantees**: Redis streams are backed by Redis persistence mechanisms (RDB/AOF). Ensure your Redis instance is configured for durability as needed.

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `REDIS_CONNECTION_STRING` | Redis connection string | `localhost:6379` |
| `REDIS_STREAM_TTL_MINUTES` | How long streams are retained after last write | `10` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | (required) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI deployment name | (required) |
| `AZURE_OPENAI_API_KEY` | API key (optional, uses Azure CLI auth if not set) | (optional) |

## Cleanup

To stop and remove the Redis Docker containers:

```bash
docker stop redis
docker rm redis
```
