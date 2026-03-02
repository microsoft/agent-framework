# Foundry-Specific Features

These samples demonstrate features that are specific to Azure AI Foundry, including
CRUD agent lifecycle management, server-side tools (code interpreter, file search, web search),
and evaluation capabilities.

For general-purpose agent samples (function tools, middleware, plugins, observability, etc.),
see the [Agents](../Agents/README.md) samples, which now use the Foundry `ProjectResponsesClient` by default.

## Agent Versioning and Static Definitions

One of the key architectural options in Foundry is managing agents with **versions** where definitions are established at creation time. This means that the agent's configuration—including instructions, tools, and options—is fixed when the agent version is created.

> [!IMPORTANT]
> Agent versions are static and strictly adhere to their original definition. Any attempt to provide or override tools, instructions, or options during an agent run or request will be ignored by the agent, as the API does not support runtime configuration changes. All agent behavior must be defined at agent creation time.

This design ensures consistency and predictability in agent behavior across all interactions with a specific agent version.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and project configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: These samples use Azure Foundry Agents. For more information, see [Azure AI Foundry documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/).

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Samples

### CRUD Agent Lifecycle

|Sample|Description|
|---|---|
|[Basics](./FoundryAgents_Step01.1_Basics/)|This sample demonstrates how to create and manage AI agents with versioning|

### Server-Side Tools (Responses API)

|Sample|Description|
|---|---|
|[Code interpreter](./FoundryAgents_Step14_CodeInterpreter/)|This sample demonstrates how to use the code interpreter tool|
|[Computer use](./FoundryAgents_Step15_ComputerUse/)|This sample demonstrates how to use computer use capabilities|
|[File search](./FoundryAgents_Step16_FileSearch/)|This sample demonstrates how to use the file search tool|
|[OpenAPI tools](./FoundryAgents_Step17_OpenAPITools/)|This sample demonstrates how to use OpenAPI tools|
|[Bing Custom Search](./FoundryAgents_Step18_BingCustomSearch/)|This sample demonstrates how to use Bing Custom Search tool|
|[SharePoint grounding](./FoundryAgents_Step19_SharePoint/)|This sample demonstrates how to use the SharePoint grounding tool|
|[Microsoft Fabric](./FoundryAgents_Step20_MicrosoftFabric/)|This sample demonstrates how to use Microsoft Fabric tool|
|[Web search](./FoundryAgents_Step21_WebSearch/)|This sample demonstrates how to use the web search tool|
|[Memory search](./FoundryAgents_Step22_MemorySearch/)|This sample demonstrates how to use memory search tool|
|[Local MCP](./FoundryAgents_Step23_LocalMCP/)|This sample demonstrates how to use a local MCP client|

## Evaluation Samples

Evaluation is critical for building trustworthy and high-quality AI applications. The evaluation samples demonstrate how to assess agent safety, quality, and performance using Azure AI Foundry's evaluation capabilities.

|Sample|Description|
|---|---|
|[Red Team Evaluation](./FoundryAgents_Evaluations_Step01_RedTeaming/)|This sample demonstrates how to use Azure AI Foundry's Red Teaming service to assess model safety against adversarial attacks|
|[Self-Reflection with Groundedness](./FoundryAgents_Evaluations_Step02_SelfReflection/)|This sample demonstrates the self-reflection pattern where agents iteratively improve responses based on groundedness evaluation|

For details on safety evaluation, see the [Red Team Evaluation README](./FoundryAgents_Evaluations_Step01_RedTeaming/README.md).

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd FoundryAgents_Step01.2_Running
```

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
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

