# Computer Use with the Responses API

This sample shows how to use the Computer Use tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Using `FoundryAITool.CreateComputerTool()` with `ChatClientAgent`
- Processing computer call actions (click, type, key press)
- Managing the computer use interaction loop with screenshots
- Handling the Azure Agents API workaround for `previous_response_id` with `computer_call_output`

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="computer-use-preview"
```

## Run the sample

```powershell
dotnet run
```
