# Observability with the Responses API

This sample demonstrates how to add OpenTelemetry observability to an agent using console and Azure Monitor exporters.

## What this sample demonstrates

- Configuring OpenTelemetry tracing with console exporter
- Optional Azure Application Insights integration
- Using `.AsBuilder().UseOpenTelemetry()` to add telemetry to the agent
- No server-side agent creation or cleanup required

## Prerequisites

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
$env:APPLICATIONINSIGHTS_CONNECTION_STRING="..."  # Optional
```

## Run the sample

```powershell
cd dotnet/samples/02-agents/AgentsWithFoundry
dotnet run --project .\Agent_Step07_Observability
```
