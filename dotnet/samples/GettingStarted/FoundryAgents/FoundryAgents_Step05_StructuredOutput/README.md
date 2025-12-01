# Structured Output with AI Agents

This sample demonstrates how to configure AI agents to produce structured output in JSON format using JSON schemas.

## What this sample demonstrates

- Configuring agents with JSON schema response formats
- Using generic RunAsync<T> method for structured output
- Deserializing structured responses into typed objects
- Running agents with streaming and structured output
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step05_StructuredOutput
```

## Expected behavior

The sample will:

1. Create an agent named "StructuredOutputAssistant" configured to produce JSON output
2. Run the agent with a prompt to extract person information
3. Deserialize the JSON response into a PersonInfo object
4. Display the structured data (Name, Age, Occupation)
5. Run the agent again with streaming and deserialize the streamed JSON response
6. Clean up resources by deleting the agent

