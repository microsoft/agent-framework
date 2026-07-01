# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent hosted using the **Responses protocol**.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. The agent supports both streaming (SSE events) and non-streaming (JSON) response modes.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

### Crash recovery for background requests

To enable crash recovery, pass `resilient_background=True` via explicit options:

```python
from azure.ai.agentserver.responses import ResponsesServerOptions

server = ResponsesHostServer(
    agent,
    options=ResponsesServerOptions(resilient_background=True),
)
```

With crash recovery enabled, if the server process crashes while handling a background request, the Foundry platform automatically re-invokes the handler on the next process start without the client needing to retry. Persisted SSE events are replayed to clients that reconnect after the crash.

Crash recovery requires a persistent response store. In a hosted Foundry environment the Foundry storage API is automatically used as the store, which satisfies this requirement. Passing `InMemoryResponseProvider` (e.g. for local testing) will raise an error when combined with `resilient_background=True`.

### Steerable conversations

To enable steerable conversations, pass `steerable_conversations=True`:

```python
server = ResponsesHostServer(agent, steerable_conversations=True)
```

With steering enabled, when a client sends a new turn while the current one is still in-progress, the new turn is queued and the running handler receives a cancellation signal instead of the client receiving HTTP 409 `conversation_locked`. Once the current turn reaches a terminal event, the queued turn runs with `context.is_steered_turn=True`. This provides a better interactive experience for long-running streaming responses.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi"}'
```

The server will respond with a JSON object containing the response text and a response ID. You can use this response ID to continue the conversation in subsequent requests.

### Multi-turn conversation

To have a multi-turn conversation with the agent, include the previous response id in the request body. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "How are you?", "previous_response_id": "REPLACE_WITH_PREVIOUS_RESPONSE_ID"}'
```

### Background requests

To send a background request that benefits from crash recovery, include `"background": true` in the request body:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Summarize the latest news", "background": true}'
```

The server responds immediately with a response ID. You can poll the response status or stream the result separately.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
