# Using Function Tools with Approvals via the Responses API

This sample demonstrates how to use function tools that require human-in-the-loop approval before execution.

## What this sample demonstrates

- Creating function tools that require approval using `ApprovalRequiredAIFunction`
- Handling approval requests from the agent
- Passing approval responses back to the agent
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
dotnet run --project .\Agent_Step04_UsingFunctionToolsWithApprovals
```
