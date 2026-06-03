# agent-framework-hosting-a2a

Agent-to-Agent (A2A) protocol channel for `agent-framework-hosting`.

Exposes the hosted target (an `Agent` or a `Workflow`) as an A2A peer agent: it
publishes an agent card and JSON-RPC routes and drives every request through the
host pipeline, so host sessions, request metadata, and run/response hooks all
apply.

```python
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_a2a import A2AChannel

agent = OpenAIChatClient().as_agent(name="Assistant")

host = AgentFrameworkHost(
    target=agent,
    channels=[A2AChannel(url="https://my-host.example.com/")],
)
host.serve(port=8000)
```

By default the channel mounts at the app root so the well-known agent card is
reachable at `/.well-known/agent-card.json`, with the JSON-RPC endpoint at `/`.
The A2A `context_id` maps onto the host session (caller-supplied session family).
A default agent card is derived from the target's name and description; pass a
fully-specified `agent_card` to override it.

> **Note:** Task state is held in an in-memory A2A task store for this version; it
> is independent of the host's session storage and is not persisted across
> restarts.

The base host plumbing lives in
[`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/).
