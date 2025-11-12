# Callback Telemetry Sample

This sample demonstrates how to use the Durable Extension for Agent Framework's response callbacks to observe
streaming updates and final agent responses in real time. The `ConversationAuditTrail` callback
records each chunk received from the Azure OpenAI agent and exposes the collected events through
an HTTP API that can be polled by a web client or dashboard.

## Highlights

- Registers a default `AgentResponseCallbackProtocol` implementation that logs streaming and final
  responses.
- Persists callback events in an in-memory store and exposes them via
  `GET /api/agents/{agentName}/callbacks/{conversationId}`.
- Shows how to reset stored callback events with `DELETE /api/agents/{agentName}/callbacks/{conversationId}`.
- Works alongside the standard `/api/agents/{agentName}/run` endpoint so you can correlate callback
  telemetry with agent responses.

## Prerequisites

Complete the shared environment setup steps in `../README.md`, including creating a virtual environment, installing dependencies, and configuring Azure OpenAI credentials and storage settings.

> **Note:** The sample stores callback events in memory for simplicity. For production scenarios you
> should persist events to Application Insights, Azure Storage, Cosmos DB, or another durable store.

## Running the Sample

Send a prompt to the agent:

```bash
curl -X POST http://localhost:7071/api/agents/CallbackAgent/run \
   -H "Content-Type: application/json" \
   -d '{"message": "Tell me a short joke"}'
```

Poll callback telemetry (replace `<conversationId>` with the value from the POST response):

```bash
curl http://localhost:7071/api/agents/CallbackAgent/callbacks/<conversationId>
```

Reset stored events:

```bash
curl -X DELETE http://localhost:7071/api/agents/CallbackAgent/callbacks/<conversationId>
```

## Expected Output

When you call `GET /api/agents/CallbackAgent/callbacks/{conversationId}` after sending a request to the agent,
the API returns a list of streaming and final callback events similar to the following:

```json
[
  {
    "timestamp": "2024-01-01T00:00:00Z",
    "agent_name": "CallbackAgent",
    "conversation_id": "<conversationId>",
    "correlation_id": "<guid>",
    "request_message": "Tell me a short joke",
    "event_type": "stream",
    "update_kind": "text",
    "text": "Sure, here's a joke..."
  },
  {
    "timestamp": "2024-01-01T00:00:01Z",
    "agent_name": "CallbackAgent",
    "conversation_id": "<conversationId>",
    "correlation_id": "<guid>",
    "request_message": "Tell me a short joke",
    "event_type": "final",
    "response_text": "Why did the cloud...",
    "usage": {
      "type": "usage_details",
      "input_token_count": 159,
      "output_token_count": 29,
      "total_token_count": 188
    }
  }
]
```
