# Middleware with the Responses API

This sample demonstrates multiple middleware layers working together: PII filtering, guardrails, function invocation logging, and human-in-the-loop approval.

## What this sample demonstrates

- Agent-level run middleware (PII filtering, guardrail enforcement)
- Function-level middleware (logging, result overrides)
- Human-in-the-loop approval workflows for sensitive function calls
- Using `.AsBuilder().Use()` to compose middleware
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
dotnet run --project .\Agent_Step12_Middleware
```
