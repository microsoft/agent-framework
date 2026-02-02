# Getting started with agents using Anthropic

The getting started with agents using Anthropic samples demonstrate the fundamental concepts and functionalities
of single agents using Anthropic as the AI provider.

These samples use Anthropic Claude models as the AI provider and use ChatCompletion as the type of service.

For other samples that demonstrate how to create and configure each type of agent that come with the agent framework,
see the [How to create an agent for each provider](../AgentProviders/README.md) samples.

## Getting started with agents using Anthropic prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Anthropic API key configured
- User has access to Anthropic Claude models

**Note**: These samples use Anthropic Claude models. For more information, see [Anthropic documentation](https://docs.anthropic.com/).

## Using Anthropic with Azure Foundry

To use Anthropic with Azure Foundry, you can check the sample [AgentProviders/Agent_With_Anthropic](../AgentProviders/Agent_With_Anthropic/README.md) for more details.

## Samples

|Sample|Description|
|---|---|
|[Running a simple agent](./Agent_Anthropic_Step01_Running/)|This sample demonstrates how to create and run a basic agent with Anthropic Claude|
|[Using reasoning with an agent](./Agent_Anthropic_Step02_Reasoning/)|This sample demonstrates how to use extended thinking/reasoning capabilities with Anthropic Claude agents|
|[Using function tools with an agent](./Agent_Anthropic_Step03_UsingFunctionTools/)|This sample demonstrates how to use function tools with an Anthropic Claude agent|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd Agent_Anthropic_Step01_Running
```

Set the following environment variables:

```powershell
$env:ANTHROPIC_API_KEY="your-anthropic-api-key"  # Replace with your Anthropic API key
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

