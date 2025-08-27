# Getting started steps

The getting started steps samples demonstrate the fundamental concepts and functionalities
of the agent framework and can be used with any agent type.

While the functionality can be used with any agent type, these samples use Azure OpenAI as the AI provider
and use ChatCompletion as the type of service.

For other samples that demonstrate how to create and configure each type of agent that come with the agent framework,
see the [Agent setup](../AgentSetup/README.md) samples.

## Getting started steps prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Samples

|Sample|Description|
|---|---|
|[Running a simple agent](./Step01_ChatClientAgent_Running/)|This sample demonstrates how to create and run a basic agent with instructions|
|[Multi-turn conversation with a simple agent](./Step02_ChatClientAgent_MultiturnConversation/)|This sample demonstrates how to implement a multi-turn conversation with a simple agent|
|[Using function tools with a simple agent](./Step03_ChatClientAgent_UsingFunctionTools/)|This sample demonstrates how to use function tools with a simple agent|
|[Using function tools with approvals](./Step04_ChatClientAgent_UsingFunctionToolsWithApprovals/)|This sample demonstrates how to use function tools where approvals require human in the loop approvals before execution|
|[Structured output with a simple agent](./Step05_ChatClientAgent_StructuredOutput/)|This sample demonstrates how to use structured output with a simple agent|
|[Persisted conversations with a simple agent](./Step06_ChatClientAgent_PersistedConversations/)|This sample demonstrates how to persist conversations and reload them later. This is useful for cases where an agent is hosted in a stateless service|
|[3rd party thread storage with a simple agent](./Step07_ChatClientAgent_3rdPartyThreadStorage/)|This sample demonstrates how to store conversation history in a 3rd party storage solution|
|[Telemetry with a simple agent](./Step08_ChatClientAgent_Telemetry/)|This sample demonstrates how to add telemetry to a simple agent|
|[Dependency injection with a simple agent](./Step09_ChatClientAgent_DependencyInjection/)|This sample demonstrates how to add and resolve an agent with a dependency injection container|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd Step01_ChatClientAgent_Running
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
