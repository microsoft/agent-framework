# Creating and Managing AI Agents with Versioning

This sample demonstrates how to create and manage AI agents with Azure Foundry Agents, including:
- Creating agents with different versions
- Retrieving agents by version or latest version
- Running multi-turn conversations with agents
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
dotnet run --project .\FoundryAgents_Step01.1_Basics
```

## What this sample demonstrates

1. **Creating agents with versions**: Shows how to create multiple versions of the same agent with different instructions
2. **Retrieving agents**: Demonstrates retrieving agents by specific version or getting the latest version
3. **Multi-turn conversations**: Shows how to use threads to maintain conversation context across multiple agent runs
4. **Agent cleanup**: Demonstrates proper resource cleanup by deleting agents
