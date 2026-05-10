# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent hosted using the **Invocations protocol** with session management. Unlike the Responses protocol, the Invocations protocol does **not** provide built-in server-side conversation history — this agent maintains an in-memory session store keyed by `agent_session_id`. In production, replace it with durable storage (Redis, Cosmos DB, etc.) so history survives restarts.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. When a request arrives, the handler looks up (or creates) a session by `session_id`, runs the agent with the user message and session context, and returns the reply. The agent supports both streaming (SSE events) and non-streaming (JSON) response modes.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `InvocationsHostServer`, which provisions a REST API endpoint compatible with the Azure AI Invocations protocol.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/invocations -i -H "Content-Type: application/json" -d '{"message": "Hi"}'
```

The server will respond with a JSON object containing the response text. The `-i` flag in the `curl` command includes the HTTP response headers in the output, which includes the session ID that can be used for multi-turn conversations. Here is an example of the response:

```
HTTP/1.1 200
content-length: 34
content-type: application/json
x-agent-invocation-id: ec04d020-a0e7-441e-ae83-db75635a9f83
x-agent-session-id: 9370b9d4-cd13-4436-a57f-03b843ac0e17
x-platform-server: azure-ai-agentserver-core/2.0.0a20260410006 (python/3.12)
date: Fri, 17 Apr 2026 23:46:44 GMT
server: hypercorn-h11

{"response":"Hi! How can I help?"}
```

### Multi-turn conversation

To have a multi-turn conversation with the agent, take the session ID from the response headers of the previous request and include it in URL parameters for the next request. For example:

```bash
curl -X POST http://localhost:8088/invocations?agent_session_id=9370b9d4-cd13-4436-a57f-03b843ac0e17 -i -H "Content-Type: application/json" -d '{"message": "How are you?"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
