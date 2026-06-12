# agent-framework-hosting-mcp

Model Context Protocol (MCP) tool channel for `agent-framework-hosting`.

Exposes the hosted target (an `Agent` or a `Workflow`) as a single MCP tool over
the Streamable-HTTP transport, so MCP clients — other agents, IDE tooling — can
invoke it. Every call is routed through the host pipeline, so host sessions,
request metadata, and run/response hooks all apply.

```python
from agent_framework.openai import OpenAIChatClient
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_mcp import MCPChannel

agent = OpenAIChatClient().as_agent(name="Assistant")

host = AgentFrameworkHost(target=agent, channels=[MCPChannel()])
host.serve(port=8000)
```

The Streamable-HTTP endpoint is mounted at `path` (default `/mcp`). The advertised
tool accepts `{"input": str, "session_id": str?}` and returns the target's reply
as MCP content blocks, including structured output when the agent returns one.
Pass `session_id` to continue a prior conversation (it maps onto the host
session). When `streaming=True` (default) incremental text is forwarded as MCP
progress notifications while the full reply is returned as the tool result.

The base host plumbing lives in
[`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/).
