# Foundry Toolbox via MCP

This sample shows how to use a Foundry Toolbox by pointing an `McpClient` at the toolbox's MCP endpoint. The agent discovers the toolbox's tools at runtime and invokes them locally over MCP.

## What this sample demonstrates

- Connecting to a Foundry toolbox's MCP endpoint via Streamable HTTP transport
- Injecting a fresh Azure AI bearer token (`https://ai.azure.com/.default`) on every MCP request
- Passing the discovered MCP tools to `AIProjectClient.AsAIAgent(...)`
- Creating a toolbox version with tool search enabled and connecting to that version

## Prerequisites

- A Microsoft Foundry project with a toolbox configured (or let the sample create one for you)
- An authenticated Azure identity (for example, sign in with `az login`)

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

The sample creates a version of `research_toolbox` on startup, then connects to
`{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/research_toolbox/versions/{version}/mcp?api-version=v1`.
Existing versions are not deleted. Review and remove sample versions in your
Foundry project when you no longer need them.

## Tool search

`ToolSearchToolboxTool` enables the toolbox's `tool_search` and `call_tool`
meta-tools. The agent searches for relevant capabilities before invoking a
discovered tool, rather than receiving all underlying tool definitions initially.
The sample prints the initial MCP tool names; expect those two meta-tools.
Remove `new ToolSearchToolboxTool()` from the creation helper to compare ordinary
toolbox discovery.

This demonstrates [Foundry toolbox tool search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-search),
not the separate request-scoped deferred-tool feature of the OpenAI Responses API.
The existing MCP integration handles discovery and invocation without adding an
Agent Framework tool-search API.

## Run the sample

```powershell
dotnet run
```
