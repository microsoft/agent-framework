# Bing Custom Search with the Responses API

This sample shows how to use the Bing Custom Search tool with a `FoundryAgentClient` using the Responses API directly.

## What this sample demonstrates

- Configuring `BingCustomSearchToolParameters` with connection ID and instance name
- Using `AgentTool.CreateBingCustomSearchTool()` with `FoundryAgentClient`
- Processing search results from agent responses

## Prerequisites

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- Bing Custom Search resource configured with a connection ID

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
$env:AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID="your-connection-id"
$env:AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME="your-instance-name"
```

## Run the sample

```powershell
dotnet run
```
