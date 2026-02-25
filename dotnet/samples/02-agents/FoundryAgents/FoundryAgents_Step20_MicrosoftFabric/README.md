# Using Microsoft Fabric Tool with AI Agents

This sample demonstrates how to use the Microsoft Fabric tool with AI Agents, allowing agents to query and interact with data in Microsoft Fabric workspaces.

## What this sample demonstrates

- Creating agents with Microsoft Fabric data access capabilities
- Using FabricDataAgentToolOptions to configure Fabric connections
- Two agent creation approaches: MEAI abstraction (Option 1) and Native SDK (Option 2)
- Managing agent lifecycle (creation and deletion)

## Agent creation options

This sample provides two approaches for creating agents with Microsoft Fabric:

- **Option 1 - MEAI + AgentFramework**: Uses the Agent Framework `ResponseTool` wrapped with `AsAITool()` to call the `CreateAIAgentAsync` overload that accepts `tools:[]`, while still relying on the same underlying Azure AI Projects SDK types as Option 2.
- **Option 2 - Native SDK**: Uses `PromptAgentDefinition` with `AgentVersionCreationOptions` to create the agent directly with the Azure AI Projects SDK types.

Both options produce the same result. Toggle between them by commenting/uncommenting the corresponding `CreateAgentWith*Async` call in `Program.cs`.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- A Microsoft Fabric workspace with a configured project connection in Azure Foundry

**Note**: This demo uses Azure Default credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource.

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
$env:FABRIC_PROJECT_CONNECTION_ID="your-fabric-connection-id"  # The Fabric project connection ID from Azure Foundry
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step20_MicrosoftFabric
```

## Expected behavior

The sample will:

1. Create an agent with Microsoft Fabric tool capabilities
2. Configure the agent with a Fabric project connection
3. Run the agent with a query about available Fabric data
4. Display the agent's response
5. Clean up resources by deleting the agent
