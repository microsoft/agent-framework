# Using Bing Custom Search with AI Agents

This sample demonstrates how to use the Bing Custom Search tool with AI agents to perform customized web searches.

## What this sample demonstrates

- Creating agents with Bing Custom Search capabilities
- Configuring custom search instances via connection ID and instance name
- Two agent creation approaches: MEAI abstraction (Option 1) and Native SDK (Option 2)
- Running search queries through the agent
- Managing agent lifecycle (creation and deletion)

## Agent creation options

This sample provides two approaches for creating agents with Bing Custom Search:

- **Option 1 - MEAI + AgentFramework**: Uses the Agent Framework `ResponseTool` wrapped with `AsAITool()` to call the `CreateAIAgentAsync` overload that accepts `tools:[]`, while still relying on the same underlying Azure AI Projects SDK types as Option 2.
- **Option 2 - Native SDK**: Uses `PromptAgentDefinition` with `AgentVersionCreationOptions` to create the agent directly with the Azure AI Projects SDK types.

Both options produce the same result. Toggle between them by commenting/uncommenting the corresponding `CreateAgentWith*Async` call in `Program.cs`.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- A Bing Custom Search resource configured in Azure and connected to your Foundry project

**Note**: This demo uses Azure Default credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource.

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<connection-name>"
$env:BING_CUSTOM_SEARCH_INSTANCE_NAME="your-configuration-name"
```

### Finding the connection ID and instance name

- **Connection ID**: The full ARM resource path including the `/projects/<name>/connections/<connection-name>` segment. Find the connection name in your Foundry project under **Management center** → **Connected resources**.
- **Instance Name**: The **configuration name** from the Bing Custom Search resource (Azure portal → your Bing Custom Search resource → **Configurations**). This is _not_ the Azure resource name.

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step18_BingCustomSearch
```

## Expected behavior

The sample will:

1. Create an agent with Bing Custom Search tool capabilities
2. Run the agent with a search query about Microsoft AI
3. Display the search results returned by the agent
4. Clean up resources by deleting the agent
