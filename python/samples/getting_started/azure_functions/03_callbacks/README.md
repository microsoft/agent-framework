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

- Python 3.11+
- Azure Functions Core Tools v4
- Access to an Azure OpenAI deployment (configure the environment variables listed in
  `local.settings.json` or export them in your shell)
- Dependencies from `requirements.txt` installed in your environment

> **Note:** The sample stores callback events in memory for simplicity. For production scenarios you
> should persist events to Application Insights, Azure Storage, Cosmos DB, or another durable store.

## Running the Sample

1. Create and activate a virtual environment:

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   **Linux/macOS:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies (from the repository root or this directory):

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `local.settings.json.template` to `local.settings.json` and update the values (or export them as environment variables) with your Azure resources, making sure `TASKHUB_NAME` matches the durable task hub specified in `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` (`default` by default).

4. Start the Functions host:

   ```powershell
   func start
   ```

5. Use the [`demo.http`](./demo.http) file (VS Code REST Client) or any HTTP client to:
   - Send a message to the agent: `POST /api/agents/CallbackAgent/run`
   - Query callback telemetry: `GET /api/agents/CallbackAgent/callbacks/{conversationId}`
   - Clear stored events: `DELETE /api/agents/CallbackAgent/callbacks/{conversationId}`

Example workflow after the host starts:

```text
POST /api/agents/CallbackAgent/run        # send a conversation message
GET  /api/agents/CallbackAgent/callbacks/test-session   # inspect streaming + final events
DELETE /api/agents/CallbackAgent/callbacks/test-session # reset telemetry for the session
```

The GET endpoint returns an array of events captured by the callback, including timestamps,
streaming chunk previews, and the final response metadata. This makes it easy to build real-time
UI updates or audit logs on top of Durable Agents.

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
