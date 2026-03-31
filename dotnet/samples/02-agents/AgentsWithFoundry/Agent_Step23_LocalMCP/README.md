# Local MCP with the Responses API

This sample demonstrates how to use a local MCP (Model Context Protocol) client with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Connecting to an MCP server via HTTP (Streamable HTTP transport)
- Resolving MCP tools locally and wrapping them with logging
- Using `DelegatingAIFunction` to add custom behavior to MCP tools
- Passing locally-resolved MCP tools to `ChatClientAgent`

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

## Run the sample

```powershell
dotnet run
```
