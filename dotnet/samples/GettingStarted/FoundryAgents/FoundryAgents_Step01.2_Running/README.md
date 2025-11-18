# Running a Simple AI Agent with Streaming

This sample demonstrates how to create and run a simple AI agent with Azure Foundry Agents, including both text and streaming responses.

## What this sample demonstrates

- Creating a simple AI agent with instructions
- Running an agent with text output
- Running an agent with streaming output
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
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
dotnet run --project .\FoundryAgents_Step01.2_Running
```

## Expected behavior

The sample will:

1. Create an agent named "JokerAgent" with instructions to tell jokes
2. Run the agent with a text prompt and display the response
3. Run the agent again with streaming to display the response as it's generated
4. Clean up resources by deleting the agent

