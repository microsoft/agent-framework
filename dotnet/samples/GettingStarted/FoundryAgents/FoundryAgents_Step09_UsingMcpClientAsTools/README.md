# Using MCP Client Tools with AI Agents

This sample demonstrates how to use Model Context Protocol (MCP) client tools with AI agents, allowing agents to access tools provided by MCP servers. This sample uses the GitHub MCP server to provide tools for querying GitHub repositories.

## What this sample demonstrates

- Creating MCP clients to connect to MCP servers (GitHub server)
- Retrieving tools from MCP servers
- Using MCP tools with AI agents
- Running agents with MCP-provided function tools
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- Node.js and npm installed (for running the GitHub MCP server)

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
dotnet run --project .\FoundryAgents_Step09_UsingMcpClientAsTools
```

## Expected behavior

The sample will:

1. Start the GitHub MCP server using `@modelcontextprotocol/server-github`
2. Create an MCP client to connect to the GitHub server
3. Retrieve the available tools from the GitHub MCP server
4. Create an agent named "AgentWithMCP" with the GitHub tools
5. Run the agent with a prompt to summarize the last four commits to the microsoft/semantic-kernel repository
6. The agent will use the GitHub MCP tools to query the repository information
7. Clean up resources by deleting the agent