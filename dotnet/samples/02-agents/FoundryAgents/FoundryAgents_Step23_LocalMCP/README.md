# Using Local MCP Client with Azure Foundry Agents

This sample demonstrates how to use a local MCP (Model Context Protocol) client with Azure Foundry Agents. Unlike the hosted MCP approach where Azure Foundry invokes the MCP server on the service side, this sample connects to the MCP server directly from the client via HTTP (Streamable HTTP transport) and passes the resolved tools to the agent.

## What this sample demonstrates

- Connecting to an MCP server locally using `HttpClientTransport`
- Discovering available tools from the MCP server client-side
- Passing locally-resolved MCP tools to a Foundry agent
- Using the Microsoft Learn MCP endpoint for documentation search
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step23_LocalMCP
```

## Expected behavior

The sample will:

1. Connect to the Microsoft Learn MCP server via HTTP and list available tools
2. Create an agent with the locally-resolved MCP tools
3. Ask two questions about Microsoft documentation
4. The agent will use the MCP tools (invoked locally) to search Microsoft Learn documentation
5. Display the agent's responses with information from the documentation
6. Clean up resources by deleting the agent
