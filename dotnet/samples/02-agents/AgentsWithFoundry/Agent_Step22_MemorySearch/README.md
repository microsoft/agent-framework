# Memory Search with the Responses API

This sample demonstrates how to use the Memory Search tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Configuring `MemorySearchPreviewTool` with a memory store and user scope
- Using memory search for cross-conversation recall
- Inspecting `MemorySearchToolCallResponseItem` results
- User profile persistence across conversations

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)
- A memory store created beforehand via Azure Portal or Python SDK

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
$env:AZURE_AI_MEMORY_STORE_ID="your-memory-store-name"
```

## Run the sample

```powershell
dotnet run
```
