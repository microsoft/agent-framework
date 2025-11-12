# Callback Telemetry Sample

This sample demonstrates how to use the Durable Extension for Agent Framework's response callbacks to observe
streaming updates and final agent responses in real time. The `ConversationAuditTrail` callback
records each chunk received from the Azure OpenAI agent and exposes the collected events through
an HTTP API that can be polled by a web client or dashboard.

## Highlights

- Registers a default `AgentResponseCallbackProtocol` implementation that logs streaming and final
  responses.
- Persists callback events in an in-memory store and exposes them via
  `GET /api/agents/{agentName}/callbacks/{thread_id}`.
- Shows how to reset stored callback events with `DELETE /api/agents/{agentName}/callbacks/{thread_id}`.
- Works alongside the standard `/api/agents/{agentName}/run` endpoint so you can correlate callback
  telemetry with agent responses.

## Prerequisites

- Python 3.10+
- [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools)
- [Azurite storage emulator](https://learn.microsoft.com/azure/storage/common/storage-use-azurite?tabs=visual-studio) running locally so the sample can use `AzureWebJobsStorage=UseDevelopmentStorage=true`
- Access to an Azure OpenAI deployment with `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY` configured (either in `local.settings.json` or exported in your shell)
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

3. Copy `local.settings.json.template` to `local.settings.json` and update `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY` (or export them as environment variables) for your Azure resources, making sure `TASKHUB_NAME` remains `default` unless you have changed the durable task hub name.

4. Start the Functions host:

   ```powershell
   func start
   ```

5. Use the [`demo.http`](./demo.http) file (VS Code REST Client) or any HTTP client to:
  - Send a message to the agent (optionally providing `thread_id`): `POST /api/agents/CallbackAgent/run`
  - Query callback telemetry for that thread: `GET /api/agents/CallbackAgent/callbacks/{thread_id}`
  - Clear stored events: `DELETE /api/agents/CallbackAgent/callbacks/{thread_id}`

  > **Note:** The run endpoint waits for the agent response by default. To return immediately, set the `x-ms-wait-for-response` header or include `"wait_for_response": false` in the request body.

Example workflow after the host starts:

```text
POST /api/agents/CallbackAgent/run        # send a thread message
GET  /api/agents/CallbackAgent/callbacks/test-thread   # inspect streaming + final events
DELETE /api/agents/CallbackAgent/callbacks/test-thread # reset telemetry for the thread
```

The GET endpoint returns an array of events captured by the callback, including timestamps,
streaming chunk previews, and the final response metadata. This makes it easy to build real-time
UI updates or audit logs on top of Durable Agents.

## Expected Output

When you call `GET /api/agents/CallbackAgent/callbacks/{thread_id}` after sending a request to the agent,
the API returns a list of streaming and final callback events similar to the following:

```json
[
  {
    "timestamp": "2024-01-01T00:00:00Z",
    "agent_name": "CallbackAgent",
    "thread_id": "<thread_id>",
    "correlation_id": "<guid>",
    "request_message": "Tell me a short joke",
    "event_type": "stream",
    "update_kind": "text",
    "text": "Sure, here's a joke..."
  },
  {
    "timestamp": "2024-01-01T00:00:01Z",
    "agent_name": "CallbackAgent",
    "thread_id": "<thread_id>",
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
