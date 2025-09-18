# Creating an AIAgent instance for various providers

These samples show how to create an AIAgent instance using various providers.
This is not an exhaustive list, but shows a variety of the more popular options.

For other samples that demonstrate how to use AIAgent instances,
see the [Getting Started Steps](../GettingStartedSteps/README.md) samples.

## Prerequisites

See the README.md for each sample for the prerequisites for that sample.

## Samples

|Sample|Description|
|---|---|
|[Creating an AIAgent with A2A](./Agent_With_A2A/)|This sample demonstrates how to create AIAgent for an existing A2A agent.|
|[Creating an AIAgent with AzureFoundry](./Agent_With_AzureFoundry/)|This sample demonstrates how to create an Azure Foundry agent and expose it as an AIAgent|
|[Creating an AIAgent with Azure OpenAI ChatCompletion](./Agent_With_AzureOpenAIChatCompletion/)|This sample demonstrates how to create an AIAgent using Azure OpenAI ChatCompletion as the underlying inference service|
|[Creating an AIAgent with Azure OpenAI Responses](./Agent_With_AzureOpenAIResponses/)|This sample demonstrates how to create an AIAgent using Azure OpenAI Responses as the underlying inference service|
|[Creating an AIAgent with a custom implementation](./Agent_With_CustomImplementation/)|This sample demonstrates how to create an AIAgent with a custom implementation|
|[Creating an AIAgent with Ollama](./Agent_With_Ollama/)|This sample demonstrates how to create an AIAgent using Ollama as the underlying inference service|
|[Creating an AIAgent with ONNX](./Agent_With_ONNX/)|This sample demonstrates how to create an AIAgent using ONNX as the underlying inference service|
|[Creating an AIAgent with OpenAI Assistants](./Agent_With_OpenAIAssistants/)|This sample demonstrates how to create an AIAgent using OpenAI Assistants as the underlying inference service.</br>WARNING: The Assistants API is deprecated and will be shut down. For more information see the OpenAI documentation: https://platform.openai.com/docs/assistants/migration|
|[Creating an AIAgent with OpenAI ChatCompletion](./Agent_With_OpenAIChatCompletion/)|This sample demonstrates how to create an AIAgent using OpenAI ChatCompletion as the underlying inference service|
|[Creating an AIAgent with OpenAI Responses](./Agent_With_OpenAIResponses/)|This sample demonstrates how to create an AIAgent using OpenAI Responses as the underlying inference service|

## Running the samples from the console

To run the samples, navigate to the desired sample directory, e.g.

```powershell
cd AIAgent_With_AzureOpenAIChatCompletion
```

Set the required environment variables as documented in the sample readme.
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
