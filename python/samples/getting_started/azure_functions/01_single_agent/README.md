# Single Agent Sample (Python)

This sample demonstrates how to use the Durable Extension for Agent Framework to create a simple Azure Functions app that hosts a single AI agent and provides direct HTTP API access for interactive conversations.

## Key Concepts Demonstrated

- Defining a simple agent with the Microsoft Agent Framework and wiring it into
  an Azure Functions app via the Durable Extension for Agent Framework.
- Calling the agent through generated HTTP endpoints (`/api/agents/Joker/run`).
- Managing conversation state with thread identifiers, so multiple clients can
  interact with the agent concurrently without sharing context.

## Prerequisites

Follow the common setup steps in `../README.md` to install tooling, configure Azure OpenAI credentials, and install the Python dependencies for this sample.

## Running the Sample

Send a prompt to the Joker agent:

```bash
curl -X POST http://localhost:7071/api/agents/Joker/run \
     -H "Content-Type: text/plain" \
     -d "Tell me a short joke about cloud computing."
```

The agent responds with a JSON payload that includes the generated joke.

> **Note:** To return immediately with an HTTP 202 response instead of waiting for the agent output, set the `x-ms-wait-for-response` header or include `"wait_for_response": false` in the request body. The default behavior waits for the response.

## Expected Output

When you send a POST request with plain-text input, the Functions host responds with an HTTP 202 and queues the request for the durable agent entity. A typical response body looks like the following:
Expected HTTP 202 payload:

```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Tell me a short joke about cloud computing.",
  "thread_id": "<guid>",
  "correlation_id": "<guid>"
}
```
