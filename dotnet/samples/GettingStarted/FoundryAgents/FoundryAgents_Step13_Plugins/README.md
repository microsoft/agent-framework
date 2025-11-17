# Using Plugins with AI Agents

This sample demonstrates how to use plugins with AI agents, where plugins are services registered in dependency injection that expose methods as AI function tools.

## What this sample demonstrates

- Creating plugin services with methods to expose as tools
- Using AsAITools() to selectively expose plugin methods
- Registering plugins in dependency injection
- Using plugins with AI agents
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
dotnet run --project .\FoundryAgents_Step13_Plugins
```

## Expected behavior

The sample will:

1. Create a plugin service with methods to expose as tools
2. Register the plugin in dependency injection
3. Create an agent named "PluginAgent" with the plugin methods as function tools
4. Run the agent with a prompt that triggers it to call plugin methods
5. The agent will invoke the plugin methods to retrieve information
6. Clean up resources by deleting the agent

