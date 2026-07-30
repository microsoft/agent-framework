# A2A Client Samples

These samples demonstrate how to **consume** remote A2A-compliant agents using the Agent Framework's `A2AAgent` class.

For hosting your own agents as A2A servers, see [`samples/04-hosting/a2a/`](../../04-hosting/a2a/).

## Samples

| Sample | Concept |
|--------|---------|
| [`agent_with_a2a.py`](agent_with_a2a.py) | Basic consumption — non-streaming and streaming |
| [`a2a_agent_as_function_tools.py`](a2a_agent_as_function_tools.py) | Expose A2A skills as function tools for a host agent |
| [`a2a_polling.py`](a2a_polling.py) | Poll a long-running task with continuation tokens |
| [`a2a_stream_reconnection.py`](a2a_stream_reconnection.py) | Resume an interrupted stream via continuation token |
| [`a2a_protocol_selection.py`](a2a_protocol_selection.py) | Configure preferred protocol bindings (JSONRPC, GRPC, HTTP+JSON) |

## Prerequisites

- A running A2A-compliant agent server (see `samples/04-hosting/a2a/` to start one)
- Set `A2A_AGENT_HOST` environment variable to the server URL
- For `a2a_agent_as_function_tools.py`: also set `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`

## Running

```bash
cd python/samples/02-agents/a2a

# Start an A2A server in another terminal first:
#   cd python/samples/04-hosting/a2a && uv run python a2a_server.py

export A2A_AGENT_HOST="http://localhost:5001/"
uv run python agent_with_a2a.py
```

## Key APIs

```python
from agent_framework.a2a import A2AAgent

# Connect to a remote agent
async with A2AAgent(url="http://localhost:5001/", agent_card=card) as agent:
    # Non-streaming
    response = await agent.run("Hello")

    # Streaming
    stream = agent.run("Hello", stream=True)
    async for update in stream:
        print(update.text)

    # Background + polling
    response = await agent.run("Long task", background=True)
    while response.continuation_token:
        response = await agent.poll_task(response.continuation_token)
```
