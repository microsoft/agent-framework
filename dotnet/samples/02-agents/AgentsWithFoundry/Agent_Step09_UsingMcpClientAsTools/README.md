# Using MCP Client as Tools with the Responses API

This sample shows how to use MCP (Model Context Protocol) client tools with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Connecting to an MCP server via HTTP client transport
- Retrieving MCP tools and passing them to a `ChatClientAgent`
- Using MCP tools for agent interactions without server-side agent creation

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- Node.js installed (for npx/MCP server)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
```

## Run the sample

```powershell
dotnet run
```
