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
|[Multi-turn conversation with a simple agent](./Step02_ChatClientAgent_MultiTurn/)|This sample demonstrates how to implement a multi-turn conversation with a simple agent|

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
