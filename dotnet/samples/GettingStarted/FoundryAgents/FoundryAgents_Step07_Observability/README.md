# Observability with OpenTelemetry

This sample demonstrates how to add observability to AI agents using OpenTelemetry for tracing and monitoring.

## What this sample demonstrates

- Setting up OpenTelemetry TracerProvider
- Configuring console exporter for telemetry output
- Configuring Azure Monitor exporter for Application Insights
- Adding OpenTelemetry middleware to agents
- Running agents with telemetry collection (text and streaming)
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- (Optional) Application Insights connection string for Azure Monitor integration

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:APPLICATIONINSIGHTS_CONNECTION_STRING="your-connection-string"  # Optional, for Azure Monitor integration
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step07_Observability
```

## Expected behavior

The sample will:

1. Create a TracerProvider with console exporter (and optionally Azure Monitor exporter)
2. Create an agent named "JokerAgent" with OpenTelemetry middleware
3. Run the agent with a text prompt and display telemetry traces to console
4. Run the agent again with streaming and display telemetry traces
5. Clean up resources by deleting the agent

