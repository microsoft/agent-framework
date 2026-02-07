# Using Bing Custom Search with AI Agents

This sample demonstrates how to use the Bing Custom Search tool with AI agents to perform customized web searches.

## What this sample demonstrates

- Creating agents with Bing Custom Search capabilities
- Configuring custom search instances via connection ID and instance name
- Running search queries through the agent
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- A Bing Custom Search resource configured in Azure

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource.

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID="your-connection-id"
$env:BING_CUSTOM_SEARCH_INSTANCE_NAME="your-instance-name"
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step21_BingCustomSearch
```

## Expected behavior

The sample will:

1. Create an agent with Bing Custom Search tool capabilities
2. Run the agent with a search query about Microsoft AI
3. Display the search results returned by the agent
4. Clean up resources by deleting the agent
