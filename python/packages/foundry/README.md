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

Each toolbox is reachable as an MCP server. Connect to the toolbox's MCP endpoint with `MCPStreamableHTTPTool` — the agent then discovers and calls its tools over MCP at runtime:

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

## Hosted tool factories

`FoundryChatClient` exposes static factory methods that return Foundry SDK tool
configurations ready to pass to an `Agent`'s `tools=[...]` argument. These
factories don't require a `FoundryChatClient` instance — you can call them
statically and reuse the same tool configuration across agents.

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

agent = Agent(
    client=FoundryChatClient(...),
    instructions="...",
    tools=[
        FoundryChatClient.get_web_search_tool(),
        FoundryChatClient.get_code_interpreter_tool(),
    ],
)
```

Generally available factories: `get_code_interpreter_tool`,
`get_file_search_tool`, `get_web_search_tool`,
`get_image_generation_tool`, `get_mcp_tool`.

> **Choosing a web grounding tool.** `get_web_search_tool` is the recommended
> default — it requires no separate Bing resource and works with Azure OpenAI
> models out of the box. Reach for `get_bing_grounding_tool` (experimental,
> see below) when you need finer Bing parameters (`count`, `freshness`,
> `market`, `set_lang`), are grounding non-OpenAI Foundry models, or are
> migrating from Grounding with Bing Search on the classic platform — it
> requires a Grounding with Bing Search Azure resource that you manage.
> `get_bing_custom_search_tool` (also experimental) is for grounding
> restricted to a curated list of domains via a Bing Custom Search instance.
> See the
> [web grounding overview](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview)
> for the full comparison.

> **Experimental — `ExperimentalFeature.FOUNDRY_TOOLS`.** The following
> factories wrap GA Foundry tool SDK classes but are new wrappers in
> `agent-framework-foundry` and may change before the wrappers themselves
> reach GA. Calls emit an `ExperimentalWarning` the first time the
> `FOUNDRY_TOOLS` feature is exercised in a process (then deduplicated).

| Factory | Foundry SDK tool |
|---------|-----------------|
| `get_azure_ai_search_tool(index_connection_id, index_name, ...)` | `AzureAISearchTool` |
| `get_bing_grounding_tool(connection_id, ...)` | `BingGroundingTool` |

> **Experimental — `ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS`.** The
> following factories wrap **preview** Foundry tool SDK types — the underlying
> Foundry capability itself is in preview and may change or be removed before
> reaching GA. Calls emit a separate `ExperimentalWarning` the first time the
> `FOUNDRY_PREVIEW_TOOLS` feature is exercised in a process (then
> deduplicated). Use `FOUNDRY_TOOLS` for "wrapper is new" and
> `FOUNDRY_PREVIEW_TOOLS` for "underlying Foundry feature is preview".

| Factory | Foundry SDK tool |
|---------|-----------------|
| `get_sharepoint_tool(connection_id)` | `SharepointPreviewTool` |
| `get_fabric_tool(connection_id)` | `MicrosoftFabricPreviewTool` |
| `get_memory_search_tool(memory_store_name, scope, ...)` | `MemorySearchPreviewTool` |
| `get_computer_use_tool(environment, display_width, display_height)` | `ComputerUsePreviewTool` |
| `get_browser_automation_tool(connection_id)` | `BrowserAutomationPreviewTool` |
| `get_bing_custom_search_tool(connection_id, instance_name, ...)` | `BingCustomSearchPreviewTool` |
| `get_a2a_tool(base_url=..., project_connection_id=..., ...)` | `A2APreviewTool` |
## Publishing an agent as a Foundry prompt agent

> **Experimental — `ExperimentalFeature.TO_PROMPT_AGENT`.** `to_prompt_agent`
> and `deploy_as_prompt_agent` are preview APIs and may change before reaching
> GA. The warning fires the first time the `TO_PROMPT_AGENT` feature is
> exercised in a process and is then deduplicated.

`to_prompt_agent(agent)` converts an `Agent` whose chat client is a
`FoundryChatClient` into a Foundry `PromptAgentDefinition`. The model is read
from `default_options["model"]` first and falls back to the bound
`FoundryChatClient.model` (matching `Agent.__init__`'s resolution order), so
the same agent definition you run locally can be published as a hosted prompt
agent without restating the model deployment name.

For the common case of "convert and publish in one step", use
`deploy_as_prompt_agent(agent, agent_name=...)`. It reuses the bound
`FoundryChatClient`'s project client to call
`project_client.agents.create_version(...)`, so the caller does not need to
construct a separate `AIProjectClient`:

```python
import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, deploy_as_prompt_agent
from azure.identity.aio import AzureCliCredential


async def main() -> None:
    credential = AzureCliCredential()
    project_endpoint = "https://<your-project>.services.ai.azure.com"

    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=project_endpoint,
            model="gpt-4o",
            credential=credential,
        ),
        name="TravelAgent",
        instructions="You are a helpful travel assistant.",
        tools=[
            FoundryChatClient.get_web_search_tool(),
            FoundryChatClient.get_code_interpreter_tool(),
        ],
    )

    created = await deploy_as_prompt_agent(agent, agent_name="travel-agent")
    print(f"Published {created.name} v{created.version}")


asyncio.run(main())
```

Reach for `to_prompt_agent(agent)` directly when you need a standalone
`PromptAgentDefinition` (e.g. to inspect, serialize, or pass to a separately
managed `AIProjectClient`).

Behaviour:

- `agent.client` must be a `FoundryChatClient` (or subclass) — otherwise the
  converter raises `TypeError`.
- The bound client must have a `model` set — otherwise the converter raises
  `ValueError`.
- Foundry SDK tool instances returned by `FoundryChatClient.get_*_tool()` are
  passed through unchanged.
- AF `FunctionTool` instances (and `@tool`-decorated callables) are emitted as
  Foundry `FunctionTool` **declarations** — the prompt agent receives the
  schema only, not the Python implementation. To execute the function when
  invoking the deployed prompt agent, connect with `FoundryAgent` and pass the
  same callable via `tools=`:

  ```python
  from agent_framework.foundry import FoundryAgent

  deployed = FoundryAgent(
      project_endpoint=project_endpoint,
      agent_name="travel-agent",
      credential=credential,
      tools=[book_hotel],  # same @tool-decorated callable used at publish time
  )
  result = await deployed.run("Book me a hotel in Seattle for 3 nights.")
  ```

  `FoundryAgent` runs the function locally when the prompt agent calls it, so
  the declaration on the server and the implementation on the client stay in
  sync via the shared `@tool` definition.
- Local Agent Framework MCP tools cannot be published as prompt-agent tools —
  the converter raises `ValueError` and points at
  `FoundryChatClient.get_mcp_tool(...)` for hosted MCP servers.

See the runnable examples under `samples/02-agents/providers/foundry/`:

- [`creating_prompt_agents.py`](../../samples/02-agents/providers/foundry/creating_prompt_agents.py)
  \u2014 build an Agent, run it locally, and publish it via both
  `deploy_as_prompt_agent` and `to_prompt_agent` + `AIProjectClient`.
- [`using_prompt_agents.py`](../../samples/02-agents/providers/foundry/using_prompt_agents.py)
  \u2014 publish with `deploy_as_prompt_agent`, then connect back with
  `FoundryAgent` and execute the same local `@tool` callable that the
  deployed prompt agent invokes by name.
