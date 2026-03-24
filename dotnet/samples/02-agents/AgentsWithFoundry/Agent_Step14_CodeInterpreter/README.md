# Code Interpreter with the Responses API

This sample shows how to use the Code Interpreter tool with a `ChatClientAgent` using the Responses API directly.

## What this sample demonstrates

- Using `HostedCodeInterpreterTool` with `ChatClientAgent`
- Extracting code input and output from agent responses
- Handling code interpreter annotations and file citations

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
