# Getting started with agents

The getting started with agents samples demonstrate the fundamental concepts and functionalities
of single agents and can be used with any agent type.

While the functionality can be used with any agent type, these samples use Azure OpenAI as the AI provider
and use ChatCompletion as the type of service.

For other samples that demonstrate how to create and configure each type of agent that come with the agent framework,
see the [How to create an agent for each provider](../AgentProviders/README.md) samples.

## Getting started with agents prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource.

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource i.e., have the `Cognitive Services OpenAI Contributor` role. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Samples

|Sample|Description|
|---|---|
|[Running a simple agent](./Agent_Step01_Running/)|This sample demonstrates how to create and run a basic agent with instructions|
|[Multi-turn conversation with a simple agent](./Agent_Step02_MultiturnConversation/)|This sample demonstrates how to implement a multi-turn conversation with a simple agent|
|[Using function tools with a simple agent](./Agent_Step03_UsingFunctionTools/)|This sample demonstrates how to use function tools with a simple agent|
|[Using function tools with approvals](./Agent_Step04_UsingFunctionToolsWithApprovals/)|This sample demonstrates how to use function tools where approvals require human in the loop approvals before execution|
|[Structured output with a simple agent](./Agent_Step05_StructuredOutput/)|This sample demonstrates how to use structured output with a simple agent|
|[Persisted conversations with a simple agent](./Agent_Step06_PersistedConversations/)|This sample demonstrates how to persist conversations and reload them later. This is useful for cases where an agent is hosted in a stateless service|
|[3rd party thread storage with a simple agent](./Agent_Step07_3rdPartyThreadStorage/)|This sample demonstrates how to store conversation history in a 3rd party storage solution|
|[Telemetry with a simple agent](./Agent_Step08_Telemetry/)|This sample demonstrates how to add telemetry to a simple agent|
|[Dependency injection with a simple agent](./Agent_Step09_DependencyInjection/)|This sample demonstrates how to add and resolve an agent with a dependency injection container|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd Agents_Step01_Running
```

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
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
