# Using Images with the Responses API

This sample demonstrates how to use image multi-modality with an agent.

## What this sample demonstrates

- Loading images using `DataContent.LoadFromAsync`
- Sending images alongside text to the agent
- Streaming the agent's image analysis response
- No server-side agent creation or cleanup required

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and a vision-capable model deployment (e.g., `gpt-4o`)
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
```

## Run the sample

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step10_UsingImages
```
