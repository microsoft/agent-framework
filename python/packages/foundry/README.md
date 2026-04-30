# Agent Framework Foundry

This package contains the Microsoft Foundry integrations for Microsoft Agent Framework, including Foundry chat clients, preconfigured Foundry agents, Foundry embedding clients, and Foundry memory providers.

## Toolboxes

A *toolbox* is a named, versioned bundle of hosted tool configurations — code interpreter, file search, image generation, MCP, web search, and so on — stored inside a Microsoft Foundry project. Toolboxes let you manage tool configuration once and reuse it across agents.

### Authoring a toolbox

Toolboxes can be authored two ways:

- **Foundry portal** — create and version toolboxes through the UI without touching code.
- **Programmatically** — use the [`azure-ai-projects`](https://pypi.org/project/azure-ai-projects/) SDK to create, update, and version toolboxes from Python.

> Toolbox authoring APIs (`ToolboxVersionObject`, `ToolboxObject`, `project_client.beta.toolboxes.*`) require `azure-ai-projects>=2.1.0`. Earlier versions can only consume toolboxes that already exist.

### Using toolboxes with `FoundryAgent`

For hosted `FoundryAgent`, the toolbox must already be attached to the agent in the Microsoft Foundry project. Once attached, the agent invokes its toolbox tools transparently — no client-side wiring required — and you interact with the agent the same way you would with any other tool-equipped Foundry agent.

### Using toolboxes with `FoundryChatClient`

There are two patterns for wiring a toolbox into a `FoundryChatClient`-backed agent.

**1. Fetch, optionally filter, and pass the tools directly**

Load the toolbox from the Microsoft Foundry project, optionally select a subset of its tools, and hand them to an `Agent` alongside any other tools you own:

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, select_toolbox_tools

client = FoundryChatClient(...)
toolbox = await client.get_toolbox("my-toolbox", version="3")

# Pass the whole toolbox:
agent = Agent(client=client, tools=toolbox)

# Or filter to a subset first:
selected = select_toolbox_tools(toolbox, include_types=["code_interpreter", "mcp"])
agent = Agent(client=client, tools=selected)
```

See [`foundry_chat_client_with_toolbox.py`](../../samples/02-agents/providers/foundry/foundry_chat_client_with_toolbox.py) for a full example, including combining multiple toolboxes.

**2. Connect to the toolbox's MCP endpoint with `MCPStreamableHTTPTool`**

Each toolbox is reachable as an MCP server. Instead of fetching and fanning out its individual tool definitions, you can point a MAF `MCPStreamableHTTPTool` at the toolbox's MCP endpoint — the agent then discovers and calls its tools over MCP at runtime:

```python
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient

async with Agent(
    client=FoundryChatClient(...),
    instructions="You are a helpful assistant. Use the toolbox tools when useful.",
    tools=MCPStreamableHTTPTool(
        name="my_toolbox",
        description="Tools served by my Foundry toolbox",
        url="https://<your-toolbox-mcp-endpoint>",
    ),
) as agent:
    result = await agent.run("What tools are available?")
    print(result.text)
```
