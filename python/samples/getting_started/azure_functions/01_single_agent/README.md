# Single Agent Sample (Python)

This sample demonstrates how to use the Durable Extension for Agent Framework to create a simple Azure Functions app that hosts a single AI agent and provides direct HTTP API access for interactive conversations.

## Key Concepts Demonstrated

- Defining a simple agent with the Microsoft Agent Framework and wiring it into
  an Azure Functions app via the Durable Extension for Agent Framework.
- Calling the agent through generated HTTP endpoints (`/api/agents/Joker/run`).
- Managing conversation state with session identifiers, so multiple clients can
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

Expected HTTP 202 payload:

```json
{
  "status": "accepted",
  "response": "Agent request accepted",
  "message": "Tell me a short joke about cloud computing.",
  "conversation_id": "<guid>",
  "correlation_id": "<guid>"
}
```
