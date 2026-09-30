# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent
hosted using the **Invocations protocol** with session management. Unlike
Responses, Invocations does **not** provide built-in conversation history.
The host persists its MAF `AgentSession` using the default file-based store
locally and Foundry storage when hosted, under the separate
`invocation_sessions` logical store. This basic agent does not configure a
history provider; add one if the model should remember previous messages.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` to create a Responses client from the
project endpoint and model deployment. When a request arrives, the host
restores (or creates) a MAF session, runs the agent with the user message
and session context, and persists its state. The agent supports streaming
and non-streaming response modes.

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

Or with streaming:

```bash
curl -X POST http://localhost:8088/invocations -i -H "Content-Type: application/json" -d '{"message": "Hi", "stream": true}'
```

The server responds with text. The `-i` flag in the `curl` command includes
HTTP response headers, including the session ID that can be reused on later
requests. Here is an example:

```
HTTP/1.1 200
content-length: 34
content-type: application/json
x-agent-invocation-id: ec04d020-a0e7-441e-ae83-db75635a9f83
x-agent-session-id: 9370b9d4-cd13-4436-a57f-03b843ac0e17
x-platform-server: azure-ai-agentserver-core/2.0.0a20260410006 (python/3.12)
date: Fri, 17 Apr 2026 23:46:44 GMT
server: hypercorn-h11

Hi! How can I help?
```

### Multi-turn conversation

To reuse the same sandbox and MAF session (not model message history in this
basic example), take the session ID from the previous response header and
include it in the URL query for the next request:

```bash
curl -X POST http://localhost:8088/invocations?agent_session_id=9370b9d4-cd13-4436-a57f-03b843ac0e17 -i -H "Content-Type: application/json" -d '{"message": "How are you?"}'
```

On Foundry, the `agent_session_id` **query parameter** routes an invocation to
the corresponding sandbox; an ID in the JSON body does not route it. The host
also requires platform user and call IDs. If the hosted container does not
receive `FOUNDRY_AGENT_SESSION_ID`, supply an explicit routed query ID even on
the first invocation (for example, [create a hosted session first](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions)).
Without either source, the host rejects the request rather than persisting
state under a generated ID. When the environment variable is present, a
different query ID is rejected. Locally, the SDK still provides a single-user
fallback for requests without an ID.
See the [state store guide](../../../../../packages/foundry_hosting/README.md#state-store)
for namespace and upgrade details.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
