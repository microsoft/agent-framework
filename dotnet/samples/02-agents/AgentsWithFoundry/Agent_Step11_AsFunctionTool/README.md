# Agent as a Function Tool with the Responses API

This sample demonstrates how to use one agent as a function tool for another agent.

## What this sample demonstrates

- Creating a specialized agent (weather) with function tools
- Exposing an agent as a function tool using `.AsAIFunction()`
- Composing agents where one agent delegates to another
- No server-side agent creation or cleanup required

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
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step11_AsFunctionTool
```
