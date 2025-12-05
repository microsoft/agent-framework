# Getting started with Foundry Agents

The getting started with Foundry Agents samples demonstrate the fundamental concepts and functionalities
of Azure Foundry Agents and can be used with Azure Foundry as the AI provider.

These samples showcase how to work with agents managed through Azure Foundry, including agent creation,
versioning, multi-turn conversations, and advanced features like code interpretation and computer use.

## Classic vs New Foundry Agents

> [!NOTE]
> Recently, Azure Foundry introduced a new and improved experience for creating and managing AI agents, which is the target of these samples.

For more information about the previous classic agents and for what's new in Foundry Agents, see the [Foundry Agents migration documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/migrate?view=foundry).

For a sample demonstrating how to use classic Foundry Agents, see the following: [Agent with Azure AI Persistent](../AgentProviders/Agent_With_AzureAIAgentsPersistent/README.md).

## Getting started with Foundry Agents prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and project configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: These samples use Azure Foundry Agents. For more information, see [Azure AI Foundry documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/).

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Samples

|Sample|Description|
|---|---|
|[Basics](./FoundryAgents_Step01.1_Basics/)|This sample demonstrates how to create and manage AI agents with versioning|
|[Running a simple agent](./FoundryAgents_Step01.2_Running/)|This sample demonstrates how to create and run a basic Foundry agent|
|[Multi-turn conversation](./FoundryAgents_Step02_MultiturnConversation/)|This sample demonstrates how to implement a multi-turn conversation with a Foundry agent|
|[Using function tools](./FoundryAgents_Step03_UsingFunctionTools/)|This sample demonstrates how to use function tools with a Foundry agent|
|[Using function tools with approvals](./FoundryAgents_Step04_UsingFunctionToolsWithApprovals/)|This sample demonstrates how to use function tools where approvals require human in the loop approvals before execution|
|[Structured output](./FoundryAgents_Step05_StructuredOutput/)|This sample demonstrates how to use structured output with a Foundry agent|
|[Persisted conversations](./FoundryAgents_Step06_PersistedConversations/)|This sample demonstrates how to persist conversations and reload them later|
|[Observability](./FoundryAgents_Step07_Observability/)|This sample demonstrates how to add telemetry to a Foundry agent|
|[Dependency injection](./FoundryAgents_Step08_DependencyInjection/)|This sample demonstrates how to add and resolve a Foundry agent with a dependency injection container|
|[Using MCP client as tools](./FoundryAgents_Step09_UsingMcpClientAsTools/)|This sample demonstrates how to use MCP clients as tools with a Foundry agent|
|[Using images](./FoundryAgents_Step10_UsingImages/)|This sample demonstrates how to use image multi-modality with a Foundry agent|
|[Exposing as a function tool](./FoundryAgents_Step11_AsFunctionTool/)|This sample demonstrates how to expose a Foundry agent as a function tool|
|[Using middleware](./FoundryAgents_Step12_Middleware/)|This sample demonstrates how to use middleware with a Foundry agent|
|[Using plugins](./FoundryAgents_Step13_Plugins/)|This sample demonstrates how to use plugins with a Foundry agent|
|[Code interpreter](./FoundryAgents_Step14_CodeInterpreter/)|This sample demonstrates how to use the code interpreter tool with a Foundry agent|
|[Computer use](./FoundryAgents_Step15_ComputerUse/)|This sample demonstrates how to use computer use capabilities with a Foundry agent|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd FoundryAgents_Step01.2_Running
```

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

If the variables are not set, you will be prompted for the values when running the samples.

Execute the following command to build the sample:

```powershell
dotnet build
```

Execute the following command to run the sample:

```powershell
dotnet run --no-build
```

Or just build and run in one step:

```powershell
dotnet run
```

## Running the samples from Visual Studio

Open the solution in Visual Studio and set the desired sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.

