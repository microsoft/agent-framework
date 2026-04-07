# Web Search with the Responses API

This sample shows how to use the Web Search tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Using `HostedWebSearchTool` with `ChatClientAgent`
- Processing web search citations and annotations
- Extracting URL citation details (title, URL) from responses

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
```

## Run the sample

```powershell
dotnet run
```
