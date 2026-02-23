# Using Web Search with AI Agents

This sample demonstrates how to use the Responses API web search tool with AI agents. The web search tool allows agents to search the web for current information to answer questions accurately.

## What this sample demonstrates

- Creating agents with web search capabilities
- Using HostedWebSearchTool (MEAI abstraction)
- Using native SDK web search tools (ResponseTool.CreateWebSearchTool)
- Extracting text responses and URL citations from agent responses
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure authentication configured for `DefaultAzureCredential` (for example, Azure CLI logged in with `az login`, environment variables, managed identity, or IDE sign-in)

**Note**: This sample authenticates using `DefaultAzureCredential` from the Azure Identity library, which will try several credential sources (including Azure CLI, environment variables, managed identity, and IDE sign-in). Ensure at least one supported credential source is available. For more information, see the [Azure Identity documentation](https://learn.microsoft.com/dotnet/api/overview/azure/identity-readme).

**Note**: The web search tool uses the built-in web search capability from the OpenAI Responses API.

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step25_WebSearch
```

## Expected behavior

The sample will:

1. Create an agent with web search capabilities using HostedWebSearchTool (MEAI abstraction)
   - Alternative: Using native SDK web search tools (commented out in code)
   - Alternative: Retrieving an existing agent by name (commented out in code)
2. Run the agent with a query: "What's the weather today in Seattle?"
3. The agent will use the web search tool to find current information
4. Display the text response from the agent
5. Display any URL citations from web search results
6. Clean up resources by deleting the agent
