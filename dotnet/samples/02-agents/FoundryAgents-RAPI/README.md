# Getting started with Foundry Agents using the Responses API

These samples demonstrate how to use the `FoundryAgentClient` to work with Azure AI Foundry
using the Responses API directly, without creating server-side agent definitions.

Unlike the standard [Foundry Agents](../FoundryAgents/README.md) samples, which create and manage
server-side agents with versioned definitions, the Responses API (RAPI) approach uses the
`FoundryAgentClient` to send requests directly to the Responses API. This means:

- **No server-side agent creation**: Instructions, tools, and options are provided locally at construction time.
- **No agent versioning**: The agent behavior is defined entirely in code.
- **Simpler lifecycle**: No need to create or delete agents in the Foundry service.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and project configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"  # Replace with your model deployment name
```

The `FoundryAgentClient` auto-discovers these environment variables at construction time, so no endpoint or credential code is needed in the samples.

## Samples

|Sample|Description|
|---|---|
|[Basics](./FoundryAgentsRAPI_Step01_Basics/)|This sample demonstrates how to create and run a basic agent using the Responses API|
|[Multi-turn conversation](./FoundryAgentsRAPI_Step02_MultiturnConversation/)|This sample demonstrates how to implement a multi-turn conversation using the Responses API|
|[Using function tools](./FoundryAgentsRAPI_Step03_UsingFunctionTools/)|This sample demonstrates how to use function tools with the Responses API|
|[Using function tools with approvals](./FoundryAgentsRAPI_Step04_UsingFunctionToolsWithApprovals/)|This sample demonstrates how to use function tools with human-in-the-loop approval|
|[Structured output](./FoundryAgentsRAPI_Step05_StructuredOutput/)|This sample demonstrates how to use structured output with the Responses API|
|[Persisted conversations](./FoundryAgentsRAPI_Step06_PersistedConversations/)|This sample demonstrates how to persist and resume conversations|
|[Observability](./FoundryAgentsRAPI_Step07_Observability/)|This sample demonstrates how to add OpenTelemetry observability|
|[Dependency injection](./FoundryAgentsRAPI_Step08_DependencyInjection/)|This sample demonstrates how to use dependency injection with a hosted service|
|[Using images](./FoundryAgentsRAPI_Step10_UsingImages/)|This sample demonstrates how to use image multi-modality|
|[Agent as function tool](./FoundryAgentsRAPI_Step11_AsFunctionTool/)|This sample demonstrates how to use one agent as a function tool for another|
|[Middleware](./FoundryAgentsRAPI_Step12_Middleware/)|This sample demonstrates multiple middleware layers (PII, guardrails, approvals)|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd FoundryAgentsRAPI_Step01_Basics
```

Ensure the following environment variables are set:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
```

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
