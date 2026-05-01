# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that
runs Python in a [Hyperlight](https://github.com/hyperlight-dev/hyperlight)
WebAssembly sandbox via the **CodeAct** pattern, hosted using the **Responses
protocol**. The model is only given a single `execute_code` tool. Local Python
tools (`compute`, `fetch_data`) are registered on `HyperlightCodeActProvider`
and are reachable from inside the sandbox via `call_tool(...)`, never as
direct LLM tools.

## How It Works

### Model integration

The agent uses `FoundryChatClient` to talk to a Foundry-hosted model deployment.
A `HyperlightCodeActProvider` is attached as a context provider, which on every
run injects the `execute_code` tool plus the CodeAct instructions that teach the
model how to author Python that calls `call_tool(...)` for sandbox-only tools.

See [`main.py`](main.py) for the full implementation.

### Agent hosting

The agent is hosted with `ResponsesHostServer` from
`agent-framework-foundry-hosting`, which exposes a REST endpoint compatible with
the OpenAI Responses protocol.

> The Hyperlight Wasm backend is currently published only for `linux/x86_64` and
> `win32/AMD64` with Python `<3.14`. The hosted container runs `python:3.12-slim`
> on linux/x86_64, which is supported.

## Running the Agent Host

Follow the instructions in the
[Running the Agent Host Locally](../../README.md#running-the-agent-host-locally)
section of the README in the parent directory.

## Interacting with the agent

Send a POST request to the server with a JSON body containing an `"input"`
field. The model should respond by calling `execute_code` with Python that uses
`call_tool(...)` to reach the sandbox-only tools:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Fetch all users, find the admins, multiply 7 by 6, and print the users, admins and multiplication result. Use execute_code with call_tool(...)."}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry)
section of the parent README.
