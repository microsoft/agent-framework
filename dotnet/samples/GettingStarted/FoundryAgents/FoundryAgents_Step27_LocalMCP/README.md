# Using Hosted MCP Tools with Azure Foundry Agents

This sample demonstrates how to use a Hosted MCP (Model Context Protocol) server tool with Azure Foundry Agents. The MCP server runs remotely and is invoked by the Azure Foundry service when needed.

## What this sample demonstrates

- Creating an agent with a Hosted MCP tool
- Using the Microsoft Learn MCP endpoint for documentation search
- Configuring MCP tool approval modes
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
dotnet run --project .\FoundryAgents_Step27_LocalMCP
```

## Expected behavior

The sample will:

1. Create an agent with the Microsoft Learn MCP tool configured
2. Ask a question about creating an Azure storage account using az cli
3. The agent will use the MCP tool to search Microsoft Learn documentation
4. Display the agent's response with information from the documentation
5. Clean up resources by deleting the agent
