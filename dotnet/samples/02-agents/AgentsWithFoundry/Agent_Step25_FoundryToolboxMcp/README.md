# Foundry Toolbox via MCP

This sample shows how to use a Foundry Toolbox by pointing an `McpClient` at the toolbox's MCP endpoint. The agent discovers the toolbox's tools at runtime and invokes them locally over MCP.

## What this sample demonstrates

- Connecting to a Foundry toolbox's MCP endpoint via Streamable HTTP transport
- Injecting a fresh Azure AI bearer token (`https://ai.azure.com/.default`) on every MCP request
- Passing the discovered MCP tools to `AIProjectClient.AsAIAgent(...)`
- Optional helper to create (or replace) a sample toolbox in the project so the sample is runnable end-to-end

## Prerequisites

- A Microsoft Foundry project with a toolbox configured (or let the sample create one for you)
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
```

The sample creates a toolbox named `research_toolbox` in your Foundry project on
startup, then connects to its MCP endpoint at
`{AZURE_AI_PROJECT_ENDPOINT}/toolboxes/research_toolbox/mcp?api-version=v{version}`.

## Run the sample

```powershell
dotnet run
```
