# Using AI Agents as Function Tools (Nested Agents)

This sample demonstrates how to expose an AI agent as a function tool, enabling nested agent scenarios where one agent can invoke another agent as a tool.

## What this sample demonstrates

- Creating an AI agent that can be used as a function tool
- Wrapping an agent as an AIFunction
- Using nested agents where one agent calls another
- Managing multiple agent instances
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
dotnet run --project .\FoundryAgents_Step11_AsFunctionTool
```

## Expected behavior

The sample will:

1. Create a "JokerAgent" that tells jokes
2. Wrap the JokerAgent as a function tool
3. Create a "CoordinatorAgent" that has the JokerAgent as a function tool
4. Run the CoordinatorAgent with a prompt that triggers it to call the JokerAgent
5. The CoordinatorAgent will invoke the JokerAgent as a function tool
6. Clean up resources by deleting both agents

