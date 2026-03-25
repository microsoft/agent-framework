# Using SharePoint Grounding with AI Agents

This sample demonstrates how to use the SharePoint grounding tool with AI agents. The SharePoint grounding tool enables agents to search and retrieve information from SharePoint sites.

## What this sample demonstrates

- Creating agents with SharePoint grounding capabilities
- Using AgentTool.CreateSharepointTool (MEAI abstraction)
- Using native SDK SharePoint tools (PromptAgentDefinition)
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure authentication configured for `DefaultAzureCredential` (for example, Azure CLI logged in with `az login`, environment variables, managed identity, or IDE sign-in)
- A SharePoint project connection configured in Azure Foundry

**Note**: This demo uses `DefaultAzureCredential` for authentication. This credential will try multiple authentication mechanisms in order (such as environment variables, managed identity, Azure CLI login, and IDE sign-in) and use the first one that works. A common option for local development is to sign in with the Azure CLI using `az login` and ensure you have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively) and the [DefaultAzureCredential documentation](https://learn.microsoft.com/dotnet/api/azure.identity.defaultazurecredential).

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:SHAREPOINT_PROJECT_CONNECTION_ID="your-sharepoint-connection-id"  # Required: SharePoint project connection ID
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step19_SharePoint
```

## Expected behavior

The sample will:

1. Create two agents with SharePoint grounding capabilities:
   - Option 1: Using AgentTool.CreateSharepointTool (MEAI abstraction)
   - Option 2: Using native SDK SharePoint tools
2. Run the agent with a query: "List the documents available in SharePoint"
3. The agent will use SharePoint grounding to search and retrieve relevant documents
4. Display the response and any grounding annotations
5. Clean up resources by deleting both agents
