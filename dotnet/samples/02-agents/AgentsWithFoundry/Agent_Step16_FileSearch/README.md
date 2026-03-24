# File Search with the Responses API

This sample shows how to use the File Search tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Uploading files and creating vector stores via `AIProjectClient`
- Using `HostedFileSearchTool` with `ChatClientAgent`
- Handling file citation annotations in agent responses
- Cleaning up file resources after use

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
